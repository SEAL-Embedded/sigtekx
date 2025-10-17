/**
 * @file streaming_executor.cpp
 * @version 0.9.3
 * @date 2025-10-16
 * @author [Kevin Rahsaz]
 *
 * @brief Stub implementation of StreamingExecutor (placeholder for v0.9.4+).
 *
 * @warning **STUB IMPLEMENTATION**
 * This executor is currently a simple wrapper around BatchExecutor and does
 * NOT implement true streaming capabilities. It is provided as an
 * architectural placeholder to demonstrate the executor abstraction pattern.
 *
 * Full streaming features (ring buffers, input accumulation, overlap handling,
 * CUDA stream pipelining, background processing) will be implemented in v0.9.4+.
 */

#include "ionosense/executors/streaming_executor.hpp"

#include <stdexcept>

#include "ionosense/executors/batch_executor.hpp"

namespace ionosense {

// ============================================================================
//  StreamingExecutor::Impl (Private Implementation)
// ============================================================================

class StreamingExecutor::Impl {
 public:
  Impl() {
    // Note: Device initialization (cudaDeviceReset, cudaSetDeviceFlags) is
    // handled by BatchExecutor's constructor. We don't duplicate it here to
    // avoid resetting the device state twice.
    batch_executor_ = std::make_unique<BatchExecutor>();
  }

  ~Impl() = default;

  void initialize(const ExecutorConfig& config,
                  std::vector<std::unique_ptr<IProcessingStage>> stages) {
    // Validate streaming mode requirements
    if (config.mode != ExecutorConfig::ExecutionMode::STREAMING) {
      throw std::runtime_error(
          "StreamingExecutor requires STREAMING execution mode");
    }

    // For now, delegate to BatchExecutor with optimized settings
    // Future: Implement dedicated ring buffer and overlap management
    ExecutorConfig streaming_config = config;
    streaming_config.stream_count =
        std::max(config.stream_count, 2);  // Ensure at least 2 streams
    streaming_config.pinned_buffer_count =
        config.max_inflight_batches;  // Use inflight count for buffers

    batch_executor_->initialize(streaming_config, std::move(stages));
  }

  void reset() { batch_executor_->reset(); }

  void submit(const float* input, float* output, size_t num_samples) {
    batch_executor_->submit(input, output, num_samples);
  }

  void submit_async(const float* input, size_t num_samples,
                    ResultCallback callback) {
    batch_executor_->submit_async(input, num_samples, callback);
  }

  void synchronize() { batch_executor_->synchronize(); }

  ProcessingStats get_stats() const { return batch_executor_->get_stats(); }

  size_t get_memory_usage() const {
    return batch_executor_->get_memory_usage();
  }

  bool is_initialized() const { return batch_executor_->is_initialized(); }

 private:
  std::unique_ptr<BatchExecutor> batch_executor_;
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
