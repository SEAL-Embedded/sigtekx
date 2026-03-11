/**
 * @file streaming_executor.cpp
 * @version 0.9.5
 * @date 2025-11-07
 * @author [Kevin Rahsaz]
 *
 * @brief Implementation of StreamingExecutor with ring buffer support.
 *
 * Implements continuous streaming with ring buffer for input accumulation,
 * frame-by-frame processing with overlap, and CUDA stream pipelining for
 * low-latency operation. Supports optional async producer-consumer pattern
 * with background thread for improved throughput.
 */

#include "sigtekx/executors/streaming_executor.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <queue>
#include <stdexcept>
#include <thread>
#include <unordered_map>

#include "sigtekx/core/cuda_wrappers.hpp"
#include "sigtekx/core/processing_stage.hpp"
#include "sigtekx/core/ring_buffer.hpp"
#include "sigtekx/profiling/nvtx.hpp"

// --- External Kernel Launch Function Declarations (from fft_wrapper.cu) ---
namespace sigtekx {
namespace kernels {

extern void launch_apply_window(const float* input, float* output,
                                const float* window, int nfft, int channels,
                                int stride, cudaStream_t stream);

extern void launch_magnitude(const float2* input, float* output, int num_bins,
                             int channels, int input_stride, float scale,
                             cudaStream_t stream);

}  // namespace kernels
}  // namespace sigtekx

namespace sigtekx {

// ============================================================================
//  StreamingExecutor::Impl (Private Implementation)
// ============================================================================

class StreamingExecutor::Impl {
 public:
  Impl() {
    // Set blocking sync scheduling policy BEFORE any device-specific CUDA
    // calls. This eliminates CPU spin-waiting and OS scheduler interference.
    cudaError_t err = cudaSetDeviceFlags(cudaDeviceScheduleBlockingSync);
    if (err != cudaSuccess && err != cudaErrorSetOnActiveProcess) {
      SIGTEKX_CUDA_CHECK(err);
    }

    // Select best device
    int device_count = 0;
    SIGTEKX_CUDA_CHECK(cudaGetDeviceCount(&device_count));
    if (device_count == 0) {
      throw std::runtime_error("No CUDA-capable devices found.");
    }

    device_id_ = signal_utils::select_best_device();
    SIGTEKX_CUDA_CHECK(cudaSetDevice(device_id_));
    SIGTEKX_CUDA_CHECK(cudaGetDeviceProperties(&device_props_, device_id_));
  }

  ~Impl() { reset(); }

