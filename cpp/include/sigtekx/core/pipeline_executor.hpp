/**
 * @file pipeline_executor.hpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Defines the abstract IPipelineExecutor interface for executing signal
 * processing pipelines.
 *
 * This header introduces the core abstraction that separates pipeline
 * definition (the "what") from execution strategy (the "how"). Different
 * executors can implement various execution patterns (batch, streaming,
 * low-latency) while using the same pipeline stages.
 */

#pragma once

#include <cstddef>
#include <functional>
#include <memory>
#include <string>
#include <vector>

#include "ionosense/core/processing_stage.hpp"

namespace ionosense {

// Forward declarations
struct ExecutorConfig;
class IProcessingStage;

/**
 * @brief Callback function type for asynchronous processing results.
 * @param magnitude Pointer to the magnitude spectrum data on the host.
 * @param num_bins The number of frequency bins in one spectrum.
 * @param num_frames The number of temporal frames in the result.
 * @param stats Performance statistics for the operation.
 */
using ResultCallback =
    std::function<void(const float* magnitude, size_t num_bins,
                       size_t num_frames, const ProcessingStats& stats)>;

/**
 * @class IPipelineExecutor
 * @brief Abstract interface for executing a signal processing pipeline.
 *
 * This interface defines the contract for all executor implementations. It
 * separates the pipeline logic (stages) from the execution strategy (how
 * those stages are orchestrated with CUDA resources).
 *
 * Key responsibilities:
 * - Own CUDA resources (streams, events, buffers)
 * - Orchestrate pipeline stage execution
 * - Manage asynchronous execution and synchronization
 * - Provide performance introspection
 */
class IPipelineExecutor {
 public:
  virtual ~IPipelineExecutor() = default;

  /**
   * @brief Initializes the executor with configuration and pipeline stages.
   *
   * This method takes ownership of the provided stages and sets up all
   * necessary CUDA resources based on the configuration.
   *
   * @param config The executor configuration including buffer counts, streams,
   * etc.
   * @param stages Vector of processing stages to execute (ownership
   * transferred).
   * @throws std::runtime_error if initialization fails or config is invalid.
   */
  virtual void initialize(
      const ExecutorConfig& config,
      std::vector<std::unique_ptr<IProcessingStage>> stages) = 0;

  /**
   * @brief Resets the executor, releasing all CUDA resources.
   *
   * After calling reset(), the executor must be re-initialized before use.
   */
  virtual void reset() = 0;

  /**
   * @brief Processes input data synchronously through the pipeline.
   *
   * Blocks until processing is complete and output is available.
   *
   * @param input Pointer to host input data.
   * @param output Pointer to host output buffer.
   * @param num_samples Total number of float samples in the input.
   * @throws std::runtime_error if executor is not initialized.
   */
  virtual void submit(const float* input, float* output,
                      size_t num_samples) = 0;

  /**
   * @brief Processes input data asynchronously with callback notification.
   *
   * Initiates processing and returns immediately. The callback is invoked
   * when results are ready.
   *
   * @param input Pointer to host input data.
   * @param num_samples Total number of float samples in the input.
   * @param callback Function to call when processing completes.
   * @throws std::runtime_error if executor is not initialized.
   */
  virtual void submit_async(const float* input, size_t num_samples,
                            ResultCallback callback) = 0;

  /**
   * @brief Blocks until all pending operations complete.
   */
  virtual void synchronize() = 0;

  /**
   * @brief Retrieves performance statistics for the last operation.
   * @return ProcessingStats structure with latency, throughput, etc.
   */
  virtual ProcessingStats get_stats() const = 0;

  /**
   * @brief Checks if this executor supports streaming mode.
   * @return True if executor can handle continuous streaming, false otherwise.
   */
  virtual bool supports_streaming() const = 0;

  /**
   * @brief Estimates current GPU memory usage by this executor.
   * @return Memory usage in bytes.
   */
  virtual size_t get_memory_usage() const = 0;

  /**
   * @brief Checks if the executor is initialized and ready for use.
   * @return True if initialized, false otherwise.
   */
  virtual bool is_initialized() const = 0;
};

}  // namespace ionosense
