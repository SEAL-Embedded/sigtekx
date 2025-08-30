/**
 * @file pipeline_engine.cpp
 * @brief Implementation of the asynchronous pipeline engine.
 */

#include "ionosense/pipeline_engine.hpp"
#include <vector>
#include <algorithm>
#include <cstdio>
#include <iostream>
#include <limits>


namespace ionosense {

// Forward declarations for kernel launchers from ops_fft.cu
namespace ops {
    void apply_window_async(float* d_data, const float* d_window, 
                           int nfft, int batch, cudaStream_t stream);
    void magnitude_async(const cufftComplex* d_spec, float* d_mag, 
                        int bins, int batch, cudaStream_t stream);
}

// ============================================================================
// PipelineStats Implementation
// ============================================================================
void PipelineStats::reset() {
    total_executions = 0;
    avg_latency_ms = 0.0;
    min_latency_ms = std::numeric_limits<double>::max();
    max_latency_ms = 0.0;
    start_time = std::chrono::steady_clock::now();
}

double PipelineStats::throughput_per_sec() const {
    auto now = std::chrono::steady_clock::now();
    auto duration = std::chrono::duration<double>(now - start_time).count();
    return duration > 0 ? total_executions / duration : 0.0;
}

// ============================================================================
// PipelineEngine::Impl (PIMPL) Definition
// ============================================================================

struct PipelineEngine::Impl {
    Impl(const PipelineConfig& config, std::unique_ptr<IProcessingStage> stage);
    ~Impl();
    
    void prepare();
    void execute_async(int stream_idx);
    void sync_stream(int stream_idx);
    void synchronize_all();
    
    float* get_input_buffer(int idx) { return h_inputs_.at(idx).get(); }
    float* get_output_buffer(int idx) { return h_outputs_.at(idx).get(); }

    const PipelineConfig& config() const { return config_; }
    const PipelineStats& stats() const { return stats_; }
    void reset_stats() { stats_.reset(); }
    bool is_prepared() const { return prepared_; }
    void set_use_graphs(bool enable);
    const IProcessingStage* stage() const { return stage_.get(); }

private:
    PipelineConfig config_;
    std::unique_ptr<IProcessingStage> stage_;
    PipelineStats stats_;
    int num_streams_;
    bool prepared_ = false;
    
    std::vector<cuda::Stream> streams_;
    std::vector<cuda::Event> completion_events_;
    std::vector<cuda::Event> prof_start_;
    std::vector<cuda::Event> prof_end_;
    std::vector<cuda::Graph> graphs_;
    
    std::vector<cuda::PinnedMemory<float>> h_inputs_;
    std::vector<cuda::PinnedMemory<float>> h_outputs_;
    std::vector<cuda::DeviceMemory<float>> d_inputs_;
    std::vector<cuda::DeviceMemory<float>> d_outputs_;
    