  void initialize(const ExecutorConfig& config,
                  std::vector<std::unique_ptr<ProcessingStage>> stages) {
    SIGTEKX_NVTX_RANGE("StreamingExecutor::Initialize",
                    profiling::colors::DARK_GRAY);

    if (initialized_) {
      reset();
    }

    // Validate streaming mode
    if (config.mode != ExecutorConfig::ExecutionMode::STREAMING) {
      throw std::runtime_error(
          "StreamingExecutor requires STREAMING execution mode");
    }

    // Validate configuration
    std::string error_msg;
    if (!config.validate(error_msg)) {
      throw std::runtime_error("Invalid executor configuration: " + error_msg);
    }

    config_ = config;
    stages_ = std::move(stages);

    if (stages_.empty()) {
      throw std::runtime_error(
          "Cannot initialize executor with empty pipeline");
    }

    // Set device if specified
    if (config_.device_id >= 0) {
      SIGTEKX_CUDA_CHECK(cudaSetDevice(config_.device_id));
      device_id_ = config_.device_id;
    }

    // Calculate buffer sizes
    hop_size_ = config_.hop_size();

    // Compute max frames per submit for batched processing (Optimization 3.1)
    if (hop_size_ > 0) {
      max_frames_per_submit_ = static_cast<int>(
          std::ceil(static_cast<double>(config_.nfft) / hop_size_)) + 1;
    } else {
      max_frames_per_submit_ = 1;
    }

    // Buffer sizes scaled by max_frames_per_submit_ for batched path
    const size_t buffer_size =
        static_cast<size_t>(config_.nfft) * config_.channels *
        max_frames_per_submit_;
    const size_t output_buffer_size =
        static_cast<size_t>(config_.num_output_bins()) * config_.channels *
        max_frames_per_submit_;
    const size_t complex_buffer_size = output_buffer_size;

    // Allocate per-channel ring buffers for true multi-channel streaming
    // Each channel maintains its own independent sample stream with overlap
    //
    // Capacity calculation (with drain-all-frames logic in submit()):
    // - Each submit() pushes nfft samples, then drains ALL available frames
    // - Maximum accumulation occurs before draining: incoming + residual
    // - Worst case (high overlap, e.g., 93.75%): hop_size = nfft/16
    //   * Start: nfft - 1 samples (not enough to process)
    //   * Push nfft → available = 2*nfft - 1
    //   * Drain all frames until < nfft remains
    // - Maximum buffered: ~2*nfft
    // - Conservative: 3*nfft provides safety margin for all overlap values
    const size_t ring_capacity_per_channel =
        static_cast<size_t>(config_.nfft) * 3;
    {
      const std::string ring_msg = profiling::format_memory_range(
          "Allocate Per-Channel Ring Buffers",
          ring_capacity_per_channel * config_.channels * sizeof(float));
      SIGTEKX_NVTX_RANGE(ring_msg.c_str(), profiling::colors::CYAN);

      // Create one ring buffer per channel
      input_ring_buffers_.resize(config_.channels);
      for (int ch = 0; ch < config_.channels; ++ch) {
        input_ring_buffers_[ch] =
            std::make_unique<RingBuffer<float>>(ring_capacity_per_channel);
      }
    }

    // Create CUDA streams
    {
      SIGTEKX_NVTX_RANGE("Create CUDA Streams", profiling::colors::DARK_GRAY);
      streams_.clear();
      for (int i = 0; i < config_.stream_count; ++i) {
        streams_.emplace_back();
      }
    }

    // Create CUDA events for synchronization
    // 3 events per buffer: H2D done, Compute done, D2H done
    {
      SIGTEKX_NVTX_RANGE("Create CUDA Events", profiling::colors::DARK_GRAY);
      events_.clear();
      for (int i = 0; i < config_.pinned_buffer_count * 3; ++i) {
        events_.emplace_back(cudaEventDisableTiming);
      }
    }

    // Initialize all pipeline stages
    {
      SIGTEKX_NVTX_RANGE("Initialize Pipeline Stages", profiling::colors::MAGENTA);
      StageConfig stage_config{};
      stage_config.nfft = config_.nfft;
      stage_config.channels = config_.channels;
      stage_config.overlap = config_.overlap;
      stage_config.sample_rate_hz = config_.sample_rate_hz;
      stage_config.warmup_iters = config_.warmup_iters;

      // Map pipeline parameters from ExecutorConfig to StageConfig enums
      stage_config.window_type =
          static_cast<StageConfig::WindowType>(config_.window_type);
      stage_config.window_symmetry =
          static_cast<StageConfig::WindowSymmetry>(config_.window_symmetry);
      stage_config.window_norm =
          static_cast<StageConfig::WindowNorm>(config_.window_norm);
      stage_config.scale_policy =
          static_cast<StageConfig::ScalePolicy>(config_.scale_policy);
      stage_config.output_mode =
          static_cast<StageConfig::OutputMode>(config_.output_mode);

      for (auto& stage : stages_) {
        SIGTEKX_NVTX_RANGE("Init Stage", profiling::colors::DARK_GRAY);
        stage->initialize(stage_config, streams_[0].get());
      }
    }

    // Allocate device buffers (round-robin like BatchExecutor)
    {
      const size_t total_bytes =
          (buffer_size + output_buffer_size + complex_buffer_size * 2) *
          static_cast<size_t>(config_.pinned_buffer_count) * sizeof(float);
      const std::string alloc_msg = profiling::format_memory_range(
          "Allocate Device Buffers", total_bytes);
      SIGTEKX_NVTX_RANGE(alloc_msg.c_str(), profiling::colors::CYAN);

      d_input_buffers_.clear();
      d_output_buffers_.clear();
      d_intermediate_buffers_.clear();

      for (int i = 0; i < config_.pinned_buffer_count; ++i) {
        d_input_buffers_.emplace_back(buffer_size);
        d_input_buffers_.back().memset(0);

        d_output_buffers_.emplace_back(output_buffer_size);
        d_output_buffers_.back().memset(0);

        d_intermediate_buffers_.emplace_back(complex_buffer_size * 2);
        d_intermediate_buffers_.back().memset(0);
      }
    }

    // Initialize component timing if enabled
    measure_components_ = config_.measure_components;
    if (measure_components_) {
      window_start_ = std::make_unique<CudaEvent>(0);
      window_end_ = std::make_unique<CudaEvent>(0);
      fft_start_ = std::make_unique<CudaEvent>(0);
      fft_end_ = std::make_unique<CudaEvent>(0);
      magnitude_start_ = std::make_unique<CudaEvent>(0);
      magnitude_end_ = std::make_unique<CudaEvent>(0);
      pipeline_start_event_ = std::make_unique<CudaEvent>(0);
    }

    // Batched frame processing setup (Optimization 3.1)
    // Generate window coefficients for direct kernel launch path
    {
      SIGTEKX_NVTX_RANGE("Generate Batched Window", profiling::colors::DARK_GRAY);
      std::vector<float> host_window(config_.nfft);
      bool sqrt_norm = (config_.window_norm ==
                        static_cast<int>(StageConfig::WindowNorm::SQRT));
      window_utils::generate_window(
          host_window.data(), config_.nfft,
          static_cast<StageConfig::WindowType>(config_.window_type), sqrt_norm,
          static_cast<StageConfig::WindowSymmetry>(config_.window_symmetry));
      if (config_.window_norm ==
          static_cast<int>(StageConfig::WindowNorm::UNITY)) {
        window_utils::normalize_window(
            host_window.data(), config_.nfft,
            static_cast<StageConfig::WindowNorm>(config_.window_norm));
      }
      d_window_.resize(config_.nfft);
      d_window_.copy_from_host(host_window.data(), config_.nfft,
                               streams_[0].get());
      SIGTEKX_CUDA_CHECK(cudaStreamSynchronize(streams_[0].get()));
    }

    // Compute magnitude scale factor
    {
      auto policy =
          static_cast<StageConfig::ScalePolicy>(config_.scale_policy);
      switch (policy) {
        case StageConfig::ScalePolicy::ONE_OVER_N:
          mag_scale_ = 1.0f / static_cast<float>(config_.nfft);
          break;
        case StageConfig::ScalePolicy::ONE_OVER_SQRT_N:
          mag_scale_ = 1.0f / std::sqrt(static_cast<float>(config_.nfft));
          break;
        case StageConfig::ScalePolicy::NONE:
        default:
          mag_scale_ = 1.0f;
          break;
      }
    }

    // Warmup batched FFT plan for most common batch size
    if (max_frames_per_submit_ > 1) {
      const int compute_stream_idx = (streams_.size() > 1) ? 1 : 0;
      get_or_create_batched_plan(max_frames_per_submit_,
                                 streams_[compute_stream_idx].get());
    }

    initialized_ = true;

    // Warmup
    if (config_.warmup_iters > 0) {
      run_warmup();
    }

    stats_ = ProcessingStats{};
    stats_.is_warmup = false;

    // Start consumer thread if async mode is enabled (v0.9.5+)
    if (config_.enable_background_thread) {
      SIGTEKX_NVTX_RANGE("Start Consumer Thread", profiling::colors::PURPLE);
      stop_flag_.store(false, std::memory_order_release);
      consumer_thread_ = std::thread(&Impl::consumer_loop, this);
    }

    SIGTEKX_NVTX_MARK("Initialization Complete", profiling::colors::CYAN);
  }

