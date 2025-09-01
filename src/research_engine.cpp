#include "ionosense/research_engine.hpp"
#include "ionosense/processing_stage.hpp"
#include "ionosense/cuda_wrappers.hpp"

#include <chrono>
#include <algorithm>
#include <numeric>
#include <sstream>
#include <iomanip>
#include <stdexcept>

namespace ionosense {

// ============================================================================
// ResearchEngine Implementation (Pimpl)
// ============================================================================

class ResearchEngine::Impl {
public:
    Impl() {
        // Query and set device
        int device_count = 0;
        IONO_CUDA_CHECK(cudaGetDeviceCount(&device_count));
        if (device_count == 0) {
            throw std::runtime_error("No CUDA devices found");
        }

        // Select best device
        device_id_ = engine_utils::select_best_device();
        IONO_CUDA_CHECK(cudaSetDevice(device_id_));

        // Get device properties
        IONO_CUDA_CHECK(cudaGetDeviceProperties(&device_props_, device_id_));
    }

    ~Impl() { reset(); }

    void initialize(const EngineConfig& config) {
        if (initialized_) {
            reset();
        }

        config_ = config;

        // --- streams ---
        streams_.clear();
        const int need_streams = std::max(3, config.stream_count);
        for (int i = 0; i < need_streams; ++i) {
            streams_.emplace_back(); // default ctor makes a stream
        }

        // --- events: one pair per pinned buffer ---
        events_.clear();
        for (int i = 0; i < config.pinned_buffer_count * 2; ++i) {
            events_.emplace_back(cudaEventDisableTiming);
        }

        // --- stage config ---
        stage_config_.nfft            = config.nfft;
        stage_config_.batch           = config.batch;
        stage_config_.overlap         = config.overlap;
        stage_config_.sample_rate_hz  = config.sample_rate_hz;
        stage_config_.warmup_iters    = config.warmup_iters;

        // --- pipeline stages ---
        if (stages_.empty()) {
            stages_ = StageFactory::create_default_pipeline();
        }
        for (auto& stage : stages_) {
            stage->initialize(stage_config_, streams_[0].get());
        }

        // --- device buffers ---
        const size_t buffer_size        = static_cast<size_t>(config.nfft) * config.batch;
        const size_t output_buffer_size = static_cast<size_t>(config.num_output_bins()) * config.batch;
        const size_t complex_buffer_size = output_buffer_size; // Same number of elements as output, but they will be float2

        d_input_buffers_.clear();
        d_output_buffers_.clear();
        d_intermediate_buffers_.clear();

        for (int i = 0; i < config.pinned_buffer_count; ++i) {
            d_input_buffers_.emplace_back(buffer_size); 
            d_output_buffers_.emplace_back(output_buffer_size); 
            d_intermediate_buffers_.emplace_back(complex_buffer_size * 2); // *2 to hold float2 as floats
        }

        // --- pinned host buffers ---
        h_input_staging_.resize(buffer_size);
        h_output_staging_.resize(output_buffer_size);

        // mark initialized BEFORE warmup so process() won't throw
        initialized_ = true;

        // warmup (optional)
        if (config_.warmup_iters > 0) {
            run_warmup();
        }

        // reset public stats and mark as non-warmup now
        stats_ = ProcessingStats{};
        stats_.is_warmup = false;
    }

