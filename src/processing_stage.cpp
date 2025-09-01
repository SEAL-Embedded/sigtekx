// src/processing_stage.cpp
#include "ionosense/processing_stage.hpp"
#include "ionosense/cuda_wrappers.hpp"
#include <cmath>
#include <algorithm>
#include <cstring>

// External kernel launch functions from ops_fft.cu
namespace ionosense {
namespace kernels {
    extern void launch_apply_window(const float* input, float* output, const float* window,
                                   int nfft, int batch, int stride, cudaStream_t stream);

    extern void launch_real_to_complex(const float* input, float2* output,
                                       int nfft, int batch, int stride, cudaStream_t stream);

    extern void launch_window_and_convert(const float* input, float2* output, const float* window,
                                         int nfft, int batch, int stride, cudaStream_t stream);

    // Non-strided magnitude (6 args)
    extern void launch_magnitude(const float2* input, float* output,
                                 int num_bins, int batch,
                                 float scale, cudaStream_t stream);

    // Strided magnitude (7 args)
    extern void launch_magnitude(const float2* input, float* output,
                                int num_bins, int batch, int input_stride,
                                float scale, cudaStream_t stream);

    extern void launch_magnitude_squared(const float2* input, float* output,
                                        int num_bins, int batch,
                                        float scale, cudaStream_t stream);

    extern void generate_hann_window_cpu(float* window, int size, bool sqrt_norm);
} // namespace kernels
} // namespace ionosense

namespace ionosense {

// ============================================================================
// WindowStage Implementation
// ============================================================================

class WindowStage::Impl {
public:
    Impl() = default;
    
    void initialize(const StageConfig& config, cudaStream_t stream) {
        config_ = config;
        stream_ = stream;
        
        // Allocate and generate window on host
        std::vector<float> host_window(config.nfft);
        bool sqrt_norm = (config.window_norm == StageConfig::WindowNorm::SQRT);
        window_utils::generate_hann_window(host_window.data(), config.nfft, sqrt_norm);
        
        // Upload window to device (once)
        d_window_.resize(config.nfft);
        d_window_.copy_from_host(host_window.data(), config.nfft, stream);
        
        // Synchronize to ensure window is uploaded
        IONO_CUDA_CHECK(cudaStreamSynchronize(stream));
        
        initialized_ = true;
    }
    
    void process(void* input, void* output, size_t num_samples, cudaStream_t stream) {
        if (!initialized_) {
            throw std::runtime_error("WindowStage not initialized");
        }
        
        // Validate input size
        if (num_samples != static_cast<size_t>(config_.nfft * config_.batch)) {
            throw std::runtime_error("Invalid number of samples for window stage");
        }
        
        // Apply window function
        const float* input_ptr = static_cast<const float*>(input);
        float* output_ptr = static_cast<float*>(output);
        
        kernels::launch_apply_window(input_ptr, output_ptr, d_window_.get(),
                                    config_.nfft, config_.batch, config_.nfft, stream);
    }
    
    size_t get_workspace_size() const {
        return d_window_.bytes();
    }

private:
    StageConfig config_;
    cudaStream_t stream_ = nullptr;
    DeviceBuffer<float> d_window_;
    bool initialized_ = false;
};

WindowStage::WindowStage() : pImpl(std::make_unique<Impl>()) {}
WindowStage::~WindowStage() = default;

void WindowStage::initialize(const StageConfig& config, cudaStream_t stream) {
    pImpl->initialize(config, stream);
}

void WindowStage::process(void* input, void* output, size_t num_samples, cudaStream_t stream) {
    pImpl->process(input, output, num_samples, stream);
}

size_t WindowStage::get_workspace_size() const {
    return pImpl->get_workspace_size();
}

// ============================================================================
// FFTStage Implementation
// ============================================================================

class FFTStage::Impl {
public:
    Impl() = default;

    void initialize(const StageConfig& config, cudaStream_t stream) {
        config_ = config;
        stream_ = stream;

        // Setup cuFFT plan for C2C transform
        int n[] = {config.nfft};
        int inembed[] = {config.nfft};
        // Output of R2C is nfft/2 + 1 complex points
        int onembed[] = {config.nfft / 2 + 1};

        plan_.create_plan_many(
            1,              // rank
            n,              // dimensions
            inembed,        // input embed
            1,              // istride
            config.nfft,    // idist
            onembed,        // output embed
            1,              // ostride
            config.nfft/2+1,// odist (<<< CRITICAL)
            CUFFT_R2C,      // TYPE
            config.batch,   // batch size
            stream
        );

        initialized_ = true;
    }

    void process(void* input, void* output, size_t num_samples, cudaStream_t stream) {
        if (!initialized_) {
            throw std::runtime_error("FFTStage not initialized");
        }

        // Validate input size
        if (num_samples != static_cast<size_t>(config_.nfft * config_.batch)) {
            throw std::runtime_error("Invalid number of samples for FFT stage");
        }

        // The input is the real, windowed data.
        // The output is the complex spectrum.
        cufftReal* fft_real_input = static_cast<cufftReal*>(input);
        cufftComplex* fft_cplx_output = reinterpret_cast<cufftComplex*>(output);
        plan_.exec_r2c(fft_real_input, fft_cplx_output);
    }


