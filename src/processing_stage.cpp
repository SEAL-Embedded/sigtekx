/**
 * @file processing_stage.cpp
 * @brief Implementation of processing stage components.
 *
 * This file contains the implementation for the base processing stages.
 * For the FFT stage, it handles configuration, validation, and resource
 * initialization, but the core execution logic remains in pipeline_engine.cpp
 * to be close to the kernel launchers.
 */

#include "ionosense/processing_stage.hpp"

namespace ionosense {

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

void FftProcessingStage::initialize(const cuda::Stream& stream) {
    if (initialized_) return;

    const size_t bins = config_.nfft / 2 + 1;
    
    d_window_ = cuda::DeviceMemory<float>(config_.nfft);
    d_spectrum_ = cuda::DeviceMemory<cufftComplex>(bins * config_.batch_size);
    
    std::vector<float> default_window(config_.nfft, 1.0f);
    d_window_.copy_from_host(default_window.data(), stream.get());
    
    plan_.create_1d_r2c(config_.nfft, config_.batch_size);
    plan_.set_stream(stream.get());
    
    size_t workspace_size = plan_.get_work_size();
    if (workspace_size > 0) {
        d_workspace_ = cuda::DeviceMemory<std::byte>(workspace_size);
        plan_.set_work_area(d_workspace_.get());
    }
    
    initialized_ = true;
}

void FftProcessingStage::enqueue_work(const cuda::Stream& stream, const float* d_input, float* d_output) {
    if (!initialized_) {
        throw cuda::StateError("FFT stage not initialized before use.");
    }
    
    // The actual kernel calls are in pipeline_engine.cpp's Impl class
    // This design is a bit unusual but keeps kernel launch logic centralized.
    // A more classic Strategy pattern would have the kernels called from here.
    // For now, this method is a placeholder for the logic inside PipelineEngine::Impl::execute_traditional
}

void FftProcessingStage::shutdown() {
    // Resources are managed by RAII wrappers (cuda::DeviceMemory, etc.).
    // No explicit cleanup is needed here, but we fulfill the interface contract.
    initialized_ = false;
}


void FftProcessingStage::set_window(const std::vector<float>& window) {
    if (window.size() != static_cast<size_t>(config_.nfft)) {
        throw cuda::ConfigurationError("Window size must match FFT size.");
    }
    if (!initialized_) {
         throw cuda::StateError("Cannot set window before stage is initialized.");
    }
    d_window_.copy_from_host(window.data());
}


// ============================================================================
// ProcessingStageFactory Implementation
// ============================================================================

std::unique_ptr<IProcessingStage> ProcessingStageFactory::create(const std::string& type_name) {
    if (type_name == "FFT" || type_name == "fft") {
        return std::make_unique<FftProcessingStage>();
    }
    // Add other stages here in the future
    // else if (type_name == "FILTER") { ... }
    throw cuda::ConfigurationError("Unknown or unsupported processing stage type: " + type_name);
}

} // namespace ionosense