    void process(const float* input, float* output, size_t num_samples) {
        if (!initialized_) {
            throw std::runtime_error("Engine not initialized");
        }

        const auto start_time = std::chrono::high_resolution_clock::now();

        // --- Resource Selection ---
        const int buffer_idx = static_cast<int>(frame_counter_ % config_.pinned_buffer_count);
        auto& d_input        = d_input_buffers_[buffer_idx];
        auto& d_output       = d_output_buffers_[buffer_idx];
        auto& d_intermediate = d_intermediate_buffers_[buffer_idx];

        const int h2d_stream_idx     = 0;
        const int compute_stream_idx = (streams_.size() > 1) ? 1 : 0;
        const int d2h_stream_idx     = (streams_.size() > 2) ? 2 : compute_stream_idx;

        auto& e_h2d_done     = events_[buffer_idx * 2 + 0];
        auto& e_compute_done = events_[buffer_idx * 2 + 1];

        // --- Asynchronous Pipeline ---

        // 1. Host-to-Device Transfer
        d_input.copy_from_host(input, num_samples, streams_[h2d_stream_idx].get());
        e_h2d_done.record(streams_[h2d_stream_idx].get());

        // 2. Processing Pipeline (on compute stream)
        IONO_CUDA_CHECK(cudaStreamWaitEvent(streams_[compute_stream_idx].get(), e_h2d_done.get(), 0));

        // Stage 1: Window (In-Place)
        // Applies Hann window directly onto the d_input buffer.
        stages_[0]->process(d_input.get(), d_input.get(), num_samples, streams_[compute_stream_idx].get());

        // Stage 2: FFT (Real-to-Complex, Out-of-Place)
        // Reads windowed real data from d_input, writes complex spectrum to d_intermediate.
        stages_[1]->process(d_input.get(), d_intermediate.get(), num_samples, streams_[compute_stream_idx].get());

        // Stage 3: Magnitude (Complex-to-Real, Out-of-Place)
        // Reads complex spectrum from d_intermediate, writes float magnitudes to d_output.
        const size_t complex_elements = static_cast<size_t>(config_.num_output_bins()) * config_.batch;
        stages_[2]->process(d_intermediate.get(), d_output.get(), complex_elements, streams_[compute_stream_idx].get());

        e_compute_done.record(streams_[compute_stream_idx].get());

        // 3. Device-to-Host Transfer
        IONO_CUDA_CHECK(cudaStreamWaitEvent(streams_[d2h_stream_idx].get(), e_compute_done.get(), 0));
        d_output.copy_to_host(output, complex_elements, streams_[d2h_stream_idx].get());
        
        // 4. Final Synchronization
        IONO_CUDA_CHECK(cudaStreamSynchronize(streams_[d2h_stream_idx].get()));

        // --- Statistics ---
        const auto end_time    = std::chrono::high_resolution_clock::now();
        const auto duration    = std::chrono::duration<float, std::micro>(end_time - start_time);
        stats_.latency_us      = duration.count();
        stats_.frames_processed++;
        stats_.throughput_gbps = calculate_throughput(num_samples, stats_.latency_us);

        frame_counter_++;
    }

    void process_async(const float* input, size_t num_samples, ResultCallback callback) {
        if (!initialized_) {
            throw std::runtime_error("Engine not initialized");
        }
        std::vector<float> output(config_.num_output_bins() * config_.batch);
        process(input, output.data(), num_samples);
        if (callback) {
            callback(output.data(), config_.num_output_bins(), config_.batch, stats_);
        }
    }

    void synchronize() {
        for (auto& s : streams_) { s.synchronize(); }
    }

    void reset() {
        synchronize();
        stages_.clear();
        streams_.clear();
        events_.clear();
        d_input_buffers_.clear();
        d_intermediate_buffers_.clear();
        d_output_buffers_.clear();
        h_input_staging_  = PinnedHostBuffer<float>();
        h_output_staging_ = PinnedHostBuffer<float>();
        frame_counter_    = 0;
        initialized_      = false;
    }

    ProcessingStats get_stats() const { return stats_; }

    RuntimeInfo get_runtime_info() const {
        RuntimeInfo info;
        int cuda_runtime_version = 0, cuda_driver_version = 0;
        IONO_CUDA_CHECK(cudaRuntimeGetVersion(&cuda_runtime_version));
        IONO_CUDA_CHECK(cudaDriverGetVersion(&cuda_driver_version));
        info.cuda_runtime_version = cuda_runtime_version;
        info.cuda_driver_version  = cuda_driver_version;
        std::ostringstream v;
        v << (cuda_runtime_version / 1000) << "." << (cuda_runtime_version % 1000) / 10;
        info.cuda_version  = v.str();
        info.cufft_version = info.cuda_version;
        info.device_name   = device_props_.name;
        info.device_compute_capability_major = device_props_.major;
        info.device_compute_capability_minor = device_props_.minor;
        info.device_memory_total_mb          = device_props_.totalGlobalMem / (1024 * 1024);
        size_t free_mem = 0, total_mem = 0;
        IONO_CUDA_CHECK(cudaMemGetInfo(&free_mem, &total_mem));
        info.device_memory_free_mb = free_mem / (1024 * 1024);
        return info;
    }

