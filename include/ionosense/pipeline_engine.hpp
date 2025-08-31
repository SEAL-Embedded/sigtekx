#pragma once

#include <cstdint>
#include <chrono>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "ionosense/processing_stage.hpp"  // ProcessingConfig/IProcessingStage/FftProcessingStage

namespace ionosense {

struct PipelineConfig {
    int  num_streams       = 1;
    bool use_graphs        = false;
    bool enable_profiling  = false;
    bool verbose           = false;

    ProcessingConfig stage_config{};
};

struct PipelineStats {
    // Implementations in src/pipeline_engine.cpp
    void   reset();
    double throughput_per_sec() const;

    // Public fields (referenced from bindings/tests/engine)
    std::uint64_t total_executions = 0;
    double        avg_latency_ms   = 0.0;
    double        min_latency_ms   = 0.0;
    double        max_latency_ms   = 0.0;

    // used internally for rate calc
    std::chrono::steady_clock::time_point start_time{};
};

class PipelineEngine {
public:
    // Implemented in src/pipeline_engine.cpp
    PipelineEngine(const PipelineConfig& cfg, std::unique_ptr<IProcessingStage> stage);
    ~PipelineEngine();
    PipelineEngine(PipelineEngine&&) noexcept;
    PipelineEngine& operator=(PipelineEngine&&) noexcept;

    void prepare();

    // returns the stream index used
    int  execute_async();
    void execute_async(int stream_idx);

    void sync_stream(int stream_idx);
    void synchronize_all();

    void set_window(const float* h_window, size_t size);

    float* get_input_buffer(int stream_idx);
    const float* get_input_buffer(int stream_idx) const;

    float* get_output_buffer(int stream_idx);
    const float* get_output_buffer(int stream_idx) const;

    const PipelineStats&  stats() const;
    void                  reset_stats();

    bool                  is_prepared() const;
    const IProcessingStage* stage() const;
    const PipelineConfig&   config() const;

    void set_use_graphs(bool enabled);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

class PipelineBuilder {
public:
    PipelineBuilder& with_streams(int n) {
        config_.num_streams = n;
        return *this;
    }
    PipelineBuilder& with_graphs(bool enabled) {
        config_.use_graphs = enabled;
        return *this;
    }
    PipelineBuilder& with_profiling(bool enabled) {
        config_.enable_profiling = enabled;
        return *this;
    }
    PipelineBuilder& with_fft(int size, int batch) {
        config_.stage_config.nfft = size;
        config_.stage_config.batch_size = batch;
        stage_type_ = "FFT";
        return *this;
    }
    PipelineBuilder& with_stage(const std::string& type) {
        stage_type_ = type;
        return *this;
    }
    PipelineBuilder& with_param(const std::string& key, float value) {
        config_.stage_config.params[key] = value;
        return *this;
    }

    std::unique_ptr<PipelineEngine> build();

    const PipelineConfig& config() const { return config_; }

private:
    PipelineConfig  config_{};
    std::string     stage_type_{};
};
} // namespace ionosense
