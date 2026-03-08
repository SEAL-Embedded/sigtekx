/**
 * @file cuda_fft.h
 * @brief Declaration of the CudaFftEngineCpp class: a GPU-accelerated,
 * multi-stream, concurrent batch FFT engine with CUDA Graph support.
 *
 * This header defines the CudaFftEngineCpp class which:
 * - Uses a triple-buffering strategy with 3 CUDA streams for concurrency.
 * - Overlaps H2D copy, kernel execution, and D2H copy.
 * - Supports CUDA Graphs for reduced launch overhead.
 * - Accepts a batch of float32 time-domain inputs.
 * - Is designed for high-throughput, low-latency scenarios.
 *
 * @note Recommended workflow:
 * 1. Construct the CudaFftEngineCpp object.
 * 2. Call prepare_for_execution() once to capture graphs.
 * 3. Call execute_async() in a high-frequency loop.
 */

#pragma once

#include <vector>
#include <stdexcept>
#include <cuda_runtime.h>
#include <cufft.h>

 // Error-checking macros for CUDA and cuFFT API calls.
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


/**
 * @class CudaFftEngineCpp
 * @brief A concurrent FFT engine using a 3-stream, triple-buffer design with CUDA Graph support.
 *
 * This engine is designed to maximize throughput by overlapping operations.
 * It manages three parallel "slots", each with its own CUDA stream, events,
 * cuFFT plan, and device/host buffers to process a batch of FFTs.
 */
class CudaFftEngineCpp {
public:
    /**
     * @brief Construct the FFT engine.
     * @param nfft     Number of samples per FFT (e.g., 4096).
     * @param batch    Total number of independent FFTs to execute in one call.
     * @param use_graphs  Enable CUDA Graphs (default: true).
     * @param verbose  Print detailed graph capture info (default: true).
     */
    CudaFftEngineCpp(int nfft, int batch, bool use_graphs = true, bool verbose = true);

    /**
     * @brief Destructor: cleans up all CUDA and cuFFT resources.
     */
    ~CudaFftEngineCpp();

    // Rule of Five: By explicitly deleting the copy constructor and copy
    // assignment operator, we prevent accidental copies of the object,
    // which would lead to double-freeing of CUDA resources and crashes.
    CudaFftEngineCpp(const CudaFftEngineCpp&) = delete;
    CudaFftEngineCpp& operator=(const CudaFftEngineCpp&) = delete;


    // --- Asynchronous Public API ---

    /**
     * @brief Warms up streams and captures CUDA graphs.
     *
     * This method should be called once after initialization and before
     * the main processing loop. It runs a single traditional execution
     * on each stream to ensure all CUDA contexts and cuFFT plans are
     * fully initialized, then captures the execution graph.
     */
    void prepare_for_execution();

    /**
     * @brief Asynchronously executes the full FFT pipeline on a given stream slot.
     *
     * This function is non-blocking. It either:
     * - Launches a pre-captured CUDA Graph (if enabled and available)
     * - Or enqueues operations traditionally on streams_[idx]
     *
     * @param idx The stream slot to use (0, 1, or 2).
     */
    void execute_async(int idx);

    /**
     * @brief Blocks the calling host thread until the work on a specific stream is complete.
     *
     * This should be called before accessing the output buffer of a given slot
     * to ensure the D2H copy has finished.
     *
     * @param idx The stream slot to synchronize with (0, 1, or 2).
     */
    void sync_stream(int idx);

    void synchronize_all_streams();

    // --- Graph Control API ---

    /**
     * @brief Enable or disable CUDA Graph usage at runtime.
     * @param enable If true, use graphs when available. If false, use traditional launches.
     */
    void set_use_graphs(bool enable) { use_graphs_ = enable; }

    /**
     * @brief Check if graphs are currently enabled.
     * @return Current graph usage state.
     */
    bool get_use_graphs() const { return use_graphs_; }

    /**
     * @brief Check if graphs have been successfully captured.
     * @return True if all streams have captured graphs.
     */
    bool graphs_ready() const { return graphs_captured_; }

