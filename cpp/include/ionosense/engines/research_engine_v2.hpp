/**
 * @file research_engine_v2.hpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Refactored ResearchEngine using executor delegation pattern.
 *
 * This is the new v0.9.3 implementation that separates pipeline definition
 * from execution strategy. The engine becomes a simple facade over
 * PipelineBuilder + BatchExecutor.
 */

#pragma once

#include <memory>
#include <string>

#include "ionosense/core/executor_config.hpp"
#include "ionosense/core/pipeline_executor.hpp"
#include "ionosense/research_engine.hpp"  // For IPipelineEngine interface

namespace ionosense {

/**
 * @class ResearchEngineV2
 * @brief Refactored research engine using the new executor architecture.
 *
 * This implementation demonstrates the new separation of concerns:
 * - Pipeline construction via PipelineBuilder
 * - Execution via BatchExecutor
 * - Engine as a simple facade combining both
 *
 * This class maintains API compatibility with the original ResearchEngine
 * while using the new composable architecture internally.
 */
class ResearchEngineV2 : public IPipelineEngine {
 public:
  ResearchEngineV2();
  ~ResearchEngineV2() override;

  // Rule of Five
  ResearchEngineV2(const ResearchEngineV2&) = delete;
  ResearchEngineV2& operator=(const ResearchEngineV2&) = delete;
  ResearchEngineV2(ResearchEngineV2&&) noexcept;
  ResearchEngineV2& operator=(ResearchEngineV2&&) noexcept;

  // IPipelineEngine interface
  void initialize(const EngineConfig& config) override;
  void process(const float* input, float* output, size_t num_samples) override;
  void process_async(const float* input, size_t num_samples,
                    ResultCallback callback) override;
  void synchronize() override;
  void reset() override;
  ProcessingStats get_stats() const override;
  RuntimeInfo get_runtime_info() const override;
  bool is_initialized() const override;

 private:
  class Impl;
  std::unique_ptr<Impl> pImpl;
};

}  // namespace ionosense
