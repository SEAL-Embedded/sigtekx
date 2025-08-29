/**
 * @file fft_engine.cpp
 * @brief Host-side orchestration for the ionosense FFT engine.
 *
 * This file contains all C++ host logic including stream management,
 * cuFFT plan lifecycle, memory management, and CUDA Graph orchestration.
 * Kernels are launched via thin wrappers defined in ops_fft.cu.
 */

#include "ionosense/fft_engine.hpp"
#include <cuda_runtime.h>
#include <cufft.h>
#include <vector>
#include <stdexcept>
#include <cstdio>
#include <cstdint>

// Forward declarations for kernel launchers in ops_fft.cu
namespace ionosense::ops {
    void apply_window_async(float* d_data, const float* d_window, int nfft, int batch, cudaStream_t stream);
    void magnitude_async(const cufftComplex* d_spec, float* d_mag, int bins, int batch, cudaStream_t stream);
}

// Error checking macros for robust CUDA API calls.
#define CUDA_CHECK(err) do { \
    cudaError_t e = (err); \
    if (e != cudaSuccess) { \
        fprintf(stderr, "CUDA Error in %s at line %d: %s\n", __FILE__, __LINE__, cudaGetErrorString(e)); \
        throw std::runtime_error(cudaGetErrorString(e)); \
    } \
} while(0)

#define CUFFT_CHECK(err) do { \
    cufftResult e = (err); \
    if (e != CUFFT_SUCCESS) { \
        fprintf(stderr, "cuFFT Error in %s at line %d: cuFFT Error\n", __FILE__, __LINE__); \
        throw std::runtime_error("cuFFT error"); \
    } \
} while(0)

namespace ionosense {

// PIMPL struct containing all private implementation details and CUDA resources.
struct RtFftEngine::Pimpl {
    static constexpr int kNumStreams = 3;

    RtFftConfig config_;
    bool use_graphs_;
    bool graphs_captured_{false};
    bool enable_profiling_{false};

    cudaStream_t streams_[kNumStreams]{};
    cudaEvent_t events_[kNumStreams]{};
    cufftHandle plans_[kNumStreams]{};
    cudaGraph_t graphs_[kNumStreams]{};
    cudaGraphExec_t graph_execs_[kNumStreams]{};
    cudaEvent_t prof_start_[kNumStreams]{};
    cudaEvent_t prof_end_[kNumStreams]{};
    float* h_inputs_[kNumStreams]{};
    float* h_outputs_[kNumStreams]{};
    cufftReal* d_inputs_[kNumStreams]{};
    cufftComplex* d_specs_[kNumStreams]{};
    float* d_mags_[kNumStreams]{};
    float* d_window_[kNumStreams]{};
    void* cufft_workspaces_[kNumStreams]{};
    size_t cufft_workspace_size_{0};

    explicit Pimpl(const RtFftConfig& config)
        : config_(config), use_graphs_(config.use_graphs) {
        init_resources();
        if (config_.verbose) {
            printf("[RtFftEngine] Initialized with NFFT=%d, Batch=%d, Graphs=%s\n",
                config_.nfft, config_.batch, use_graphs_ ? "ENABLED" : "DISABLED");
        }
    }

    ~Pimpl() {
        cleanup();
    }

