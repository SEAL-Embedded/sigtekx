/**
 * @file test_fft_engine.cpp
 * @brief Unit tests for the core C++ ionosense FFT engine.
 */

#define _USE_MATH_DEFINES // Required for M_PI on Windows
#include <cmath>
#include <gtest/gtest.h>
#include <vector>
#include <stdexcept>
#include <algorithm>
#include "ionosense/fft_engine.hpp"

namespace ionosense {

// Test fixture for FFT engine tests
class FftEngineTest : public ::testing::Test {
protected:
    void SetUp() override {
        config.nfft = 1024;
        config.batch = 4;
        config.use_graphs = true;
        config.verbose = false;
    }

    RtFftConfig config;
};

TEST_F(FftEngineTest, Construction) {
    ASSERT_NO_THROW({
        RtFftEngine engine(config);
        EXPECT_EQ(engine.get_fft_size(), 1024);
        EXPECT_EQ(engine.get_batch_size(), 4);
        EXPECT_EQ(engine.get_num_streams(), 3);
        EXPECT_TRUE(engine.get_use_graphs());
    });
}

// Test legacy interface compatibility alias
TEST_F(FftEngineTest, LegacyInterfaceTest) {
    config.use_graphs = false;
    // Use the compatibility alias
    ASSERT_NO_THROW({
        CudaFftEngineCpp engine(config);
        EXPECT_EQ(engine.get_fft_size(), 1024);
        EXPECT_FALSE(engine.get_use_graphs());
    });
}

TEST_F(FftEngineTest, BufferAccessTest) {
    RtFftEngine engine(config);
    for (int i = 0; i < engine.get_num_streams(); ++i) {
        float* input = engine.pinned_input(i);
        float* output = engine.pinned_output(i);
        EXPECT_NE(input, nullptr);
        EXPECT_NE(output, nullptr);
    }
}

TEST_F(FftEngineTest, InvalidStreamIndexTest) {
    RtFftEngine engine(config);
    EXPECT_THROW(engine.execute_async(-1), std::out_of_range);
    EXPECT_THROW(engine.execute_async(3), std::out_of_range);
    EXPECT_THROW(engine.sync_stream(-1), std::out_of_range);
    EXPECT_THROW(engine.sync_stream(3), std::out_of_range);
    EXPECT_THROW(engine.pinned_input(-1), std::out_of_range);
    EXPECT_THROW(engine.pinned_output(3), std::out_of_range);
}

TEST_F(FftEngineTest, WindowFunctionTest) {
    RtFftEngine engine(config);
    std::vector<float> h_window(config.nfft);
    for (int i = 0; i < config.nfft; ++i) {
        h_window[i] = 0.5f * (1.0f - cos(2.0f * M_PI * i / (config.nfft - 1)));
    }
    ASSERT_NO_THROW(engine.set_window(h_window.data()));
}

} // namespace ionosense
