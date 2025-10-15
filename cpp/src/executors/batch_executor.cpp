/**
 * @file batch_executor.cpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Implementation of BatchExecutor.
 *
 * Extracted from ResearchEngine::Impl with the same execution logic,
 * now as a standalone executor component.
 */

#include "ionosense/executors/batch_executor.hpp"

#include <algorithm>
#include <chrono>
#include <stdexcept>

#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/core/profiling_macros.hpp"

namespace ionosense {

// ============================================================================
//  BatchExecutor::Impl (Private Implementation)
// ============================================================================

class BatchExecutor::Impl {
 public:
  Impl() {
    // Clear any existing device state from previous runs
    // This ensures a clean slate for device flags
    cudaDeviceReset();

    // Set blocking sync scheduling policy BEFORE any device-specific CUDA calls.
    // This eliminates CPU spin-waiting and OS scheduler interference during
    // synchronization calls, critical for reproducible benchmarking.
    // CUDA Programming Guide: "cudaSetDeviceFlags must be called before device
    // is initialized". This reduces CV from 57-84% to <10%.
    IONO_CUDA_CHECK(cudaSetDeviceFlags(cudaDeviceScheduleBlockingSync));

    // Select best device
    int device_count = 0;
    IONO_CUDA_CHECK(cudaGetDeviceCount(&device_count));
    if (device_count == 0) {
      throw std::runtime_error("No CUDA-capable devices found.");
    }

    device_id_ = engine_utils::select_best_device();
    IONO_CUDA_CHECK(cudaSetDevice(device_id_));
    IONO_CUDA_CHECK(cudaGetDeviceProperties(&device_props_, device_id_));
  }

  ~Impl() { reset(); }

  void initialize(const ExecutorConfig& config,
                  std::vector<std::unique_ptr<IProcessingStage>> stages) {
    IONO_NVTX_RANGE("BatchExecutor::Initialize", profiling::colors::DARK_GRAY);

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
      IONO_CUDA_CHECK(cudaSetDevice(config_.device_id));
      device_id_ = config_.device_id;
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
      stage_config.batch = config_.batch;
      stage_config.overlap = config_.overlap;
      stage_config.sample_rate_hz = config_.sample_rate_hz;
      stage_config.warmup_iters = config_.warmup_iters;

      for (auto& stage : stages_) {
        IONO_NVTX_RANGE("Init Stage", profiling::colors::DARK_GRAY);
        stage->initialize(stage_config, streams_[0].get());
      }
    }

    // Allocate device buffers
    const size_t buffer_size =
        static_cast<size_t>(config_.nfft) * config_.batch;
    const size_t output_buffer_size =
        static_cast<size_t>(config_.num_output_bins()) * config_.batch;
    const size_t complex_buffer_size = output_buffer_size;

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
      IONO_NVTX_RANGE("Wait for Buffer Availability",
                      profiling::colors::YELLOW);
      IONO_CUDA_CHECK(
          cudaStreamSynchronize(streams_[compute_stream_idx].get()));
      IONO_CUDA_CHECK(cudaStreamSynchronize(streams_[d2h_stream_idx].get()));
    }

    // H2D Transfer
    {
      const size_t bytes = num_samples * sizeof(float);
      const std::string h2d_msg =
          profiling::format_memory_range("H2D Transfer", bytes);
      IONO_NVTX_RANGE(h2d_msg.c_str(), profiling::colors::GREEN);
      d_input.copy_from_host(input, num_samples,
                             streams_[h2d_stream_idx].get());
      e_h2d_done.record(streams_[h2d_stream_idx].get());
    }

    // Processing Pipeline
    IONO_CUDA_CHECK(cudaStreamWaitEvent(streams_[compute_stream_idx].get(),
                                        e_h2d_done.get(), 0));

    {
      IONO_NVTX_RANGE("Compute Pipeline", profiling::colors::PURPLE);
      // Assume 3-stage pipeline: Window → FFT → Magnitude
      if (stages_.size() >= 3) {
        stages_[0]->process(d_input.get(), d_input.get(), num_samples,
                            streams_[compute_stream_idx].get());
        stages_[1]->process(d_input.get(), d_intermediate.get(), num_samples,
                            streams_[compute_stream_idx].get());
        const size_t complex_elements =
            static_cast<size_t>(config_.num_output_bins()) * config_.batch;
        stages_[2]->process(d_intermediate.get(), d_output.get(),
                            complex_elements,
                            streams_[compute_stream_idx].get());
      }
      e_compute_done.record(streams_[compute_stream_idx].get());
    }

    // D2H Transfer
    {
      const size_t complex_elements =
          static_cast<size_t>(config_.num_output_bins()) * config_.batch;
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

    // Update statistics
    const auto end_time = std::chrono::high_resolution_clock::now();
    const auto duration =
        std::chrono::duration<float, std::micro>(end_time - start_time);
    stats_.latency_us = duration.count();
    stats_.frames_processed++;
    stats_.throughput_gbps =
        calculate_throughput(num_samples, stats_.latency_us);

    frame_counter_++;
  }

  void submit_async(const float* input, size_t num_samples,
                    ResultCallback callback) {
    IONO_NVTX_RANGE_FUNCTION(profiling::colors::NVIDIA_BLUE);
    if (!initialized_) {
      throw std::runtime_error("Executor not initialized");
    }

    std::vector<float> output(config_.num_output_bins() * config_.batch);
    submit(input, output.data(), num_samples);

    if (callback) {
      IONO_NVTX_RANGE("Result Callback", profiling::colors::CYAN);
      callback(output.data(), config_.num_output_bins(), config_.batch, stats_);
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
        static_cast<size_t>(config_.nfft) * config_.batch, 0.0f);
    std::vector<float> dummy_output(
        static_cast<size_t>(config_.num_output_bins()) * config_.batch);

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
  std::vector<std::unique_ptr<IProcessingStage>> stages_;
  std::vector<CudaStream> streams_;
  std::vector<CudaEvent> events_;
  std::vector<DeviceBuffer<float>> d_input_buffers_;
  std::vector<DeviceBuffer<float>> d_intermediate_buffers_;
  std::vector<DeviceBuffer<float>> d_output_buffers_;
  bool initialized_ = false;
  uint64_t frame_counter_ = 0;
  ProcessingStats stats_{};
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
    std::vector<std::unique_ptr<IProcessingStage>> stages) {
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

}  // namespace ionosense
