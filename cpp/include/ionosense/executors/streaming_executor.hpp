/**
 * @file streaming_executor.hpp
 * @version 0.9.4
 * @date 2025-10-18
 * @author [Kevin Rahsaz]
 *
 * @brief Streaming executor with low-latency continuous processing.
 *
 * Implements continuous streaming processing with ring buffer management,
 * overlap-aware frame extraction, and CUDA stream pipelining for minimal
 * latency.
 */

#pragma once

#include <memory>

#include "ionosense/core/executor_config.hpp"
#include "ionosense/core/pipeline_executor.hpp"

namespace ionosense {

/**
 * @class StreamingExecutor
 * @brief Executor for low-latency continuous streaming processing.
 *
 * Implements true streaming with ring buffer for input accumulation and
 * overlap-aware frame extraction. Optimized for continuous processing with
 * minimal latency.
 *
 * **Key Features (v0.9.4):**
 * - Ring buffer for continuous input accumulation
 * - Overlap-aware batch extraction for STFT processing
 * - Frame-by-frame processing as samples arrive
 * - CUDA stream pipelining (H2D → Compute → D2H)
 * - Round-robin device buffers for in-flight batches
 * - Minimal blocking with event-based synchronization
 *
 * **Usage Pattern:**
 * ```cpp
 * StreamingExecutor executor;
 * ExecutorConfig config;
 * config.mode = ExecutorConfig::ExecutionMode::STREAMING;
 * config.nfft = 1024;
 * config.batch = 2;
 * config.overlap = 0.5;  // 50% overlap (hop_size = 512)
 * executor.initialize(config, stages);
 *
 * // Feed samples incrementally (e.g., 256 samples at a time)
 * executor.submit(samples, output, 256);  // Processes when enough samples
 * available
 * ```
 *
 * **Future Enhancements (v0.9.5+):**
 * - True async with background thread (submit_async() currently synchronous)
 * - Optional CUDA graph optimization for zero-overhead kernel launches
 */
class StreamingExecutor : public IPipelineExecutor {
 public:
  StreamingExecutor();
  ~StreamingExecutor() override;

  // Disable copy, enable move
  StreamingExecutor(const StreamingExecutor&) = delete;
  StreamingExecutor& operator=(const StreamingExecutor&) = delete;
  StreamingExecutor(StreamingExecutor&&) noexcept;
  StreamingExecutor& operator=(StreamingExecutor&&) noexcept;

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
   * @brief Reports streaming capability.
   * @return true - streaming fully implemented with ring buffer (v0.9.4+).
   */
  bool supports_streaming() const override { return true; }
  size_t get_memory_usage() const override;
  bool is_initialized() const override;

 private:
  class Impl;
  std::unique_ptr<Impl> pImpl;
};

}  // namespace ionosense
