/**
 * @file processing_stage.hpp
 * @version 1.0
 * @date 2025-09-01
 * @author [Kevin Rahsaz]
 *
 * @brief Defines the abstract interface and concrete implementations for stages
 * in the signal processing pipeline.
 *
 * This file specifies the IProcessingStage interface using the Strategy design
 * pattern, allowing for a flexible and extensible pipeline architecture. It
 * also provides the concrete stages for the v1.0 pipeline: Window, FFT, and
 * Magnitude. The design promotes modularity and testability, key tenets of
 * RSE/RE.
 */

#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

// Forward declare CUDA stream type to avoid including CUDA headers in C++ TUs
struct CUstream_st;
using cudaStream_t = CUstream_st*;

namespace ionosense {

/**
 * @struct StageConfig
 * @brief Configuration parameters for all processing stages.
 *
 * Consolidates settings for FFT, windowing, scaling, and execution logic
 * to ensure consistent configuration across the entire pipeline.
 */
struct StageConfig {
  // --- FFT Parameters ---
  int nfft = 1024;  ///< FFT size (number of points). Must be a power of 2.
  int channels = 2;    ///< Number of independent signal channels (renamed from batch in v0.9.4).
  float overlap =
      0.5f;  ///< Overlap factor between consecutive frames [0.0, 1.0).
  int sample_rate_hz = 48000;  ///< Sample rate of the input signal in Hz.

  // --- Windowing Parameters ---
  enum class WindowType {
    RECTANGULAR,  ///< No taper (rectangular window).
    HANN,         ///< Hann window (raised cosine).
    BLACKMAN      ///< Blackman window for higher sidelobe suppression.
  };  ///< Enumeration of supported window types.
  WindowType window_type = WindowType::HANN;  ///< The window function to apply.

  enum class WindowNorm {
    UNITY,  ///< Normalize to unity power/energy gain
    SQRT    ///< Apply square root normalization
  };  ///< Normalization type for the window.
  WindowNorm window_norm = WindowNorm::UNITY;  ///< The normalization scheme.

  /**
   * @enum WindowSymmetry
   * @brief Defines window endpoint behavior for different use cases.
   *
   * Window symmetry controls the denominator in window coefficient
   * calculations, affecting endpoint values and spectral characteristics:
   *
   * - **PERIODIC (N)**: For FFT-based spectral analysis (default)
   *   - Denominator: N (window size)
   *   - Endpoints: Non-zero (except at i=0)
   *   - Use case: Spectral analysis, STFT, ionosphere research
   *   - Example: Hann[i] = 0.5 * (1 - cos(2πi/N))
   *
   * - **SYMMETRIC (N-1)**: For time-domain signal analysis
   *   - Denominator: N-1
   *   - Endpoints: Exactly zero at both ends
   *   - Use case: FIR filter design, signal windowing
   *   - Example: Hann[i] = 0.5 * (1 - cos(2πi/(N-1)))
   *
   * **Default**: PERIODIC is appropriate for FFT processing where the window
   * is applied to periodic signals in the frequency domain.
   */
  enum class WindowSymmetry {
    PERIODIC,  ///< Periodic window (FFT processing, denominator N)
    SYMMETRIC  ///< Symmetric window (signal analysis, denominator N-1)
  };
  WindowSymmetry window_symmetry =
      WindowSymmetry::PERIODIC;  ///< Default to PERIODIC for FFT-based
                                 ///< ionosphere analysis.

  bool preload_window = true;  ///< If true, window coefficients are uploaded to
                               ///< GPU once at initialization.

  // --- Scaling Parameters ---
  enum class ScalePolicy {
    NONE,
    ONE_OVER_N,
    ONE_OVER_SQRT_N
  };  ///< FFT output scaling policies.
  ScalePolicy scale_policy =
      ScalePolicy::ONE_OVER_N;  ///< Scaling policy for the FFT output.

  // --- Output Parameters ---
  enum class OutputMode {
    MAGNITUDE,
    COMPLEX_PASSTHROUGH
  };  ///< Desired output format.
  OutputMode output_mode = OutputMode::MAGNITUDE;  ///< Output format.

  // --- Execution Parameters ---
  bool inplace = true;   ///< Hint for whether stages can operate in-place.
  int warmup_iters = 1;  ///< Number of warmup iterations during initialization.

  /**
   * @brief Calculates the hop size (number of samples between frames).
   * @return The hop size in samples.
   */
  int hop_size() const { return static_cast<int>(nfft * (1.0f - overlap)); }
};

/**
 * @struct ProcessingStats
 * @brief Holds performance metrics for a processing operation.
 */
struct ProcessingStats {
  float latency_us =
      0.0f;  ///< Total latency for the operation in microseconds.
  float throughput_gbps = 0.0f;  ///< Achieved throughput in GB/s.
  size_t frames_processed = 0;   ///< Cumulative count of processed frames.
  bool is_warmup =
      true;  ///< Flag indicating if the metric is from a warmup run.
};

/**
 * @struct RuntimeInfo
 * @brief Runtime device and platform information.
 */
struct RuntimeInfo {
  std::string device_name;       ///< CUDA device name
  std::string cuda_version;      ///< CUDA runtime version string
  int cuda_runtime_version = 0;  ///< CUDA runtime version (integer)
  int cuda_driver_version = 0;   ///< CUDA driver version (integer)
};

/**
 * @class IProcessingStage
 * @brief Abstract base class for a stage in the processing pipeline (Strategy
 * Pattern).
 *
 * Defines the common interface that all processing stages must implement,
 * ensuring interchangeability and a consistent pipeline structure.
 */
class IProcessingStage {
 public:
  virtual ~IProcessingStage() = default;

