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

    // returns the stream index used (or -1 style sentinel as per .cpp)
    int  execute_async();
    void execute_async(int stream_idx);

    void sync_stream(int stream_idx);
    void synchronize_all();

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
    // Implementations in src/pipeline_engine.cpp (no inline bodies here)
    PipelineBuilder& with_streams(int n);
    PipelineBuilder& with_graphs(bool enabled);
    PipelineBuilder& with_profiling(bool enabled);

    PipelineBuilder& with_fft(int size, int batch);
    PipelineBuilder& with_stage(const std::string& type);
    PipelineBuilder& with_param(const std::string& key, float value);

    std::unique_ptr<PipelineEngine> build();

    // Access (used by legacy wrapper)
    const PipelineConfig& config() const { return config_; }

private:
    PipelineConfig  config_{};
    std::string     stage_type_{};
};

// ==== Legacy FFT wrapper API maintained for compatibility ====

struct RtFftConfig {
    int  nfft            = 0;
    int  batch           = 0;
    int  num_streams     = 1;
    bool enable_profiling= false;
    bool use_graphs      = false;
    bool verbose         = false;

    std::vector<float> window{}; // optional window

    // Implemented in src/pipeline_engine.cpp
    PipelineConfig to_pipeline_config() const;
};

class RtFftEngine {
public:
    // Implementations in src/pipeline_engine.cpp
    explicit RtFftEngine(const RtFftConfig& cfg);
    ~RtFftEngine();
    RtFftEngine(RtFftEngine&&) noexcept;
    RtFftEngine& operator=(RtFftEngine&&) noexcept;

    void prepare_for_execution();

    void execute_async(int stream_idx);
    void sync_stream(int stream_idx);
    void synchronize_all_streams();

    float* pinned_input(int stream_idx) const;
    float* pinned_output(int stream_idx) const;

    void  set_window(const float* h_window_data);

    void  set_use_graphs(bool enabled);
    bool  get_use_graphs() const;
    bool  graphs_ready() const;

    int   get_fft_size() const;
    int   get_batch_size() const;
    int   get_num_streams() const;

private:
    std::unique_ptr<PipelineEngine> engine_;
    RtFftConfig                     legacy_config_;
};

} // namespace ionosense