    size_t get_workspace_size() const {
        return plan_.work_size();
    }

private:
    StageConfig           config_;
    cudaStream_t          stream_ = nullptr;
    CufftPlan             plan_;
    bool                  initialized_ = false;
};

FFTStage::FFTStage() : pImpl(std::make_unique<Impl>()) {}
FFTStage::~FFTStage() = default;

void FFTStage::initialize(const StageConfig& config, cudaStream_t stream) {
    pImpl->initialize(config, stream);
}

void FFTStage::process(void* input, void* output, size_t num_samples, cudaStream_t stream) {
    pImpl->process(input, output, num_samples, stream);
}

size_t FFTStage::get_workspace_size() const {
    return pImpl->get_workspace_size();
}

// ============================================================================
// MagnitudeStage Implementation
// ============================================================================

class MagnitudeStage::Impl {
public:
    Impl() = default;

    void initialize(const StageConfig& cfg, cudaStream_t /*stream*/) {
        config_ = cfg;
        num_output_bins_ = static_cast<int>(config_.nfft / 2 + 1);

        // scale_ selection (qualify the enum to match the header)
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

        initialized_ = true;
    }

    void process(void* input, void* output, size_t num_samples, cudaStream_t stream) {
        if (!initialized_) {
            throw std::runtime_error("MagnitudeStage not initialized");
        }

        const float2*  complex_input  = static_cast<const float2*>(input);
        float*         mag_output     = static_cast<float*>(output);

        const int  bins_per_frame  = num_output_bins_;    // nfft/2 + 1
        const int  frames          = static_cast<int>(config_.batch);

        // Accept either tight-packed [bins_per_frame] or full-FFT stride [nfft].
        // Compute stride directly from what we were given.
        if (frames <= 0) {
            throw std::runtime_error("MagnitudeStage: invalid batch");
        }
        if (num_samples % static_cast<size_t>(frames) != 0) {
            throw std::runtime_error("MagnitudeStage: num_samples not divisible by batch");
        }

        const int inferred_stride = static_cast<int>(num_samples / static_cast<size_t>(frames));
        // Valid cases:
        //  - inferred_stride == bins_per_frame  -> tight-packed (R2C-like)
        //  - inferred_stride == config_.nfft    -> full C2C, first bins_per_frame are valid
        if (!(inferred_stride == bins_per_frame || inferred_stride == static_cast<int>(config_.nfft))) {
            throw std::runtime_error("MagnitudeStage: unsupported layout (expected stride nfft or nfft/2+1)");
        }

        // Single unified call: read using 'inferred_stride', write densely.
        kernels::launch_magnitude(
            complex_input,
            mag_output,
            bins_per_frame,       // number of output bins (0..nfft/2)
            frames,               // number of frames
            inferred_stride,      // distance between frame starts in input
            scale_,               // scaling
            stream
        );
    }


    size_t get_workspace_size() const { return 0; }

private:
    StageConfig  config_{};
    float        scale_ = 1.0f;
    int          num_output_bins_ = 0;
    bool         initialized_ = false;
};


MagnitudeStage::MagnitudeStage() : pImpl(std::make_unique<Impl>()) {}
MagnitudeStage::~MagnitudeStage() = default;

void MagnitudeStage::initialize(const StageConfig& config, cudaStream_t stream) {
    pImpl->initialize(config, stream);
}

void MagnitudeStage::process(void* input, void* output, size_t num_samples, cudaStream_t stream) {
    pImpl->process(input, output, num_samples, stream);
}

size_t MagnitudeStage::get_workspace_size() const {
    return pImpl->get_workspace_size();
}

// ============================================================================
// StageFactory Implementation
// ============================================================================

std::unique_ptr<IProcessingStage> StageFactory::create(StageType type) {
    switch (type) {
        case StageType::WINDOW:
            return std::make_unique<WindowStage>();
        case StageType::FFT:
            return std::make_unique<FFTStage>();
        case StageType::MAGNITUDE:
            return std::make_unique<MagnitudeStage>();
        default:
            throw std::invalid_argument("Unknown stage type");
    }
}

std::vector<std::unique_ptr<IProcessingStage>> StageFactory::create_default_pipeline() {
    std::vector<std::unique_ptr<IProcessingStage>> stages;
    stages.push_back(create(StageType::WINDOW));
    stages.push_back(create(StageType::FFT));
    stages.push_back(create(StageType::MAGNITUDE));
    return stages;
}

// ============================================================================
// Window Utility Functions
// ============================================================================

namespace window_utils {

void generate_hann_window(float* window, int size, bool sqrt_norm) {
    const float pi = 3.14159265358979323846f;
    
    for (int i = 0; i < size; ++i) {
        float val = 0.5f * (1.0f - std::cos(2.0f * pi * i / (size - 1)));
        window[i] = sqrt_norm ? std::sqrt(val) : val;
    }
}

void normalize_window(float* window, int size, StageConfig::WindowNorm norm) {
    if (norm == StageConfig::WindowNorm::UNITY) {
        float sum = 0.0f;
        for (int i = 0; i < size; ++i) {
            sum += window[i];
        }
        if (sum > 0.0f) {
            const float scale = 1.0f / (sum / size);
            for (int i = 0; i < size; ++i) {
                window[i] *= scale;
            }
        }
    } else if (norm == StageConfig::WindowNorm::SQRT) {
        for (int i = 0; i < size; ++i) {
            window[i] = std::sqrt(window[i]);
        }
    }
}

}  // namespace window_utils

}  // namespace ionosense