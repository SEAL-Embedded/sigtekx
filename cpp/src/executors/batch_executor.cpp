/**
 * @file batch_executor.cpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Implementation of BatchExecutor.
 *
 * Batch executor implementation for high-throughput processing
 * with pipelined CUDA streams and asynchronous memory transfers.
 */

#include "sigtekx/executors/batch_executor.hpp"

#include <algorithm>
#include <chrono>
#include <iostream>
#include <stdexcept>

#include "sigtekx/core/cuda_wrappers.hpp"
#include "sigtekx/profiling/nvtx.hpp"

namespace sigtekx {

// ============================================================================
//  BatchExecutor::Impl (Private Implementation)
// ============================================================================

class BatchExecutor::Impl {
 public:
  Impl() {
    // Set blocking sync scheduling policy BEFORE any device-specific CUDA
    // calls. This eliminates CPU spin-waiting and OS scheduler interference
    // during synchronization calls, critical for reproducible benchmarking.
    // CUDA Programming Guide: "cudaSetDeviceFlags must be called before device
    // is initialized". This reduces CV from 57-84% to <10%.
    //
    // NOTE: cudaDeviceReset() was removed from here because it destroys ALL
    // CUDA state globally (across all executors), causing crashes in tests
    // that create multiple executor instances. Device flags can be set without
    // a full reset if they're configured before first CUDA API call.
    cudaError_t err = cudaSetDeviceFlags(cudaDeviceScheduleBlockingSync);
    if (err != cudaSuccess && err != cudaErrorSetOnActiveProcess) {
      SIGTEKX_CUDA_CHECK(err);  // Throw if it's a real error
    }
    // cudaErrorSetOnActiveProcess is expected if CUDA was already initialized

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
    SIGTEKX_NVTX_RANGE("BatchExecutor::Initialize", profiling::colors::DARK_GRAY);

    if (initialized_) {
      reset();
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

    // Create CUDA streams
    {
      SIGTEKX_NVTX_RANGE("Create CUDA Streams", profiling::colors::DARK_GRAY);
      streams_.clear();
      for (int i = 0; i < config_.stream_count; ++i) {
        streams_.emplace_back();
      }
    }

    // Create CUDA events for synchronization
    {
      SIGTEKX_NVTX_RANGE("Create CUDA Events", profiling::colors::DARK_GRAY);
      events_.clear();
      for (int i = 0; i < config_.pinned_buffer_count * 2; ++i) {
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

      // Map pipeline parameters from EngineConfig to StageConfig enums
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

    // Setup component timing if requested
    measure_components_ = config_.measure_components;
    if (measure_components_) {
      SIGTEKX_NVTX_RANGE("Setup Component Timing", profiling::colors::CYAN);
      window_timer_ = std::make_unique<StageTimers>();
      fft_timer_ = std::make_unique<StageTimers>();
      magnitude_timer_ = std::make_unique<StageTimers>();
    }

    // Allocate device buffers
    const size_t buffer_size =
        static_cast<size_t>(config_.nfft) * config_.channels;
    const size_t output_buffer_size =
        static_cast<size_t>(config_.num_output_bins()) * config_.channels;
    const size_t complex_buffer_size = output_buffer_size;

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

    initialized_ = true;

    // Warmup
    if (config_.warmup_iters > 0) {
      run_warmup();
    }

    stats_ = ProcessingStats{};
    stats_.is_warmup = false;

    // Restore component timing enabled flag if active (reset above wiped it)
    if (measure_components_) {
      stats_.stage_metrics.enabled = true;
    }

    SIGTEKX_NVTX_MARK("Initialization Complete", profiling::colors::CYAN);
  }

  void reset() {
    SIGTEKX_NVTX_RANGE_FUNCTION(profiling::colors::RED);
    if (!initialized_) return;

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

    const auto start_time = std::chrono::high_resolution_clock::now();

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

    auto& e_h2d_done = events_[buffer_idx * 2 + 0];
    auto& e_compute_done = events_[buffer_idx * 2 + 1];

    // Guard buffer reuse with D2H sync
    // Critical for correctness with round-robin buffer reuse
    if (frame_counter_ >= static_cast<size_t>(config_.pinned_buffer_count)) {
      SIGTEKX_NVTX_RANGE("Wait for Buffer Availability",
                      profiling::colors::YELLOW);
      SIGTEKX_CUDA_CHECK(
          cudaStreamSynchronize(streams_[compute_stream_idx].get()));
      SIGTEKX_CUDA_CHECK(cudaStreamSynchronize(streams_[d2h_stream_idx].get()));
    }

    // H2D Transfer
    {
      const size_t bytes = num_samples * sizeof(float);
      const std::string h2d_msg =
          profiling::format_memory_range("H2D Transfer", bytes);
      SIGTEKX_NVTX_RANGE(h2d_msg.c_str(), profiling::colors::GREEN);
      d_input.copy_from_host(input, num_samples,
                             streams_[h2d_stream_idx].get());
      e_h2d_done.record(streams_[h2d_stream_idx].get());
    }

    // Processing Pipeline
    SIGTEKX_CUDA_CHECK(cudaStreamWaitEvent(streams_[compute_stream_idx].get(),
                                        e_h2d_done.get(), 0));

    {
      SIGTEKX_NVTX_RANGE("Compute Pipeline", profiling::colors::PURPLE);
      // Generalized stage execution with dynamic buffer routing
      // Strategy:
      // - First stage: always operates on d_input (may be in-place)
      // - Middle stages: ping-pong between d_intermediate and d_output
      // - Last stage: always writes to d_output
      //
      // Buffer sizing:
      // - Input space: nfft * batch samples
      // - Complex space (post-FFT): (nfft/2 + 1) * batch * 2 floats
      // - Output space: (nfft/2 + 1) * batch floats (magnitude)

      if (stages_.empty()) {
        throw std::runtime_error("Empty pipeline in submit()");
      }

      void* current_input = d_input.get();
      void* current_output = nullptr;
      size_t current_size = num_samples;

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

        // Record start event if measuring components
        StageTimers* timer = nullptr;
        if (measure_components_) {
          if (stage_name == "WindowStage") {
            timer = window_timer_.get();
          } else if (stage_name == "FFTStage") {
            timer = fft_timer_.get();
          } else if (stage_name == "MagnitudeStage") {
            timer = magnitude_timer_.get();
          }

          if (timer) {
            timer->start.record(streams_[compute_stream_idx].get());
          }
        }

        // Process this stage with CURRENT input size
        {
          const std::string stage_msg = "Stage: " + stage_name;
          SIGTEKX_NVTX_RANGE(stage_msg.c_str(), profiling::colors::MAGENTA);
          stage->process(current_input, current_output, current_size,
                         streams_[compute_stream_idx].get());
        }

        // Record end event if measuring components
        if (timer) {
          timer->end.record(streams_[compute_stream_idx].get());
        }

        // Update size for NEXT stage based on what THIS stage outputs
        if (stage_name == "FFTStage") {
          // FFT outputs (nfft/2 + 1) * batch complex pairs
          // MagnitudeStage expects element count (complex pairs), not float
          // count
          current_size =
              static_cast<size_t>(config_.num_output_bins()) * config_.channels;
        } else if (stage_name == "MagnitudeStage") {
          // Magnitude: complex → real, halves size
          current_size =
              static_cast<size_t>(config_.num_output_bins()) * config_.channels;
        }
        // For other stages (Window, etc.), size stays the same

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
    }

    // Final synchronization
    {
      SIGTEKX_NVTX_RANGE("Stream Sync", profiling::colors::YELLOW);
      SIGTEKX_CUDA_CHECK(cudaStreamSynchronize(streams_[d2h_stream_idx].get()));
    }

    // Update statistics
    const auto end_time = std::chrono::high_resolution_clock::now();
    const auto duration =
        std::chrono::duration<float, std::micro>(end_time - start_time);
    stats_.latency_us = duration.count();
    stats_.frames_processed++;
    stats_.throughput_gbps =
        calculate_throughput(num_samples, stats_.latency_us);

    // Compute component metrics if enabled
    StageMetrics component_metrics{};
    if (measure_components_) {
      // Synchronize compute stream to ensure events are complete
      SIGTEKX_CUDA_CHECK(cudaStreamSynchronize(streams_[compute_stream_idx].get()));

      // Calculate elapsed times (elapsed_ms returns milliseconds, convert to microseconds)
      component_metrics.window_us =
          window_timer_->end.elapsed_ms(window_timer_->start) * 1000.0f;
      component_metrics.fft_us =
          fft_timer_->end.elapsed_ms(fft_timer_->start) * 1000.0f;
      component_metrics.magnitude_us =
          magnitude_timer_->end.elapsed_ms(magnitude_timer_->start) * 1000.0f;

      component_metrics.total_measured_us = component_metrics.window_us +
                                             component_metrics.fft_us +
                                             component_metrics.magnitude_us;

      // Overhead = end-to-end latency - sum of stages
      component_metrics.overhead_us =
          stats_.latency_us - component_metrics.total_measured_us;
      component_metrics.enabled = true;
    }

    // Store in stats
    stats_.stage_metrics = component_metrics;

    frame_counter_++;
  }

  void submit_async(const float* input, size_t num_samples,
                    ResultCallback callback) {
    SIGTEKX_NVTX_RANGE_FUNCTION(profiling::colors::NVIDIA_BLUE);
    if (!initialized_) {
      throw std::runtime_error("Executor not initialized");
    }

    // NOTE: Despite the "async" name, this implementation is SYNCHRONOUS
    // (blocks until completion). True async behavior with non-blocking
    // submission and deferred callback invocation is deferred to v0.9.4+.
    //
    // This approach avoids complex lifetime management of output buffers
    // while maintaining API consistency with the executor interface.
    std::vector<float> output(config_.num_output_bins() * config_.channels);
    submit(input, output.data(), num_samples);

    if (callback) {
      SIGTEKX_NVTX_RANGE("Result Callback", profiling::colors::CYAN);
      // Note: Third parameter is num_frames. Currently passes config_.channels
      // because each submit() processes 1 temporal frame with N spatial
      // channels, producing N spectra. In future versions with true temporal
      // batching, this will represent the number of temporal frames processed.
      callback(output.data(), config_.num_output_bins(), config_.channels,
               stats_);
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
    for (const auto& buf : d_input_buffers_) {
      total += buf.size() * sizeof(float);
    }
    for (const auto& buf : d_output_buffers_) {
      total += buf.size() * sizeof(float);
    }
    for (const auto& buf : d_intermediate_buffers_) {
      total += buf.size() * sizeof(float);
    }

    // Add stage workspace
    for (const auto& stage : stages_) {
      total += stage->get_workspace_size();
    }

    return total;
  }

  bool is_initialized() const { return initialized_; }

 private:
  void run_warmup() {
    std::vector<float> dummy_input(
        static_cast<size_t>(config_.nfft) * config_.channels, 0.0f);
    std::vector<float> dummy_output(
        static_cast<size_t>(config_.num_output_bins()) * config_.channels);

    stats_.is_warmup = true;
    for (int i = 0; i < config_.warmup_iters; ++i) {
      submit(dummy_input.data(), dummy_output.data(), dummy_input.size());
    }
    stats_.is_warmup = false;
  }

  float calculate_throughput(size_t num_samples, float latency_us) const {
    const size_t bytes = num_samples * sizeof(float) * 2;  // Input + Output
    const float secs = latency_us * 1e-6f;
    if (secs < 1e-9f) return 0.0f;
    return (static_cast<float>(bytes) / (1024.0f * 1024.0f * 1024.0f)) / secs;
  }

  // Member variables
  ExecutorConfig config_{};
  int device_id_ = 0;
  cudaDeviceProp device_props_{};
  std::vector<std::unique_ptr<ProcessingStage>> stages_;
  std::vector<CudaStream> streams_;
  std::vector<CudaEvent> events_;
  std::vector<DeviceBuffer<float>> d_input_buffers_;
  std::vector<DeviceBuffer<float>> d_intermediate_buffers_;
  std::vector<DeviceBuffer<float>> d_output_buffers_;
  bool initialized_ = false;
  uint64_t frame_counter_ = 0;
  ProcessingStats stats_{};

  // Component timing infrastructure (only allocated if measure_components=true)
  struct StageTimers {
    CudaEvent start;
    CudaEvent end;
    StageTimers() : start(0), end(0) {}  // Flags=0 enables timing
  };

  std::unique_ptr<StageTimers> window_timer_;
  std::unique_ptr<StageTimers> fft_timer_;
  std::unique_ptr<StageTimers> magnitude_timer_;
  bool measure_components_ = false;
};

// ============================================================================
//  BatchExecutor Public Interface
// ============================================================================

BatchExecutor::BatchExecutor() : pImpl(std::make_unique<Impl>()) {}
BatchExecutor::~BatchExecutor() = default;
BatchExecutor::BatchExecutor(BatchExecutor&&) noexcept = default;
BatchExecutor& BatchExecutor::operator=(BatchExecutor&&) noexcept = default;

void BatchExecutor::initialize(
    const ExecutorConfig& config,
    std::vector<std::unique_ptr<ProcessingStage>> stages) {
  pImpl->initialize(config, std::move(stages));
}

void BatchExecutor::reset() { pImpl->reset(); }

void BatchExecutor::submit(const float* input, float* output,
                           size_t num_samples) {
  pImpl->submit(input, output, num_samples);
}

void BatchExecutor::submit_async(const float* input, size_t num_samples,
                                 ResultCallback callback) {
  pImpl->submit_async(input, num_samples, callback);
}

void BatchExecutor::synchronize() { pImpl->synchronize(); }

ProcessingStats BatchExecutor::get_stats() const { return pImpl->get_stats(); }

size_t BatchExecutor::get_memory_usage() const {
  return pImpl->get_memory_usage();
}

bool BatchExecutor::is_initialized() const { return pImpl->is_initialized(); }

}  // namespace sigtekx
