/**
 * @file research_engine.hpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Research engine using composable executor architecture.
 *
 * The ResearchEngine separates pipeline definition from execution strategy,
 * providing a flexible facade over PipelineBuilder + BatchExecutor.
 */

#pragma once

#include <functional>
#include <memory>
#include <string>

#include "ionosense/core/engine_config.hpp"
#include "ionosense/core/executor_config.hpp"
#include "ionosense/core/pipeline_executor.hpp"
#include "ionosense/core/processing_stage.hpp"

namespace ionosense {

// Forward declarations
struct RuntimeInfo;

/**
 * @struct RuntimeInfo
 * @brief CUDA runtime environment information.
 */
struct RuntimeInfo {
  std::string cuda_version;
  std::string cufft_version;
  std::string device_name;
  int device_compute_capability_major;
  int device_compute_capability_minor;
  size_t device_memory_total_mb;
  size_t device_memory_free_mb;
  int cuda_driver_version;
  int cuda_runtime_version;
};

/**
 * @brief Callback function type for asynchronous processing results.
 */
using ResultCallback =
    std::function<void(const float* magnitude, size_t num_bins,
                       size_t batch_size, const ProcessingStats& stats)>;

/**
 * @class ResearchEngine
 * @brief Main signal processing engine using composable architecture.
 *
 * The ResearchEngine provides:
 * - Pipeline construction via PipelineBuilder
 * - Execution via BatchExecutor
 * - Clean separation of concerns
 * - Extensible design for custom pipelines
 */
class ResearchEngine {
 public:
  ResearchEngine();
  ~ResearchEngine();

  // Rule of Five
  ResearchEngine(const ResearchEngine&) = delete;
  ResearchEngine& operator=(const ResearchEngine&) = delete;
  ResearchEngine(ResearchEngine&&) noexcept;
  ResearchEngine& operator=(ResearchEngine&&) noexcept;

  // Core interface
  void initialize(const EngineConfig& config);
  void process(const float* input, float* output, size_t num_samples);
  void process_async(const float* input, size_t num_samples,
                    ResultCallback callback);
  void synchronize();
  void reset();
  ProcessingStats get_stats() const;
  RuntimeInfo get_runtime_info() const;
  bool is_initialized() const;

 private:
  class Impl;
  std::unique_ptr<Impl> pImpl;
};

}  // namespace ionosense
