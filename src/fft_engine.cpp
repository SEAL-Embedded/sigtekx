/**
 * @file fft_engine.cpp
 * @brief Host orchestration for the ionosense FFT engine
 * 
 * This file contains all host-side logic including stream management,
 * cuFFT plan lifecycle, memory management, and CUDA Graph orchestration.
 * Kernels are launched via thin wrappers in ops_fft.cu.
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

// Error checking macros
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
        fprintf(stderr, "cuFFT Error in %s at line %d\n", __FILE__, __LINE__); \
        throw std::runtime_error("cuFFT error"); \
    } \
} while(0)

namespace ionosense {

// Implementation structure containing all internal state
struct RtFftEngine::Impl {
    // Configuration
    static constexpr int kNumStreams = 3;
    int nfft_;
    int batch_;
    bool use_graphs_;
    bool verbose_;
    bool graphs_captured_;
    bool enable_profiling_;
    
    // CUDA Resources (one per stream)
    cudaStream_t streams_[kNumStreams];
    cudaEvent_t events_[kNumStreams];
    cufftHandle plans_[kNumStreams];
    
    // Graph Resources
    cudaGraph_t graphs_[kNumStreams];
    cudaGraphExec_t graphs_execs_[kNumStreams];
    
    // Profiling Events
    cudaEvent_t prof_start_[kNumStreams];
    cudaEvent_t prof_end_[kNumStreams];
    
    // Host Pinned Buffers
    float* h_inputs_[kNumStreams];
    float* h_outputs_[kNumStreams];
    
    // Device Buffers
    cufftReal* d_inputs_[kNumStreams];
    cufftComplex* d_specs_[kNumStreams];
    float* d_mags_[kNumStreams];
    float* d_window_[kNumStreams];
    
    // cuFFT Workspaces (for graph compatibility)
    void* cufft_workspaces_[kNumStreams];
    size_t cufft_workspace_size_;
    
    // Constructor
    Impl(const RtFftConfig& config) 
        : nfft_(config.nfft), 
          batch_(config.batch),
          use_graphs_(config.use_graphs),
          verbose_(config.verbose),
          graphs_captured_(false),
          enable_profiling_(false),
          cufft_workspace_size_(0) {
        
        // Initialize all pointers to nullptr
        for (int i = 0; i < kNumStreams; ++i) {
            streams_[i]           =  nullptr;
            events_[i]            =  nullptr;
            plans_[i]             =  0;
            h_inputs_[i]          =  nullptr;
            h_outputs_[i]         =  nullptr;
            d_inputs_[i]          =  nullptr;
            d_specs_[i]           =  nullptr;
            d_mags_[i]            =  nullptr;
            d_window_[i]          =  nullptr;
            graphs_[i]            =  nullptr;
            graphs_execs_[i]      =  nullptr;
            cufft_workspaces_[i]  =  nullptr;
            prof_start_[i]        =  nullptr;
            prof_end_[i]          =  nullptr;
        }
        
        init_resources();
        
        if (verbose_) {
            printf("[RtFftEngine] Initialized with NFFT=%d, Batch=%d, Graphs=%s\n",
                nfft_, batch_, use_graphs_ ? "ENABLED" : "DISABLED");
        }
    }
    
    // Destructor
    ~Impl() {
        cleanup();
    }
    
    void init_resources() {
        const size_t in_bytes = sizeof(float) * nfft_ * batch_;
        const size_t bins = (nfft_ / 2 + 1);
        const size_t out_bytes = sizeof(float) * bins * batch_;
        const size_t spec_bytes = sizeof(cufftComplex) * bins * batch_;
        
        // Configure memory pools for better graph performance
        if (use_graphs_) {
            cudaMemPool_t mempool;
            CUDA_CHECK(cudaDeviceGetDefaultMemPool(&mempool, 0));
            uint64_t threshold = UINT64_MAX;
            CUDA_CHECK(cudaMemPoolSetAttribute(mempool,
                cudaMemPoolAttrReleaseThreshold, &threshold));
        }
        
        for (int i = 0; i < kNumStreams; ++i) {
            // 1. Create Stream and Event
            CUDA_CHECK(cudaStreamCreate(&streams_[i]));
            CUDA_CHECK(cudaEventCreateWithFlags(&events_[i], cudaEventDisableTiming));
            
            // Create profiling events if needed
            if (enable_profiling_) {
                CUDA_CHECK(cudaEventCreate(&prof_start_[i]));
                CUDA_CHECK(cudaEventCreate(&prof_end_[i]));
            }
            
            // 2. Allocate Pinned Host Memory
            CUDA_CHECK(cudaHostAlloc(&h_inputs_[i], in_bytes, cudaHostAllocDefault));
            CUDA_CHECK(cudaHostAlloc(&h_outputs_[i], out_bytes, cudaHostAllocDefault));
            
            // 3. Allocate Device Memory
            CUDA_CHECK(cudaMalloc(&d_inputs_[i], in_bytes));
            CUDA_CHECK(cudaMalloc(&d_specs_[i], spec_bytes));
            CUDA_CHECK(cudaMalloc(&d_mags_[i], out_bytes));
            CUDA_CHECK(cudaMalloc(&d_window_[i], sizeof(float) * nfft_));
            init_default_window(d_window_[i], nfft_, streams_[i]);
            
            // 4. Create cuFFT Plan and configure for graphs
            CUFFT_CHECK(cufftCreate(&plans_[i]));
            
            const int rank = 1;  // 1D FFT
            int n[] = { nfft_ };
            int istride = 1;
            int ostride = 1;
            int idist = nfft_;
            int odist = (nfft_ / 2 + 1);
            
            CUFFT_CHECK(cufftPlanMany(&plans_[i], rank, n,
                nullptr, istride, idist,
                nullptr, ostride, odist,
                CUFFT_R2C, batch_));
            
            CUFFT_CHECK(cufftSetStream(plans_[i], streams_[i]));
            
            // Setup cuFFT for graph compatibility if graphs are enabled
            if (use_graphs_) {
                setup_cufft_for_graphs(i);
            }
        }
    }
    
    void setup_cufft_for_graphs(int idx) {
        // Get workspace size requirement
        size_t workspace_size;
        CUFFT_CHECK(cufftGetSize(plans_[idx], &workspace_size));
        
        // Use the maximum workspace size across all plans
        if (workspace_size > cufft_workspace_size_) {
            cufft_workspace_size_ = workspace_size;
        }
        
        // Allocate user-managed workspace
        CUDA_CHECK(cudaMalloc(&cufft_workspaces_[idx], workspace_size));
        
        // Disable auto-allocation and set the workspace
        CUFFT_CHECK(cufftSetAutoAllocation(plans_[idx], 0));
        CUFFT_CHECK(cufftSetWorkArea(plans_[idx], cufft_workspaces_[idx]));
    }
    
    void execute_pipeline_operations(int idx) {
        const size_t in_bytes = sizeof(float) * nfft_ * batch_;
        const size_t bins = (nfft_ / 2 + 1);
        const size_t out_bytes = sizeof(float) * bins * batch_;
        
        // Get resources for the specified stream index
        cudaStream_t   stream =    streams_[idx];
        cufftHandle      plan =      plans_[idx];
        float*           h_in =   h_inputs_[idx];
        float*          h_out =  h_outputs_[idx];
        cufftReal*       d_in =   d_inputs_[idx];
        cufftComplex*  d_spec =    d_specs_[idx];
        float*          d_mag =     d_mags_[idx];
        
        // 1. H2D Copy
        CUDA_CHECK(cudaMemcpyAsync(d_in, h_in, in_bytes, cudaMemcpyHostToDevice, stream));
        
        // 2. Window Kernel (via launcher in ops_fft.cu)
        ionosense::ops::apply_window_async(d_in, d_window_[idx], nfft_, batch_, stream);
        
        // 3. cuFFT Execution (Real to Complex)
        CUFFT_CHECK(cufftExecR2C(plan, d_in, d_spec));
        
        // 4. Magnitude Kernel (via launcher in ops_fft.cu)
        ionosense::ops::magnitude_async(d_spec, d_mag, bins, batch_, stream);
        
        // 5. D2H Copy
        CUDA_CHECK(cudaMemcpyAsync(h_out, d_mag, out_bytes, cudaMemcpyDeviceToHost, stream));
    }
    
    void capture_graph(int idx) {
        if (verbose_) printf("[Graph] Capturing graph for stream %d...\n", idx);
        
        // Begin capture
        CUDA_CHECK(cudaStreamBeginCapture(streams_[idx], cudaStreamCaptureModeGlobal));
        
        // Execute the pipeline operations (these will be captured)
        execute_pipeline_operations(idx);
        
        // End capture
        CUDA_CHECK(cudaStreamEndCapture(streams_[idx], &graphs_[idx]));
        
        if (verbose_) {
            size_t num_nodes;
            CUDA_CHECK(cudaGraphGetNodes(graphs_[idx], nullptr, &num_nodes));
            printf("[Graph] Captured %zu nodes for stream %d\n", num_nodes, idx);
        }
        
        // Instantiate the graph
        CUDA_CHECK(cudaGraphInstantiate(&graphs_execs_[idx], graphs_[idx],
            nullptr, nullptr, 0));
        
        if (verbose_) printf("[Graph] Graph instantiated for stream %d\n", idx);
    }
    
    void execute_async_traditional(int idx) {
        if (enable_profiling_ && prof_start_[idx]) {
            CUDA_CHECK(cudaEventRecord(prof_start_[idx], streams_[idx]));
        }
        
        execute_pipeline_operations(idx);
        
        if (enable_profiling_ && prof_end_[idx]) {
            CUDA_CHECK(cudaEventRecord(prof_end_[idx], streams_[idx]));
        }
        
        CUDA_CHECK(cudaEventRecord(events_[idx], streams_[idx]));
    }
    
    void execute_async_graph(int idx) {
        if (enable_profiling_ && prof_start_[idx]) {
            CUDA_CHECK(cudaEventRecord(prof_start_[idx], streams_[idx]));
        }
        
        CUDA_CHECK(cudaGraphLaunch(graphs_execs_[idx], streams_[idx]));
        
        if (enable_profiling_ && prof_end_[idx]) {
            CUDA_CHECK(cudaEventRecord(prof_end_[idx], streams_[idx]));
        }
        
        CUDA_CHECK(cudaEventRecord(events_[idx], streams_[idx]));
    }
    
    void init_default_window(float* d_window, int nfft, cudaStream_t stream) {
        const size_t window_bytes = sizeof(float) * nfft;
        std::vector<float> h_window(nfft, 1.0f);
        CUDA_CHECK(cudaMemcpyAsync(d_window, h_window.data(), window_bytes, 
                                   cudaMemcpyHostToDevice, stream));
        CUDA_CHECK(cudaStreamSynchronize(stream));
    }
    
    void cleanup() {
        // Ensure all streams are idle before cleanup
        for (int i = 0; i < kNumStreams; ++i) {
            if (streams_[i]) {
                cudaStreamSynchronize(streams_[i]);
            }
        }
        
        // Destroy graph resources first
        for (int i = 0; i < kNumStreams; ++i) {
            if (graphs_execs_[i]) {
                CUDA_CHECK(cudaGraphExecDestroy(graphs_execs_[i]));
            }
            if (graphs_[i]) {
                CUDA_CHECK(cudaGraphDestroy(graphs_[i]));
            }
        }
        
        // Clean up the rest
        for (int i = 0; i < kNumStreams; ++i) {
            if (events_[i])           CUDA_CHECK(cudaEventDestroy(events_[i]));
            if (prof_start_[i])       CUDA_CHECK(cudaEventDestroy(prof_start_[i]));
            if (prof_end_[i])         CUDA_CHECK(cudaEventDestroy(prof_end_[i]));
            if (streams_[i])          CUDA_CHECK(cudaStreamDestroy(streams_[i]));
            if (plans_[i])            CUFFT_CHECK(cufftDestroy(plans_[i]));
            if (h_inputs_[i])         CUDA_CHECK(cudaFreeHost(h_inputs_[i]));
            if (h_outputs_[i])        CUDA_CHECK(cudaFreeHost(h_outputs_[i]));
            if (d_inputs_[i])         CUDA_CHECK(cudaFree(d_inputs_[i]));
            if (d_specs_[i])          CUDA_CHECK(cudaFree(d_specs_[i]));
            if (d_mags_[i])           CUDA_CHECK(cudaFree(d_mags_[i]));
            if (d_window_[i])         CUDA_CHECK(cudaFree(d_window_[i]));
            if (cufft_workspaces_[i]) CUDA_CHECK(cudaFree(cufft_workspaces_[i]));
        }
    }
};

// Public API implementation

RtFftEngine::RtFftEngine(const RtFftConfig& config) 
    : p_(new Impl(config)) {
}

RtFftEngine::~RtFftEngine() {
    delete p_;
}

void RtFftEngine::prepare_for_execution() {
    if (!p_->use_graphs_ || p_->graphs_captured_) {
        return;
    }
    
    if (p_->verbose_) {
        printf("[Graph] Preparing for execution by warming up and capturing graphs...\n");
    }
    
    for (int i = 0; i < p_->kNumStreams; ++i) {
        // Warm up the stream with one traditional execution
        p_->execute_async_traditional(i);
        CUDA_CHECK(cudaStreamSynchronize(p_->streams_[i]));
        
        p_->capture_graph(i);
    }
    
    p_->graphs_captured_ = true;
    if (p_->verbose_) {
        printf("[Graph] All graphs captured and ready!\n");
    }
}

void RtFftEngine::execute_async(int idx) {
    if (idx < 0 || idx >= p_->kNumStreams) {
        throw std::out_of_range("Stream index is out of range.");
    }
    
    if (p_->use_graphs_ && p_->graphs_captured_) {
        p_->execute_async_graph(idx);
    } else {
        p_->execute_async_traditional(idx);
    }
}

void RtFftEngine::sync_stream(int idx) {
    if (idx < 0 || idx >= p_->kNumStreams) {
        throw std::out_of_range("Stream index is out of range.");
    }
    CUDA_CHECK(cudaEventSynchronize(p_->events_[idx]));
}

void RtFftEngine::synchronize_all_streams() {
    for (int i = 0; i < p_->kNumStreams; ++i) {
        if (p_->streams_[i]) {
            CUDA_CHECK(cudaStreamSynchronize(p_->streams_[i]));
        }
    }
}

// Future API stubs (not implemented yet)
void RtFftEngine::push(const float* ch0, const float* ch1, std::size_t count) {
    // TODO: Implement circular buffer push logic
    (void)ch0; (void)ch1; (void)count;
}

void RtFftEngine::run() {
    // TODO: Implement processing trigger
}

void RtFftEngine::pop(float* mag0, float* mag1, std::size_t n_bins) {
    // TODO: Implement result retrieval  
    (void)mag0; (void)mag1; (void)n_bins;
}

void RtFftEngine::set_use_graphs(bool enable) {
    p_->use_graphs_ = enable;
}

bool RtFftEngine::get_use_graphs() const {
    return p_->use_graphs_;
}

bool RtFftEngine::graphs_ready() const {
    return p_->graphs_captured_;
}

float RtFftEngine::get_last_exec_time_ms(int idx) const {
    if (!p_->enable_profiling_ || !p_->prof_start_[idx] || !p_->prof_end_[idx]) {
        return -1.0f;
    }
    
    float ms = 0.0f;
    CUDA_CHECK(cudaEventElapsedTime(&ms, p_->prof_start_[idx], p_->prof_end_[idx]));
    return ms;
}

float* RtFftEngine::pinned_input(int idx) const {
    if (idx < 0 || idx >= p_->kNumStreams) {
        throw std::out_of_range("Stream index is out of range for pinned_input.");
    }
    return p_->h_inputs_[idx];
}

float* RtFftEngine::pinned_output(int idx) const {
    if (idx < 0 || idx >= p_->kNumStreams) {
        throw std::out_of_range("Stream index is out of range for pinned_output.");
    }
    return p_->h_outputs_[idx];
}

void RtFftEngine::set_window(const float* h_window_data) {
    const size_t window_bytes = sizeof(float) * p_->nfft_;
    for (int i = 0; i < p_->kNumStreams; ++i) {
        CUDA_CHECK(cudaMemcpy(p_->d_window_[i], h_window_data, window_bytes, 
                             cudaMemcpyHostToDevice));
    }
}

int RtFftEngine::get_fft_size() const {
    return p_->nfft_;
}

int RtFftEngine::get_batch_size() const {
    return p_->batch_;
}

int RtFftEngine::get_num_streams() const {
    return p_->kNumStreams;
}

} // namespace ionosense