#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "ionosense/cuda_wrappers.hpp"  // cuda::Stream, cuda::DeviceMemory, cuda::FftPlan

namespace ionosense {

struct ProcessingConfig {
    int nfft        = 0;
    int batch_size  = 0;
    bool verbose    = false;
    std::unordered_map<std::string, float> params{};

    // Tiny helper kept inline; not implemented in .cpp
    float get_param(const std::string& key, float default_val = 0.f) const {
        auto it = params.find(key);
        return (it == params.end()) ? default_val : it->second;
    }
};

class IProcessingStage {
public:
    virtual ~IProcessingStage() = default;

    // lifecycle
    virtual void configure(const ProcessingConfig& cfg) = 0;
    virtual void validate_config() const = 0;
    virtual void initialize(const cuda::Stream& stream) = 0;
    virtual void enqueue_work(const cuda::Stream& stream,
                              const float* d_input,
                              float* d_output) = 0;
    virtual void shutdown() = 0;

    // sizes
    virtual int input_size() const = 0;
    virtual int output_size() const = 0;
};

class FftProcessingStage final : public IProcessingStage {
public:
    FftProcessingStage() = default;
    ~FftProcessingStage() override = default;

    // Implemented in src/processing_stage.cpp (no inline bodies here)
    void configure(const ProcessingConfig& cfg) override;
    void validate_config() const override;
    void initialize(const cuda::Stream& stream) override;
    void enqueue_work(const cuda::Stream& stream,
                      const float* d_input,
                      float* d_output) override;
    void shutdown() override;

    // Convenience; implemented in .cpp
    void set_window(const std::vector<float>& h_window);

    // Trivial, safe to inline
    int input_size()  const override { return config_.nfft * config_.batch_size; }
    int output_size() const override { return (config_.nfft / 2 + 1) * config_.batch_size; }

    const ProcessingConfig& config() const { return config_; }
    bool is_initialized() const { return initialized_; }

private:
    ProcessingConfig config_{};
    bool initialized_ = false;

    // GPU resources
    cuda::DeviceMemory<float>        d_window_{};
    cuda::DeviceMemory<cufftComplex> d_spectrum_{};
    cuda::DeviceMemory<std::byte>    d_workspace_{};
    cuda::FftPlan                    plan_{};
};

struct ProcessingStageFactory {
    // Implemented in src/processing_stage.cpp
    static std::unique_ptr<IProcessingStage> create(const std::string& type);
};

} // namespace ionosense