  /**
   * @brief Initializes the stage with a given configuration and CUDA stream.
   * @param config The configuration settings for the stage.
   * @param stream The CUDA stream to be used for initialization tasks.
   */
  virtual void initialize(const StageConfig& config, cudaStream_t stream) = 0;

  /**
   * @brief Processes data through this stage.
   * @param input Pointer to the input data on the device. Type is
   * stage-dependent.
   * @param output Pointer to the output data on the device.
   * @param num_elements The number of elements to process.
   * @param stream The CUDA stream to execute the processing on.
   */
  virtual void process(void* input, void* output, size_t num_elements,
                       cudaStream_t stream) = 0;

  /**
   * @brief Gets the name of the stage for identification.
   * @return A string containing the stage's name.
   */
  virtual std::string name() const = 0;

  /**
   * @brief Reports whether the stage supports in-place processing.
   * @return True if the stage can use the same buffer for input and output,
   * false otherwise.
   */
  virtual bool supports_inplace() const = 0;

  /**
   * @brief Gets the device memory size required by the stage for its workspace.
   * @return The required workspace size in bytes.
   */
  virtual size_t get_workspace_size() const = 0;
};

/**
 * @class WindowStage
 * @brief Applies a window function to the input signal.
 */
class WindowStage : public IProcessingStage {
 public:
  WindowStage();
  ~WindowStage();

  void initialize(const StageConfig& config, cudaStream_t stream) override;
  void process(void* input, void* output, size_t num_samples,
               cudaStream_t stream) override;
  std::string name() const override { return "WindowStage"; }
  bool supports_inplace() const override { return true; }
  size_t get_workspace_size() const override;

 private:
  class Impl;
  std::unique_ptr<Impl> pImpl;
};

/**
 * @class FFTStage
 * @brief Performs the Fast Fourier Transform using cuFFT.
 */
class FFTStage : public IProcessingStage {
 public:
  FFTStage();
  ~FFTStage();

  void initialize(const StageConfig& config, cudaStream_t stream) override;
  void process(void* input, void* output, size_t num_samples,
               cudaStream_t stream) override;
  std::string name() const override { return "FFTStage"; }
  bool supports_inplace() const override { return true; }
  size_t get_workspace_size() const override;

 private:
  class Impl;
  std::unique_ptr<Impl> pImpl;
};

/**
 * @class MagnitudeStage
 * @brief Computes the magnitude from the complex FFT output.
 */
class MagnitudeStage : public IProcessingStage {
 public:
  MagnitudeStage();
  ~MagnitudeStage();

  void initialize(const StageConfig& config, cudaStream_t stream) override;
  void process(void* input, void* output, size_t num_samples,
               cudaStream_t stream) override;
  std::string name() const override { return "MagnitudeStage"; }
  bool supports_inplace() const override { return false; }
  size_t get_workspace_size() const override;

 private:
  class Impl;
  std::unique_ptr<Impl> pImpl;
};

/**
 * @class StageFactory
 * @brief Factory for creating processing stage objects.
 *
 * Encapsulates the creation logic for different pipeline stages, promoting
 * loose coupling and simplifying pipeline construction.
 */
class StageFactory {
 public:
  /** @enum StageType Enumeration of available stage types. */
  enum class StageType { WINDOW, FFT, MAGNITUDE };

  /**
   * @brief Creates a single processing stage of a specified type.
   * @param type The type of stage to create.
   * @return A unique_ptr to the created IProcessingStage.
   */
  static std::unique_ptr<IProcessingStage> create(StageType type);

  /**
   * @brief Creates the default sequence of stages for the v1.0 pipeline.
   * @return A vector of unique_ptrs to the pipeline stages in order.
   */
  static std::vector<std::unique_ptr<IProcessingStage>>
  create_default_pipeline();
};

/**
 * @namespace window_utils
 * @brief Provides utility functions for generating window coefficients.
 */
namespace window_utils {
/**
 * @brief Generates window coefficients on the CPU.
 * @param[out] window Pointer to the host array to store coefficients.
 * @param size The size of the window (number of coefficients).
 * @param type The type of window to generate.
 * @param sqrt_norm If true, applies a square root normalization.
 * @param symmetry Window symmetry mode (see window_functions.hpp for detailed
 * documentation).
 */
void generate_window(float* window, int size, StageConfig::WindowType type,
                     bool sqrt_norm = false,
                     StageConfig::WindowSymmetry symmetry =
                         StageConfig::WindowSymmetry::PERIODIC);

/**
 * @brief Normalizes a window to have a specific property (e.g., unity gain).
 * @param[in,out] window Pointer to the window coefficients to normalize.
 * @param size The size of the window.
 * @param norm The normalization policy to apply.
 */
void normalize_window(float* window, int size, StageConfig::WindowNorm norm);
}  // namespace window_utils

}  // namespace ionosense
