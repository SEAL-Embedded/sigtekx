/**
 * @file gtest_cuda_fft.cpp
 * @brief GoogleTest suite for the concurrent, 3-stream CudaFftEngineCpp.
 *
 * This test suite validates the new asynchronous, multi-stream FFT engine.
 *
 * Key Tests:
 * - API Accessors: Verifies correct properties (NFFT, batch, stream count).
 * - Correctness (Zero Input): Ensures zero input produces zero output.
 * - Correctness (DC Signal): Verifies a constant input produces the expected DC component.
 * - Correctness (Sine Wave): Verifies a pure sine wave produces a peak in the correct bin.
 * - Stream Independence: Launches unique workloads on all three streams concurrently
 * to confirm no data races or interference.
 * - Correctness with Graphs Disabled: Repeats a key correctness test with CUDA Graphs
 * turned off to validate the traditional execution path.
 * - API Error Handling: Ensures out-of-bounds indices throw exceptions as expected.
 *
 * All tests use an FFT size of N=32 and a batch size of 2 channels.
 * Tolerance for floating-point comparisons is ε=1e-5.
 */

#include <gtest/gtest.h>
#include <memory>
#include <vector>
#include <numeric>
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <math_constants.h>
#include "cuda_fft.h"

 // Test constants
static constexpr float kEps = 1e-5f;
static constexpr int NFFT = 32;
static constexpr int BATCH = 2;
static constexpr int BINS_PER_CHANNEL = NFFT / 2 + 1;
static constexpr int TOTAL_BINS = BINS_PER_CHANNEL * BATCH;
static constexpr int TOTAL_INPUT_SAMPLES = NFFT * BATCH;

/**
 * @brief Test fixture for the multi-stream CudaFftEngineCpp.
 */
class CudaFftEngineTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Default engine uses graphs
        engine_ = std::make_unique<CudaFftEngineCpp>(NFFT, BATCH);
    }

    std::unique_ptr<CudaFftEngineCpp> engine_;
};

// --- Test Cases ---

/**
 * @brief Verifies that API accessors return correct values and buffer pointers are valid.
 */
TEST_F(CudaFftEngineTest, AccessorsAndBuffersAreValid) {
    ASSERT_NE(engine_, nullptr);
    EXPECT_EQ(engine_->get_fft_size(), NFFT);
    EXPECT_EQ(engine_->get_batch_size(), BATCH);
    EXPECT_EQ(engine_->get_num_streams(), 3);

    for (int i = 0; i < engine_->get_num_streams(); ++i) {
        ASSERT_NE(engine_->pinned_input(i), nullptr) << "Input buffer for stream " << i << " is null.";
        ASSERT_NE(engine_->pinned_output(i), nullptr) << "Output buffer for stream " << i << " is null.";
    }
}

/**
 * @brief Tests that a zero-level input signal results in a zero-magnitude spectrum.
 */
TEST_F(CudaFftEngineTest, ZeroInputProducesZeroOutput) {
    const int stream_idx = 0;
    float* input_ptr = engine_->pinned_input(stream_idx);
    float* output_ptr = engine_->pinned_output(stream_idx);

    // This test does not require a window as the input is all zeros.
    std::fill_n(input_ptr, TOTAL_INPUT_SAMPLES, 0.0f);

    engine_->execute_async(stream_idx);
    engine_->sync_stream(stream_idx);

    for (int i = 0; i < TOTAL_BINS; ++i) {
        EXPECT_NEAR(output_ptr[i], 0.0f, kEps) << "Mismatch at bin " << i;
    }
}

/**
 * @brief Tests that a constant DC input signal produces the known FFT of a Hann window.
 * The FFT of a Hann-windowed DC signal is the FFT of the Hann window itself, which
 * has a specific, known structure: a peak at DC (N/2), smaller peaks at bin 1 (-N/4),
 * and zeros elsewhere.
 */
