// include/ionosense/processing_stage.hpp
#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <vector>
#include <cuda_runtime_api.h>

// IMPORTANT: pull the real template BEFORE anyone uses DeviceBuffer<T>.
#include "ionosense/cuda_wrappers.hpp"

namespace ionosense {

// Configuration for processing stages
struct StageConfig {
    // FFT parameters
    int nfft = 1024;
    int batch = 2;  // Dual channels
    float overlap = 0.5f;
    int sample_rate_hz = 48000;
    
    // Window parameters
    enum class WindowType { HANN };
    WindowType window_type = WindowType::HANN;
    enum class WindowNorm { UNITY, SQRT };
    WindowNorm window_norm = WindowNorm::UNITY;
    bool preload_window = true;
    
    // Scaling parameters
    enum class ScalePolicy { NONE, ONE_OVER_N, ONE_OVER_SQRT_N };
    ScalePolicy scale_policy = ScalePolicy::NONE;
    
    // Output parameters
    enum class OutputMode { MAGNITUDE, COMPLEX_PASSTHROUGH };
    OutputMode output_mode = OutputMode::MAGNITUDE;
    
    // Execution parameters
    bool inplace = true;
    int warmup_iters = 1;
    
    // Derived parameters (computed)
    int hop_size() const {
        return static_cast<int>(nfft * (1.0f - overlap));
    }
};

// Processing statistics for monitoring
struct ProcessingStats {
    float latency_us = 0.0f;
    float throughput_gbps = 0.0f;
    size_t frames_processed = 0;
    bool is_warmup = true;
};

// Abstract base class for processing stages (Strategy pattern)
class IProcessingStage {
public:
    virtual ~IProcessingStage() = default;
    
    // Initialize the stage with configuration
    virtual void initialize(const StageConfig& config, cudaStream_t stream) = 0;
    
    // Process data through this stage
    virtual void process(void* input, void* output, size_t num_samples,
                        cudaStream_t stream) = 0;
    
    // Get stage name for debugging/profiling
    virtual std::string name() const = 0;
    
    // Check if stage can work in-place
    virtual bool supports_inplace() const = 0;
    
    // Get memory requirements
    virtual size_t get_workspace_size() const = 0;
};

// Window stage - applies window function to input signal
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

// FFT stage - performs cuFFT transform
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

// Magnitude stage - computes magnitude from complex FFT output
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

// Stage factory for creating processing stages
class StageFactory {
public:
    enum class StageType {
        WINDOW,
        FFT,
        MAGNITUDE
    };
    
    static std::unique_ptr<IProcessingStage> create(StageType type);
    
    // Create the default v1.0 pipeline stages
    static std::vector<std::unique_ptr<IProcessingStage>> create_default_pipeline();
};

// Utility functions for window generation
namespace window_utils {
    // Generate Hann window coefficients
    void generate_hann_window(float* window, int size, bool sqrt_norm = false);
    
    // Apply normalization to window
    void normalize_window(float* window, int size, StageConfig::WindowNorm norm);
}

}  // namespace ionosense