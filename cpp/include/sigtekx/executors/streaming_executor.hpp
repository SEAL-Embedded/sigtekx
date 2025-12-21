/**
 * @file streaming_executor.hpp
 * @version 0.9.4
 * @date 2025-10-23
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

#include "sigtekx/core/executor_config.hpp"
#include "sigtekx/core/pipeline_executor.hpp"

namespace sigtekx {

/**
 * @class StreamingExecutor
 * @brief Executor for low-latency continuous streaming processing.
 *
 * Implements true streaming with ring buffer for input accumulation and
 * overlap-aware frame extraction. Optimized for continuous processing with
 * minimal latency.
 *
 * **Key Features (v0.9.4):**
 * - **Per-channel ring buffers** for true multi-channel streaming
 * - **Independent channel processing** with per-channel overlap
 * - **Channel-major input layout**: [ch0[0..N], ch1[0..N], ...]
 * - Frame-by-frame processing as samples arrive
 * - CUDA stream pipelining (H2D → Compute → D2H)
 * - Round-robin device buffers for in-flight batches
 * - Minimal blocking with event-based synchronization
 *
 * **Multi-Channel Architecture:**
 * Each channel maintains its own independent ring buffer and sample stream.
 * Overlap is managed per-channel, enabling true dual-antenna support where
 * each antenna produces an independent signal stream.
 *
 * **Usage Pattern:**
 * ```cpp
 * StreamingExecutor executor;
 * ExecutorConfig config;
 * config.mode = ExecutorConfig::ExecutionMode::STREAMING;
 * config.nfft = 1024;
 * config.channels = 2;  // Dual-antenna system
 * config.overlap = 0.5;  // 50% overlap (hop_size = 512)
 * executor.initialize(config, stages);
 *
 * // Feed samples incrementally in channel-major layout
 * // Input: [ch0_samples[0..255], ch1_samples[0..255]]
 * executor.submit(samples, output, 512);  // 256 samples per channel
 * ```
 *
 * **Input Layout Requirement:**
 * Input must be in channel-major layout: all samples for channel 0, then all
 * samples for channel 1, etc. The total num_samples must be a multiple of
 * the number of channels.
 *
 * **Thread Safety (v0.9.5):**
 * - Thread-compatible: different StreamingExecutor instances may be used on
 *   different threads, but a single instance requires external synchronization.
 * - Single-producer requirement: only one thread may call initialize(),
 *   reset(), submit(), or submit_async() on the same instance at a time.
 * - Async/background mode uses a single consumer thread; ring buffers are
 *   designed for single-producer/single-consumer access and do not protect
 *   against multiple concurrent producers.
 * - Do not call submit_async() concurrently with submit() or while a background
 *   thread is enabled; use one submission path per instance.
 *
 * **Safe Usage Pattern:**
 * ```cpp
 * StreamingExecutor exec;
 * exec.initialize(config, stages);
 * exec.submit(samples_a, output, num_samples);
 * exec.submit(samples_b, output, num_samples);
 * ```
 *
 * **Unsafe Usage Pattern:**
 * ```cpp
 * StreamingExecutor exec;
 * exec.initialize(config, stages);
 * std::thread t1([&] { exec.submit(samples_a, output, num_samples); });
 * std::thread t2([&] { exec.submit(samples_b, output, num_samples); });  // Race
 * t1.join();
 * t2.join();
 * ```
 *
 * **Future Enhancements (v0.9.5+):**
 * - True async with background thread (submit_async() currently synchronous)
 * - Optional CUDA graph optimization for zero-overhead kernel launches
 */
class StreamingExecutor : public PipelineExecutor {
 public:
  StreamingExecutor();
  ~StreamingExecutor() override;

  // Disable copy, enable move
  StreamingExecutor(const StreamingExecutor&) = delete;
  StreamingExecutor& operator=(const StreamingExecutor&) = delete;
  StreamingExecutor(StreamingExecutor&&) noexcept;
  StreamingExecutor& operator=(StreamingExecutor&&) noexcept;

  // PipelineExecutor interface
  void initialize(
      const ExecutorConfig& config,
      std::vector<std::unique_ptr<ProcessingStage>> stages) override;
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

}  // namespace sigtekx