    /**
     * @brief Get performance metrics for the last execution.
     * @param idx The stream slot index.
     * @return Execution time in milliseconds (requires profiling events enabled).
     */
    float get_last_exec_time_ms(int idx) const;

    // --- Buffer Accessors & Properties ---

    /**
     * @brief Get a pointer to the pinned host input buffer for a specific stream slot.
     * @param idx The stream slot index (0, 1, or 2).
     * @return float* Pointer to the time-domain input buffer for the whole batch.
     */
    float* pinned_input(int idx) const;

    /**
     * @brief Get a pointer to the pinned host output buffer for a specific stream slot.
     * @param idx The stream slot index (0, 1, or 2).
     * @return float* Pointer to the magnitude output buffer for the whole batch.
     */
    float* pinned_output(int idx) const;

   /**
    * @brief Sets the windowing function from a host-side array.
    * @param h_window_data Pointer to an array of size NFFT with the window samples.
    */
    void set_window(const float* h_window_data);

    /** @brief Get the FFT size (number of points per FFT). */
    int get_fft_size() const { return nfft_; }

    /** @brief Get the batch size (number of FFTs per call). */
    int get_batch_size() const { return batch_; }

    /** @brief Get the number of concurrent streams. */
    int get_num_streams() const { return kNumStreams; }


private:
    // --- Constants ---
    static constexpr int kNumStreams = 3;

    // --- Core Properties ---
    int nfft_;
    int batch_;
    bool verbose_;

    // --- CUDA Resources (one per stream) ---
    cudaStream_t    streams_[kNumStreams];    ///< Array of CUDA streams.
    cudaEvent_t      events_[kNumStreams];    ///< Events to track completion on each stream.
    cufftHandle       plans_[kNumStreams];    ///< cuFFT plans, one per stream.

    // --- Graph Resources ---
    cudaGraph_t              graphs_[kNumStreams];    ///< Captured graphs for each stream
    cudaGraphExec_t    graphs_execs_[kNumStreams];    ///< Executable graphs for each stream

    // --- Graph Control ---
    bool use_graphs_;       ///< Runtime flag to enable/disable graphs
    bool graphs_captured_;  ///< True when graphs have been captured

    // --- Profiling Events (optional) ---
    cudaEvent_t    prof_start_[kNumStreams];    ///< Profiling start events
    cudaEvent_t      prof_end_[kNumStreams];    ///< Profiling end events
    bool           enable_profiling_;           ///< Enable timing measurements

    // --- Host Pinned Buffers (one set per stream) ---
    float*    h_inputs_[kNumStreams];    ///< Pinned host buffers for input.
    float*   h_outputs_[kNumStreams];    ///< Pinned host buffers for output.

    // --- Device Buffers (one set per stream) ---
    cufftReal*      d_inputs_[kNumStreams];    ///< Device buffers for time-domain data.
    cufftComplex*    d_specs_[kNumStreams];    ///< Device buffers for complex spectrum.
    float*            d_mags_[kNumStreams];    ///< Device buffers for magnitude.
    cufftReal*      d_window_[kNumStreams];    ///< Device buffers for the window function.

    // --- cuFFT Workspaces (for graph compatibility) ---
    void*     cufft_workspaces_[kNumStreams];    ///< User-managed workspaces for cuFFT
    size_t    cufft_workspace_size_;             ///< Size of each workspace

    // --- Internal Methods ---

    /** @brief Initializes all resources: streams, events, buffers, and plans. */
    void init_resources();

    /** @brief Destroys all resources. */
    void cleanup();

    void init_default_window(float* d_window, int nfft, cudaStream_t stream);

    /** @brief Setup cuFFT plans for graph compatibility. */
    void setup_cufft_for_graphs(int idx);

    /** @brief Capture the FFT pipeline as a CUDA graph for a stream. */
    void capture_graph(int idx);

    /** @brief Execute the FFT pipeline traditionally (without graphs). */
    void execute_async_traditional(int idx);

    /** @brief Execute the FFT pipeline using captured graph. */
    void execute_async_graph(int idx);

    /** @brief Core FFT pipeline operations (used by both traditional and graph paths). */
    void execute_pipeline_operations(int idx);
};