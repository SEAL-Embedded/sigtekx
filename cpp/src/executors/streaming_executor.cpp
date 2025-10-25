/**
 * @file streaming_executor.cpp
 * @version 0.9.4
 * @date 2025-10-23
 * @author [Kevin Rahsaz]
 *
 * @brief Implementation of StreamingExecutor with ring buffer support.
 *
 * Implements continuous streaming with ring buffer for input accumulation,
 * frame-by-frame processing with overlap, and CUDA stream pipelining for
 * low-latency operation.
 */

#include "ionosense/executors/streaming_executor.hpp"

#include <algorithm>
#include <chrono>
#include <stdexcept>

#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/core/ring_buffer.hpp"
#include "ionosense/profiling/nvtx.hpp"

namespace ionosense {

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
      IONO_CUDA_CHECK(err);
    }

    // Select best device
    int device_count = 0;
    IONO_CUDA_CHECK(cudaGetDeviceCount(&device_count));
    if (device_count == 0) {
      throw std::runtime_error("No CUDA-capable devices found.");
    }

    device_id_ = signal_utils::select_best_device();
    IONO_CUDA_CHECK(cudaSetDevice(device_id_));
    IONO_CUDA_CHECK(cudaGetDeviceProperties(&device_props_, device_id_));
  }

  ~Impl() { reset(); }

  void initialize(const ExecutorConfig& config,
                  std::vector<std::unique_ptr<IProcessingStage>> stages) {
    IONO_NVTX_RANGE("StreamingExecutor::Initialize",
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
      IONO_CUDA_CHECK(cudaSetDevice(config_.device_id));
      device_id_ = config_.device_id;
    }

    // Calculate buffer sizes
    hop_size_ = config_.hop_size();
    const size_t buffer_size =
        static_cast<size_t>(config_.nfft) * config_.channels;
    const size_t output_buffer_size =
        static_cast<size_t>(config_.num_output_bins()) * config_.channels;
    const size_t complex_buffer_size = output_buffer_size;

    // Allocate per-channel ring buffers for true multi-channel streaming
    // Each channel maintains its own independent sample stream with overlap
    // Size per channel: enough for one frame (nfft) + extra capacity for benchmarks
    // Benchmarks may push nfft samples per channel at once
    const size_t min_capacity_per_channel = static_cast<size_t>(config_.nfft);
    const size_t benchmark_chunk_per_channel = static_cast<size_t>(config_.nfft);
    const size_t ring_capacity_per_channel = min_capacity_per_channel + benchmark_chunk_per_channel;
    {
      const std::string ring_msg = profiling::format_memory_range(
          "Allocate Per-Channel Ring Buffers",
          ring_capacity_per_channel * config_.channels * sizeof(float));
      IONO_NVTX_RANGE(ring_msg.c_str(), profiling::colors::CYAN);

      // Create one ring buffer per channel
      input_ring_buffers_.resize(config_.channels);
      for (int ch = 0; ch < config_.channels; ++ch) {
        input_ring_buffers_[ch] = std::make_unique<RingBuffer<float>>(ring_capacity_per_channel);
      }
    }

    // Allocate pinned staging buffer for batch extraction
    {
      const std::string staging_msg = profiling::format_memory_range(
          "Allocate Staging Buffer", buffer_size * sizeof(float));
      IONO_NVTX_RANGE(staging_msg.c_str(), profiling::colors::CYAN);
      h_batch_staging_.resize(buffer_size);
      h_batch_staging_.memset(0);
    }

    // Create CUDA streams
    {
      IONO_NVTX_RANGE("Create CUDA Streams", profiling::colors::DARK_GRAY);
      streams_.clear();
      for (int i = 0; i < config_.stream_count; ++i) {
        streams_.emplace_back();
      }
    }

    // Create CUDA events for synchronization
    {
      IONO_NVTX_RANGE("Create CUDA Events", profiling::colors::DARK_GRAY);
      events_.clear();
      for (int i = 0; i < config_.pinned_buffer_count * 2; ++i) {
        events_.emplace_back(cudaEventDisableTiming);
      }
    }

    // Initialize all pipeline stages
    {
      IONO_NVTX_RANGE("Initialize Pipeline Stages", profiling::colors::MAGENTA);
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
        IONO_NVTX_RANGE("Init Stage", profiling::colors::DARK_GRAY);
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
      IONO_NVTX_RANGE(alloc_msg.c_str(), profiling::colors::CYAN);

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
    IONO_NVTX_MARK("Initialization Complete", profiling::colors::CYAN);
  }

  void reset() {
    IONO_NVTX_RANGE_FUNCTION(profiling::colors::RED);
    if (!initialized_) return;

    {
      IONO_NVTX_RANGE("Synchronize All Streams", profiling::colors::YELLOW);
      synchronize();
    }

    {
      IONO_NVTX_RANGE("Release Resources", profiling::colors::RED);
      stages_.clear();
      streams_.clear();
      events_.clear();
      d_input_buffers_.clear();
      d_intermediate_buffers_.clear();
      d_output_buffers_.clear();
      h_batch_staging_.resize(0);

      // Reset all per-channel ring buffers
      for (auto& ring_buffer : input_ring_buffers_) {
        if (ring_buffer) {
          ring_buffer.reset();
        }
      }
      input_ring_buffers_.clear();
    }

    frame_counter_ = 0;
    initialized_ = false;
    IONO_NVTX_MARK("Reset Complete", profiling::colors::RED);
  }

  void submit(const float* input, float* output, size_t num_samples) {
    IONO_NVTX_RANGE_FUNCTION(profiling::colors::NVIDIA_BLUE);
    if (!initialized_) {
      throw std::runtime_error("Executor not initialized");
    }

    // Validate input size: must be multiple of channels for channel-major layout
    // Expected layout: [ch0_sample0, ch0_sample1, ..., ch0_sampleN,
    //                   ch1_sample0, ch1_sample1, ..., ch1_sampleN, ...]
    if (num_samples % config_.channels != 0) {
      throw std::runtime_error(
          "Input size must be a multiple of channels. Expected channel-major layout: "
          "[ch0[0..N], ch1[0..N], ...]. Got num_samples=" + std::to_string(num_samples) +
          ", channels=" + std::to_string(config_.channels));
    }

    const auto start_time = std::chrono::high_resolution_clock::now();
    const size_t samples_per_channel = num_samples / config_.channels;

    // Push samples to per-channel ring buffers (channel-major layout)
    {
      IONO_NVTX_RANGE("Push to Per-Channel Ring Buffers", profiling::colors::CYAN);
      for (int ch = 0; ch < config_.channels; ++ch) {
        const float* channel_input = input + ch * samples_per_channel;
        input_ring_buffers_[ch]->push(channel_input, samples_per_channel);
      }
    }

    // Samples needed per channel for one frame (no longer batch-dependent)
    const size_t samples_needed_per_channel = static_cast<size_t>(config_.nfft);

    // Process all available frames (synchronized across channels)
    // All channels must have enough samples to extract a frame
    size_t batches_processed = 0;
    while (input_ring_buffers_[0]->available() >= samples_needed_per_channel) {
      // Verify all channels have sufficient samples
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

      process_one_batch(output + batches_processed * config_.num_output_bins() *
                                     config_.channels);
      batches_processed++;
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
    }
  }

  void submit_async(const float* input, size_t num_samples,
                    ResultCallback callback) {
    IONO_NVTX_RANGE_FUNCTION(profiling::colors::NVIDIA_BLUE);
    if (!initialized_) {
      throw std::runtime_error("Executor not initialized");
    }

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
        IONO_NVTX_RANGE("Result Callback", profiling::colors::CYAN);
        // Note: Third parameter is num_frames. Currently passes config_.channels
        // because each processed batch is 1 temporal frame with N spatial channels,
        // producing N spectra. In future versions with true temporal batching,
        // this will represent the number of temporal frames processed.
        callback(output.data(), config_.num_output_bins(), config_.channels,
                 stats_);
      }
    }
  }

  void synchronize() {
    IONO_NVTX_RANGE_FUNCTION(profiling::colors::YELLOW);
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

    // Staging buffer
    total += h_batch_staging_.bytes();

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
        const float* channel_input = dummy_input.data() + ch * samples_per_channel;
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

  void process_one_batch(float* output) {
    IONO_NVTX_RANGE("Process One Batch", profiling::colors::PURPLE);

    // Extract one frame per channel independently to staging buffer
    // Output layout: channel-major [ch0[0..nfft-1], ch1[0..nfft-1], ...]
    {
      IONO_NVTX_RANGE("Extract Per-Channel Frames", profiling::colors::GREEN);
      for (int ch = 0; ch < config_.channels; ++ch) {
        float* channel_staging = h_batch_staging_.get() + ch * config_.nfft;

        // Extract nfft samples from this channel's ring buffer
        // Simple non-overlapping extraction (ring buffer handles the read position)
        input_ring_buffers_[ch]->extract_frame(channel_staging, config_.nfft);
      }
    }

    // Advance each channel's ring buffer read pointer by hop_size
    // This implements the sliding window for STFT overlap independently per channel
    {
      IONO_NVTX_RANGE("Advance Per-Channel Ring Buffers", profiling::colors::GREEN);
      for (int ch = 0; ch < config_.channels; ++ch) {
        input_ring_buffers_[ch]->advance(hop_size_);
      }
    }

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

    // Guard buffer reuse with synchronization
    if (frame_counter_ >= static_cast<uint64_t>(config_.pinned_buffer_count)) {
      IONO_NVTX_RANGE("Wait for Buffer Availability",
                      profiling::colors::YELLOW);
      IONO_CUDA_CHECK(
          cudaStreamSynchronize(streams_[compute_stream_idx].get()));
      IONO_CUDA_CHECK(cudaStreamSynchronize(streams_[d2h_stream_idx].get()));
    }

    // H2D Transfer
    {
      const size_t num_samples =
          static_cast<size_t>(config_.nfft) * config_.channels;
      const size_t bytes = num_samples * sizeof(float);
      const std::string h2d_msg =
          profiling::format_memory_range("H2D Transfer", bytes);
      IONO_NVTX_RANGE(h2d_msg.c_str(), profiling::colors::GREEN);
      d_input.copy_from_host(h_batch_staging_.get(), num_samples,
                             streams_[h2d_stream_idx].get());
      e_h2d_done.record(streams_[h2d_stream_idx].get());
    }

    // Processing Pipeline
    IONO_CUDA_CHECK(cudaStreamWaitEvent(streams_[compute_stream_idx].get(),
                                        e_h2d_done.get(), 0));

    {
      IONO_NVTX_RANGE("Compute Pipeline", profiling::colors::PURPLE);

      if (stages_.empty()) {
        throw std::runtime_error("Empty pipeline in process_one_batch()");
      }

      void* current_input = d_input.get();
      void* current_output = nullptr;
      size_t current_size = static_cast<size_t>(config_.nfft) * config_.channels;

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
          IONO_NVTX_RANGE(stage_msg.c_str(), profiling::colors::MAGENTA);
          stage->process(current_input, current_output, current_size,
                         streams_[compute_stream_idx].get());
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
      IONO_NVTX_RANGE(d2h_msg.c_str(), profiling::colors::ORANGE);
      IONO_CUDA_CHECK(cudaStreamWaitEvent(streams_[d2h_stream_idx].get(),
                                          e_compute_done.get(), 0));
      d_output.copy_to_host(output, complex_elements,
                            streams_[d2h_stream_idx].get());
    }

    // Final synchronization
    {
      IONO_NVTX_RANGE("Stream Sync", profiling::colors::YELLOW);
      IONO_CUDA_CHECK(cudaStreamSynchronize(streams_[d2h_stream_idx].get()));
    }

    frame_counter_++;
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
  size_t hop_size_ = 0;

  // Per-channel ring buffers for true multi-channel streaming (v0.9.4+)
  // Each channel maintains independent sample stream with overlap
  std::vector<std::unique_ptr<RingBuffer<float>>> input_ring_buffers_;

  // Pinned staging buffer for batch extraction
  PinnedHostBuffer<float> h_batch_staging_;

  // Pipeline and resources
  std::vector<std::unique_ptr<IProcessingStage>> stages_;
  std::vector<CudaStream> streams_;
  std::vector<CudaEvent> events_;
  std::vector<DeviceBuffer<float>> d_input_buffers_;
  std::vector<DeviceBuffer<float>> d_intermediate_buffers_;
  std::vector<DeviceBuffer<float>> d_output_buffers_;

  // State tracking
  bool initialized_ = false;
  uint64_t frame_counter_ = 0;
  ProcessingStats stats_{};
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
    std::vector<std::unique_ptr<IProcessingStage>> stages) {
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

}  // namespace ionosense