  void reset() {
    SIGTEKX_NVTX_RANGE_FUNCTION(profiling::colors::RED);
    if (!initialized_) return;

    // Stop consumer thread if running (v0.9.5+)
    if (consumer_thread_.joinable()) {
      SIGTEKX_NVTX_RANGE("Stop Consumer Thread", profiling::colors::PURPLE);
      stop_flag_.store(true, std::memory_order_release);
      cv_data_ready_.notify_all();  // Wake up consumer thread if waiting
      consumer_thread_.join();      // Wait for thread to exit cleanly

      // Clear any remaining results
      std::lock_guard<std::mutex> lock(result_mutex_);
      while (!result_queue_.empty()) {
        result_queue_.pop();
      }
    }

    {
      SIGTEKX_NVTX_RANGE("Synchronize All Streams", profiling::colors::YELLOW);
      synchronize();
    }

    {
      SIGTEKX_NVTX_RANGE("Release Resources", profiling::colors::RED);
      stages_.clear();
      streams_.clear();
      events_.clear();
      d_input_buffers_.clear();
      d_intermediate_buffers_.clear();
      d_output_buffers_.clear();

      // Clean up batched processing resources
      d_window_ = DeviceBuffer<float>();
      batched_fft_plans_.clear();

      // Reset all per-channel ring buffers
      for (auto& ring_buffer : input_ring_buffers_) {
        if (ring_buffer) {
          ring_buffer.reset();
        }
      }
      input_ring_buffers_.clear();

      // Clear timing events
      window_start_.reset();
      window_end_.reset();
      fft_start_.reset();
      fft_end_.reset();
      magnitude_start_.reset();
      magnitude_end_.reset();
      pipeline_start_event_.reset();
    }

    frame_counter_ = 0;
    initialized_ = false;
    SIGTEKX_NVTX_MARK("Reset Complete", profiling::colors::RED);
  }

  void submit(const float* input, float* output, size_t num_samples) {
    SIGTEKX_NVTX_RANGE_FUNCTION(profiling::colors::NVIDIA_BLUE);
    if (!initialized_) {
      throw std::runtime_error("Executor not initialized");
    }

    // Validate input size: must be multiple of channels for channel-major
    // layout Expected layout: [ch0_sample0, ch0_sample1, ..., ch0_sampleN,
    //                   ch1_sample0, ch1_sample1, ..., ch1_sampleN, ...]
    if (num_samples % config_.channels != 0) {
      throw std::runtime_error(
          "Input size must be a multiple of channels. Expected channel-major "
          "layout: "
          "[ch0[0..N], ch1[0..N], ...]. Got num_samples=" +
          std::to_string(num_samples) +
          ", channels=" + std::to_string(config_.channels));
    }

    const auto start_time = std::chrono::high_resolution_clock::now();
    const size_t samples_per_channel = num_samples / config_.channels;

    // Push samples to per-channel ring buffers (channel-major layout)
    {
      SIGTEKX_NVTX_RANGE("Push to Per-Channel Ring Buffers",
                      profiling::colors::CYAN);
      for (int ch = 0; ch < config_.channels; ++ch) {
        const float* channel_input = input + ch * samples_per_channel;
        input_ring_buffers_[ch]->push(channel_input, samples_per_channel);
      }
    }

    // Samples needed per channel for one frame (no longer batch-dependent)
    const size_t samples_needed_per_channel = static_cast<size_t>(config_.nfft);

    // Dual-mode processing: async producer-consumer or synchronous
    if (config_.enable_background_thread) {
      // ===== ASYNC MODE: Producer-consumer pattern (v0.9.5+) =====
      SIGTEKX_NVTX_RANGE("Async Mode: Notify Consumer", profiling::colors::PURPLE);

      // Notify consumer thread that new data is available
      cv_data_ready_.notify_one();

      // Wait for result from consumer thread (with timeout for safety)
      std::vector<float> result;
      bool got_result = false;
      {
        SIGTEKX_NVTX_RANGE("Wait for Consumer Result", profiling::colors::PURPLE);
        std::unique_lock<std::mutex> lock(result_mutex_);

        // Wait up to 2 seconds for result (config_.timeout_ms or default
        // 2000ms)
        const auto timeout = std::chrono::milliseconds(
            config_.timeout_ms > 0 ? config_.timeout_ms : 2000);
        const auto deadline = std::chrono::steady_clock::now() + timeout;

        // Wait with predicate checking both result availability and stop condition
        if (!cv_data_ready_.wait_until(lock, deadline, [this] {
              return !result_queue_.empty() || stop_flag_.load(std::memory_order_acquire);
            })) {
          // Predicate returned false (timeout occurred)
          if (stop_flag_.load(std::memory_order_acquire)) {
            throw std::runtime_error(
                "Async processing stopped during wait");
          }
          throw std::runtime_error(
              "Async processing timeout: no result after " +
              std::to_string(config_.timeout_ms > 0 ? config_.timeout_ms : 2000) + "ms");
        }

        // Predicate ensures result is available (unless stopped)
        if (stop_flag_.load(std::memory_order_acquire)) {
          throw std::runtime_error(
              "Async processing stopped before result ready");
        }

        // Result must be available if we reach here
        if (result_queue_.empty()) {
          throw std::runtime_error(
              "Internal error: result queue empty after CV wait returned");
        }

        result = std::move(result_queue_.front());
        result_queue_.pop();
        got_result = true;
      }

      if (got_result) {
        // Copy result to output buffer
        const size_t output_size =
            static_cast<size_t>(config_.num_output_bins()) * config_.channels;
        std::memcpy(output, result.data(), output_size * sizeof(float));

        // Update statistics
        const auto end_time = std::chrono::high_resolution_clock::now();
        const auto duration =
            std::chrono::duration<float, std::micro>(end_time - start_time);
        stats_.latency_us = duration.count();
        stats_.frames_processed++;
        stats_.throughput_gbps =
            calculate_throughput(num_samples, duration.count());
      } else {
        throw std::runtime_error(
            "Async processing timeout: consumer thread did not produce result");
      }

    } else {
      // ===== SYNC MODE: Batched frame processing (Optimization 3.1) =====
      // Count all available frames and process them in a single GPU
      // submission. For N=1, falls back to existing process_one_batch().
      // For N>=2, uses process_batched_frames() with 1 sync instead of N.
      size_t batches_processed = 0;
      int num_frames = count_available_frames();

      if (num_frames == 0) {
        // No complete frames available
      } else if (num_frames == 1) {
        // Single frame: use existing per-frame path (zero overhead)
        process_one_batch(output);
        batches_processed = 1;
      } else {
        // Multiple frames: batched GPU submission (1 sync instead of N)
        process_batched_frames(output, num_frames);
        batches_processed = static_cast<size_t>(num_frames);
      }

      // Update statistics (for last processed batch)
      if (batches_processed > 0) {
        const auto end_time = std::chrono::high_resolution_clock::now();
        const auto duration =
            std::chrono::duration<float, std::micro>(end_time - start_time);
        stats_.latency_us =
            duration.count() / static_cast<float>(batches_processed);
        stats_.frames_processed += batches_processed;
        stats_.throughput_gbps = calculate_throughput(
            num_samples * batches_processed, duration.count());

        // Calculate overhead now that latency_us is finalized
        // (overhead was left as-is in process_one_batch(), update it here)
        if (measure_components_ && stats_.stage_metrics.enabled) {
          stats_.stage_metrics.overhead_us =
              stats_.latency_us - stats_.stage_metrics.total_measured_us;
        }
      }
    }
  }

