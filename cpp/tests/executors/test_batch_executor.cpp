/**
 * @file test_batch_executor.cpp
 * @version 0.9.3
 * @date 2025-10-15
 * @author [Kevin Rahsaz]
 *
 * @brief Unit tests for the BatchExecutor class.
 *
 * This test suite validates BatchExecutor's pipeline execution logic,
 * configuration handling, multi-stage support, and resource management.
 */

#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "sigtekx/core/cuda_wrappers.hpp"
#include "sigtekx/core/pipeline_builder.hpp"
#include "sigtekx/executors/batch_executor.hpp"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

using namespace sigtekx;

/**
 * @class BatchExecutorTest
 * @brief Test fixture for BatchExecutor tests.
 */
class BatchExecutorTest : public ::testing::Test {
 protected:
  void SetUp() override {
    // Check for CUDA device availability
    int device_count = 0;
    cudaError_t err = cudaGetDeviceCount(&device_count);
    if (err != cudaSuccess || device_count == 0) {
      GTEST_SKIP() << "No CUDA devices available for testing.";
    }

    // Standard executor configuration
    config_.nfft = 512;
    config_.channels = 2;
    config_.overlap = 0.5f;
    config_.sample_rate_hz = 48000;
    config_.stream_count = 3;
    config_.pinned_buffer_count = 2;
    config_.warmup_iters = 1;
  }

  std::vector<float> generate_sinusoid(size_t size, float frequency) {
    std::vector<float> signal(size);
    for (size_t i = 0; i < size; ++i) {
      signal[i] = std::sin(2.0f * M_PI * frequency * i / size);
    }
    return signal;
  }

  ExecutorConfig config_;
};

// ============================================================================
//  Construction and Initialization Tests
// ============================================================================

TEST_F(BatchExecutorTest, Construction) {
  EXPECT_NO_THROW(BatchExecutor executor);
}

TEST_F(BatchExecutorTest, InitializationWithStandardPipeline) {
  BatchExecutor executor;
  EXPECT_FALSE(executor.is_initialized());

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_window(StageConfig::WindowType::HANN)
                    .add_fft()
                    .add_magnitude()
                    .build();

  EXPECT_NO_THROW(executor.initialize(config_, std::move(stages)));
  EXPECT_TRUE(executor.is_initialized());
}

TEST_F(BatchExecutorTest, InitializeWithEmptyPipelineFails) {
  BatchExecutor executor;
  std::vector<std::unique_ptr<IProcessingStage>> empty_stages;

  EXPECT_THROW(executor.initialize(config_, std::move(empty_stages)),
               std::runtime_error);
}

TEST_F(BatchExecutorTest, InitializeWithInvalidConfigFails) {
  BatchExecutor executor;

  ExecutorConfig bad_config = config_;
  bad_config.nfft = 1000;  // Not a power of 2

  // The PipelineBuilder validates nfft during build(), so we need to catch
  // the exception from build() itself, not from executor.initialize()
  EXPECT_THROW(
      {
        PipelineBuilder builder;
        auto stages =
            builder
                .with_config(StageConfig{bad_config.nfft, bad_config.channels})
                .add_fft()
                .build();
        executor.initialize(bad_config, std::move(stages));
      },
      std::runtime_error);
}

TEST_F(BatchExecutorTest, DoubleInitialization) {
  BatchExecutor executor;

  PipelineBuilder builder1;
  auto stages1 =
      builder1.with_config(StageConfig{config_.nfft, config_.channels})
          .add_fft()
          .build();
  executor.initialize(config_, std::move(stages1));
  EXPECT_TRUE(executor.is_initialized());

  // Re-initialize should work (triggers reset first)
  PipelineBuilder builder2;
  auto stages2 =
      builder2.with_config(StageConfig{config_.nfft, config_.channels})
          .add_fft()
          .build();
  EXPECT_NO_THROW(executor.initialize(config_, std::move(stages2)));
  EXPECT_TRUE(executor.is_initialized());
}

TEST_F(BatchExecutorTest, Reset) {
  BatchExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_fft()
                    .build();
  executor.initialize(config_, std::move(stages));
  EXPECT_TRUE(executor.is_initialized());

  executor.reset();
  EXPECT_FALSE(executor.is_initialized());
}

// ============================================================================
//  Multi-Stage Pipeline Tests
// ============================================================================

