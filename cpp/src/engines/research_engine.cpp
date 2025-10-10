/**
 * @file research_engine.cpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Implementation of ResearchEngine using composable architecture.
 */

#include "ionosense/engines/research_engine.hpp"

#include <sstream>
#include <stdexcept>

#include "ionosense/core/pipeline_builder.hpp"
#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/executors/batch_executor.hpp"
#include "ionosense/core/profiling_macros.hpp"

namespace ionosense {

// ============================================================================
//  ResearchEngine::Impl
// ============================================================================

class ResearchEngine::Impl {
 public:
  Impl() = default;
  ~Impl() = default;

  void initialize(const EngineConfig& config) {
    IONO_NVTX_RANGE("ResearchEngine::Initialize",
                    profiling::colors::DARK_GRAY);

    // Build the default pipeline
    PipelineBuilder builder;
    StageConfig stage_config;
    stage_config.nfft = config.nfft;
    stage_config.batch = config.batch;
    stage_config.overlap = config.overlap;
    stage_config.sample_rate_hz = config.sample_rate_hz;
    stage_config.warmup_iters = config.warmup_iters;

    auto stages = builder.with_config(stage_config)
                      .add_window(StageConfig::WindowType::HANN)
                      .add_fft()
                      .add_magnitude()
                      .build();

    // Create executor config
    ExecutorConfig exec_config;
    static_cast<EngineConfig&>(exec_config) = config;  // Copy base config
    exec_config.mode = ExecutorConfig::ExecutionMode::BATCH;
    exec_config.prefer_cuda_graphs = config.use_cuda_graphs;

    // Initialize executor
    executor_ = std::make_unique<BatchExecutor>();
    executor_->initialize(exec_config, std::move(stages));
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

  RuntimeInfo get_runtime_info() const {
    IONO_NVTX_RANGE_FUNCTION(profiling::colors::CYAN);

    RuntimeInfo info;
    int cuda_runtime_version = 0, cuda_driver_version = 0;
    IONO_CUDA_CHECK(cudaRuntimeGetVersion(&cuda_runtime_version));
    IONO_CUDA_CHECK(cudaDriverGetVersion(&cuda_driver_version));
    info.cuda_runtime_version = cuda_runtime_version;
    info.cuda_driver_version = cuda_driver_version;

    std::ostringstream v;
    v << (cuda_runtime_version / 1000) << "."
      << (cuda_runtime_version % 1000) / 10;
    info.cuda_version = v.str();
    info.cufft_version = info.cuda_version;

    // Get device properties
    int device_id = 0;
    cudaDeviceProp props{};
    IONO_CUDA_CHECK(cudaGetDevice(&device_id));
    IONO_CUDA_CHECK(cudaGetDeviceProperties(&props, device_id));

    info.device_name = props.name;
    info.device_compute_capability_major = props.major;
    info.device_compute_capability_minor = props.minor;
    info.device_memory_total_mb = props.totalGlobalMem / (1024 * 1024);

    size_t free_mem = 0, total_mem = 0;
    IONO_CUDA_CHECK(cudaMemGetInfo(&free_mem, &total_mem));
    info.device_memory_free_mb = free_mem / (1024 * 1024);

    return info;
  }

  bool is_initialized() const {
    return executor_ && executor_->is_initialized();
  }

 private:
  std::unique_ptr<IPipelineExecutor> executor_;
};

// ============================================================================
//  ResearchEngine Public Interface
// ============================================================================

ResearchEngine::ResearchEngine() : pImpl(std::make_unique<Impl>()) {}
ResearchEngine::~ResearchEngine() = default;
ResearchEngine::ResearchEngine(ResearchEngine&&) noexcept = default;
ResearchEngine& ResearchEngine::operator=(ResearchEngine&&) noexcept =
    default;

void ResearchEngine::initialize(const EngineConfig& config) {
  pImpl->initialize(config);
}

void ResearchEngine::process(const float* input, float* output,
                             size_t num_samples) {
  pImpl->process(input, output, num_samples);
}

void ResearchEngine::process_async(const float* input, size_t num_samples,
                                  ResultCallback callback) {
  pImpl->process_async(input, num_samples, callback);
}

void ResearchEngine::synchronize() { pImpl->synchronize(); }

void ResearchEngine::reset() { pImpl->reset(); }

ProcessingStats ResearchEngine::get_stats() const {
  return pImpl->get_stats();
}

RuntimeInfo ResearchEngine::get_runtime_info() const {
  return pImpl->get_runtime_info();
}

bool ResearchEngine::is_initialized() const {
  return pImpl->is_initialized();
}

}  // namespace ionosense