  void submit_async(const float* input, size_t num_samples,
                    ResultCallback callback) {
    SIGTEKX_NVTX_RANGE_FUNCTION(profiling::colors::NVIDIA_BLUE);
    if (!initialized_) {
      throw std::runtime_error("Executor not initialized");
    }

    // THREAD SAFETY:
    // - Single-producer only. This method assumes a single caller thread.
    // - RingBuffer is SPSC-friendly but does not protect against multiple
    //   concurrent producers. Do not call submit_async() concurrently or mix
    //   with submit() while a background consumer thread is active.

    // Validate input size
    if (num_samples % config_.channels != 0) {
      throw std::runtime_error(
          "Input size must be a multiple of channels for channel-major layout");
    }

    const size_t samples_per_channel = num_samples / config_.channels;

    // Push samples to per-channel ring buffers
    for (int ch = 0; ch < config_.channels; ++ch) {
      const float* channel_input = input + ch * samples_per_channel;
      input_ring_buffers_[ch]->push(channel_input, samples_per_channel);
    }

    // Samples needed per channel
    const size_t samples_needed_per_channel = static_cast<size_t>(config_.nfft);

    // Process all available batches
    while (input_ring_buffers_[0]->available() >= samples_needed_per_channel) {
      // Verify all channels ready
      bool all_channels_ready = true;
      for (int ch = 0; ch < config_.channels; ++ch) {
        if (input_ring_buffers_[ch]->available() < samples_needed_per_channel) {
          all_channels_ready = false;
          break;
        }
      }

      if (!all_channels_ready) {
        break;
      }

      // Allocate output buffer for this batch
      std::vector<float> output(config_.num_output_bins() * config_.channels);
      process_one_batch(output.data());

      // Invoke callback immediately (true async with background thread is
      // v0.9.5+)
      if (callback) {
        SIGTEKX_NVTX_RANGE("Result Callback", profiling::colors::CYAN);
        // Note: Third parameter is num_frames. Currently passes
        // config_.channels because each processed batch is 1 temporal frame
        // with N spatial channels, producing N spectra. In future versions with
        // true temporal batching, this will represent the number of temporal
        // frames processed.
        callback(output.data(), config_.num_output_bins(), config_.channels,
                 stats_);
      }
    }
  }

  void synchronize() {
    SIGTEKX_NVTX_RANGE_FUNCTION(profiling::colors::YELLOW);
    for (auto& s : streams_) {
      s.synchronize();
    }
  }

  ProcessingStats get_stats() const { return stats_; }

  size_t get_memory_usage() const {
    if (!initialized_) return 0;

    size_t total = 0;

    // Per-channel ring buffers
    for (const auto& ring_buffer : input_ring_buffers_) {
      total += ring_buffer->capacity() * sizeof(float);
    }

    // Device buffers
    for (const auto& buf : d_input_buffers_) {
      total += buf.size() * sizeof(float);
    }
    for (const auto& buf : d_output_buffers_) {
      total += buf.size() * sizeof(float);
    }
    for (const auto& buf : d_intermediate_buffers_) {
      total += buf.size() * sizeof(float);
    }

    // Stage workspace
    for (const auto& stage : stages_) {
      total += stage->get_workspace_size();
    }

    // Batched processing resources
    total += d_window_.size() * sizeof(float);
    for (const auto& [batch_count, plan] : batched_fft_plans_) {
      total += plan.work_size();
    }

    return total;
  }

  bool is_initialized() const { return initialized_; }

 private:
  void run_warmup() {
    // Prepare warmup data: nfft samples per channel
    const size_t samples_per_channel = static_cast<size_t>(config_.nfft);
    const size_t total_warmup_samples = samples_per_channel * config_.channels;
    std::vector<float> dummy_input(total_warmup_samples, 0.0f);
    std::vector<float> dummy_output(
        static_cast<size_t>(config_.num_output_bins()) * config_.channels);

    stats_.is_warmup = true;
    for (int i = 0; i < config_.warmup_iters; ++i) {
      // Clear all per-channel ring buffers before each warmup iteration
      for (auto& ring_buffer : input_ring_buffers_) {
        ring_buffer->reset();
      }

      // Push to per-channel buffers (channel-major layout)
      for (int ch = 0; ch < config_.channels; ++ch) {
        const float* channel_input =
            dummy_input.data() + ch * samples_per_channel;
        input_ring_buffers_[ch]->push(channel_input, samples_per_channel);
      }

      process_one_batch(dummy_output.data());
    }
    stats_.is_warmup = false;

    // Clear all ring buffers after warmup
    for (auto& ring_buffer : input_ring_buffers_) {
      ring_buffer->reset();
    }
  }

  /**
   * @brief Counts how many complete frames are available across all channels.
   * @return Number of frames that can be processed (clamped to
   * max_frames_per_submit_).
   */
  int count_available_frames() const {
    size_t min_available = SIZE_MAX;
    for (int ch = 0; ch < config_.channels; ++ch) {
      min_available =
          std::min(min_available, input_ring_buffers_[ch]->available());
    }
    if (min_available < static_cast<size_t>(config_.nfft)) return 0;
    int num_frames = 1;
    size_t consumed = static_cast<size_t>(config_.nfft);
    while (consumed + hop_size_ <= min_available &&
           num_frames < max_frames_per_submit_) {
      num_frames++;
      consumed += hop_size_;
    }
    return num_frames;
  }

