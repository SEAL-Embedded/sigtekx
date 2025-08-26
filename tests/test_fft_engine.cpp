/**
 * @file test_fft_engine.cpp
 * @brief Unit tests for the core C++ ionosense FFT engine
 */

#include <gtest/gtest.h>
#include <vector>
#include <stdexcept>
#include <algorithm>
#include "ionosense/fft_engine.hpp"

// Test fixture for FFT engine tests
class FftEngineTest : public ::testing::Test {};

// Test basic construction and properties
TEST_F(FftEngineTest, ConstructionTest) {
    ionosense::RtFftConfig config;
    config.nfft = 1024;
    config.batch = 4;
    config.use_graphs = true;
    
    ionosense::RtFftEngine engine(config);
    
    EXPECT_EQ(engine.get_fft_size(), 1024);
    EXPECT_EQ(engine.get_batch_size(), 4);
    EXPECT_EQ(engine.get_num_streams(), 3);
    EXPECT_TRUE(engine.get_use_graphs());
}

// Test legacy interface compatibility for backward compatibility
TEST_F(FftEngineTest, LegacyInterfaceTest) {
    ionosense::RtFftConfig config;
    config.nfft = 512;
    config.batch = 2;
    config.use_graphs = false;
    
    // Use the compatibility alias
    ionosense::CudaFftEngineCpp engine(config);
    
    EXPECT_EQ(engine.get_fft_size(), 512);
    EXPECT_EQ(engine.get_batch_size(), 2);
    EXPECT_FALSE(engine.get_use_graphs());
}

// Test that pinned memory buffers are accessible via the C++ API
TEST_F(FftEngineTest, BufferAccessTest) {
    ionosense::RtFftConfig config;
    config.nfft = 256;
    config.batch = 1;
    
    ionosense::RtFftEngine engine(config);
    
    // Check that we can access buffers for all streams without error
    for (int i = 0; i < engine.get_num_streams(); ++i) {
        float* input = engine.pinned_input(i);
        float* output = engine.pinned_output(i);
        
        EXPECT_NE(input, nullptr);
        EXPECT_NE(output, nullptr);
    }
}

// Test that out-of-bounds access throws the correct C++ exception
TEST_F(FftEngineTest, InvalidStreamIndexTest) {
    ionosense::RtFftConfig config;
    config.nfft = 256;
    config.batch = 1;

    ionosense::RtFftEngine engine(config);
    
    // Test that invalid indices throw std::out_of_range
    EXPECT_THROW(engine.execute_async(-1), std::out_of_range);
    EXPECT_THROW(engine.execute_async(3), std::out_of_range);
    EXPECT_THROW(engine.sync_stream(-1), std::out_of_range);
    EXPECT_THROW(engine.sync_stream(3), std::out_of_range);
    EXPECT_THROW(engine.pinned_input(-1), std::out_of_range);
    EXPECT_THROW(engine.pinned_output(3), std::out_of_range);
}