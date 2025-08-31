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
    void set_window(const float* h_window, size_t size);
    
    float* get_input_buffer(int idx) { return h_inputs_.at(idx).get(); }
    float* get_output_buffer(int idx) { return h_outputs_.at(idx).get(); }
    const PipelineConfig& config() const { return config_; }
    const PipelineStats& stats() const { return stats_; }
    void reset_stats() { stats_.reset(); }
    bool is_prepared() const { return prepared_; }
    void set_use_graphs(bool enable);
    const IProcessingStage* stage() const { return stage_.get(); }
    uint64_t get_total_executions() const { return stats_.total_executions; }

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
    
    // CPU-side window for applying to pinned memory
    std::vector<float> h_window_;
    bool has_window_ = false;
    
    void init_resources();
    void configure_memory_pool();
    void execute_traditional(int idx);
    void capture_graphs();
    void update_stats(float latency_ms);
    void apply_window_cpu(float* h_data, int stream_idx);
};

// ============================================================================
// PipelineEngine::Impl Implementation
// ============================================================================
PipelineEngine::Impl::Impl(const PipelineConfig& config, std::unique_ptr<IProcessingStage> stage)
    : config_(config), stage_(std::move(stage)), num_streams_(config.num_streams) {
    if (num_streams_ < 1 || num_streams_ > 16) {
        throw cuda::ConfigurationError("Number of streams must be between 1 and 16.");
    }
    init_resources();
}

PipelineEngine::Impl::~Impl() {
    try {
        synchronize_all();
    } catch (const std::exception& e) {
        std::cerr << "Error during pipeline destruction: " << e.what() << std::endl;
    }
}

