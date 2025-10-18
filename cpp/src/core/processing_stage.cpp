/**
 * @file processing_stage.cpp
 * @version 1.0
 * @date 2025-09-01
 * @author [Kevin Rahsaz]
 *
 * @brief Implements the concrete processing stages for the signal processing
 * pipeline.
 *
 * This file provides the implementations for the Window, FFT, and Magnitude
 * stages declared in processing_stage.hpp. It uses the Pimpl idiom to hide
 * internal implementation details (like cuFFT plans and device buffers) from
 * the header, promoting cleaner architecture and faster compile times.
 */

#include "ionosense/core/processing_stage.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/core/window_functions.hpp"
#include "ionosense/profiling/nvtx.hpp"

// --- External Kernel Launch Function Declarations (from ops_fft.cu) ---
namespace ionosense {
namespace kernels {
// Declares functions defined in another translation unit (.cu file).
extern void launch_apply_window(const float* input, float* output,
                                const float* window, int nfft, int batch,
                                int stride, cudaStream_t stream);

extern void launch_magnitude(const float2* input, float* output, int num_bins,
                             int batch, int input_stride, float scale,
                             cudaStream_t stream);

}  // namespace kernels
}  // namespace ionosense

namespace ionosense {

// ============================================================================
//  WindowStage Implementation
// ============================================================================

/**
 * @class WindowStage::Impl
 * @brief Private implementation of the WindowStage.
 *
 * Hides CUDA-specific resources like the device buffer for the window.
 */
class WindowStage::Impl {
 public:
  Impl() = default;

  void initialize(const StageConfig& config, cudaStream_t stream) {
    IONO_NVTX_RANGE("WindowStage::Initialize", profiling::colors::DARK_GRAY);
    config_ = config;

    // Generate window coefficients on the host CPU.
    {
      IONO_NVTX_RANGE("Generate Window Coefficients",
                      profiling::colors::DARK_GRAY);
      std::vector<float> host_window(config.nfft);
      bool sqrt_norm = (config.window_norm == StageConfig::WindowNorm::SQRT);
      window_utils::generate_window(host_window.data(), config.nfft,
                                    config.window_type, sqrt_norm,
                                    config.window_symmetry);

      // Apply window normalization (UNITY or SQRT)
      // Note: SQRT normalization is already applied during generation
      // UNITY normalization needs to be applied here
      if (config.window_norm == StageConfig::WindowNorm::UNITY) {
        IONO_NVTX_RANGE("Apply UNITY Normalization", profiling::colors::CYAN);
        window_utils::normalize_window(host_window.data(), config.nfft,
                                       config.window_norm);
      }

      // Allocate device memory and upload the window coefficients.
      d_window_.resize(config.nfft);
      {
        const size_t bytes = static_cast<size_t>(config.nfft) * sizeof(float);
        const std::string msg =
            profiling::format_memory_range("Upload Window Coefficients", bytes);
        IONO_NVTX_RANGE(msg.c_str(), profiling::colors::GREEN);
      }
      d_window_.copy_from_host(host_window.data(), config.nfft, stream);
    }

    // Ensure the window is fully uploaded before subsequent stages might use
    // it.
    {
      IONO_NVTX_RANGE("Window Upload Sync", profiling::colors::YELLOW);
      IONO_CUDA_CHECK(cudaStreamSynchronize(stream));
    }

    initialized_ = true;
    IONO_NVTX_MARK("WindowStage Ready", profiling::colors::CYAN);
  }

  void process(void* input, void* output, size_t num_samples,
               cudaStream_t stream) {
    const std::string range_name =
        profiling::format_stage_range("Window", config_.batch, config_.nfft);
    IONO_NVTX_RANGE(range_name.c_str(), profiling::colors::PURPLE);
    if (!initialized_) {
      throw std::runtime_error("WindowStage not initialized");
    }

    if (num_samples != static_cast<size_t>(config_.nfft * config_.batch)) {
      throw std::runtime_error("Invalid number of samples for window stage");
    }

    const float* input_ptr = static_cast<const float*>(input);
    float* output_ptr = static_cast<float*>(output);

    {
      IONO_NVTX_RANGE("Window Kernel Launch", profiling::colors::PURPLE);
      kernels::launch_apply_window(input_ptr, output_ptr, d_window_.get(),
                                   config_.nfft, config_.batch, config_.nfft,
                                   stream);
    }
  }

  size_t get_workspace_size() const { return d_window_.bytes(); }

 private:
  StageConfig config_;
  DeviceBuffer<float> d_window_;
  bool initialized_ = false;
};

// --- Public WindowStage methods forwarding to Impl ---
WindowStage::WindowStage() : pImpl(std::make_unique<Impl>()) {}
WindowStage::~WindowStage() = default;
void WindowStage::initialize(const StageConfig& config, cudaStream_t stream) {
  pImpl->initialize(config, stream);
}
void WindowStage::process(void* input, void* output, size_t num_samples,
                          cudaStream_t stream) {
  pImpl->process(input, output, num_samples, stream);
}
size_t WindowStage::get_workspace_size() const {
  return pImpl->get_workspace_size();
}

// ============================================================================
//  FFTStage Implementation
// ============================================================================

/**
 * @class FFTStage::Impl
 * @brief Private implementation of the FFTStage.
 *
 * Manages the cuFFT plan and execution details.
 */
class FFTStage::Impl {
 public:
  Impl() = default;

