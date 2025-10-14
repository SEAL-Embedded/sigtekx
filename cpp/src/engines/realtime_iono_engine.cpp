/**
 * @file realtime_iono_engine.cpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Implementation of RealtimeIonoEngine.
 */

#include "ionosense/engines/realtime_iono_engine.hpp"

#include <stdexcept>

#include "ionosense/core/pipeline_builder.hpp"
#include "ionosense/executors/realtime_executor.hpp"

namespace ionosense {

// ============================================================================
//  RealtimeIonoEngine::Impl
// ============================================================================

class RealtimeIonoEngine::Impl {
 public:
  explicit Impl(const IonosphereConfig& config) {
    // Build ionosphere-specific pipeline
    PipelineBuilder builder;

    StageConfig stage_config;
    stage_config.nfft = config.nfft;
    stage_config.batch = config.batch;
    stage_config.overlap = config.overlap;
    stage_config.sample_rate_hz = config.sample_rate_hz;
    stage_config.warmup_iters = config.warmup_iters;

    // Use Blackman window for ionosphere work (better sidelobe suppression)
    auto stages = builder.with_config(stage_config)
                      .add_window(StageConfig::WindowType::BLACKMAN)
                      .add_fft()
                      .add_magnitude()
                      .build();

    // TODO: Add ionosphere-specific metrics stage here in future
    // .add_stage(std::make_unique<IonoMetricsStage>())

    // Initialize executor with realtime/streaming config
    executor_ = std::make_unique<RealtimeExecutor>();
    executor_->initialize(config, std::move(stages));
  }

  void process(const float* input, float* output, size_t num_samples) {
    if (!executor_) {
      throw std::runtime_error("Engine not initialized");
    }
    executor_->submit(input, output, num_samples);
  }

  void process_async(const float* input, size_t num_samples,
                     ResultCallback callback) {
    if (!executor_) {
      throw std::runtime_error("Engine not initialized");
    }
    executor_->submit_async(input, num_samples, callback);
  }

  void synchronize() {
    if (executor_) {
      executor_->synchronize();
    }
  }

  void reset() {
    if (executor_) {
      executor_->reset();
    }
  }

  ProcessingStats get_stats() const {
    if (!executor_) {
      return ProcessingStats{};
    }
    return executor_->get_stats();
  }

  bool is_initialized() const {
    return executor_ && executor_->is_initialized();
  }

 private:
  std::unique_ptr<IPipelineExecutor> executor_;
};

// ============================================================================
//  RealtimeIonoEngine Public Interface
// ============================================================================

RealtimeIonoEngine::RealtimeIonoEngine(const IonosphereConfig& config)
    : pImpl(std::make_unique<Impl>(config)) {}

RealtimeIonoEngine::~RealtimeIonoEngine() = default;
RealtimeIonoEngine::RealtimeIonoEngine(RealtimeIonoEngine&&) noexcept = default;
RealtimeIonoEngine& RealtimeIonoEngine::operator=(
    RealtimeIonoEngine&&) noexcept = default;

void RealtimeIonoEngine::process(const float* input, float* output,
                                 size_t num_samples) {
  pImpl->process(input, output, num_samples);
}

void RealtimeIonoEngine::process_async(const float* input, size_t num_samples,
                                       ResultCallback callback) {
  pImpl->process_async(input, num_samples, callback);
}

void RealtimeIonoEngine::synchronize() { pImpl->synchronize(); }

void RealtimeIonoEngine::reset() { pImpl->reset(); }

ProcessingStats RealtimeIonoEngine::get_stats() const {
  return pImpl->get_stats();
}

bool RealtimeIonoEngine::is_initialized() const {
  return pImpl->is_initialized();
}

}  // namespace ionosense
