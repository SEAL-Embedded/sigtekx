/**
 * @file test_pipeline_builder.cpp
 * @version 0.9.3
 * @date 2025-10-15
 * @author [Kevin Rahsaz]
 *
 * @brief Unit tests for the PipelineBuilder class.
 *
 * This test suite validates the PipelineBuilder's fluent interface, validation
 * logic, memory estimation, and ownership transfer semantics.
 */

#include <gtest/gtest.h>

#include "sigtekx/core/cuda_wrappers.hpp"
#include "sigtekx/core/pipeline_builder.hpp"
#include "sigtekx/core/processing_stage.hpp"

using namespace sigtekx;

/**
 * @class PipelineBuilderTest
 * @brief Test fixture for PipelineBuilder tests.
 */
class PipelineBuilderTest : public ::testing::Test {
 protected:
  void SetUp() override {
    // Check for CUDA device availability
    int device_count = 0;
    cudaError_t err = cudaGetDeviceCount(&device_count);
    if (err != cudaSuccess || device_count == 0) {
      GTEST_SKIP() << "No CUDA devices available for testing.";
    }

    // Standard configuration for tests
    config_.nfft = 512;
    config_.channels = 2;
    config_.overlap = 0.5f;
    config_.sample_rate_hz = 48000;
  }

  StageConfig config_;
};

// ============================================================================
//  Construction and Basic API Tests
// ============================================================================

TEST_F(PipelineBuilderTest, DefaultConstruction) {
  PipelineBuilder builder;
  EXPECT_EQ(builder.num_stages(), 0);
}

TEST_F(PipelineBuilderTest, WithConfig) {
  PipelineBuilder builder;
  builder.with_config(config_);
  // Config should be set (we can't directly inspect, but validation will check)
  EXPECT_EQ(builder.num_stages(), 0);
}

TEST_F(PipelineBuilderTest, AddWindowStage) {
  PipelineBuilder builder;
  builder.with_config(config_).add_window(StageConfig::WindowType::HANN);
  EXPECT_EQ(builder.num_stages(), 1);
}

TEST_F(PipelineBuilderTest, AddFFTStage) {
  PipelineBuilder builder;
  builder.with_config(config_).add_fft();
  EXPECT_EQ(builder.num_stages(), 1);
}

TEST_F(PipelineBuilderTest, AddMagnitudeStage) {
  PipelineBuilder builder;
  builder.with_config(config_).add_magnitude();
  EXPECT_EQ(builder.num_stages(), 1);
}

TEST_F(PipelineBuilderTest, FluentChaining) {
  PipelineBuilder builder;
  builder.with_config(config_)
      .add_window(StageConfig::WindowType::HANN)
      .add_fft()
      .add_magnitude();
  EXPECT_EQ(builder.num_stages(), 3);
}

TEST_F(PipelineBuilderTest, Clear) {
  PipelineBuilder builder;
  builder.with_config(config_)
      .add_window(StageConfig::WindowType::HANN)
      .add_fft();
  EXPECT_EQ(builder.num_stages(), 2);

  builder.clear();
  EXPECT_EQ(builder.num_stages(), 0);
}

// ============================================================================
//  Validation Tests
// ============================================================================