  void initialize(const StageConfig& config, cudaStream_t stream) {
    IONO_NVTX_RANGE("FFTStage::Initialize", profiling::colors::DARK_GRAY);
    config_ = config;

    // Configure dimensions for a batched 1D Real-to-Complex transform.
    {
      IONO_NVTX_RANGE("Create cuFFT Plan", profiling::colors::DARK_GRAY);
      int n[] = {config.nfft};
      plan_.create_plan_many(
          1,                    // rank (1D transform)
          n,                    // dimensions
          nullptr,              // inembed (not used for simple layout)
          1,                    // istride
          config.nfft,          // idist (distance between batches)
          nullptr,              // onembed
          1,                    // ostride
          config.nfft / 2 + 1,  // odist (distance for R2C output)
          CUFFT_R2C,            // Transform type
          config.batch,         // Number of transforms in the batch
          stream);
    }
    initialized_ = true;
    IONO_NVTX_MARK("FFTStage Ready", profiling::colors::CYAN);
  }

  void process(void* input, void* output, size_t num_samples,
               cudaStream_t /*stream*/) {
    const std::string range_name =
        profiling::format_stage_range("FFT", config_.batch, config_.nfft);
    IONO_NVTX_RANGE(range_name.c_str(), profiling::colors::PURPLE);
    if (!initialized_) {
      throw std::runtime_error("FFTStage not initialized");
    }

    if (num_samples != static_cast<size_t>(config_.nfft * config_.batch)) {
      throw std::runtime_error("Invalid number of samples for FFT stage");
    }

    // Execute the R2C transform. Input is real, output is complex.
    {
      IONO_NVTX_RANGE("cuFFT Execution", profiling::colors::PURPLE);
      cufftReal* fft_real_input = static_cast<cufftReal*>(input);
      cufftComplex* fft_cplx_output = reinterpret_cast<cufftComplex*>(output);
      plan_.exec_r2c(fft_real_input, fft_cplx_output);
    }
  }

  size_t get_workspace_size() const { return plan_.work_size(); }

 private:
  StageConfig config_;
  CufftPlan plan_;
  bool initialized_ = false;
};

// --- Public FFTStage methods forwarding to Impl ---
FFTStage::FFTStage() : pImpl(std::make_unique<Impl>()) {}
FFTStage::~FFTStage() = default;
void FFTStage::initialize(const StageConfig& config, cudaStream_t stream) {
  pImpl->initialize(config, stream);
}
void FFTStage::process(void* input, void* output, size_t num_samples,
                       cudaStream_t stream) {
  pImpl->process(input, output, num_samples, stream);
}
size_t FFTStage::get_workspace_size() const {
  return pImpl->get_workspace_size();
}

// ============================================================================
//  MagnitudeStage Implementation
// ============================================================================

/**
 * @class MagnitudeStage::Impl
 * @brief Private implementation of the MagnitudeStage.
 */
class MagnitudeStage::Impl {
 public:
  Impl() = default;

  void initialize(const StageConfig& cfg, cudaStream_t /*stream*/) {
    IONO_NVTX_RANGE("MagnitudeStage::Initialize", profiling::colors::DARK_GRAY);
    config_ = cfg;
    num_output_bins_ = static_cast<int>(config_.nfft / 2 + 1);

    // Pre-calculate the scaling factor based on the selected policy.
    {
      IONO_NVTX_RANGE("Calculate Scaling Factor", profiling::colors::CYAN);
      switch (config_.scale_policy) {
        case StageConfig::ScalePolicy::ONE_OVER_N:
          scale_ = 1.0f / static_cast<float>(config_.nfft);
          break;
        case StageConfig::ScalePolicy::ONE_OVER_SQRT_N:
          scale_ = 1.0f / std::sqrt(static_cast<float>(config_.nfft));
          break;
        case StageConfig::ScalePolicy::NONE:
        default:
          scale_ = 1.0f;
          break;
      }
    }
    initialized_ = true;
  }

  void process(void* input, void* output, size_t num_elements,
               cudaStream_t stream) {
    const std::string range_name =
        profiling::format_stage_range("Magnitude", config_.batch, config_.nfft);
    IONO_NVTX_RANGE(range_name.c_str(), profiling::colors::PURPLE);
    if (!initialized_) {
      throw std::runtime_error("MagnitudeStage not initialized");
    }

    const float2* complex_input = static_cast<const float2*>(input);
    float* mag_output = static_cast<float*>(output);

    const int bins_per_frame = num_output_bins_;
    const int frames = static_cast<int>(config_.batch);

    if (frames <= 0) {
      throw std::runtime_error("MagnitudeStage: invalid batch size");
    }
    if (num_elements % static_cast<size_t>(frames) != 0) {
      throw std::runtime_error(
          "MagnitudeStage: num_elements not divisible by batch size");
    }

    const int inferred_stride =
        static_cast<int>(num_elements / static_cast<size_t>(frames));
    if (!(inferred_stride == bins_per_frame ||
          inferred_stride == static_cast<int>(config_.nfft))) {
      throw std::runtime_error("MagnitudeStage: unsupported input layout");
    }

    {
      IONO_NVTX_RANGE("Magnitude Kernel Launch", profiling::colors::PURPLE);
      kernels::launch_magnitude(complex_input, mag_output, bins_per_frame,
                                frames, inferred_stride, scale_, stream);
    }
  }

