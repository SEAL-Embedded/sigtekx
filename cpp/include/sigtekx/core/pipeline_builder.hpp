/**
 * @file pipeline_builder.hpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Builder pattern for constructing signal processing pipelines.
 *
 * Provides a fluent interface for constructing processing pipelines with
 * validation and memory estimation capabilities.
 */

#pragma once

#include <memory>
#include <string>
#include <vector>

#include "sigtekx/core/processing_stage.hpp"

namespace sigtekx {

/**
 * @class PipelineBuilder
 * @brief Fluent builder for constructing signal processing pipelines.
 *
 * This class provides a type-safe, easy-to-use interface for building
 * pipelines. It supports:
 * - Adding stages in sequence
 * - Validating pipeline configuration
 * - Estimating memory requirements
 * - Building the final pipeline with ownership transfer
 *
 * Example usage:
 * @code
 *   PipelineBuilder builder;
 *   auto stages = builder
 *       .with_config(config)
 *       .add_window(StageConfig::WindowType::HANN)
 *       .add_fft()
 *       .add_magnitude()
 *       .build();
 * @endcode
 */
class PipelineBuilder {
 public:
  /**
   * @brief Constructs a new pipeline builder with default configuration.
   */
  PipelineBuilder();

  /**
   * @brief Destructor.
   */
  ~PipelineBuilder();

  /**
   * @brief Sets the stage configuration for all pipeline stages.
   * @param config The stage configuration to use.
   * @return Reference to this builder for chaining.
   */
  PipelineBuilder& with_config(const StageConfig& config);

  /**
   * @brief Adds a custom processing stage to the pipeline.
   * @param stage Unique pointer to the stage (ownership transferred).
   * @return Reference to this builder for chaining.
   */
  PipelineBuilder& add_stage(std::unique_ptr<IProcessingStage> stage);

  /**
   * @brief Adds a window stage with the specified window type.
   * @param type The window function to apply (Hann, Blackman, etc.).
   * @return Reference to this builder for chaining.
   */
  PipelineBuilder& add_window(StageConfig::WindowType type);

  /**
   * @brief Adds an FFT stage to the pipeline.
   * @return Reference to this builder for chaining.
   */
  PipelineBuilder& add_fft();

  /**
   * @brief Adds a magnitude computation stage.
   * @return Reference to this builder for chaining.
   */
  PipelineBuilder& add_magnitude();

  /**
   * @brief Validates the current pipeline configuration.
   *
   * Checks for:
   * - Empty pipeline
   * - Stage compatibility (e.g., in-place requirements)
   * - Configuration validity
   *
   * @param[out] error_msg Error message if validation fails.
   * @return True if pipeline is valid, false otherwise.
   */
  bool validate(std::string& error_msg) const;

  /**
   * @brief Estimates GPU memory usage for the configured pipeline.
   *
   * Sums up workspace requirements for all stages plus buffer allocations
   * based on the stage configuration.
   *
   * @return Estimated memory usage in bytes.
   */
  size_t estimate_memory_usage() const;

  /**
   * @brief Builds the pipeline and transfers ownership of all stages.
   *
   * After calling build(), the builder is reset to an empty state.
   *
   * @return Vector of processing stages ready for executor initialization.
   * @throws std::runtime_error if pipeline validation fails.
   */
  std::vector<std::unique_ptr<IProcessingStage>> build();

  /**
   * @brief Returns the number of stages currently in the pipeline.
   * @return Stage count.
   */
  size_t num_stages() const;

  /**
   * @brief Clears all stages from the builder.
   */
  void clear();

 private:
  class Impl;
  std::unique_ptr<Impl> pImpl;
};

}  // namespace sigtekx
