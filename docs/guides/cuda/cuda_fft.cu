/**
 * cuda_fft.cu
 * -----------------------------------------------------------------------------
 * Implementation of the concurrent, multi-stream CudaFftEngineCpp with
 * CUDA Graph support for reduced kernel launch overhead.
 *
 * This file implements the methods declared in cuda_fft.h. It handles the
 * initialization, execution, and cleanup of a 3-stream CUDA pipeline
 * designed to overlap H2D copy, kernel execution, and D2H copy for
 * maximum FFT throughput. Now includes CUDA Graph capture and execution.
 */

#include "cuda_fft.h"
#include <math_constants.h> // For CUDART_PI_F
#include <stdexcept>
#include <vector>
#include <cstdio>


 /* ------------------------------------------------------------------------- *
 |                               Device Kernels                               |
 * ------------------------------------------------------------------------- */

 /**
  * @kernel applyWindow
  * Applies a Hann window to a contiguous batch of FFT data.
  * This kernel is designed to work on a batch of FFTs laid out end-to-end.
  */
__global__ void applyWindow(float* data, const float* window, int nfft, int batch) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= nfft * batch) return; // Safety guard for the entire batch

    int sample_idx = idx % nfft;  // `idx % nfft` gives the sample index within each FFT frame

    data[idx] *= window[sample_idx];
}

/**
 * @kernel magnitudeKernel
 * Computes magnitude = sqrt(re² + im²) for a batch of FFT outputs.
 */
__global__ void magnitudeKernel(const cufftComplex* spec, float* mag, int nfft, int batch) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int num_bins = (nfft / 2 + 1);
    if (idx >= num_bins * batch) return;

    int fft_idx = idx / num_bins;    // Which FFT in the batch (0 or 1)
    int bin_idx = idx % num_bins;    // Which bin in the FFT (0 to 16)

    int spec_idx = fft_idx * num_bins + bin_idx;    // Calculate the index into the flat spectrum array

    float re = spec[spec_idx].x;
    float im = spec[spec_idx].y;
    mag[idx] = sqrtf(re * re + im * im);
}


/* ------------------------------------------------------------------------- *
|                          CudaFftEngineCpp Methods                          |
* ------------------------------------------------------------------------- */

/**
 * @brief Constructor: Initializes all CUDA resources.
 */
CudaFftEngineCpp::CudaFftEngineCpp(int nfft, int batch, bool use_graphs, bool verbose)
    : nfft_(nfft), batch_(batch), use_graphs_(use_graphs), verbose_(verbose),
    graphs_captured_(false), enable_profiling_(false),
    cufft_workspace_size_(0) {

    for (int i = 0; i < kNumStreams; ++i) {
        streams_[i]           = nullptr;
        events_[i]            = nullptr;
        plans_[i]             = 0;
        h_inputs_[i]          = nullptr;
        h_outputs_[i]         = nullptr;
        d_inputs_[i]          = nullptr;
        d_specs_[i]           = nullptr;
        d_mags_[i]            = nullptr;
		d_window_[i]          = nullptr;
        graphs_[i]            = nullptr;
        graphs_execs_[i]      = nullptr;
        cufft_workspaces_[i]  = nullptr;
        prof_start_[i]        = nullptr;
        prof_end_[i]          = nullptr;
    }

    init_resources();

    if (verbose_) {
        printf("[CudaFftEngine] Initialized with NFFT=%d, Batch=%d, Graphs=%s\n",
            nfft_, batch_, use_graphs_ ? "ENABLED" : "DISABLED");
    }
}

/**
 * @brief Destructor: Releases all CUDA resources.
 */
CudaFftEngineCpp::~CudaFftEngineCpp() {
    cleanup();
}

/**
 * @brief Initializes all streams, events, buffers, and cuFFT plans.
 */
