/**
 * @file executor_config.hpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Configuration structures for pipeline executors.
 *
 * Defines ExecutorConfig which extends EngineConfig with executor-specific
 * settings like execution mode, CUDA graph preferences, and resource hints.
 */

#pragma once

#include "ionosense/core/engine_config.hpp"  // For EngineConfig base

namespace ionosense {

/**
 * @struct ExecutorConfig
 * @brief Configuration for pipeline executor behavior and resource management.
 *
 * Extends EngineConfig with executor-specific settings that control how the
 * pipeline is executed (batch vs streaming) and which optimizations to apply.
 */
struct ExecutorConfig : EngineConfig {
  /**
   * @enum ExecutionMode
   * @brief Defines the execution strategy for the pipeline.
   */
  enum class ExecutionMode {
    BATCH,     ///< Process complete batches with maximum throughput
    STREAMING  ///< Continuous processing with low-latency via ring buffer
  };

  // --- Executor-Specific Settings ---

  /// Execution strategy to use
  ExecutionMode mode = ExecutionMode::BATCH;

  /// Maximum number of batches that can be in-flight simultaneously
  /// (used in streaming mode - deferred to v0.9.4+)
  int max_inflight_batches = 2;

  /// Device ID to use (defaults to best available)
  int device_id = -1;  // -1 means auto-select

  // NOTE: prefer_cuda_graphs removed in v0.9.3 - deferred to v0.9.4+
  // CUDA graph optimization will be added when async/streaming features
  // are fully implemented.

  /**
   * @brief Validates the executor configuration.
   * @param[out] error_msg Error message if validation fails.
   * @return True if configuration is valid, false otherwise.
   */
  bool validate(std::string& error_msg) const {
    // First validate base EngineConfig
    if (!engine_utils::validate_config(*this, error_msg)) {
      return false;
    }

    // Validate executor-specific constraints
    if (max_inflight_batches < 1) {
      error_msg = "max_inflight_batches must be at least 1.";
      return false;
    }

    if (mode == ExecutionMode::STREAMING &&
        pinned_buffer_count < max_inflight_batches) {
      error_msg =
          "pinned_buffer_count must be >= max_inflight_batches for streaming "
          "mode.";
      return false;
    }

    error_msg.clear();
    return true;
  }
};

}  // namespace ionosense