  /**
   * @brief Gets or creates a batched cuFFT plan for the given frame count.
   * @param num_frames Number of frames to batch.
   * @param stream CUDA stream to associate with new plans.
   * @return Reference to the cached CufftPlan.
   */
  CufftPlan& get_or_create_batched_plan(int num_frames, cudaStream_t stream) {
    int total_batch = num_frames * config_.channels;
    auto it = batched_fft_plans_.find(total_batch);
    if (it != batched_fft_plans_.end()) return it->second;

    auto [ins_it, inserted] =
        batched_fft_plans_.try_emplace(total_batch);
    int n[] = {config_.nfft};
    ins_it->second.create_plan_many(
        1, n, nullptr, 1, config_.nfft, nullptr, 1, config_.nfft / 2 + 1,
        CUFFT_R2C, total_batch, stream);
    return ins_it->second;
  }

  /**
   * @brief Processes N frames in a single batched GPU submission.
   *
   * Replaces N sequential process_one_batch() calls with one batched
   * submission: 1 H2D (all frames), 3 kernel launches (window, FFT,
   * magnitude), 1 D2H (last frame only), 1 cudaStreamSynchronize.
   *
   * @param output Host output buffer for the last frame's magnitude result.
   * @param num_frames Number of frames to process (must be >= 2).
   */
  void process_batched_frames(float* output, int num_frames) {
    SIGTEKX_NVTX_RANGE("Process Batched Frames", profiling::colors::PURPLE);

    const int total_batch = num_frames * config_.channels;
    const int output_bins = config_.num_output_bins();

    // Round-robin buffer selection (same as process_one_batch)
    const int buffer_idx =
        static_cast<int>(frame_counter_ % config_.pinned_buffer_count);
    auto& d_input = d_input_buffers_[buffer_idx];
    auto& d_output_buf = d_output_buffers_[buffer_idx];
    auto& d_intermediate = d_intermediate_buffers_[buffer_idx];

    // Stream assignment
    const int h2d_stream_idx = 0;
    const int compute_stream_idx = (streams_.size() > 1) ? 1 : 0;
    const int d2h_stream_idx =
        (streams_.size() > 2) ? 2 : compute_stream_idx;

    auto& e_h2d_done = events_[buffer_idx * 3 + 0];
    auto& e_compute_done = events_[buffer_idx * 3 + 1];
    auto& e_d2h_done = events_[buffer_idx * 3 + 2];

    // Guard buffer reuse with event-based synchronization
    if (frame_counter_ >=
        static_cast<uint64_t>(config_.pinned_buffer_count)) {
      SIGTEKX_NVTX_RANGE("Wait for Buffer Availability",
                          profiling::colors::YELLOW);
      auto& e_reuse_buffer_done = events_[buffer_idx * 3 + 2];
      e_reuse_buffer_done.synchronize();
    }

    // Zero-copy H2D: peek N frames from ring buffers, DMA all to device
    // Layout: [ch0_f0 | ch1_f0 | ch0_f1 | ch1_f1 | ... ]
    {
      SIGTEKX_NVTX_RANGE("H2D Transfer (Batched)", profiling::colors::GREEN);
      for (int frame_i = 0; frame_i < num_frames; ++frame_i) {
        const size_t offset = static_cast<size_t>(frame_i) * hop_size_;
        for (int ch = 0; ch < config_.channels; ++ch) {
          auto view = input_ring_buffers_[ch]->peek_frame_at_offset(
              config_.nfft, offset);
          float* d_dst =
              d_input.get() +
              (frame_i * config_.channels + ch) * config_.nfft;

          SIGTEKX_CUDA_CHECK(cudaMemcpyAsync(
              d_dst, view.first.data, view.first.count * sizeof(float),
              cudaMemcpyHostToDevice, streams_[h2d_stream_idx].get()));

          if (!view.is_contiguous()) {
            SIGTEKX_CUDA_CHECK(cudaMemcpyAsync(
                d_dst + view.first.count, view.second.data,
                view.second.count * sizeof(float), cudaMemcpyHostToDevice,
                streams_[h2d_stream_idx].get()));
          }
        }
      }
      e_h2d_done.record(streams_[h2d_stream_idx].get());
    }

    // Processing Pipeline (3 kernel launches for all N frames)
    SIGTEKX_CUDA_CHECK(cudaStreamWaitEvent(
        streams_[compute_stream_idx].get(), e_h2d_done.get(), 0));

    if (measure_components_) {
      pipeline_start_event_->record(streams_[compute_stream_idx].get());
    }

    {
      SIGTEKX_NVTX_RANGE("Compute Pipeline (Batched)",
                          profiling::colors::PURPLE);

      // 1. Window (in-place, batch = N * channels)
      {
        SIGTEKX_NVTX_RANGE("Stage: WindowStage", profiling::colors::MAGENTA);
        if (measure_components_) {
          window_start_->record(streams_[compute_stream_idx].get());
        }
        kernels::launch_apply_window(
            d_input.get(), d_input.get(), d_window_.get(), config_.nfft,
            total_batch, config_.nfft,
            streams_[compute_stream_idx].get());
        if (measure_components_) {
          window_end_->record(streams_[compute_stream_idx].get());
        }
      }

      // 2. FFT (batched R2C, batch = N * channels)
      {
        SIGTEKX_NVTX_RANGE("Stage: FFTStage", profiling::colors::MAGENTA);
        if (measure_components_) {
          fft_start_->record(streams_[compute_stream_idx].get());
        }
        auto& plan = get_or_create_batched_plan(
            num_frames, streams_[compute_stream_idx].get());
        plan.exec_r2c(
            d_input.get(),
            reinterpret_cast<cufftComplex*>(d_intermediate.get()));
        if (measure_components_) {
          fft_end_->record(streams_[compute_stream_idx].get());
        }
      }

      // 3. Magnitude (batch = N * channels)
      {
        SIGTEKX_NVTX_RANGE("Stage: MagnitudeStage",
                            profiling::colors::MAGENTA);
        if (measure_components_) {
          magnitude_start_->record(streams_[compute_stream_idx].get());
        }
        kernels::launch_magnitude(
            reinterpret_cast<const float2*>(d_intermediate.get()),
            d_output_buf.get(), output_bins, total_batch, output_bins,
            mag_scale_, streams_[compute_stream_idx].get());
        if (measure_components_) {
          magnitude_end_->record(streams_[compute_stream_idx].get());
        }
      }

      e_compute_done.record(streams_[compute_stream_idx].get());
    }

    // D2H Transfer (last frame only)
    {
      const size_t last_frame_offset =
          static_cast<size_t>(num_frames - 1) * config_.channels *
          output_bins;
      const size_t output_elements =
          static_cast<size_t>(config_.channels) * output_bins;
      const size_t bytes = output_elements * sizeof(float);
      const std::string d2h_msg =
          profiling::format_memory_range("D2H Transfer (Last Frame)", bytes);
      SIGTEKX_NVTX_RANGE(d2h_msg.c_str(), profiling::colors::ORANGE);

      SIGTEKX_CUDA_CHECK(cudaStreamWaitEvent(
          streams_[d2h_stream_idx].get(), e_compute_done.get(), 0));

      SIGTEKX_CUDA_CHECK(cudaMemcpyAsync(
          output, d_output_buf.get() + last_frame_offset,
          bytes, cudaMemcpyDeviceToHost, streams_[d2h_stream_idx].get()));

      e_d2h_done.record(streams_[d2h_stream_idx].get());
    }

    // Single synchronization point (1 sync instead of N)
    {
      SIGTEKX_NVTX_RANGE("Stream Sync", profiling::colors::YELLOW);
      SIGTEKX_CUDA_CHECK(
          cudaStreamSynchronize(streams_[d2h_stream_idx].get()));
    }

    // Advance ring buffers by total consumed samples
    {
      SIGTEKX_NVTX_RANGE("Advance Ring Buffers", profiling::colors::GREEN);
      const size_t total_advance =
          static_cast<size_t>(num_frames - 1) * hop_size_ + config_.nfft;
      // Advance by (num_frames-1)*hop + nfft would over-advance.
      // We want to consume exactly: nfft + (num_frames-1)*hop_size samples
      // But we only advance by (num_frames)*hop_size to leave the overlap
      // residual for the next batch (same as N sequential advances).
      const size_t advance_amount =
          static_cast<size_t>(num_frames) * hop_size_;
      for (int ch = 0; ch < config_.channels; ++ch) {
        input_ring_buffers_[ch]->advance(advance_amount);
      }
    }

    // Component timing: calculate stage metrics
    if (measure_components_) {
      SIGTEKX_CUDA_CHECK(
          cudaStreamSynchronize(streams_[compute_stream_idx].get()));
      float window_ms, fft_ms, magnitude_ms;
      cudaEventElapsedTime(&window_ms, window_start_->get(),
                           window_end_->get());
      cudaEventElapsedTime(&fft_ms, fft_start_->get(), fft_end_->get());
      cudaEventElapsedTime(&magnitude_ms, magnitude_start_->get(),
                           magnitude_end_->get());

      stats_.stage_metrics.enabled = true;
      stats_.stage_metrics.window_us = window_ms * 1000.0f;
      stats_.stage_metrics.fft_us = fft_ms * 1000.0f;
      stats_.stage_metrics.magnitude_us = magnitude_ms * 1000.0f;
      stats_.stage_metrics.total_measured_us =
          stats_.stage_metrics.window_us + stats_.stage_metrics.fft_us +
          stats_.stage_metrics.magnitude_us;
    }

    frame_counter_++;
  }

