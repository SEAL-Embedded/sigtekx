#pragma once

#include <cstddef>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "ionosense/cuda_wrappers.hpp"

namespace ionosense {

struct ProcessingConfig {
    int nfft        = 0;
    int batch_size  = 0;
    bool verbose    = false;
    std::unordered_map<std::string, float> params{};

    float get_param(const std::string& key, float default_val = 0.f) const {
        auto it = params.find(key);
        return (it == params.end()) ? default_val : it->second;
    }
};

class IProcessingStage {
public:
    virtual ~IProcessingStage() = default;
    virtual void initialize(const std::vector<cuda::Stream>& streams) = 0;
    virtual void enqueue_work(const cuda::Stream& stream, int stream_idx,
                              float* d_input, float* d_output) = 0;
    virtual void configure(const ProcessingConfig& cfg) = 0;
    virtual void validate_config() const = 0;
    virtual void shutdown() = 0;
    virtual const char* name() const = 0;
    virtual int input_size() const = 0;
    virtual int output_size() const = 0;
};

class FftProcessingStage final : public IProcessingStage {
public:
    FftProcessingStage() = default;
    ~FftProcessingStage() override = default;

    void initialize(const std::vector<cuda::Stream>& streams) override;
    void enqueue_work(const cuda::Stream& stream, int stream_idx,
                      float* d_input, float* d_output) override;

    void configure(const ProcessingConfig& cfg) override;
    void validate_config() const override;
    void shutdown() override;
    const char* name() const override;

    int input_size()  const override { return config_.nfft * config_.batch_size; }
    int output_size() const override { return (config_.nfft / 2 + 1) * config_.batch_size; }
    const ProcessingConfig& config() const { return config_; }

private:
    ProcessingConfig config_{};
    bool initialized_ = false;
    
    // Removed d_window_ - windowing happens CPU-side now
    std::vector<cuda::FftPlan> plans_;
    std::vector<cuda::DeviceMemory<std::byte>> d_workspaces_;
    std::vector<cuda::DeviceMemory<cufftComplex>> d_spectrums_;
};

struct ProcessingStageFactory {
    static std::unique_ptr<IProcessingStage> create(const std::string& type);
};

} // namespace ionosense