void PipelineEngine::Impl::init_resources() {
    if (!stage_) {
        throw cuda::ConfigurationError("Processing stage is not set.");
    }
    stage_->configure(config_.stage_config);
    stage_->validate_config();

    for (int i = 0; i < num_streams_; ++i) {
        streams_.emplace_back();
        completion_events_.emplace_back();
        graphs_.emplace_back();
        if (config_.enable_profiling) {
            prof_start_.emplace_back(0);
            prof_end_.emplace_back(0);
        }
        h_inputs_.emplace_back(stage_->input_size());
        h_outputs_.emplace_back(stage_->output_size());
        d_inputs_.emplace_back(stage_->input_size());
        d_outputs_.emplace_back(stage_->output_size());
    }

    stage_->initialize(streams_);

    // Initialize default window (unity)
    const int nfft = config_.stage_config.nfft;
    h_window_.resize(nfft, 1.0f);
    has_window_ = true;

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

void PipelineEngine::Impl::set_window(const float* h_window, size_t size) {
    if (size != static_cast<size_t>(config_.stage_config.nfft)) {
        throw cuda::ConfigurationError("Window size must match FFT size.");
    }
    
    // Store window CPU-side for applying to pinned memory
    h_window_.assign(h_window, h_window + size);
    has_window_ = true;
    
    // Note: We do NOT upload window to GPU since windowing happens CPU-side
}

void PipelineEngine::Impl::apply_window_cpu(float* h_data, int stream_idx) {
    if (!has_window_) return;
    
    const int nfft = config_.stage_config.nfft;
    const int batch = config_.stage_config.batch_size;
    
    // Apply window to each batch element in pinned memory
    for (int b = 0; b < batch; ++b) {
        float* batch_ptr = h_data + b * nfft;
        for (int i = 0; i < nfft; ++i) {
            batch_ptr[i] *= h_window_[i];
        }
    }
}

void PipelineEngine::Impl::prepare() {
    if (prepared_) throw cuda::StateError("Pipeline already prepared.");
    
    // Warm-up runs
    for (int i = 0; i < num_streams_; ++i) {
        // Initialize with test data
        std::fill(h_inputs_[i].get(), h_inputs_[i].get() + stage_->input_size(), 1.0f);
        apply_window_cpu(h_inputs_[i].get(), i);
        
        d_inputs_[i].copy_from_host(h_inputs_[i].get(), streams_[i].get());
        execute_traditional(i);
        d_outputs_[i].copy_to_host(h_outputs_[i].get(), streams_[i].get());
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
    // Only FFT and magnitude - NO windowing (that happens CPU-side)
    stage_->enqueue_work(streams_[idx], idx, d_inputs_[idx].get(), d_outputs_[idx].get());
}

void PipelineEngine::Impl::capture_graphs() {
    IONO_CUDA_CHECK(cudaDeviceSynchronize());
    
    for (int i = 0; i < num_streams_; ++i) {
        // Capture only the FFT+magnitude operations
        graphs_[i].begin_capture(streams_[i].get(), cudaStreamCaptureModeGlobal);
        
        try {
            execute_traditional(i);  // Just FFT + magnitude
            graphs_[i].end_capture(streams_[i].get());
        } catch (...) {
            cudaGraph_t temp_graph = nullptr;
            cudaStreamEndCapture(streams_[i].get(), &temp_graph);
            if (temp_graph) cudaGraphDestroy(temp_graph);
            throw;
        }
        
        streams_[i].synchronize();
    }
    
    if (config_.verbose) {
        std::cout << "[Pipeline] Captured " << num_streams_ << " CUDA graphs." << std::endl;
    }
}

void PipelineEngine::Impl::execute_async(int stream_idx) {
    if (!prepared_) throw cuda::StateError("Pipeline not prepared. Call prepare() first.");
    if (stream_idx < 0 || stream_idx >= num_streams_) throw std::out_of_range("Invalid stream index.");
    
    stats_.total_executions++;
    
    // CRITICAL: Apply window CPU-side BEFORE copying to GPU
    // Assume data is already in h_inputs_[stream_idx]
    apply_window_cpu(h_inputs_[stream_idx].get(), stream_idx);
    
    // Copy windowed data to device
    d_inputs_[stream_idx].copy_from_host(h_inputs_[stream_idx].get(), streams_[stream_idx].get());
    
    if (config_.enable_profiling) {
        prof_start_[stream_idx].record(streams_[stream_idx]);
    }
    
    // Execute FFT+magnitude (via graph or traditional)
    if (config_.use_graphs && graphs_[stream_idx].is_instantiated()) {
        graphs_[stream_idx].launch(streams_[stream_idx]);
    } else {
        execute_traditional(stream_idx);
    }
    
    if (config_.enable_profiling) {
        prof_end_[stream_idx].record(streams_[stream_idx]);
    }
    
    // Copy results back
    d_outputs_[stream_idx].copy_to_host(h_outputs_[stream_idx].get(), streams_[stream_idx].get());
    
    completion_events_[stream_idx].record(streams_[stream_idx]);
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
        config_.use_graphs = true;
        capture_graphs();
    } else {
        config_.use_graphs = enable;
    }
}

void PipelineEngine::Impl::update_stats(float latency_ms) {
    double current_latency = static_cast<double>(latency_ms);
    stats_.min_latency_ms = std::min(stats_.min_latency_ms, current_latency);
    stats_.max_latency_ms = std::max(stats_.max_latency_ms, current_latency);
    double n = static_cast<double>(stats_.total_executions);
    if (n > 0) {
       stats_.avg_latency_ms = (stats_.avg_latency_ms * (n - 1) + current_latency) / n;
    }
}

// ... Public Method Implementations ...
PipelineEngine::PipelineEngine(const PipelineConfig& config, std::unique_ptr<IProcessingStage> stage) : impl_(std::make_unique<Impl>(config, std::move(stage))) {}
PipelineEngine::~PipelineEngine() = default;
PipelineEngine::PipelineEngine(PipelineEngine&&) noexcept = default;
PipelineEngine& PipelineEngine::operator=(PipelineEngine&&) noexcept = default;
void PipelineEngine::set_window(const float* h_window, size_t size) { impl_->set_window(h_window, size); }
void PipelineEngine::prepare() { impl_->prepare(); }
int PipelineEngine::execute_async() { int idx = impl_->config().num_streams > 0 ? impl_->get_total_executions() % impl_->config().num_streams : 0; impl_->execute_async(idx); return idx; }
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

std::unique_ptr<PipelineEngine> PipelineBuilder::build() {
    auto stage = ProcessingStageFactory::create(stage_type_);
    return std::make_unique<PipelineEngine>(config_, std::move(stage));
}
} // namespace ionosense