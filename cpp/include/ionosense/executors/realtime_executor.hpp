/**
 * @file realtime_executor.hpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Realtime streaming executor with low-latency processing.
 *
 * Implements continuous streaming processing with callback-based output
 * delivery and minimal blocking operations.
 */

#pragma once

#include <memory>

#include "ionosense/core/executor_config.hpp"
#include "ionosense/core/pipeline_executor.hpp"

namespace ionosense {

/**
 * @class RealtimeExecutor
 * @brief Placeholder executor for low-latency continuous streaming.
 *
 * @warning **STUB IMPLEMENTATION (v0.9.3)**
 * This executor is currently a thin wrapper around BatchExecutor and does NOT
 * implement true streaming capabilities. It is provided as an architectural
 * placeholder for v0.9.4+ where full streaming features will be added.
 *
 * **Current behavior:**
 * - Delegates all operations to BatchExecutor
 * - Does NOT accumulate input in ring buffers
 * - Does NOT process frames as they arrive
 * - Does NOT support true streaming (supports_streaming() returns false)
 *
 * **Planned features for v0.9.4+:**
 * - Ring buffer for input accumulation
 * - Frame-by-frame processing as data arrives
 * - Overlap handling for continuous streams
 * - Callback invocation upon frame completion
 * - Optional CUDA graph optimization for minimal overhead
 *
 * For now, use BatchExecutor directly for batch processing, or wait for
 * v0.9.4 for true realtime streaming support.
 */
class RealtimeExecutor : public IPipelineExecutor {
 public:
  RealtimeExecutor();
  ~RealtimeExecutor() override;

  // Disable copy, enable move
  RealtimeExecutor(const RealtimeExecutor&) = delete;
  RealtimeExecutor& operator=(const RealtimeExecutor&) = delete;
  RealtimeExecutor(RealtimeExecutor&&) noexcept;
  RealtimeExecutor& operator=(RealtimeExecutor&&) noexcept;

  // IPipelineExecutor interface
  void initialize(
      const ExecutorConfig& config,
      std::vector<std::unique_ptr<IProcessingStage>> stages) override;
  void reset() override;
  void submit(const float* input, float* output, size_t num_samples) override;
  void submit_async(const float* input, size_t num_samples,
                    ResultCallback callback) override;
  void synchronize() override;
  ProcessingStats get_stats() const override;

  /**
   * @brief Reports streaming capability (currently false).
   * @return false - streaming not implemented in v0.9.3 stub.
   */
  bool supports_streaming() const override { return false; }
  size_t get_memory_usage() const override;
  bool is_initialized() const override;

 private:
  class Impl;
  std::unique_ptr<Impl> pImpl;
};

}  // namespace ionosense
