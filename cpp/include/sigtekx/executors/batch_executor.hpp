/**
 * @file batch_executor.hpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Batch-oriented pipeline executor with round-robin buffer management.
 *
 * Implements the PipelineExecutor interface for high-throughput batch
 * processing using multiple CUDA streams and double/triple buffering.
 */

#pragma once

#include <memory>

#include "sigtekx/core/executor_config.hpp"
#include "sigtekx/core/pipeline_executor.hpp"

namespace sigtekx {

/**
 * @class BatchExecutor
 * @brief Executor optimized for batch processing with maximum throughput.
 *
 * This executor implements batch processing with maximum throughput.
 * It manages:
 * - Multiple CUDA streams for H2D, compute, and D2H operations
 * - Round-robin buffer selection for pipelining
 * - Event-based synchronization between pipeline stages
 * - Double/triple buffering for overlapping operations
 *
 * Key features:
 * - Asynchronous H2D → Compute → D2H pipeline
 * - Minimal blocking with event-based dependencies
 * - Proper buffer reuse with cross-frame synchronization
 * - NVTX profiling integration
 */
class BatchExecutor : public PipelineExecutor {
 public:
  BatchExecutor();
  ~BatchExecutor() override;

  // Disable copy, enable move
  BatchExecutor(const BatchExecutor&) = delete;
  BatchExecutor& operator=(const BatchExecutor&) = delete;
  BatchExecutor(BatchExecutor&&) noexcept;
  BatchExecutor& operator=(BatchExecutor&&) noexcept;

  // PipelineExecutor interface
  void initialize(
      const ExecutorConfig& config,
      std::vector<std::unique_ptr<ProcessingStage>> stages) override;
  void reset() override;
  void submit(const float* input, float* output, size_t num_samples) override;

  /**
   * @brief Submits input for processing with callback notification.
   *
   * @warning **SYNCHRONOUS IMPLEMENTATION (v0.9.3)**
   * Despite the "async" name, this method currently BLOCKS until processing
   * completes, then invokes the callback immediately. True asynchronous
   * behavior (non-blocking submission with deferred callback) is deferred to
   * v0.9.4+.
   *
   * This design choice avoids complex lifetime management of output buffers
   * while providing a callback-based API for consistency with the executor
   * interface.
   *
   * @param input Pointer to host input data.
   * @param num_samples Total number of samples in input.
   * @param callback Function to invoke with results (called before return).
   */
  void submit_async(const float* input, size_t num_samples,
                    ResultCallback callback) override;
  void synchronize() override;
  ProcessingStats get_stats() const override;
  bool supports_streaming() const override { return false; }
  size_t get_memory_usage() const override;
  bool is_initialized() const override;

 private:
  class Impl;
  std::unique_ptr<Impl> pImpl;
};

}  // namespace sigtekx