  void process_one_batch(float* output) {
    SIGTEKX_NVTX_RANGE("Process One Batch", profiling::colors::PURPLE);

    // Round-robin buffer selection
    const int buffer_idx =
        static_cast<int>(frame_counter_ % config_.pinned_buffer_count);
    auto& d_input = d_input_buffers_[buffer_idx];
    auto& d_output = d_output_buffers_[buffer_idx];
    auto& d_intermediate = d_intermediate_buffers_[buffer_idx];

    // Stream assignment
    const int h2d_stream_idx = 0;
    const int compute_stream_idx = (streams_.size() > 1) ? 1 : 0;
    const int d2h_stream_idx = (streams_.size() > 2) ? 2 : compute_stream_idx;

    auto& e_h2d_done = events_[buffer_idx * 3 + 0];
    auto& e_compute_done = events_[buffer_idx * 3 + 1];
    auto& e_d2h_done = events_[buffer_idx * 3 + 2];

    // Guard buffer reuse with event-based synchronization
    // Wait for previous use of this buffer to complete (D2H transfer done)
    if (frame_counter_ >= static_cast<uint64_t>(config_.pinned_buffer_count)) {
      SIGTEKX_NVTX_RANGE("Wait for Buffer Availability",
                      profiling::colors::YELLOW);

      // Calculate which buffer we're about to reuse
      const int reuse_buffer_idx =
          static_cast<int>(frame_counter_ % config_.pinned_buffer_count);

      // Synchronize on D2H completion event for this specific buffer
      // This implicitly guarantees H2D and compute are done due to stream ordering
      auto& e_reuse_buffer_done = events_[reuse_buffer_idx * 3 + 2];
      e_reuse_buffer_done.synchronize();
    }

    // Zero-copy H2D: peek into ring buffers, DMA directly to device
    // Ring buffers use CUDA pinned memory, so we can DMA without staging
    {
      SIGTEKX_NVTX_RANGE("H2D Transfer (Zero-Copy)", profiling::colors::GREEN);
      for (int ch = 0; ch < config_.channels; ++ch) {
        auto view = input_ring_buffers_[ch]->peek_frame(config_.nfft);
        float* d_dst = d_input.get() + ch * config_.nfft;

        SIGTEKX_CUDA_CHECK(cudaMemcpyAsync(d_dst, view.first.data,
            view.first.count * sizeof(float),
            cudaMemcpyHostToDevice, streams_[h2d_stream_idx].get()));

        if (!view.is_contiguous()) {
          SIGTEKX_CUDA_CHECK(cudaMemcpyAsync(
              d_dst + view.first.count, view.second.data,
              view.second.count * sizeof(float),
              cudaMemcpyHostToDevice, streams_[h2d_stream_idx].get()));
        }
      }
      e_h2d_done.record(streams_[h2d_stream_idx].get());
    }

    // Processing Pipeline
    SIGTEKX_CUDA_CHECK(cudaStreamWaitEvent(streams_[compute_stream_idx].get(),
                                        e_h2d_done.get(), 0));

    // Component timing: record pipeline start
    if (measure_components_) {
      pipeline_start_event_->record(streams_[compute_stream_idx].get());
    }

    {
      SIGTEKX_NVTX_RANGE("Compute Pipeline", profiling::colors::PURPLE);

      if (stages_.empty()) {
        throw std::runtime_error("Empty pipeline in process_one_batch()");
      }

      void* current_input = d_input.get();
      void* current_output = nullptr;
      size_t current_size =
          static_cast<size_t>(config_.nfft) * config_.channels;

      for (size_t stage_idx = 0; stage_idx < stages_.size(); ++stage_idx) {
        const auto& stage = stages_[stage_idx];
        const std::string stage_name = stage->name();

        // Determine output buffer for this stage
        if (stage_idx == 0) {
          // First stage: Window is typically in-place
          if (stage->supports_inplace()) {
            current_output = d_input.get();
          } else {
            current_output = d_intermediate.get();
          }
        } else if (stage_name == "FFTStage") {
          // FFT: real → complex, output to intermediate buffer
          current_output = d_intermediate.get();
        } else if (stage_idx == stages_.size() - 1) {
          // Last stage: always write to final output buffer
          current_output = d_output.get();
        } else {
          // Middle stages: use intermediate buffer
          current_output = d_intermediate.get();
        }

        // Process this stage
        {
          const std::string stage_msg = "Stage: " + stage_name;
          SIGTEKX_NVTX_RANGE(stage_msg.c_str(), profiling::colors::MAGENTA);

          // Component timing: record start event
          CudaEvent* start_event = nullptr;
          CudaEvent* end_event = nullptr;
          if (measure_components_) {
            if (stage_name == "WindowStage") {
              start_event = window_start_.get();
              end_event = window_end_.get();
            } else if (stage_name == "FFTStage") {
              start_event = fft_start_.get();
              end_event = fft_end_.get();
            } else if (stage_name == "MagnitudeStage") {
              start_event = magnitude_start_.get();
              end_event = magnitude_end_.get();
            }

            if (start_event) {
              start_event->record(streams_[compute_stream_idx].get());
            }
          }

          stage->process(current_input, current_output, current_size,
                         streams_[compute_stream_idx].get());

          // Component timing: record end event
          if (end_event) {
            end_event->record(streams_[compute_stream_idx].get());
          }
        }

        // Update size for next stage
        if (stage_name == "FFTStage") {
          current_size =
              static_cast<size_t>(config_.num_output_bins()) * config_.channels;
        } else if (stage_name == "MagnitudeStage") {
          current_size =
              static_cast<size_t>(config_.num_output_bins()) * config_.channels;
        }

        // Next stage's input is this stage's output
        current_input = current_output;
      }

      e_compute_done.record(streams_[compute_stream_idx].get());
    }

    // D2H Transfer
    {
      const size_t complex_elements =
          static_cast<size_t>(config_.num_output_bins()) * config_.channels;
      const size_t bytes = complex_elements * sizeof(float);
      const std::string d2h_msg =
          profiling::format_memory_range("D2H Transfer", bytes);
      SIGTEKX_NVTX_RANGE(d2h_msg.c_str(), profiling::colors::ORANGE);
      SIGTEKX_CUDA_CHECK(cudaStreamWaitEvent(streams_[d2h_stream_idx].get(),
                                          e_compute_done.get(), 0));
      d_output.copy_to_host(output, complex_elements,
                            streams_[d2h_stream_idx].get());

      // Record D2H completion for buffer reuse synchronization
      e_d2h_done.record(streams_[d2h_stream_idx].get());
    }

    // Final synchronization
    {
      SIGTEKX_NVTX_RANGE("Stream Sync", profiling::colors::YELLOW);
      SIGTEKX_CUDA_CHECK(cudaStreamSynchronize(streams_[d2h_stream_idx].get()));
    }

    // Advance ring buffers (safe: D2H sync guarantees H2D DMA complete
    // via event chain H2D → Compute → D2H)
    {
      SIGTEKX_NVTX_RANGE("Advance Ring Buffers", profiling::colors::GREEN);
      for (int ch = 0; ch < config_.channels; ++ch) {
        input_ring_buffers_[ch]->advance(hop_size_);
      }
    }

    // Component timing: calculate stage metrics
    // Current implementation (Option 1): Last-frame timing
    // Reports timing for the most recently processed frame. Simple, zero-overhead,
    // sufficient for bottleneck identification and dashboard visualization.
    //
    // Future enhancement options if needed:
    // - Option 1.5: Exponential Moving Average (smooth variance, ~20 lines)
    // - Option 2: Per-frame event pools (full accuracy, research use, ~80 lines)
    if (measure_components_) {
      // Synchronize compute stream to ensure events are complete
      SIGTEKX_CUDA_CHECK(cudaStreamSynchronize(streams_[compute_stream_idx].get()));

      // Query CUDA events for last processed frame
      // cudaEventElapsedTime returns milliseconds, convert to microseconds
      float window_ms, fft_ms, magnitude_ms;
      cudaEventElapsedTime(&window_ms, window_start_->get(), window_end_->get());
      cudaEventElapsedTime(&fft_ms, fft_start_->get(), fft_end_->get());
      cudaEventElapsedTime(&magnitude_ms, magnitude_start_->get(), magnitude_end_->get());

      // Populate stage metrics (convert ms → µs)
      stats_.stage_metrics.enabled = true;
      stats_.stage_metrics.window_us = window_ms * 1000.0f;
      stats_.stage_metrics.fft_us = fft_ms * 1000.0f;
      stats_.stage_metrics.magnitude_us = magnitude_ms * 1000.0f;
      stats_.stage_metrics.total_measured_us =
          stats_.stage_metrics.window_us + stats_.stage_metrics.fft_us + stats_.stage_metrics.magnitude_us;
      // Note: overhead_us will be calculated in submit() after latency_us is finalized
    }

    frame_counter_++;
  }