    bool is_initialized() const { return initialized_; }

    void set_profiling_enabled(bool enabled) { profiling_enabled_ = enabled; }

    void add_stage(std::unique_ptr<IProcessingStage> stage) {
        if (initialized_) {
            throw std::runtime_error("Cannot add stages after initialization");
        }
        stages_.push_back(std::move(stage));
    }

    void clear_stages() {
        if (initialized_) {
            throw std::runtime_error("Cannot clear stages after initialization");
        }
        stages_.clear();
    }

    size_t num_stages() const { return stages_.size(); }

    void set_stage_config(const StageConfig& cfg) { stage_config_ = cfg; }
    StageConfig get_stage_config() const { return stage_config_; }

private:
    void run_warmup() {
        std::vector<float> dummy_input( static_cast<size_t>(config_.nfft) * config_.batch, 0.0f );
        std::vector<float> dummy_output(static_cast<size_t>(config_.num_output_bins()) * config_.batch);

        stats_.is_warmup = true;
        for (int i = 0; i < config_.warmup_iters; ++i) {
            process(dummy_input.data(), dummy_output.data(), dummy_input.size());
        }
        stats_.is_warmup = false;
    }

    float calculate_throughput(size_t num_samples, float latency_us) const {
        const size_t bytes = num_samples * sizeof(float) * 2; // input + output
        const float  secs  = latency_us * 1e-6f;
        return (bytes / (1024.0f * 1024.0f * 1024.0f)) / std::max(secs, 1e-9f);
    }

private:
    // Configuration
    EngineConfig config_{};
    StageConfig  stage_config_{};

    // Device properties
    int           device_id_ = 0;
    cudaDeviceProp device_props_{};

    // Pipeline
    std::vector<std::unique_ptr<IProcessingStage>> stages_;

    // CUDA resources
    std::vector<CudaStream> streams_;
    std::vector<CudaEvent>  events_;
    int h2d_stream_idx_      = 0;
    int compute_stream_idx_  = 0;
    int d2h_stream_idx_      = 0;

    // Per-slot device buffers
    std::vector<DeviceBuffer<float>> d_input_buffers_;        // time-domain floats
    std::vector<DeviceBuffer<float>> d_intermediate_buffers_; // complex (float2 payload as floats)
    std::vector<DeviceBuffer<float>> d_output_buffers_;       // magnitude floats

    // Pinned host buffers (not used directly in v1.0 pipeline, but kept for API parity)
    PinnedHostBuffer<float> h_input_staging_;
    PinnedHostBuffer<float> h_output_staging_;