TEST_F(CudaFftEngineTest, DCInputProducesDCPeak) {
    const int stream_idx = 1;
    float* input_ptr = engine_->pinned_input(stream_idx);
    float* output_ptr = engine_->pinned_output(stream_idx);

    // Create and set the window, which is now required by the engine
    std::vector<float> hann_window(NFFT);
    for (int i = 0; i < NFFT; ++i) {
        hann_window[i] = 0.5f * (1.0f - cosf(2.0f * CUDART_PI_F * i / NFFT));
    }
    engine_->set_window(hann_window.data());

    std::fill_n(input_ptr, TOTAL_INPUT_SAMPLES, 1.0f);

    engine_->execute_async(stream_idx);
    engine_->sync_stream(stream_idx);

    const float expected_dc_mag = static_cast<float>(NFFT) / 2.0f; // 16.0
    const float expected_bin1_mag = static_cast<float>(NFFT) / 4.0f; // 8.0

    for (int ch = 0; ch < BATCH; ++ch) {
        const int offset = ch * BINS_PER_CHANNEL;

        // 1. Verify Bin 0 (DC component)
        EXPECT_NEAR(output_ptr[offset + 0], expected_dc_mag, kEps)
            << "Mismatch in DC bin for channel " << ch;

        // 2. Verify Bin 1 (First side-lobe of Hann window)
        EXPECT_NEAR(output_ptr[offset + 1], expected_bin1_mag, kEps)
            << "Mismatch in Bin 1 for channel " << ch;

        // 3. Verify all other bins are zero
        for (int i = 2; i < BINS_PER_CHANNEL; ++i) {
            EXPECT_NEAR(output_ptr[offset + i], 0.0f, kEps)
                << "Mismatch in zero-bin " << i << " for channel " << ch;
        }
    }
}


/**
 * @brief Tests a pure sine wave input, which should produce a single peak in the corresponding frequency bin.
 */
TEST_F(CudaFftEngineTest, SineWaveInputProducesCorrectFrequencyPeak) {
    const int stream_idx = 2;
    float* input_ptr = engine_->pinned_input(stream_idx);
    float* output_ptr = engine_->pinned_output(stream_idx);

    // Create and set the window, which is now required by the engine
    std::vector<float> hann_window(NFFT);
    for (int i = 0; i < NFFT; ++i) {
        hann_window[i] = 0.5f * (1.0f - cosf(2.0f * CUDART_PI_F * i / NFFT));
    }
    engine_->set_window(hann_window.data());

    const int sine_wave_bin = 4;
    std::vector<float> ch1(NFFT), ch2(NFFT);
    for (int i = 0; i < NFFT; ++i) {
        float val = sin(2.0 * CUDART_PI_F * sine_wave_bin * i / NFFT);
        ch1[i] = val;
        ch2[i] = val; // Use the same signal for both channels
    }

    std::copy(ch1.begin(), ch1.end(), input_ptr);
    std::copy(ch2.begin(), ch2.end(), input_ptr + NFFT);

    engine_->execute_async(stream_idx);
    engine_->sync_stream(stream_idx);

    for (int ch = 0; ch < BATCH; ++ch) {
        float max_mag = -1.0f;
        int peak_bin = -1;
        const int offset = ch * BINS_PER_CHANNEL;

        for (int i = 0; i < BINS_PER_CHANNEL; ++i) {
            if (output_ptr[offset + i] > max_mag) {
                max_mag = output_ptr[offset + i];
                peak_bin = i;
            }
        }
        EXPECT_GT(max_mag, 0.0f) << "Max magnitude should be positive for channel " << ch;
        EXPECT_EQ(peak_bin, sine_wave_bin) << "Peak frequency bin is incorrect for channel " << ch;
    }
}

/**
 * @brief Verifies that all three streams can run concurrently with different inputs
 * and produce the correct, independent outputs without interference.
 */