  float calculate_throughput(size_t num_samples, float latency_us) const {
    const size_t bytes = num_samples * sizeof(float) * 2;  // Input + Output
    const float secs = latency_us * 1e-6f;
    if (secs < 1e-9f) return 0.0f;
    return (static_cast<float>(bytes) / (1024.0f * 1024.0f * 1024.0f)) / secs;
  }

  /**
   * @brief Background thread consumer loop for async processing.
   *
   * Continuously drains ring buffers and processes frames on GPU.
   * Runs until stop_flag_ is set. Uses condition variable for efficient
   * waiting.
   */
  void consumer_loop() {
    SIGTEKX_NVTX_RANGE("Consumer Thread", profiling::colors::PURPLE);

    // THREAD SAFETY:
    // - Single consumer thread for ring buffers in async mode.
    // - Producers push samples via submit(); assumes one producer at a time.
    // - Coordination uses cv_data_ready_ and result_mutex_.

    // Set CUDA context for this thread
    SIGTEKX_CUDA_CHECK(cudaSetDevice(device_id_));

    const size_t samples_needed_per_channel = static_cast<size_t>(config_.nfft);
    const size_t output_size =
        static_cast<size_t>(config_.num_output_bins()) * config_.channels;

    while (!stop_flag_.load(std::memory_order_acquire)) {
      // Wait for data or stop signal
      {
        std::unique_lock<std::mutex> lock(cv_mutex_);
        cv_data_ready_.wait(lock, [this, samples_needed_per_channel] {
          // Check if we have enough samples in ALL channels
          bool have_data = true;
          for (int ch = 0; ch < config_.channels; ++ch) {
            if (input_ring_buffers_[ch]->available() <
                samples_needed_per_channel) {
              have_data = false;
              break;
            }
          }
          return have_data || stop_flag_.load(std::memory_order_acquire);
        });

        if (stop_flag_.load(std::memory_order_acquire)) {
          break;  // Exit cleanly
        }
      }

      // Process all available frames (batched when possible)
      while (!stop_flag_.load(std::memory_order_acquire)) {
        int num_frames = count_available_frames();
        if (num_frames == 0) {
          break;  // No more complete frames, go back to waiting
        }

        // Allocate result buffer
        std::vector<float> result(output_size);

        if (num_frames == 1) {
          process_one_batch(result.data());
        } else {
          process_batched_frames(result.data(), num_frames);
        }

        // Store result in queue and notify waiting producer
        {
          std::lock_guard<std::mutex> lock(result_mutex_);
          result_queue_.push(std::move(result));
        }
        cv_data_ready_.notify_one();
      }
    }
  }