    // State
    bool          initialized_ = false;
    bool          profiling_enabled_ = false;
    size_t        frame_counter_ = 0;
    ProcessingStats stats_{};
};

// ============================================================================
// ResearchEngine Public Interface
// ============================================================================

ResearchEngine::ResearchEngine() : pImpl(std::make_unique<Impl>()) {}
ResearchEngine::~ResearchEngine() = default;

ResearchEngine::ResearchEngine(ResearchEngine&&) noexcept = default;
ResearchEngine& ResearchEngine::operator=(ResearchEngine&&) noexcept = default;

void ResearchEngine::initialize(const EngineConfig& config) { pImpl->initialize(config); }
void ResearchEngine::process(const float* in, float* out, size_t n) { pImpl->process(in, out, n); }
void ResearchEngine::process_async(const float* in, size_t n, ResultCallback cb) { pImpl->process_async(in, n, cb); }
void ResearchEngine::synchronize() { pImpl->synchronize(); }
void ResearchEngine::reset() { pImpl->reset(); }
ProcessingStats ResearchEngine::get_stats() const { return pImpl->get_stats(); }
RuntimeInfo ResearchEngine::get_runtime_info() const { return pImpl->get_runtime_info(); }
bool ResearchEngine::is_initialized() const { return pImpl->is_initialized(); }
void ResearchEngine::set_profiling_enabled(bool enabled) { pImpl->set_profiling_enabled(enabled); }
void ResearchEngine::dump_profiling_data(const std::string&) { /* reserved for NVTX/Nsight */ }
void ResearchEngine::add_stage(std::unique_ptr<IProcessingStage> s) { pImpl->add_stage(std::move(s)); }
void ResearchEngine::clear_stages() { pImpl->clear_stages(); }
size_t ResearchEngine::num_stages() const { return pImpl->num_stages(); }
void ResearchEngine::set_stage_config(const StageConfig& c) { pImpl->set_stage_config(c); }
StageConfig ResearchEngine::get_stage_config() const { return pImpl->get_stage_config(); }

// ============================================================================
// Factory and Utility Functions
// ============================================================================

std::unique_ptr<IPipelineEngine> create_engine(const std::string& engine_type) {
    if (engine_type == "research") {
        return std::make_unique<ResearchEngine>();
    } else if (engine_type == "ife" || engine_type == "obe") {
        throw std::runtime_error("Engine type '" + engine_type + "' not implemented in v1.0");
    } else {
        throw std::invalid_argument("Unknown engine type: " + engine_type);
    }
}

namespace engine_utils {

std::vector<std::string> get_available_devices() {
    std::vector<std::string> devices;
    int device_count = 0;
    if (cudaGetDeviceCount(&device_count) == cudaSuccess) {
        for (int i = 0; i < device_count; ++i) {
            cudaDeviceProp prop{};
            if (cudaGetDeviceProperties(&prop, i) == cudaSuccess) {
                std::ostringstream oss;
                oss << "[" << i << "] " << prop.name << " (SM " << prop.major << "." << prop.minor << ")";
                devices.push_back(oss.str());
            }
        }
    }
    return devices;
}

int select_best_device() {
    int device_count = 0;
    IONO_CUDA_CHECK(cudaGetDeviceCount(&device_count));
    if (device_count == 0) {
        throw std::runtime_error("No CUDA devices found");
    }
    int best_device = 0;
    int best_sm = -1;
    for (int i = 0; i < device_count; ++i) {
        cudaDeviceProp prop{};
        IONO_CUDA_CHECK(cudaGetDeviceProperties(&prop, i));
        if (prop.multiProcessorCount > best_sm) {
            best_sm = prop.multiProcessorCount;
            best_device = i;
        }
    }
    return best_device;
}

bool validate_config(const EngineConfig& cfg, std::string& error_msg) {
    if (cfg.nfft <= 0 || (cfg.nfft & (cfg.nfft - 1)) != 0) {
        error_msg = "nfft must be a positive power of 2";
        return false;
    }
    if (cfg.batch <= 0) {
        error_msg = "batch must be positive";
        return false;
    }
    if (cfg.overlap < 0.0f || cfg.overlap >= 1.0f) {
        error_msg = "overlap must be in range [0, 1)";
        return false;
    }
    if (cfg.sample_rate_hz <= 0) {
        error_msg = "sample_rate_hz must be positive";
        return false;
    }
    if (cfg.stream_count <= 0) {
        error_msg = "stream_count must be positive";
        return false;
    }
    if (cfg.pinned_buffer_count < 2) {
        error_msg = "pinned_buffer_count must be at least 2 for double buffering";
        return false;
    }
    error_msg.clear();
    return true;
}

size_t estimate_memory_usage(const EngineConfig& cfg) {
    size_t total = 0;
    total += cfg.pinned_buffer_count * static_cast<size_t>(cfg.nfft) * cfg.batch * sizeof(float);                          // inputs
    total += cfg.pinned_buffer_count * static_cast<size_t>(cfg.num_output_bins()) * cfg.batch * sizeof(float);              // outputs
    total += cfg.pinned_buffer_count * static_cast<size_t>(cfg.nfft) * cfg.batch * sizeof(float) * 2;                      // complex scratch
    total += static_cast<size_t>(cfg.nfft) * sizeof(float);                                                                  // window
    total += static_cast<size_t>(cfg.nfft) * cfg.batch * sizeof(float) * 4;                                                  // cufft work est.
    return total;
}

} // namespace engine_utils

} // namespace ionosense
