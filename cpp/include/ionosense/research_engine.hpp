/**
 * @file research_engine.hpp
 * @version 1.0
 * @date 2025-09-01
 * @author [Kevin Rahsaz]
 *
 * @brief Public API for the Ionosense High-Performance Computing (HPC) Research
 * Engine.
 *
 * This header defines the primary interface for the signal processing pipeline.
 * It follows the Pimpl (Pointer to Implementation) idiom to hide CUDA-specific
 * details, ensuring a clean public API and reducing compile-time dependencies.
 * The interfaces are designed according to RSE/RE principles for robustness
 * and ease of use in research and production environments.
 */

#pragma once

#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace ionosense {

// Forward declarations to minimize header dependencies, a key RSE practice.
struct StageConfig;
struct ProcessingStats;
class IProcessingStage;

/**
 * @struct EngineConfig
 * @brief Configuration structure for the entire processing engine.
 *
 * Encapsulates all tunable parameters for the pipeline, from signal
 * characteristics to performance and execution settings.
 */
struct EngineConfig {
  // --- Signal Parameters ---
  int nfft = 1024;       ///< FFT size (points). Must be a power of 2.
  int batch = 2;         ///< Number of signals processed in parallel (e.g.,
                         ///< dual-channel antenna).
  float overlap = 0.5f;  ///< Frame overlap factor [0.0, 1.0).
  int sample_rate_hz = 48000;  ///< Input signal sample rate in Hz.

  // --- Execution Parameters ---
  int stream_count = 3;  ///< Number of CUDA streams for concurrent execution.
  int pinned_buffer_count =
      2;  ///< Number of pinned host buffers (e.g., for double-buffering).
  int warmup_iters =
      1;  ///< Number of warmup iterations to stabilize GPU clocks.
  int timeout_ms =
      1000;  ///< Timeout for asynchronous operations (in milliseconds).

  // --- Performance Tuning ---
  bool use_cuda_graphs =
      false;  ///< If true, enables CUDA Graphs for low-overhead kernel
              ///< launches. (Future feature)
  bool enable_profiling =
      false;  ///< If true, enables internal performance metric collection.

  /**
   * @brief Computes the hop size (samples between frames) based on nfft and
   * overlap.
   * @return The hop size in samples.
   */
  int hop_size() const { return static_cast<int>(nfft * (1.0f - overlap)); }

  /**
   * @brief Computes the number of output bins for a real-to-complex FFT.
   * @return The number of frequency bins (nfft/2 + 1).
   */
  int num_output_bins() const { return nfft / 2 + 1; }
};

/**
 * @struct RuntimeInfo
 * @brief Contains information about the CUDA runtime environment and GPU
 * device.
 *
 * This structure is used to query and report the state of the hardware and
 * software environment, crucial for ensuring reproducibility (RE).
 */
struct RuntimeInfo {
  std::string cuda_version;   ///< CUDA Runtime version string.
  std::string cufft_version;  ///< cuFFT library version string.
  std::string
      device_name;  ///< Name of the GPU device (e.g., "NVIDIA RTX 4000 Ada").
  int device_compute_capability_major;  ///< Major compute capability of the
                                        ///< device.
  int device_compute_capability_minor;  ///< Minor compute capability of the
                                        ///< device.
  size_t device_memory_total_mb;  ///< Total global memory on the device in MB.
  size_t device_memory_free_mb;   ///< Free global memory on the device in MB.
  int cuda_driver_version;        ///< Installed NVIDIA driver version.
  int cuda_runtime_version;       ///< CUDA runtime version.
};

/**
 * @brief Callback function type for asynchronous processing results.
 * @param magnitude Pointer to the magnitude spectrum data on the host.
 * @param num_bins The number of bins in the spectrum.
 * @param batch_size The number of spectra in the batch.
 * @param stats Performance statistics for the operation.
 */
using ResultCallback =
    std::function<void(const float* magnitude, size_t num_bins,
                       size_t batch_size, const ProcessingStats& stats)>;

