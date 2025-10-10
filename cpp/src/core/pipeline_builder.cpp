/**
 * @file pipeline_builder.cpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Implementation of the PipelineBuilder class.
 */

#include "ionosense/core/pipeline_builder.hpp"

#include <algorithm>
#include <stdexcept>

#include "ionosense/core/profiling_macros.hpp"

namespace ionosense {

// ============================================================================
//  PipelineBuilder::Impl (Private Implementation)
// ============================================================================

class PipelineBuilder::Impl {
 public:
  Impl() = default;

  PipelineBuilder& with_config(const StageConfig& config) {
    config_ = config;
    return builder_ref_;
  }

  PipelineBuilder& add_stage(std::unique_ptr<IProcessingStage> stage) {
    if (stage) {
      stages_.push_back(std::move(stage));
    }
    return builder_ref_;
  }

  PipelineBuilder& add_window(StageConfig::WindowType type) {
    config_.window_type = type;
    stages_.push_back(StageFactory::create(StageFactory::StageType::WINDOW));
    return builder_ref_;
  }

  PipelineBuilder& add_fft() {
    stages_.push_back(StageFactory::create(StageFactory::StageType::FFT));
    return builder_ref_;
  }

  PipelineBuilder& add_magnitude() {
    stages_.push_back(StageFactory::create(StageFactory::StageType::MAGNITUDE));
    return builder_ref_;
  }

  bool validate(std::string& error_msg) const {
    if (stages_.empty()) {
      error_msg = "Pipeline is empty. Add at least one stage.";
      return false;
    }

    // Validate stage configuration
    if (config_.nfft <= 0 || (config_.nfft & (config_.nfft - 1)) != 0) {
      error_msg = "nfft must be a positive power of 2.";
      return false;
    }

    if (config_.batch <= 0) {
      error_msg = "batch must be positive.";
      return false;
    }

    if (config_.overlap < 0.0f || config_.overlap >= 1.0f) {
      error_msg = "overlap must be in the range [0.0, 1.0).";
      return false;
    }

    // Check for in-place compatibility issues
    // Note: This is a basic check. More sophisticated validation could be added.
    for (size_t i = 0; i < stages_.size(); ++i) {
      if (!stages_[i]) {
        error_msg = "Pipeline contains null stage at index " + std::to_string(i);
        return false;
      }
    }

    error_msg.clear();
    return true;
  }

  size_t estimate_memory_usage() const {
    size_t total = 0;

    // Sum workspace requirements from all stages
    for (const auto& stage : stages_) {
      if (stage) {
        total += stage->get_workspace_size();
      }
    }

    // Add buffer allocations based on configuration
    const size_t input_buffer_size =
        static_cast<size_t>(config_.nfft) * config_.batch * sizeof(float);
    const size_t output_buffer_size =
        static_cast<size_t>(config_.nfft / 2 + 1) * config_.batch *
        sizeof(float);
    const size_t complex_buffer_size = output_buffer_size * 2;

    // Assume double-buffering as minimum
    total += 2 * (input_buffer_size + output_buffer_size + complex_buffer_size);

    return total;
  }

  std::vector<std::unique_ptr<IProcessingStage>> build() {
    std::string error_msg;
    if (!validate(error_msg)) {
      throw std::runtime_error("Pipeline validation failed: " + error_msg);
    }

    // Transfer ownership
    auto result = std::move(stages_);
    stages_.clear();
    return result;
  }

  size_t num_stages() const { return stages_.size(); }

  void clear() { stages_.clear(); }

  void set_builder_ref(PipelineBuilder& builder) { builder_ref_ = builder; }

  const StageConfig& get_config() const { return config_; }

 private:
  StageConfig config_{};
  std::vector<std::unique_ptr<IProcessingStage>> stages_;
  std::reference_wrapper<PipelineBuilder> builder_ref_{
      *reinterpret_cast<PipelineBuilder*>(this)};
};

// ============================================================================
//  PipelineBuilder Public Interface
// ============================================================================

PipelineBuilder::PipelineBuilder() : pImpl(std::make_unique<Impl>()) {
  pImpl->set_builder_ref(*this);
}

PipelineBuilder::~PipelineBuilder() = default;

PipelineBuilder& PipelineBuilder::with_config(const StageConfig& config) {
  return pImpl->with_config(config);
}

PipelineBuilder& PipelineBuilder::add_stage(
    std::unique_ptr<IProcessingStage> stage) {
  return pImpl->add_stage(std::move(stage));
}

PipelineBuilder& PipelineBuilder::add_window(StageConfig::WindowType type) {
  return pImpl->add_window(type);
}

PipelineBuilder& PipelineBuilder::add_fft() { return pImpl->add_fft(); }

PipelineBuilder& PipelineBuilder::add_magnitude() {
  return pImpl->add_magnitude();
}

bool PipelineBuilder::validate(std::string& error_msg) const {
  return pImpl->validate(error_msg);
}

size_t PipelineBuilder::estimate_memory_usage() const {
  return pImpl->estimate_memory_usage();
}

std::vector<std::unique_ptr<IProcessingStage>> PipelineBuilder::build() {
  return pImpl->build();
}

size_t PipelineBuilder::num_stages() const { return pImpl->num_stages(); }

void PipelineBuilder::clear() { pImpl->clear(); }

}  // namespace ionosense
