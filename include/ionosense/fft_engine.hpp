/**
 * @file fft_engine.hpp
 * @brief Public API for the ionosense real-time FFT engine
 * 
 * This header provides a stable public interface using PIMPL to hide
 * all CUDA implementation details from consumers.
 */

#pragma once

#include <cstddef>

namespace ionosense {

/**
 * @brief Configuration for the real-time FFT engine
 */
struct RtFftConfig {
    int sample_rate;        ///< Sample rate (currently unused, for future use)
    int nfft;              ///< FFT size (must be power of 2)
    int batch;             ///< Number of FFTs to process in parallel
    bool compute_db{false}; ///< Convert magnitude to dB (future feature)
    bool use_graphs{true};  ///< Enable CUDA Graphs for reduced overhead
    bool verbose{true};     ///< Enable verbose logging
};

/**
 * @class RtFftEngine
 * @brief High-performance GPU-accelerated FFT engine with multi-stream concurrency
 * 
 * This engine provides a triple-buffered, multi-stream architecture for
 * maximum throughput FFT processing. It supports CUDA Graphs to minimize
 * kernel launch overhead in real-time scenarios.
 */
class RtFftEngine {
public:
    /**
     * @brief Construct the FFT engine with specified configuration
     * @param config Configuration parameters for the engine
     */
    explicit RtFftEngine(const RtFftConfig& config);
    
    /**
     * @brief Destructor - releases all GPU resources
     */
    ~RtFftEngine();
    
    // Disable copy operations to prevent resource management issues
    RtFftEngine(const RtFftEngine&) = delete;
    RtFftEngine& operator=(const RtFftEngine&) = delete;
    
    // --- Stream-based Async API (existing interface) ---
    
    /**
     * @brief Prepare for execution by warming up and capturing graphs
     * 
     * Call this once after construction to initialize CUDA Graphs.
     * This performs a warmup run and captures the execution graph.
     */
    void prepare_for_execution();
    
    /**
     * @brief Execute FFT pipeline asynchronously on specified stream
     * @param idx Stream slot index (0, 1, or 2)
     */
    void execute_async(int idx);
    
    /**
     * @brief Wait for completion of work on specified stream
     * @param idx Stream slot index (0, 1, or 2)
     */
    void sync_stream(int idx);
    
    /**
     * @brief Synchronize all streams
     */
    void synchronize_all_streams();
    
    // --- New simplified API (future interface) ---
    
    /**
     * @brief Push input samples to the engine (future API)
     * @param ch0 Channel 0 samples (size: count)
     * @param ch1 Channel 1 samples (size: count) 
     * @param count Number of samples to push
     */
    void push(const float* ch0, const float* ch1, std::size_t count);
    
    /**
     * @brief Execute the FFT processing (future API)
     */
    void run();
    
    /**
     * @brief Pop magnitude results (future API)
     * @param mag0 Output buffer for channel 0 magnitudes
     * @param mag1 Output buffer for channel 1 magnitudes
     * @param n_bins Number of frequency bins to retrieve
     */
    void pop(float* mag0, float* mag1, std::size_t n_bins);
    
    // --- Configuration & Control ---
    
    /**
     * @brief Enable/disable CUDA Graph usage at runtime
     * @param enable True to use graphs, false for traditional execution
     */
    void set_use_graphs(bool enable);
    
    /**
     * @brief Check if graphs are enabled
     * @return Current graph usage state
     */
    bool get_use_graphs() const;
    
    /**
     * @brief Check if graphs have been captured
     * @return True if graphs are ready for use
     */
    bool graphs_ready() const;
    
    /**
     * @brief Get execution time of last operation
     * @param idx Stream slot index
     * @return Execution time in milliseconds (-1 if profiling disabled)
     */
    float get_last_exec_time_ms(int idx) const;
    
    // --- Buffer Access ---
    
    /**
     * @brief Get pointer to pinned input buffer
     * @param idx Stream slot index (0, 1, or 2)
     * @return Pointer to pinned host memory for input data
     */
    float* pinned_input(int idx) const;
    
    /**
     * @brief Get pointer to pinned output buffer
     * @param idx Stream slot index (0, 1, or 2)
     * @return Pointer to pinned host memory for output data
     */
    float* pinned_output(int idx) const;
    
    /**
     * @brief Set window function for FFT
     * @param h_window_data Host array of window coefficients (size: nfft)
     */
    void set_window(const float* h_window_data);
    
    // --- Properties ---
    
    /**
     * @brief Get FFT size
     * @return Number of points per FFT
     */
    int get_fft_size() const;
    
    /**
     * @brief Get batch size
     * @return Number of parallel FFTs per execution
     */
    int get_batch_size() const;
    
    /**
     * @brief Get number of streams
     * @return Number of concurrent stream slots (always 3)
     */
    int get_num_streams() const;

private:
    struct Impl;
    Impl* p_;  ///< Pointer to implementation (PIMPL pattern)
};

// Temporary compatibility alias for existing code
using CudaFftEngineCpp = RtFftEngine;

} // namespace ionosense