TEST_F(BatchExecutorTest, SingleStagePipeline) {
  BatchExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_window(StageConfig::WindowType::HANN)
                    .build();
  executor.initialize(config_, std::move(stages));

  const size_t input_size = config_.nfft * config_.channels;
  auto input = generate_sinusoid(input_size, 10.0f);
  std::vector<float> output(input_size);

  EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));
}

TEST_F(BatchExecutorTest, TwoStagePipeline) {
  BatchExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_window(StageConfig::WindowType::HANN)
                    .add_fft()
                    .build();
  executor.initialize(config_, std::move(stages));

  const size_t input_size = config_.nfft * config_.channels;
  const size_t output_size = config_.num_output_bins() * config_.channels * 2;
  auto input = generate_sinusoid(input_size, 10.0f);
  std::vector<float> output(output_size);

  EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));
}

TEST_F(BatchExecutorTest, ThreeStagePipeline) {
  BatchExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_window(StageConfig::WindowType::HANN)
                    .add_fft()
                    .add_magnitude()
                    .build();
  executor.initialize(config_, std::move(stages));

  const size_t input_size = config_.nfft * config_.channels;
  const size_t output_size = config_.num_output_bins() * config_.channels;
  auto input = generate_sinusoid(input_size, 10.0f);
  std::vector<float> output(output_size);

  EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));

  // Verify output has non-zero values
  bool has_nonzero = false;
  for (float val : output) {
    if (val > 1e-6f) {
      has_nonzero = true;
      break;
    }
  }
  EXPECT_TRUE(has_nonzero);
}

TEST_F(BatchExecutorTest, FourStagePipeline) {
  // Test with 4 stages (window, fft, magnitude, magnitude)
  // This validates the generalized stage loop
  BatchExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_window(StageConfig::WindowType::HANN)
                    .add_fft()
                    .add_magnitude()
                    .add_magnitude()  // Extra stage
                    .build();
  executor.initialize(config_, std::move(stages));

  const size_t input_size = config_.nfft * config_.channels;
  const size_t output_size = config_.num_output_bins() * config_.channels;
  auto input = generate_sinusoid(input_size, 10.0f);
  std::vector<float> output(output_size);

  EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));
}

// ============================================================================
//  Processing and Statistics Tests
// ============================================================================

TEST_F(BatchExecutorTest, BasicProcessing) {
  BatchExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_window(StageConfig::WindowType::HANN)
                    .add_fft()
                    .add_magnitude()
                    .build();
  executor.initialize(config_, std::move(stages));

  const size_t input_size = config_.nfft * config_.channels;
  const size_t output_size = config_.num_output_bins() * config_.channels;
  auto input = generate_sinusoid(input_size, 10.0f);
  std::vector<float> output(output_size);

  executor.submit(input.data(), output.data(), input_size);

  auto stats = executor.get_stats();
  EXPECT_GT(stats.latency_us, 0.0f);
  EXPECT_LT(stats.latency_us, 10000.0f);  // Sanity check: < 10ms
  EXPECT_GE(stats.frames_processed, 1);
  EXPECT_FALSE(stats.is_warmup);
}

TEST_F(BatchExecutorTest, MultipleFrameProcessing) {
  BatchExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_window(StageConfig::WindowType::HANN)
                    .add_fft()
                    .add_magnitude()
                    .build();
  executor.initialize(config_, std::move(stages));

  const size_t input_size = config_.nfft * config_.channels;
  const size_t output_size = config_.num_output_bins() * config_.channels;
  const int num_frames = 10;

  for (int i = 0; i < num_frames; ++i) {
    auto input = generate_sinusoid(input_size, 10.0f + i);
    std::vector<float> output(output_size);
    EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));
  }

  auto stats = executor.get_stats();
  EXPECT_EQ(stats.frames_processed, static_cast<size_t>(num_frames));
}

TEST_F(BatchExecutorTest, StatsProgression) {
  BatchExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_fft()
                    .build();
  executor.initialize(config_, std::move(stages));

  const size_t input_size = config_.nfft * config_.channels;
  const size_t output_size = config_.num_output_bins() * config_.channels * 2;
  auto input = generate_sinusoid(input_size, 10.0f);
  std::vector<float> output(output_size);

  executor.submit(input.data(), output.data(), input_size);
  auto stats1 = executor.get_stats();
  EXPECT_EQ(stats1.frames_processed, 1);

  executor.submit(input.data(), output.data(), input_size);
  auto stats2 = executor.get_stats();
  EXPECT_EQ(stats2.frames_processed, 2);
}