    void init_resources();
    void configure_memory_pool();
    void execute_traditional(int idx);
    void capture_graphs();
    void update_stats(float latency_ms);
};

// ============================================================================
// PipelineEngine::Impl Implementation
// ============================================================================

PipelineEngine::Impl::Impl(const PipelineConfig& config, std::unique_ptr<IProcessingStage> stage)
    : config_(config), stage_(std::move(stage)), num_streams_(config.num_streams) {
    if (num_streams_ < 1 || num_streams_ > 16) { // Increased max streams
        throw cuda::ConfigurationError("Number of streams must be between 1 and 16.");
    }
    init_resources();
}

PipelineEngine::Impl::~Impl() {
    try {
        synchronize_all();
    } catch (const std::exception& e) {
        // Suppress exceptions in destructor
        std::cerr << "Error during pipeline destruction: " << e.what() << std::endl;
    }
}

void PipelineEngine::Impl::init_resources() {
    if (!stage_) {
        throw cuda::ConfigurationError("Processing stage is not set.");
    }
    stage_->configure(config_.stage_config);
    stage_->validate_config();

    const size_t input_size = stage_->input_size();
    const size_t output_size = stage_->output_size();

    for (int i = 0; i < num_streams_; ++i) {
        streams_.emplace_back();
        completion_events_.emplace_back();
        graphs_.emplace_back();

        if (config_.enable_profiling) {
            prof_start_.emplace_back(0); // Timing enabled event
            prof_end_.emplace_back(0);   // Timing enabled event
        }
        
        h_inputs_.emplace_back(input_size);
        h_outputs_.emplace_back(output_size);
        d_inputs_.emplace_back(input_size);
        d_outputs_.emplace_back(output_size);

        stage_->initialize(streams_[i]);
    }

    if (config_.use_graphs) {
        configure_memory_pool();
    }
}

void PipelineEngine::Impl::configure_memory_pool() {
    cudaMemPool_t mempool;
    IONO_CUDA_CHECK(cudaDeviceGetDefaultMemPool(&mempool, 0));
    uint64_t threshold = UINT64_MAX;
    IONO_CUDA_CHECK(cudaMemPoolSetAttribute(mempool, cudaMemPoolAttrReleaseThreshold, &threshold));
}

void PipelineEngine::Impl::prepare() {
    if (prepared_) {
        throw cuda::StateError("Pipeline already prepared.");
    }
    
    for (int i = 0; i < num_streams_; ++i) {
        execute_traditional(i);
        streams_[i].synchronize();
    }
    
    if (config_.use_graphs) {
        capture_graphs();
    }
    
    prepared_ = true;
    stats_.reset();

    if (config_.verbose) {
        std::cout << "[Pipeline] Prepared with " << num_streams_ 
                  << " streams, graphs=" << (config_.use_graphs ? "enabled" : "disabled") 
                  << std::endl;
    }
}

void PipelineEngine::Impl::execute_traditional(int idx) {
    const auto& stream = streams_[idx];
    
    d_inputs_[idx].copy_from_host(h_inputs_[idx].get(), stream.get());
    stage_->enqueue_work(stream, d_inputs_[idx].get(), d_outputs_[idx].get());
    d_outputs_[idx].copy_to_host(h_outputs_[idx].get(), stream.get());
}

void PipelineEngine::Impl::capture_graphs() {
    for (int i = 0; i < num_streams_; ++i) {
        graphs_[i].begin_capture(streams_[i].get());
        execute_traditional(i);
        graphs_[i].end_capture(streams_[i].get());
    }
    if (config_.verbose) {
        std::cout << "[Pipeline] Captured " << num_streams_ << " CUDA graphs." << std::endl;
    }
}

void PipelineEngine::Impl::execute_async(int stream_idx) {
    if (!prepared_) throw cuda::StateError("Pipeline not prepared. Call prepare() first.");
    if (stream_idx < 0 || stream_idx >= num_streams_) throw std::out_of_range("Invalid stream index.");
    
    if (config_.enable_profiling) {
        prof_start_[stream_idx].record(streams_[stream_idx]);
    }
    
    if (config_.use_graphs && graphs_[stream_idx].is_instantiated()) {
        graphs_[stream_idx].launch(streams_[stream_idx]);
    } else {
        execute_traditional(stream_idx);
    }
    
    completion_events_[stream_idx].record(streams_[stream_idx]);
    
    if (config_.enable_profiling) {
        prof_end_[stream_idx].record(streams_[stream_idx]);
    }
}

void PipelineEngine::Impl::sync_stream(int stream_idx) {
    if (stream_idx < 0 || stream_idx >= num_streams_) throw std::out_of_range("Invalid stream index.");
    completion_events_[stream_idx].synchronize();
    
    if (config_.enable_profiling && prepared_) {
        update_stats(prof_end_[stream_idx].elapsed_time(prof_start_[stream_idx]));
    }
}

void PipelineEngine::Impl::synchronize_all() {
    for (int i = 0; i < num_streams_; ++i) {
        streams_[i].synchronize();
    }
}

void PipelineEngine::Impl::set_use_graphs(bool enable) {
    if (prepared_ && enable && !config_.use_graphs) {
        // Transitioning from non-graph to graph mode after preparation
        config_.use_graphs = true;
        capture_graphs();
    } else {
        config_.use_graphs = enable;
    }
}

void PipelineEngine::Impl::update_stats(float latency_ms) {
    stats_.total_executions++;
    double current_latency = static_cast<double>(latency_ms);
    stats_.min_latency_ms = std::min(stats_.min_latency_ms, current_latency);
    stats_.max_latency_ms = std::max(stats_.max_latency_ms, current_latency);
    double n = static_cast<double>(stats_.total_executions);
    stats_.avg_latency_ms = (stats_.avg_latency_ms * (n - 1) + current_latency) / n;
}

// ============================================================================
// PipelineEngine Public Method Implementations
// ============================================================================

PipelineEngine::PipelineEngine(const PipelineConfig& config, std::unique_ptr<IProcessingStage> stage)
    : impl_(std::make_unique<Impl>(config, std::move(stage))) {}

PipelineEngine::~PipelineEngine() = default;
PipelineEngine::PipelineEngine(PipelineEngine&&) noexcept = default;
PipelineEngine& PipelineEngine::operator=(PipelineEngine&&) noexcept = default;

void PipelineEngine::prepare() { impl_->prepare(); }
int PipelineEngine::execute_async() {
    int idx = impl_->config().num_streams > 0 ? impl_->stats().total_executions % impl_->config().num_streams : 0;
    impl_->execute_async(idx);
    return idx;
}
void PipelineEngine::execute_async(int stream_idx) { impl_->execute_async(stream_idx); }
void PipelineEngine::sync_stream(int stream_idx) { impl_->sync_stream(stream_idx); }
void PipelineEngine::synchronize_all() { impl_->synchronize_all(); }
float* PipelineEngine::get_input_buffer(int stream_idx) { return impl_->get_input_buffer(stream_idx); }
const float* PipelineEngine::get_input_buffer(int stream_idx) const { return impl_->get_input_buffer(stream_idx); }
float* PipelineEngine::get_output_buffer(int stream_idx) { return impl_->get_output_buffer(stream_idx); }
const float* PipelineEngine::get_output_buffer(int stream_idx) const { return impl_->get_output_buffer(stream_idx); }
const PipelineStats& PipelineEngine::stats() const { return impl_->stats(); }
void PipelineEngine::reset_stats() { impl_->reset_stats(); }
bool PipelineEngine::is_prepared() const { return impl_->is_prepared(); }
const IProcessingStage* PipelineEngine::stage() const { return impl_->stage(); }
const PipelineConfig& PipelineEngine::config() const { return impl_->config(); }
void PipelineEngine::set_use_graphs(bool enable) { impl_->set_use_graphs(enable); }


// ============================================================================
// PipelineBuilder Implementation
// ============================================================================

PipelineBuilder& PipelineBuilder::with_streams(int num) {
    config_.num_streams = num;
    return *this;
}
PipelineBuilder& PipelineBuilder::with_graphs(bool enable) {
    config_.use_graphs = enable;
    return *this;
}
PipelineBuilder& PipelineBuilder::with_profiling(bool enable) {
    config_.enable_profiling = enable;
    return *this;
}
PipelineBuilder& PipelineBuilder::with_fft(int size, int batch) {
    config_.stage_config.nfft = size;
    config_.stage_config.batch_size = batch;
    stage_type_ = "FFT";
    return *this;
}
PipelineBuilder& PipelineBuilder::with_stage(const std::string& type) {
    stage_type_ = type;
    return *this;
}
PipelineBuilder& PipelineBuilder::with_param(const std::string& key, float value) {
    config_.stage_config.params[key] = value;
    return *this;
}
std::unique_ptr<PipelineEngine> PipelineBuilder::build() {
    auto stage = ProcessingStageFactory::create(stage_type_);
    return std::make_unique<PipelineEngine>(config_, std::move(stage));
}

// ============================================================================
// Legacy Compatibility Layer
// ============================================================================

PipelineConfig RtFftConfig::to_pipeline_config() const {
    PipelineConfig cfg;
    cfg.num_streams = num_streams;
    cfg.use_graphs = use_graphs;
    cfg.verbose = verbose;
    cfg.stage_config.nfft = nfft;
    cfg.stage_config.batch_size = batch;
    cfg.stage_config.verbose = verbose;
    return cfg;
}

RtFftEngine::RtFftEngine(const RtFftConfig& config) 
    : legacy_config_(config) {
    engine_ = PipelineBuilder()
        .with_fft(config.nfft, config.batch)
        .with_streams(config.num_streams)
        .with_graphs(config.use_graphs)
        .build();
}

RtFftEngine::~RtFftEngine() = default;
RtFftEngine::RtFftEngine(RtFftEngine&&) noexcept = default;
RtFftEngine& RtFftEngine::operator=(RtFftEngine&&) noexcept = default;

void RtFftEngine::prepare_for_execution() { engine_->prepare(); }
void RtFftEngine::execute_async(int stream_idx) { engine_->execute_async(stream_idx); }
void RtFftEngine::sync_stream(int stream_idx) { engine_->sync_stream(stream_idx); }
void RtFftEngine::synchronize_all_streams() { engine_->synchronize_all(); }
float* RtFftEngine::pinned_input(int idx) const { return engine_->get_input_buffer(idx); }
float* RtFftEngine::pinned_output(int idx) const { return engine_->get_output_buffer(idx); }

void RtFftEngine::set_window(const float* h_window_data) {
    auto* stage = dynamic_cast<FftProcessingStage*>(const_cast<IProcessingStage*>(engine_->stage()));
    if (stage) {
        std::vector<float> window(h_window_data, h_window_data + legacy_config_.nfft);
        stage->set_window(window);
    }
}

void RtFftEngine::set_use_graphs(bool enable) { engine_->set_use_graphs(enable); }
bool RtFftEngine::get_use_graphs() const { return engine_->config().use_graphs; }
bool RtFftEngine::graphs_ready() const { return engine_->is_prepared(); }
int RtFftEngine::get_fft_size() const { return legacy_config_.nfft; }
int RtFftEngine::get_batch_size() const { return legacy_config_.batch; }
int RtFftEngine::get_num_streams() const { return engine_->config().num_streams; }

} // namespace ionosense