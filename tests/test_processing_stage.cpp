/**
 * @file test_processing_stage.cpp
 * @brief Unit tests for the processing stage interface and factory.
 *
 * Validates the Strategy pattern implementation, ensuring that stages can
 * be configured correctly and that the factory produces the right objects.
 */

#include <gtest/gtest.h>
#include "ionosense/processing_stage.hpp"

using namespace ionosense;

class ProcessingStageTest : public ::testing::Test {
protected:
    void SetUp() override {
        config.nfft = 2048;
        config.batch_size = 8;
        config.verbose = false;
    }
    ProcessingConfig config;
};

TEST_F(ProcessingStageTest, FactoryCreatesFftStage) {
    auto stage = ProcessingStageFactory::create("FFT");
    ASSERT_NE(stage, nullptr);
    EXPECT_EQ(stage->name(), "FFT");

    auto stage_lower = ProcessingStageFactory::create("fft");
    ASSERT_NE(stage_lower, nullptr);
    EXPECT_EQ(stage_lower->name(), "FFT");
}

TEST_F(ProcessingStageTest, FactoryThrowsOnUnknown) {
    EXPECT_THROW(ProcessingStageFactory::create("UnknownStage"), cuda::ConfigurationError);
}

TEST_F(ProcessingStageTest, FftStageConfiguration) {
    auto stage = std::make_unique<FftProcessingStage>();
    ASSERT_NO_THROW(stage->configure(config));
    
    EXPECT_EQ(stage->input_size(), 2048 * 8);
    EXPECT_EQ(stage->output_size(), (2048 / 2 + 1) * 8);
}

TEST_F(ProcessingStageTest, FftStageInvalidConfig) {
    auto stage = std::make_unique<FftProcessingStage>();
    
    // Test invalid nfft (not a power of 2)
    config.nfft = 1000;
    EXPECT_THROW(stage->configure(config), cuda::ConfigurationError);

    // Test invalid batch size
    config.nfft = 2048; // Reset nfft
    config.batch_size = 0;
    EXPECT_THROW(stage->configure(config), cuda::ConfigurationError);
}

TEST_F(ProcessingStageTest, FftStageInitialization) {
    auto stage = std::make_unique<FftProcessingStage>();
    stage->configure(config);

    // Initialization requires a valid CUDA stream
    cuda::Stream stream;
    ASSERT_NO_THROW(stage->initialize(stream));
    
    // Double initialization should be a no-op and not throw
    ASSERT_NO_THROW(stage->initialize(stream));
}