TEST_F(PipelineBuilderTest, ValidateEmptyPipeline) {
  PipelineBuilder builder;
  std::string error_msg;
  EXPECT_FALSE(builder.validate(error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("empty"), std::string::npos);
}

TEST_F(PipelineBuilderTest, ValidateValidPipeline) {
  PipelineBuilder builder;
  builder.with_config(config_)
      .add_window(StageConfig::WindowType::HANN)
      .add_fft()
      .add_magnitude();

  std::string error_msg;
  EXPECT_TRUE(builder.validate(error_msg));
  EXPECT_TRUE(error_msg.empty());
}

TEST_F(PipelineBuilderTest, ValidateInvalidNFFT) {
  StageConfig bad_config = config_;
  bad_config.nfft = 1000;  // Not a power of 2

  PipelineBuilder builder;
  builder.with_config(bad_config).add_fft();

  std::string error_msg;
  EXPECT_FALSE(builder.validate(error_msg));
  EXPECT_FALSE(error_msg.empty());
}

TEST_F(PipelineBuilderTest, ValidateInvalidBatch) {
  StageConfig bad_config = config_;
  bad_config.channels = 0;  // Not positive

  PipelineBuilder builder;
  builder.with_config(bad_config).add_fft();

  std::string error_msg;
  EXPECT_FALSE(builder.validate(error_msg));
  EXPECT_FALSE(error_msg.empty());
}

TEST_F(PipelineBuilderTest, ValidateInvalidOverlap) {
  StageConfig bad_config = config_;
  bad_config.overlap = 1.5f;  // Out of range [0, 1)

  PipelineBuilder builder;
  builder.with_config(bad_config).add_window(StageConfig::WindowType::HANN);

  std::string error_msg;
  EXPECT_FALSE(builder.validate(error_msg));
  EXPECT_FALSE(error_msg.empty());
}

// ============================================================================
//  Memory Estimation Tests
// ============================================================================

TEST_F(PipelineBuilderTest, EstimateMemoryUsageSingleStage) {
  PipelineBuilder builder;
  builder.with_config(config_).add_fft();

  size_t estimated = builder.estimate_memory_usage();
  EXPECT_GT(estimated, 0);
}

TEST_F(PipelineBuilderTest, EstimateMemoryUsageMultipleStages) {
  PipelineBuilder builder;
  builder.with_config(config_)
      .add_window(StageConfig::WindowType::HANN)
      .add_fft()
      .add_magnitude();

  size_t estimated = builder.estimate_memory_usage();

  // Memory should be reasonable for this config
  // nfft=512, batch=2 -> ~few KB to few MB range
  EXPECT_GT(estimated, 1024);                // > 1 KB
  EXPECT_LT(estimated, 1024 * 1024 * 1024);  // < 1 GB
}

TEST_F(PipelineBuilderTest, EstimateMemoryScalesWithConfig) {
  PipelineBuilder small_builder;
  small_builder.with_config(config_).add_fft();
  size_t small_estimate = small_builder.estimate_memory_usage();

  StageConfig large_config = config_;
  large_config.nfft = 4096;
  large_config.channels = 8;

  PipelineBuilder large_builder;
  large_builder.with_config(large_config).add_fft();
  size_t large_estimate = large_builder.estimate_memory_usage();

  EXPECT_GT(large_estimate, small_estimate);
}

// ============================================================================
//  Build and Ownership Transfer Tests
// ============================================================================

TEST_F(PipelineBuilderTest, BuildValidPipeline) {
  PipelineBuilder builder;
  builder.with_config(config_)
      .add_window(StageConfig::WindowType::HANN)
      .add_fft()
      .add_magnitude();

  auto stages = builder.build();
  EXPECT_EQ(stages.size(), 3);
  EXPECT_NE(stages[0], nullptr);
  EXPECT_NE(stages[1], nullptr);
  EXPECT_NE(stages[2], nullptr);

  // After build, builder should be cleared
  EXPECT_EQ(builder.num_stages(), 0);
}

TEST_F(PipelineBuilderTest, BuildInvalidPipelineThrows) {
  PipelineBuilder builder;
  // Empty pipeline should throw on build
  EXPECT_THROW(builder.build(), std::runtime_error);
}

TEST_F(PipelineBuilderTest, BuildTransfersOwnership) {
  PipelineBuilder builder;
  builder.with_config(config_).add_fft();

  auto stages = builder.build();
  ASSERT_EQ(stages.size(), 1);

  // Move ownership to another vector
  std::vector<std::unique_ptr<IProcessingStage>> moved_stages =
      std::move(stages);
  ASSERT_EQ(moved_stages.size(), 1);
  EXPECT_NE(moved_stages[0], nullptr);

  // Original vector should be empty after move
  EXPECT_EQ(stages.size(), 0);
}

TEST_F(PipelineBuilderTest, DoubleBuildClearsFirst) {
  PipelineBuilder builder;
  builder.with_config(config_).add_fft();

  auto stages1 = builder.build();
  EXPECT_EQ(stages1.size(), 1);
  EXPECT_EQ(builder.num_stages(), 0);

  // Build again - should work but return empty since builder was cleared
  builder.add_fft();
  auto stages2 = builder.build();
  EXPECT_EQ(stages2.size(), 1);
}

// ============================================================================
//  Custom Stage Addition Tests
// ============================================================================

TEST_F(PipelineBuilderTest, AddCustomStage) {
  PipelineBuilder builder;
  builder.with_config(config_);

  // Create a custom stage
  auto custom_stage = std::make_unique<WindowStage>();
  builder.add_stage(std::move(custom_stage));

  EXPECT_EQ(builder.num_stages(), 1);

  auto stages = builder.build();
  ASSERT_EQ(stages.size(), 1);
  EXPECT_EQ(stages[0]->name(), "WindowStage");
}

TEST_F(PipelineBuilderTest, MixCustomAndHelperStages) {
  PipelineBuilder builder;
  builder.with_config(config_);

  auto custom_window = std::make_unique<WindowStage>();
  builder.add_stage(std::move(custom_window))
      .add_fft()  // Helper method
      .add_magnitude();

  EXPECT_EQ(builder.num_stages(), 3);
}

// ============================================================================
//  Edge Case Tests
// ============================================================================

TEST_F(PipelineBuilderTest, SingleStagePipeline) {
  PipelineBuilder builder;
  builder.with_config(config_).add_window(StageConfig::WindowType::HANN);

  std::string error_msg;
  EXPECT_TRUE(builder.validate(error_msg));

  auto stages = builder.build();
  EXPECT_EQ(stages.size(), 1);
}

TEST_F(PipelineBuilderTest, TwoStagePipeline) {
  PipelineBuilder builder;
  builder.with_config(config_)
      .add_window(StageConfig::WindowType::HANN)
      .add_fft();

  auto stages = builder.build();
  EXPECT_EQ(stages.size(), 2);
}

TEST_F(PipelineBuilderTest, FourStagePipeline) {
  PipelineBuilder builder;
  builder.with_config(config_)
      .add_window(StageConfig::WindowType::HANN)
      .add_fft()
      .add_magnitude()
      .add_magnitude();  // Duplicate stage for testing

  auto stages = builder.build();
  EXPECT_EQ(stages.size(), 4);
}