    void init_resources();
    void cleanup();
    void setup_cufft_for_graphs(int idx);
    void execute_pipeline_operations(int idx);
    void capture_graph(int idx);
    void execute_async_traditional(int idx);
    void execute_async_graph(int idx);
    void init_default_window(float* d_window, int nfft, cudaStream_t stream);
};

// --- Pimpl Method Implementations ---

void RtFftEngine::Pimpl::init_resources() {
    const size_t in_bytes = sizeof(float) * config_.nfft * config_.batch;
    const size_t bins = (config_.nfft / 2 + 1);
    const size_t out_bytes = sizeof(float) * bins * config_.batch;
    const size_t spec_bytes = sizeof(cufftComplex) * bins * config_.batch;

    if (use_graphs_) {
        cudaMemPool_t mempool;
        CUDA_CHECK(cudaDeviceGetDefaultMemPool(&mempool, 0));
        uint64_t threshold = UINT64_MAX;
        CUDA_CHECK(cudaMemPoolSetAttribute(mempool, cudaMemPoolAttrReleaseThreshold, &threshold));
    }

    for (int i = 0; i < kNumStreams; ++i) {
        CUDA_CHECK(cudaStreamCreate(&streams_[i]));
        CUDA_CHECK(cudaEventCreateWithFlags(&events_[i], cudaEventDisableTiming));
        if (enable_profiling_) {
            CUDA_CHECK(cudaEventCreate(&prof_start_[i]));
            CUDA_CHECK(cudaEventCreate(&prof_end_[i]));
        }

        CUDA_CHECK(cudaHostAlloc(&h_inputs_[i], in_bytes, cudaHostAllocDefault));
        CUDA_CHECK(cudaHostAlloc(&h_outputs_[i], out_bytes, cudaHostAllocDefault));

        CUDA_CHECK(cudaMalloc(&d_inputs_[i], in_bytes));
        CUDA_CHECK(cudaMalloc(&d_specs_[i], spec_bytes));
        CUDA_CHECK(cudaMalloc(&d_mags_[i], out_bytes));
        CUDA_CHECK(cudaMalloc(&d_window_[i], sizeof(float) * config_.nfft));
        init_default_window(d_window_[i], config_.nfft, streams_[i]);

        CUFFT_CHECK(cufftCreate(&plans_[i]));
        const int rank = 1;
        int n[] = { config_.nfft };
        int istride = 1, ostride = 1;
        int idist = config_.nfft, odist = bins;
        CUFFT_CHECK(cufftPlanMany(&plans_[i], rank, n, nullptr, istride, idist, nullptr, ostride, odist, CUFFT_R2C, config_.batch));
        CUFFT_CHECK(cufftSetStream(plans_[i], streams_[i]));

        if (use_graphs_) {
            setup_cufft_for_graphs(i);
        }
    }
}

void RtFftEngine::Pimpl::setup_cufft_for_graphs(int idx) {
    size_t workspace_size;
    CUFFT_CHECK(cufftGetSize(plans_[idx], &workspace_size));
    if (workspace_size > cufft_workspace_size_) {
        cufft_workspace_size_ = workspace_size;
    }
    if (workspace_size > 0) {
        CUDA_CHECK(cudaMalloc(&cufft_workspaces_[idx], workspace_size));
        CUFFT_CHECK(cufftSetAutoAllocation(plans_[idx], 0));
        CUFFT_CHECK(cufftSetWorkArea(plans_[idx], cufft_workspaces_[idx]));
    }
}

void RtFftEngine::Pimpl::cleanup() {
    for (int i = 0; i < kNumStreams; ++i) {
        if (streams_[i]) { cudaStreamSynchronize(streams_[i]); }
    }
    for (int i = 0; i < kNumStreams; ++i) {
        if (graph_execs_[i]) { cudaGraphExecDestroy(graph_execs_[i]); }
        if (graphs_[i]) { cudaGraphDestroy(graphs_[i]); }
    }
    for (int i = 0; i < kNumStreams; ++i) {
        if (events_[i]) { CUDA_CHECK(cudaEventDestroy(events_[i])); }
        if (prof_start_[i]) { CUDA_CHECK(cudaEventDestroy(prof_start_[i])); }
        if (prof_end_[i]) { CUDA_CHECK(cudaEventDestroy(prof_end_[i])); }
        if (streams_[i]) { CUDA_CHECK(cudaStreamDestroy(streams_[i])); }
        if (plans_[i]) { CUFFT_CHECK(cufftDestroy(plans_[i])); }
        if (h_inputs_[i]) { CUDA_CHECK(cudaFreeHost(h_inputs_[i])); }
        if (h_outputs_[i]) { CUDA_CHECK(cudaFreeHost(h_outputs_[i])); }
        if (d_inputs_[i]) { CUDA_CHECK(cudaFree(d_inputs_[i])); }
        if (d_specs_[i]) { CUDA_CHECK(cudaFree(d_specs_[i])); }
        if (d_mags_[i]) { CUDA_CHECK(cudaFree(d_mags_[i])); }
        if (d_window_[i]) { CUDA_CHECK(cudaFree(d_window_[i])); }
        if (cufft_workspaces_[i]) { CUDA_CHECK(cudaFree(cufft_workspaces_[i])); }
    }
}

void RtFftEngine::Pimpl::init_default_window(float* d_window, int nfft, cudaStream_t stream) {
    std::vector<float> h_window(nfft, 1.0f);
    CUDA_CHECK(cudaMemcpyAsync(d_window, h_window.data(), sizeof(float) * nfft, cudaMemcpyHostToDevice, stream));
    CUDA_CHECK(cudaStreamSynchronize(stream));
}

void RtFftEngine::Pimpl::execute_pipeline_operations(int idx) {
    const size_t in_bytes = sizeof(float) * config_.nfft * config_.batch;
    const size_t bins = (config_.nfft / 2 + 1);
    const size_t out_bytes = sizeof(float) * bins * config_.batch;

    cudaStream_t stream = streams_[idx];
    cufftHandle plan = plans_[idx];

    CUDA_CHECK(cudaMemcpyAsync(d_inputs_[idx], h_inputs_[idx], in_bytes, cudaMemcpyHostToDevice, stream));
    ops::apply_window_async(d_inputs_[idx], d_window_[idx], config_.nfft, config_.batch, stream);
    CUFFT_CHECK(cufftExecR2C(plan, d_inputs_[idx], d_specs_[idx]));
    ops::magnitude_async(d_specs_[idx], d_mags_[idx], bins, config_.batch, stream);
    CUDA_CHECK(cudaMemcpyAsync(h_outputs_[idx], d_mags_[idx], out_bytes, cudaMemcpyDeviceToHost, stream));
}

void RtFftEngine::Pimpl::capture_graph(int idx) {
    if (config_.verbose) printf("[Graph] Capturing graph for stream %d...\n", idx);
    CUDA_CHECK(cudaStreamBeginCapture(streams_[idx], cudaStreamCaptureModeGlobal));
    execute_pipeline_operations(idx);
    CUDA_CHECK(cudaStreamEndCapture(streams_[idx], &graphs_[idx]));
    CUDA_CHECK(cudaGraphInstantiate(&graph_execs_[idx], graphs_[idx], nullptr, nullptr, 0));
    if (config_.verbose) printf("[Graph] Graph instantiated for stream %d.\n", idx);
}

void RtFftEngine::Pimpl::execute_async_traditional(int idx) {
    if (enable_profiling_) CUDA_CHECK(cudaEventRecord(prof_start_[idx], streams_[idx]));
    execute_pipeline_operations(idx);
    if (enable_profiling_) CUDA_CHECK(cudaEventRecord(prof_end_[idx], streams_[idx]));
    CUDA_CHECK(cudaEventRecord(events_[idx], streams_[idx]));
}

void RtFftEngine::Pimpl::execute_async_graph(int idx) {
    if (enable_profiling_) CUDA_CHECK(cudaEventRecord(prof_start_[idx], streams_[idx]));
    CUDA_CHECK(cudaGraphLaunch(graph_execs_[idx], streams_[idx]));
    if (enable_profiling_) CUDA_CHECK(cudaEventRecord(prof_end_[idx], streams_[idx]));
    CUDA_CHECK(cudaEventRecord(events_[idx], streams_[idx]));
}


// --- Public RtFftEngine Methods (forwarding to Pimpl) ---

RtFftEngine::RtFftEngine(const RtFftConfig& config) : p_(new Pimpl(config)) {}
RtFftEngine::~RtFftEngine() { delete p_; }

void RtFftEngine::prepare_for_execution() {
    if (!p_->use_graphs_ || p_->graphs_captured_) return;
    if (p_->config_.verbose) printf("[Graph] Preparing for execution by warming up and capturing graphs...\n");
    for (int i = 0; i < Pimpl::kNumStreams; ++i) {
        p_->execute_async_traditional(i);
        CUDA_CHECK(cudaStreamSynchronize(p_->streams_[i]));
        p_->capture_graph(i);
    }
    p_->graphs_captured_ = true;
    if (p_->config_.verbose) printf("[Graph] All graphs captured and ready!\n");
}

void RtFftEngine::execute_async(int stream_idx) {
    if (stream_idx < 0 || stream_idx >= Pimpl::kNumStreams) throw std::out_of_range("Stream index is out of range.");
    if (p_->use_graphs_ && p_->graphs_captured_) {
        p_->execute_async_graph(stream_idx);
    } else {
        p_->execute_async_traditional(stream_idx);
    }
}

void RtFftEngine::sync_stream(int stream_idx) {
    if (stream_idx < 0 || stream_idx >= Pimpl::kNumStreams) throw std::out_of_range("Stream index is out of range.");
    CUDA_CHECK(cudaEventSynchronize(p_->events_[stream_idx]));
}

void RtFftEngine::synchronize_all_streams() {
    for (int i = 0; i < Pimpl::kNumStreams; ++i) {
        if (p_->streams_[i]) {
            CUDA_CHECK(cudaStreamSynchronize(p_->streams_[i]));
        }
    }
}

void RtFftEngine::set_use_graphs(bool enable) { p_->use_graphs_ = enable; }
bool RtFftEngine::get_use_graphs() const { return p_->use_graphs_; }
bool RtFftEngine::graphs_ready() const { return p_->graphs_captured_; }

float RtFftEngine::get_last_exec_time_ms(int idx) const {
    if (!p_->enable_profiling_ || !p_->prof_start_[idx] || !p_->prof_end_[idx]) return -1.0f;
    float ms = 0.0f;
    cudaEventElapsedTime(&ms, p_->prof_start_[idx], p_->prof_end_[idx]);
    return ms;
}

float* RtFftEngine::pinned_input(int idx) const {
    if (idx < 0 || idx >= Pimpl::kNumStreams) throw std::out_of_range("Stream index out of range for pinned_input.");
    return p_->h_inputs_[idx];
}

float* RtFftEngine::pinned_output(int idx) const {
    if (idx < 0 || idx >= Pimpl::kNumStreams) throw std::out_of_range("Stream index out of range for pinned_output.");
    return p_->h_outputs_[idx];
}

void RtFftEngine::set_window(const float* h_window_data) {
    const size_t window_bytes = sizeof(float) * p_->config_.nfft;
    for (int i = 0; i < Pimpl::kNumStreams; ++i) {
        CUDA_CHECK(cudaMemcpy(p_->d_window_[i], h_window_data, window_bytes, cudaMemcpyHostToDevice));
    }
}

int RtFftEngine::get_fft_size() const { return p_->config_.nfft; }
int RtFftEngine::get_batch_size() const { return p_->config_.batch; }
int RtFftEngine::get_num_streams() const { return Pimpl::kNumStreams; }

} // namespace ionosense