void CudaFftEngineCpp::init_resources() {
    const size_t in_bytes    = sizeof(float) * nfft_ * batch_;
    const size_t bins        = (nfft_ / 2 + 1);
    const size_t out_bytes   = sizeof(float) * bins * batch_;
    const size_t spec_bytes  = sizeof(cufftComplex) * bins * batch_;

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

        const int rank  = 1;                // 1D FFT
        int n[]         = { nfft_ };        // Size of the FFT in each dimension
        int istride     = 1;                // Distance between two successive input elements
        int ostride     = 1;                // Distance between two successive output elements
        int idist       = nfft_;            // Distance between the start of two consecutive FFTs in the input data
        int odist       = (nfft_ / 2 + 1);  // Distance between the start of two consecutive FFTs in the output data
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

/**
 * @brief Setup cuFFT plans to be compatible with CUDA Graphs.
 */
void CudaFftEngineCpp::setup_cufft_for_graphs(int idx) {
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

/**
 * @brief Core pipeline operations used by both traditional and graph execution.
 */
void CudaFftEngineCpp::execute_pipeline_operations(int idx) {
    const size_t in_bytes   = sizeof(float) * nfft_ * batch_;
    const size_t bins       = (nfft_ / 2 + 1);
    const size_t out_bytes  = sizeof(float) * bins * batch_;

    // Get resources for the specified stream index
    cudaStream_t   stream  =    streams_[idx];
    cufftHandle    plan    =      plans_[idx];
    float*         h_in    =   h_inputs_[idx];
    float*         h_out   =  h_outputs_[idx];
    cufftReal*     d_in    =   d_inputs_[idx];
    cufftComplex*  d_spec  =    d_specs_[idx];
    float*         d_mag   =     d_mags_[idx];

	// Kernel launch parameters
    dim3 threads(256);
    dim3 blocks((nfft_ * batch_ + threads.x - 1) / threads.x);

    // 1. H2D Copy
    CUDA_CHECK(cudaMemcpyAsync(d_in, h_in, in_bytes, cudaMemcpyHostToDevice, stream));

    // 2. Window Kernel
    applyWindow << <blocks, threads, 0, stream >> > (d_in, d_window_[idx], nfft_, batch_);
    CUDA_CHECK(cudaGetLastError());

    // 3. cuFFT Execution (Real to Complex)
    CUFFT_CHECK(cufftExecR2C(plan, d_in, d_spec));

    // 4. Magnitude Kernel
    dim3 mag_blocks((bins * batch_ + threads.x - 1) / threads.x);
    magnitudeKernel << <mag_blocks, threads, 0, stream >> > (d_spec, d_mag, nfft_, batch_);
    CUDA_CHECK(cudaGetLastError());

    // 5. D2H Copy
    CUDA_CHECK(cudaMemcpyAsync(h_out, d_mag, out_bytes, cudaMemcpyDeviceToHost, stream));
}

/**
 * @brief Capture the FFT pipeline as a CUDA graph.
 */
void CudaFftEngineCpp::capture_graph(int idx) {
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

/**
 * @brief Execute the FFT pipeline traditionally (without graphs).
 */
void CudaFftEngineCpp::execute_async_traditional(int idx) {
    if (enable_profiling_ && prof_start_[idx]) {
        CUDA_CHECK(cudaEventRecord(prof_start_[idx], streams_[idx]));
    }

    execute_pipeline_operations(idx);

    if (enable_profiling_ && prof_end_[idx]) {
        CUDA_CHECK(cudaEventRecord(prof_end_[idx], streams_[idx]));
    }

    CUDA_CHECK(cudaEventRecord(events_[idx], streams_[idx]));
}

/**
 * @brief Execute the FFT pipeline using captured graph.
 */
void CudaFftEngineCpp::execute_async_graph(int idx) {
    if (enable_profiling_ && prof_start_[idx]) {
        CUDA_CHECK(cudaEventRecord(prof_start_[idx], streams_[idx]));
    }

    CUDA_CHECK(cudaGraphLaunch(graphs_execs_[idx], streams_[idx]));

    if (enable_profiling_ && prof_end_[idx]) {
        CUDA_CHECK(cudaEventRecord(prof_end_[idx], streams_[idx]));
    }

    CUDA_CHECK(cudaEventRecord(events_[idx], streams_[idx]));
}

/**
 * @brief Warms up streams and captures CUDA graphs.
 */
void CudaFftEngineCpp::prepare_for_execution() {
    if (!use_graphs_ || graphs_captured_) {
        return;
    }

    if (verbose_) printf("[Graph] Preparing for execution by warming up and capturing graphs...\n");

    for (int i = 0; i < kNumStreams; ++i) {
        // Warm up the stream with one traditional execution
        execute_async_traditional(i);
        CUDA_CHECK(cudaStreamSynchronize(streams_[i]));

        capture_graph(i);
    }

    graphs_captured_ = true;
    if (verbose_) printf("[Graph] All graphs captured and ready!\n");
}

/**
 * @brief Asynchronously executes the FFT pipeline on a specific stream slot.
 */
void CudaFftEngineCpp::execute_async(int idx) {
    if (idx < 0 || idx >= kNumStreams) {
        throw std::out_of_range("Stream index is out of range.");
    }

    if (use_graphs_ && graphs_captured_) {
        execute_async_graph(idx);
    }
    else {
        execute_async_traditional(idx);
    }
}

/**
 * @brief Blocks the host until work on a specific stream is complete.
 */
void CudaFftEngineCpp::sync_stream(int idx) {
    if (idx < 0 || idx >= kNumStreams) {
        throw std::out_of_range("Stream index is out of range.");
    }
    CUDA_CHECK(cudaEventSynchronize(events_[idx]));
}

void CudaFftEngineCpp::synchronize_all_streams() {
    for (int i = 0; i < kNumStreams; ++i) {
        if (streams_[i]) {
            CUDA_CHECK(cudaStreamSynchronize(streams_[i]));
        }
    }
}

void CudaFftEngineCpp::init_default_window(float* d_window, int nfft, cudaStream_t stream) {
    const size_t window_bytes = sizeof(float) * nfft;
    std::vector<float> h_window(nfft, 1.0f);
    CUDA_CHECK(cudaMemcpyAsync(d_window, h_window.data(), window_bytes, cudaMemcpyHostToDevice, stream));
    CUDA_CHECK(cudaStreamSynchronize(stream));
}

/**
 * @brief Get performance metrics for the last execution.
 */
float CudaFftEngineCpp::get_last_exec_time_ms(int idx) const {
    if (!enable_profiling_ || !prof_start_[idx] || !prof_end_[idx]) {
        return -1.0f; // Profiling not enabled
    }

    float ms = 0.0f;
    CUDA_CHECK(cudaEventElapsedTime(&ms, prof_start_[idx], prof_end_[idx]));
    return ms;
}

/**
 * @brief Get a pointer to the pinned host input buffer for a specific stream slot.
 */
float* CudaFftEngineCpp::pinned_input(int idx) const {
    if (idx < 0 || idx >= kNumStreams) {
        throw std::out_of_range("Stream index is out of range for pinned_input.");
    }
    return h_inputs_[idx];
}

/**
 * @brief Get a pointer to the pinned host output buffer for a specific stream slot.
 */
float* CudaFftEngineCpp::pinned_output(int idx) const {
    if (idx < 0 || idx >= kNumStreams) {
        throw std::out_of_range("Stream index is out of range for pinned_output.");
    }
    return h_outputs_[idx];
}

void CudaFftEngineCpp::set_window(const float* h_window_data) {
    const size_t window_bytes = sizeof(float) * nfft_;
    for (int i = 0; i < kNumStreams; ++i) {
        CUDA_CHECK(cudaMemcpy(d_window_[i], h_window_data, window_bytes, cudaMemcpyHostToDevice));
    }
}

/**
 * @brief Releases all allocated resources.
 */
void CudaFftEngineCpp::cleanup() {
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