  // Member variables
  ExecutorConfig config_{};
  int device_id_ = 0;
  cudaDeviceProp device_props_{};
  size_t hop_size_ = 0;

  // Per-channel ring buffers for true multi-channel streaming (v0.9.4+)
  // Each channel maintains independent sample stream with overlap
  std::vector<std::unique_ptr<RingBuffer<float>>> input_ring_buffers_;

  // Pipeline and resources
  std::vector<std::unique_ptr<ProcessingStage>> stages_;
  std::vector<CudaStream> streams_;
  std::vector<CudaEvent> events_;
  std::vector<DeviceBuffer<float>> d_input_buffers_;
  std::vector<DeviceBuffer<float>> d_intermediate_buffers_;
  std::vector<DeviceBuffer<float>> d_output_buffers_;

  // State tracking
  bool initialized_ = false;
  uint64_t frame_counter_ = 0;
  ProcessingStats stats_{};

  // Batched frame processing (Optimization 3.1)
  int max_frames_per_submit_ = 1;
  DeviceBuffer<float> d_window_;     // Window coefficients for batched path
  float mag_scale_ = 1.0f;          // Magnitude scale factor
  std::unordered_map<int, CufftPlan> batched_fft_plans_;  // batch_count -> plan

  // Component timing (only allocated if measure_components=true)
  std::unique_ptr<CudaEvent> window_start_;
  std::unique_ptr<CudaEvent> window_end_;
  std::unique_ptr<CudaEvent> fft_start_;
  std::unique_ptr<CudaEvent> fft_end_;
  std::unique_ptr<CudaEvent> magnitude_start_;
  std::unique_ptr<CudaEvent> magnitude_end_;
  std::unique_ptr<CudaEvent> pipeline_start_event_;  // Pipeline timing event
  bool measure_components_ = false;

  // Async producer-consumer infrastructure (v0.9.5+)
  std::thread consumer_thread_;            // Background processing thread
  std::atomic<bool> stop_flag_{false};     // Signal to stop consumer thread
  std::condition_variable cv_data_ready_;  // Notify consumer of new data
  std::mutex cv_mutex_;                    // Mutex for condition variable only
  std::queue<std::vector<float>>
      result_queue_;         // Completed results from consumer
  std::mutex result_mutex_;  // Protects result_queue_
};

// ============================================================================
//  StreamingExecutor Public Interface
// ============================================================================

StreamingExecutor::StreamingExecutor() : pImpl(std::make_unique<Impl>()) {}
StreamingExecutor::~StreamingExecutor() = default;
StreamingExecutor::StreamingExecutor(StreamingExecutor&&) noexcept = default;
StreamingExecutor& StreamingExecutor::operator=(StreamingExecutor&&) noexcept =
    default;

void StreamingExecutor::initialize(
    const ExecutorConfig& config,
    std::vector<std::unique_ptr<ProcessingStage>> stages) {
  pImpl->initialize(config, std::move(stages));
}

void StreamingExecutor::reset() { pImpl->reset(); }

void StreamingExecutor::submit(const float* input, float* output,
                               size_t num_samples) {
  pImpl->submit(input, output, num_samples);
}

void StreamingExecutor::submit_async(const float* input, size_t num_samples,
                                     ResultCallback callback) {
  pImpl->submit_async(input, num_samples, callback);
}

void StreamingExecutor::synchronize() { pImpl->synchronize(); }

ProcessingStats StreamingExecutor::get_stats() const {
  return pImpl->get_stats();
}

size_t StreamingExecutor::get_memory_usage() const {
  return pImpl->get_memory_usage();
}

bool StreamingExecutor::is_initialized() const {
  return pImpl->is_initialized();
}

}  // namespace sigtekx
