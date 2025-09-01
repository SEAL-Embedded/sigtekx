// include/ionosense/research_engine.hpp
#pragma once

#include <memory>
#include <vector>
#include <string>
#include <functional>

namespace ionosense {

// Forward declarations
struct StageConfig;
struct ProcessingStats;
class IProcessingStage;

// Engine configuration
struct EngineConfig {
    // Signal parameters
    int nfft = 1024;
    int batch = 2;  // Dual channels
    float overlap = 0.5f;
    int sample_rate_hz = 48000;
    
    // Execution parameters
    int stream_count = 3;
    int pinned_buffer_count = 2;
    int warmup_iters = 1;
    int timeout_ms = 1000;
    
    // Performance tuning
    bool use_cuda_graphs = false;  // For future optimization
    bool enable_profiling = false;
    
    // Derived parameters
    int hop_size() const {
        return static_cast<int>(nfft * (1.0f - overlap));
    }
    
    int num_output_bins() const {
        return nfft / 2 + 1;  // For real FFT output
    }
};

// Runtime information about the engine
struct RuntimeInfo {
    std::string cuda_version;
    std::string cufft_version;
    std::string device_name;
    int device_compute_capability_major;
    int device_compute_capability_minor;
    size_t device_memory_total_mb;
    size_t device_memory_free_mb;
    int cuda_driver_version;
    int cuda_runtime_version;
};

// Callback for processing results
using ResultCallback = std::function<void(const float* magnitude, 
                                         size_t num_bins, 
                                         size_t batch_size,
                                         const ProcessingStats& stats)>;

// Abstract interface for pipeline engines
class IPipelineEngine {
public:
    virtual ~IPipelineEngine() = default;
    
    // Initialize the engine
    virtual void initialize(const EngineConfig& config) = 0;
    
    // Process a batch of input samples
    virtual void process(const float* input, float* output, size_t num_samples) = 0;
    
    // Async processing with callback
    virtual void process_async(const float* input, size_t num_samples,
                              ResultCallback callback) = 0;
    
    // Synchronize all pending operations
    virtual void synchronize() = 0;
    
    // Reset the engine state
    virtual void reset() = 0;
    
    // Get current statistics
    virtual ProcessingStats get_stats() const = 0;
    
    // Get runtime information
    virtual RuntimeInfo get_runtime_info() const = 0;
    
    // Check if engine is initialized
    virtual bool is_initialized() const = 0;
};

// Research Engine - main implementation for v1.0
class ResearchEngine : public IPipelineEngine {
public:
    ResearchEngine();
    ~ResearchEngine();
    
    // Disable copy, enable move
    ResearchEngine(const ResearchEngine&) = delete;
    ResearchEngine& operator=(const ResearchEngine&) = delete;
    ResearchEngine(ResearchEngine&&) noexcept;
    ResearchEngine& operator=(ResearchEngine&&) noexcept;
    
    // IPipelineEngine interface
    void initialize(const EngineConfig& config) override;
    void process(const float* input, float* output, size_t num_samples) override;
    void process_async(const float* input, size_t num_samples,
                       ResultCallback callback) override;
    void synchronize() override;
    void reset() override;
    ProcessingStats get_stats() const override;
    RuntimeInfo get_runtime_info() const override;
    bool is_initialized() const override;
    
    // Additional research-specific methods
    void set_profiling_enabled(bool enabled);
    void dump_profiling_data(const std::string& filename);
    
    // Stage management (for research flexibility)
    void add_stage(std::unique_ptr<IProcessingStage> stage);
    void clear_stages();
    size_t num_stages() const;
    
    // Advanced configuration
    void set_stage_config(const StageConfig& config);
    StageConfig get_stage_config() const;

private:
    // Pimpl idiom to hide CUDA/cuFFT details from public API
    class Impl;
    std::unique_ptr<Impl> pImpl;
};

// Factory function for creating engines
std::unique_ptr<IPipelineEngine> create_engine(const std::string& engine_type = "research");

// Utility functions
namespace engine_utils {
    // Query available GPU devices
    std::vector<std::string> get_available_devices();
    
    // Select best device based on compute capability
    int select_best_device();
    
    // Validate configuration
    bool validate_config(const EngineConfig& config, std::string& error_msg);
    
    // Estimate memory requirements
    size_t estimate_memory_usage(const EngineConfig& config);
}

}  // namespace ionosense