  size_t get_workspace_size() const { return 0; }

 private:
  StageConfig config_{};
  float scale_ = 1.0f;
  int num_output_bins_ = 0;
  bool initialized_ = false;
};

// --- Public MagnitudeStage methods forwarding to Impl ---
MagnitudeStage::MagnitudeStage() : pImpl(std::make_unique<Impl>()) {}
MagnitudeStage::~MagnitudeStage() = default;
void MagnitudeStage::initialize(const StageConfig& config,
                                cudaStream_t stream) {
  pImpl->initialize(config, stream);
}
void MagnitudeStage::process(void* input, void* output, size_t num_samples,
                             cudaStream_t stream) {
  pImpl->process(input, output, num_samples, stream);
}
size_t MagnitudeStage::get_workspace_size() const {
  return pImpl->get_workspace_size();
}

// ============================================================================
//  StageFactory Implementation
// ============================================================================

std::unique_ptr<IProcessingStage> StageFactory::create(StageType type) {
  IONO_NVTX_RANGE("StageFactory::Create", profiling::colors::DARK_GRAY);
  switch (type) {
    case StageType::WINDOW: {
      IONO_NVTX_MARK("Create WindowStage", profiling::colors::MAGENTA);
      return std::make_unique<WindowStage>();
    }
    case StageType::FFT: {
      IONO_NVTX_MARK("Create FFTStage", profiling::colors::MAGENTA);
      return std::make_unique<FFTStage>();
    }
    case StageType::MAGNITUDE: {
      IONO_NVTX_MARK("Create MagnitudeStage", profiling::colors::MAGENTA);
      return std::make_unique<MagnitudeStage>();
    }
    default: {
      throw std::invalid_argument(
          "Unknown stage type requested from StageFactory");
    }
  }
}

std::vector<std::unique_ptr<IProcessingStage>>
StageFactory::create_default_pipeline() {
  IONO_NVTX_RANGE("StageFactory::CreateDefaultPipeline",
                  profiling::colors::DARK_GRAY);
  std::vector<std::unique_ptr<IProcessingStage>> stages;
  stages.push_back(create(StageType::WINDOW));
  stages.push_back(create(StageType::FFT));
  stages.push_back(create(StageType::MAGNITUDE));
  IONO_NVTX_MARK("Default Pipeline Created", profiling::colors::MAGENTA);
  return stages;
}

// ============================================================================
//  Window Utility Functions Implementation
// ============================================================================

namespace window_utils {

window_functions::WindowKind to_window_kind(StageConfig::WindowType type) {
  switch (type) {
    case StageConfig::WindowType::RECTANGULAR:
      return window_functions::WindowKind::RECTANGULAR;
    case StageConfig::WindowType::HANN:
      return window_functions::WindowKind::HANN;
    case StageConfig::WindowType::BLACKMAN:
      return window_functions::WindowKind::BLACKMAN;
  }
  return window_functions::WindowKind::RECTANGULAR;
}

window_functions::WindowSymmetry to_window_symmetry(
    StageConfig::WindowSymmetry symmetry) {
  switch (symmetry) {
    case StageConfig::WindowSymmetry::PERIODIC:
      return window_functions::WindowSymmetry::PERIODIC;
    case StageConfig::WindowSymmetry::SYMMETRIC:
      return window_functions::WindowSymmetry::SYMMETRIC;
  }
  return window_functions::WindowSymmetry::PERIODIC;
}

void generate_window(float* window, int size, StageConfig::WindowType type,
                     bool sqrt_norm, StageConfig::WindowSymmetry symmetry) {
  IONO_NVTX_RANGE("Generate Window", profiling::colors::DARK_GRAY);
  const auto kind = to_window_kind(type);
  const auto sym = to_window_symmetry(symmetry);
  window_functions::fill_window(window, size, kind, sqrt_norm, sym);
}

void normalize_window(float* window, int size, StageConfig::WindowNorm norm) {
  IONO_NVTX_RANGE("Normalize Window", profiling::colors::DARK_GRAY);
  if (norm == StageConfig::WindowNorm::UNITY) {
    float sum = 0.0f;
    for (int i = 0; i < size; ++i) {
      sum += window[i];
    }
    if (sum > 1e-9f) {  // Avoid division by zero
      const float scale = static_cast<float>(size) / sum;
      for (int i = 0; i < size; ++i) {
        window[i] *= scale;
      }
    }
  }
  // SQRT normalization is applied during generation in generate_window.
}

}  // namespace window_utils
}  // namespace ionosense