// ============================================================================
//  Async and Synchronization Tests
// ============================================================================

TEST_F(BatchExecutorTest, SubmitAsync) {
  BatchExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_window(StageConfig::WindowType::HANN)
                    .add_fft()
                    .add_magnitude()
                    .build();
  executor.initialize(config_, std::move(stages));

  const size_t input_size = config_.nfft * config_.channels;
  auto input = generate_sinusoid(input_size, 15.0f);

  bool callback_called = false;
  size_t received_bins = 0;

  executor.submit_async(input.data(), input_size,
                        [&](const float* magnitude, size_t num_bins,
                            size_t num_frames, const ProcessingStats& stats) {
                          callback_called = true;
                          received_bins = num_bins;
                          EXPECT_NE(magnitude, nullptr);
                          EXPECT_GT(stats.latency_us, 0.0f);
                        });

  EXPECT_TRUE(callback_called);  // Synchronous implementation
  EXPECT_EQ(received_bins, static_cast<size_t>(config_.num_output_bins()));
}

TEST_F(BatchExecutorTest, Synchronize) {
  BatchExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_fft()
                    .build();
  executor.initialize(config_, std::move(stages));

  const size_t input_size = config_.nfft * config_.channels;
  const size_t output_size = config_.num_output_bins() * config_.channels * 2;
  auto input = generate_sinusoid(input_size, 10.0f);
  std::vector<float> output(output_size);

  executor.submit(input.data(), output.data(), input_size);
  EXPECT_NO_THROW(executor.synchronize());
}

// ============================================================================
//  Resource Management Tests
// ============================================================================

TEST_F(BatchExecutorTest, MemoryUsage) {
  BatchExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_window(StageConfig::WindowType::HANN)
                    .add_fft()
                    .add_magnitude()
                    .build();

  // Before initialization
  EXPECT_EQ(executor.get_memory_usage(), 0);

  executor.initialize(config_, std::move(stages));

  // After initialization
  size_t memory = executor.get_memory_usage();
  EXPECT_GT(memory, 0);
  EXPECT_LT(memory, 1024 * 1024 * 1024);  // Sanity check: < 1GB
}

TEST_F(BatchExecutorTest, SupportsStreaming) {
  BatchExecutor executor;
  EXPECT_FALSE(executor.supports_streaming());
}

// ============================================================================
//  Move Semantics Tests
// ============================================================================

TEST_F(BatchExecutorTest, MoveConstruction) {
  BatchExecutor executor1;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_fft()
                    .build();
  executor1.initialize(config_, std::move(stages));

  BatchExecutor executor2(std::move(executor1));
  EXPECT_TRUE(executor2.is_initialized());
}

TEST_F(BatchExecutorTest, MoveAssignment) {
  BatchExecutor executor1;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_fft()
                    .build();
  executor1.initialize(config_, std::move(stages));

  BatchExecutor executor2;
  executor2 = std::move(executor1);
  EXPECT_TRUE(executor2.is_initialized());
}

// ============================================================================
//  Configuration Validation Tests
// ============================================================================

TEST_F(BatchExecutorTest, ConfigValidationInvalidMaxInflightBatches) {
  ExecutorConfig invalid_config = config_;
  invalid_config.max_inflight_batches = 0;  // Invalid: must be >= 1

  std::string error_msg;
  EXPECT_FALSE(invalid_config.validate(error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("max_inflight_batches"), std::string::npos);
}

TEST_F(BatchExecutorTest, ConfigValidationStreamingModeInsufficientBuffers) {
  ExecutorConfig invalid_config = config_;
  invalid_config.mode = ExecutorConfig::ExecutionMode::STREAMING;
  invalid_config.max_inflight_batches = 3;
  invalid_config.pinned_buffer_count =
      2;  // Invalid: must be >= max_inflight_batches

  std::string error_msg;
  EXPECT_FALSE(invalid_config.validate(error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("pinned_buffer_count"), std::string::npos);
}

TEST_F(BatchExecutorTest, ConfigValidationSuccess) {
  ExecutorConfig valid_config = config_;
  valid_config.mode = ExecutorConfig::ExecutionMode::STREAMING;
  valid_config.max_inflight_batches = 2;
  valid_config.pinned_buffer_count = 3;  // Valid: >= max_inflight_batches

  std::string error_msg;
  EXPECT_TRUE(valid_config.validate(error_msg));
  EXPECT_TRUE(error_msg.empty());
}