TEST_F(CudaFftEngineTest, StreamsAreIndependent) {
    // Create and set the window once for the main engine instance
    std::vector<float> hann_window(NFFT);
    for (int i = 0; i < NFFT; ++i) {
        hann_window[i] = 0.5f * (1.0f - cosf(2.0f * CUDART_PI_F * i / NFFT));
    }
    engine_->set_window(hann_window.data());

    // Stream 0: Zero input
    std::fill_n(engine_->pinned_input(0), TOTAL_INPUT_SAMPLES, 0.0f);

    // Stream 1: DC input
    std::fill_n(engine_->pinned_input(1), TOTAL_INPUT_SAMPLES, 1.0f);

    // Stream 2: Sine wave input (peak at bin 4)
    std::vector<float> input2_ch1(NFFT), input2_ch2(NFFT);
    const int sine_wave_bin = 4;
    for (int i = 0; i < NFFT; ++i) {
        float val = sin(2.0 * CUDART_PI_F * sine_wave_bin * i / NFFT);
        input2_ch1[i] = val;
        input2_ch2[i] = val;
    }

    float* input_ptr_2 = engine_->pinned_input(2);
    std::copy(input2_ch1.begin(), input2_ch1.end(), input_ptr_2);
    std::copy(input2_ch2.begin(), input2_ch2.end(), input_ptr_2 + NFFT);

    // Launch all three streams asynchronously
    engine_->execute_async(0);
    engine_->execute_async(1);
    engine_->execute_async(2);

    // Synchronize all streams
    engine_->sync_stream(0);
    engine_->sync_stream(1);
    engine_->sync_stream(2);

    // Verify Stream 0 (Zero input -> Zero output)
    for (int i = 0; i < TOTAL_BINS; ++i) {
        EXPECT_NEAR(engine_->pinned_output(0)[i], 0.0f, kEps) << "Stream 0 failed at bin " << i;
    }

    // Verify Stream 1 (DC input -> correct Hann FFT)
    const float expected_dc_mag = static_cast<float>(NFFT) / 2.0f;
    const float expected_bin1_mag = static_cast<float>(NFFT) / 4.0f;
    for (int ch = 0; ch < BATCH; ++ch) {
        const int offset = ch * BINS_PER_CHANNEL;
        EXPECT_NEAR(engine_->pinned_output(1)[offset + 0], expected_dc_mag, kEps)
            << "Stream 1 failed at DC bin for channel " << ch;
        EXPECT_NEAR(engine_->pinned_output(1)[offset + 1], expected_bin1_mag, kEps)
            << "Stream 1 failed at Bin 1 for channel " << ch;
    }

    // Verify Stream 2 (Sine wave -> correct peak bin)
    for (int ch = 0; ch < BATCH; ++ch) {
        float max_mag = -1.0f;
        int peak_bin = -1;
        const int offset = ch * BINS_PER_CHANNEL;
        for (int i = 0; i < BINS_PER_CHANNEL; ++i) {
            if (engine_->pinned_output(2)[offset + i] > max_mag) {
                max_mag = engine_->pinned_output(2)[offset + i];
                peak_bin = i;
            }
        }
        EXPECT_EQ(peak_bin, sine_wave_bin) << "Stream 2 failed for channel " << ch;
    }
}

/**
 * @brief Verifies correctness with CUDA Graphs disabled.
 * This ensures the traditional (non-graphed) execution path is also correct.
 */
TEST_F(CudaFftEngineTest, CorrectnessWithGraphsDisabled) {
    // Create a new engine with graphs explicitly disabled
    auto non_graph_engine = std::make_unique<CudaFftEngineCpp>(NFFT, BATCH, false);

    // Create and set the window for the new engine instance
    std::vector<float> hann_window(NFFT);
    for (int i = 0; i < NFFT; ++i) {
        hann_window[i] = 0.5f * (1.0f - cosf(2.0f * CUDART_PI_F * i / NFFT));
    }
    non_graph_engine->set_window(hann_window.data());

    const int stream_idx = 0;
    float* input_ptr = non_graph_engine->pinned_input(stream_idx);
    float* output_ptr = non_graph_engine->pinned_output(stream_idx);

    // Use the same sine wave test as before
    const int sine_wave_bin = 4;
    std::vector<float> ch1(NFFT), ch2(NFFT);
    for (int i = 0; i < NFFT; ++i) {
        float val = sin(2.0 * CUDART_PI_F * sine_wave_bin * i / NFFT);
        ch1[i] = val;
        ch2[i] = val;
    }

    std::copy(ch1.begin(), ch1.end(), input_ptr);
    std::copy(ch2.begin(), ch2.end(), input_ptr + NFFT);

    non_graph_engine->execute_async(stream_idx);
    non_graph_engine->sync_stream(stream_idx);

    for (int ch = 0; ch < BATCH; ++ch) {
        float max_mag = -1.0f;
        int peak_bin = -1;
        const int offset = ch * BINS_PER_CHANNEL;
        for (int i = 0; i < BINS_PER_CHANNEL; ++i) {
            if (output_ptr[offset + i] > max_mag) {
                max_mag = output_ptr[offset + i];
                peak_bin = i;
            }
        }
        EXPECT_EQ(peak_bin, sine_wave_bin) << "Peak frequency bin is incorrect for channel " << ch;
    }
}

/**
 * @brief Verifies the API throws exceptions for invalid indices.
 */
TEST_F(CudaFftEngineTest, ApiThrowsOnInvalidIndex) {
    // Test indices that are out of bounds (valid indices are 0, 1, 2)
    EXPECT_THROW(engine_->execute_async(-1), std::out_of_range);
    EXPECT_THROW(engine_->execute_async(3), std::out_of_range);
    EXPECT_THROW(engine_->sync_stream(-1), std::out_of_range);
    EXPECT_THROW(engine_->sync_stream(3), std::out_of_range);
    EXPECT_THROW(engine_->pinned_input(-1), std::out_of_range);
    EXPECT_THROW(engine_->pinned_input(3), std::out_of_range);
}