/**
 * @class IPipelineEngine
 * @brief Abstract interface for a generic signal processing pipeline engine.
 *
 * Defines a contract for engine implementations, allowing different engine
 * strategies (e.g., research vs. production) to be used interchangeably.
 */
class IPipelineEngine {
 public:
  virtual ~IPipelineEngine() = default;

  virtual void initialize(const EngineConfig& config) = 0;
  virtual void process(const float* input, float* output,
                       size_t num_samples) = 0;
  virtual void process_async(const float* input, size_t num_samples,
                             ResultCallback callback) = 0;
  virtual void synchronize() = 0;
  virtual void reset() = 0;
  virtual ProcessingStats get_stats() const = 0;
  virtual RuntimeInfo get_runtime_info() const = 0;
  virtual bool is_initialized() const = 0;
};

/**
 * @class ResearchEngine
 * @brief The primary concrete implementation of the IPipelineEngine for v1.0.
 *
 * This engine is designed for flexibility and introspection, making it suitable
 * for research and development. It uses a configurable pipeline of processing
 * stages.
 */
class ResearchEngine : public IPipelineEngine {
 public:
  ResearchEngine();
  ~ResearchEngine();

  // --- Rule of Five: Disable copy, enable move for proper resource management
  // ---
  ResearchEngine(const ResearchEngine&) = delete;
  ResearchEngine& operator=(const ResearchEngine&) = delete;
  ResearchEngine(ResearchEngine&&) noexcept;
  ResearchEngine& operator=(ResearchEngine&&) noexcept;

  // --- IPipelineEngine Interface Implementation ---
  void initialize(const EngineConfig& config) override;
  void process(const float* input, float* output, size_t num_samples) override;
  void process_async(const float* input, size_t num_samples,
                     ResultCallback callback) override;
  void synchronize() override;
  void reset() override;
  ProcessingStats get_stats() const override;
  RuntimeInfo get_runtime_info() const override;
  bool is_initialized() const override;

  // --- Research-Specific Methods ---
  void set_profiling_enabled(bool enabled);
  void dump_profiling_data(const std::string& filename);

  // --- Stage Management for Pipeline Customization ---
  void add_stage(std::unique_ptr<IProcessingStage> stage);
  void clear_stages();
  size_t num_stages() const;

  // --- Advanced Configuration ---
  void set_stage_config(const StageConfig& config);
  StageConfig get_stage_config() const;

 private:
  // Pimpl idiom hides implementation details (CUDA headers, etc.) from this
  // public header.
  class Impl;
  std::unique_ptr<Impl> pImpl;
};

/**
 * @brief Factory function to create different types of pipeline engines.
 * @param engine_type A string identifying the engine type (e.g., "research").
 * @return A unique_ptr to the created IPipelineEngine.
 */
std::unique_ptr<IPipelineEngine> create_engine(
    const std::string& engine_type = "research");

/**
 * @namespace engine_utils
 * @brief Provides utility functions related to the engine and CUDA environment.
 */
namespace engine_utils {
/**
 * @brief Queries and returns a list of available CUDA-capable devices.
 * @return A vector of strings, each describing an available device.
 */
std::vector<std::string> get_available_devices();

/**
 * @brief Selects the best available CUDA device based on a performance
 * heuristic.
 * @return The integer device ID of the best device.
 */
int select_best_device();

/**
 * @brief Validates an EngineConfig structure.
 * @param config The configuration to validate.
 * @param[out] error_msg A string to receive an error message if validation
 * fails.
 * @return True if the configuration is valid, false otherwise.
 */
bool validate_config(const EngineConfig& config, std::string& error_msg);

/**
 * @brief Estimates the GPU memory usage for a given configuration.
 * @param config The engine configuration.
 * @return An estimated memory usage in bytes.
 */
size_t estimate_memory_usage(const EngineConfig& config);
}  // namespace engine_utils

}  // namespace ionosense
