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
 * @brief Executor optimized for low-latency continuous streaming.
 *
 * This executor is designed for realtime applications where:
 * - Input arrives continuously in small chunks
 * - Low latency is critical
 * - Callback-based notification is preferred over blocking
 *
 * Key features:
 * - Ring buffer for input accumulation
 * - Frame-by-frame processing as data arrives
 * - Callback invocation upon completion
 * - Optional CUDA graph optimization for minimal overhead
 *
 * Note: This is a simplified implementation for v0.9.3. Full features
 * like ring buffer management and overlap handling will be added in
 * future versions.
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
  bool supports_streaming() const override { return true; }
  size_t get_memory_usage() const override;
  bool is_initialized() const override;

 private:
  class Impl;
  std::unique_ptr<Impl> pImpl;
};

}  // namespace ionosense
