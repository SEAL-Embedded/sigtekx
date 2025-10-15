/**
 * @file realtime_executor.cpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Implementation of RealtimeExecutor.
 *
 * Note: This is a simplified implementation for v0.9.3 that demonstrates
 * the architecture. It currently delegates to batch processing logic but
 * with streaming-optimized settings. Full ring buffer and overlap handling
 * will be added in future iterations.
 */

#include "ionosense/executors/realtime_executor.hpp"

#include <stdexcept>

#include "ionosense/executors/batch_executor.hpp"

namespace ionosense {

// ============================================================================
//  RealtimeExecutor::Impl (Private Implementation)
// ============================================================================

class RealtimeExecutor::Impl {
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
    if (config.mode != ExecutorConfig::ExecutionMode::STREAMING &&
        config.mode != ExecutorConfig::ExecutionMode::LOW_LATENCY) {
      throw std::runtime_error(
          "RealtimeExecutor requires STREAMING or LOW_LATENCY execution mode");
    }

    // For now, delegate to BatchExecutor with optimized settings
    // Future: Implement dedicated ring buffer and overlap management
    ExecutorConfig realtime_config = config;
    realtime_config.stream_count =
        std::max(config.stream_count, 2);  // Ensure at least 2 streams
    realtime_config.pinned_buffer_count =
        config.max_inflight_batches;  // Use inflight count for buffers

    batch_executor_->initialize(realtime_config, std::move(stages));
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
//  RealtimeExecutor Public Interface
// ============================================================================

RealtimeExecutor::RealtimeExecutor() : pImpl(std::make_unique<Impl>()) {}
RealtimeExecutor::~RealtimeExecutor() = default;
RealtimeExecutor::RealtimeExecutor(RealtimeExecutor&&) noexcept = default;
RealtimeExecutor& RealtimeExecutor::operator=(RealtimeExecutor&&) noexcept =
    default;

void RealtimeExecutor::initialize(
    const ExecutorConfig& config,
    std::vector<std::unique_ptr<IProcessingStage>> stages) {
  pImpl->initialize(config, std::move(stages));
}

void RealtimeExecutor::reset() { pImpl->reset(); }

void RealtimeExecutor::submit(const float* input, float* output,
                              size_t num_samples) {
  pImpl->submit(input, output, num_samples);
}

void RealtimeExecutor::submit_async(const float* input, size_t num_samples,
                                    ResultCallback callback) {
  pImpl->submit_async(input, num_samples, callback);
}

void RealtimeExecutor::synchronize() { pImpl->synchronize(); }

ProcessingStats RealtimeExecutor::get_stats() const {
  return pImpl->get_stats();
}

size_t RealtimeExecutor::get_memory_usage() const {
  return pImpl->get_memory_usage();
}

bool RealtimeExecutor::is_initialized() const {
  return pImpl->is_initialized();
}

}  // namespace ionosense
