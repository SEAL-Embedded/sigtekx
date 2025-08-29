/**
 * @file fft_engine.hpp
 * @brief Public API for the ionosense real-time FFT engine.
 *
 * This header provides a stable public interface using the PIMPL idiom to hide
 * all CUDA implementation details from consumers, ensuring a clean and stable API
 * for both C++ and Python clients.
 */

#pragma once

#include <cstddef> // For std::size_t

namespace ionosense {

/**
 * @brief Configuration for the real-time FFT engine.
 * This struct is used to initialize the engine with all necessary parameters.
 */
struct RtFftConfig {
    int nfft;               ///< FFT size (must be a power of 2).
    int batch;              ///< Number of FFTs to process in parallel.
    bool use_graphs{true};  ///< Enable CUDA Graphs for reduced overhead.
    bool verbose{false};    ///< Enable verbose logging during initialization.
};

/**
 * @class RtFftEngine
 * @brief High-performance GPU-accelerated FFT engine with multi-stream concurrency.
 *
 * This engine provides a triple-buffered, multi-stream architecture for
 * maximum throughput FFT processing. It supports CUDA Graphs to minimize
 * kernel launch overhead in real-time scenarios.
 */
class RtFftEngine {
public:
    /**
     * @brief Construct the FFT engine with specified configuration.
     * @param config A validated RtFftConfig object.
     */
    explicit RtFftEngine(const RtFftConfig& config);

    /**
     * @brief Destructor to clean up all CUDA and cuFFT resources.
     */
    ~RtFftEngine();

    // --- Deleted copy/move semantics for safety ---
    // This prevents accidental copies which would lead to resource management issues.
    RtFftEngine(const RtFftEngine&) = delete;
    RtFftEngine& operator=(const RtFftEngine&) = delete;
    RtFftEngine(RtFftEngine&&) = delete;
    RtFftEngine& operator=(RtFftEngine&&) = delete;

    // --- Primary Methods ---

    /**
     * @brief Warms up streams and captures CUDA graphs if enabled.
     * This must be called once after construction and before the main processing loop.
     */
    void prepare_for_execution();

    /**
     * @brief Asynchronously executes the full FFT pipeline on a stream.
     * @param stream_idx The stream slot index (0, 1, or 2).
     */
    void execute_async(int stream_idx);

    /**
     * @brief Blocks the CPU until a specific stream's tasks are complete.
     * @param stream_idx The stream slot index (0, 1, or 2).
     */
    void sync_stream(int stream_idx);

    /**
     * @brief Blocks the CPU until all streams are complete.
     */
    void synchronize_all_streams();

    // --- Configuration ---
    void set_use_graphs(bool enable);
    bool get_use_graphs() const;
    bool graphs_ready() const;
    float get_last_exec_time_ms(int idx) const;

    // --- Buffer Accessors (for zero-copy) ---
    float* pinned_input(int idx) const;
    float* pinned_output(int idx) const;
    void set_window(const float* h_window_data);

    // --- Properties ---
    int get_fft_size() const;
    int get_batch_size() const;
    int get_num_streams() const;

private:
    // PIMPL: Forward-declare the implementation struct to hide CUDA details.
    struct Pimpl;
    Pimpl* p_;
};

// Compatibility alias for existing code or tests if needed.
using CudaFftEngineCpp = RtFftEngine;

} // namespace ionosense

