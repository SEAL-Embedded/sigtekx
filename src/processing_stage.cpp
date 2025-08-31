/**
 * @file processing_stage.cpp
 * @brief Implementation of processing stage components.
 */

#include "ionosense/processing_stage.hpp"

namespace ionosense {

// Forward declarations from ops_fft.cu
namespace ops {
    void magnitude_async(const cufftComplex* d_spec, float* d_mag, 
                        int bins, int batch, cudaStream_t stream);
}

// ============================================================================
// FftProcessingStage Implementation
// ============================================================================

void FftProcessingStage::configure(const ProcessingConfig& config) {
    config_ = config;
    validate_config();
}

void FftProcessingStage::validate_config() const {
    if (config_.nfft <= 0 || (config_.nfft & (config_.nfft - 1)) != 0) {
        throw cuda::ConfigurationError("FFT size must be a positive power of 2.");
    }
    if (config_.batch_size < 1) {
        throw cuda::ConfigurationError("Batch size must be at least 1.");
    }
}

void FftProcessingStage::initialize(const std::vector<cuda::Stream>& streams) {
    if (initialized_) return;

    const int nfft = config_.nfft;
    const int batch = config_.batch_size;
    const size_t bins = nfft / 2 + 1;
    const int num_streams = streams.size();

    // Create FFT plans
    plans_.resize(num_streams);
    size_t max_workspace_size = 0;
    
    for (int i = 0; i < num_streams; ++i) {
        plans_[i].create_1d_r2c(nfft, batch);
        size_t ws_size = plans_[i].get_work_size();
        if (ws_size > max_workspace_size) {
            max_workspace_size = ws_size;
        }
    }
    
    // Allocate workspaces
    if (max_workspace_size > 0) {
        d_workspaces_.resize(num_streams);
        for (int i = 0; i < num_streams; ++i) {
            d_workspaces_[i] = cuda::DeviceMemory<std::byte>(max_workspace_size);
            plans_[i].set_work_area(d_workspaces_[i].get());
            plans_[i].set_stream(streams[i].get());
        }
    } else {
        for (int i = 0; i < num_streams; ++i) {
            plans_[i].set_stream(streams[i].get());
        }
    }
    
    // Allocate spectrum buffers
    d_spectrums_.resize(num_streams);
    for (int i = 0; i < num_streams; ++i) {
        d_spectrums_[i] = cuda::DeviceMemory<cufftComplex>(bins * batch);
    }
    
    IONO_CUDA_CHECK(cudaDeviceSynchronize());
    initialized_ = true;
}

void FftProcessingStage::enqueue_work(const cuda::Stream& stream, int stream_idx,
                                      float* d_input, float* d_output) {
    if (!initialized_) {
        throw cuda::StateError("FFT stage not initialized before use.");
    }

    const auto& plan = plans_.at(stream_idx);
    auto& spectrum_buffer = d_spectrums_.at(stream_idx);
    const int bins = config_.nfft / 2 + 1;
    
    // Input is already windowed (done CPU-side)
    // Just do FFT and magnitude
    plan.execute_r2c(d_input, spectrum_buffer.get());
    ops::magnitude_async(spectrum_buffer.get(), d_output, bins, config_.batch_size, stream.get());
}

void FftProcessingStage::shutdown() {
    initialized_ = false;
    plans_.clear();
    d_workspaces_.clear();
    d_spectrums_.clear();
}

const char* FftProcessingStage::name() const {
    return "FFT";
}

// ============================================================================
// ProcessingStageFactory Implementation
// ============================================================================

std::unique_ptr<IProcessingStage> ProcessingStageFactory::create(const std::string& type_name) {
    if (type_name == "FFT" || type_name == "fft") {
        return std::make_unique<FftProcessingStage>();
    }
    throw cuda::ConfigurationError("Unknown processing stage type: " + type_name);
}

} // namespace ionosense