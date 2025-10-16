/**
 * @file test_realtime_executor.cpp
 * @version 0.9.3
 * @date 2025-10-15
 * @author [Kevin Rahsaz]
 *
 * @brief Unit tests for the RealtimeExecutor class (stub implementation).
 *
 * Note: RealtimeExecutor is currently a stub that delegates to BatchExecutor.
 * These tests validate that the stub behaves correctly and clearly documents
 * current limitations until full streaming support is added in v0.10.0+.
 */

#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/core/pipeline_builder.hpp"
#include "ionosense/executors/realtime_executor.hpp"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

using namespace ionosense;

/**
 * @class RealtimeExecutorTest
 * @brief Test fixture for RealtimeExecutor tests.
 */
class RealtimeExecutorTest : public ::testing::Test {
 protected:
  void SetUp() override {
    // Check for CUDA device availability
    int device_count = 0;
    cudaError_t err = cudaGetDeviceCount(&device_count);
    if (err != cudaSuccess || device_count == 0) {
      GTEST_SKIP() << "No CUDA devices available for testing.";
    }

    // Standard executor configuration for streaming/low-latency mode
    config_.nfft = 512;
    config_.batch = 2;
    config_.overlap = 0.5f;
    config_.sample_rate_hz = 48000;
    config_.stream_count = 3;
    config_.pinned_buffer_count = 2;
    config_.warmup_iters = 1;
    config_.mode = ExecutorConfig::ExecutionMode::STREAMING;
    config_.max_inflight_batches = 2;
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

TEST_F(RealtimeExecutorTest, Construction) {
  EXPECT_NO_THROW(RealtimeExecutor executor);
}

TEST_F(RealtimeExecutorTest, InitializationWithStreamingMode) {
  RealtimeExecutor executor;
  EXPECT_FALSE(executor.is_initialized());

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.batch})
                     .add_window(StageConfig::WindowType::HANN)
                     .add_fft()
                     .add_magnitude()
                     .build();

  EXPECT_NO_THROW(executor.initialize(config_, std::move(stages)));
  EXPECT_TRUE(executor.is_initialized());
}

TEST_F(RealtimeExecutorTest, InitializationWithLowLatencyMode) {
  RealtimeExecutor executor;

  ExecutorConfig low_latency_config = config_;
  low_latency_config.mode = ExecutorConfig::ExecutionMode::LOW_LATENCY;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.batch})
                     .add_fft()
                     .build();

  EXPECT_NO_THROW(executor.initialize(low_latency_config, std::move(stages)));
  EXPECT_TRUE(executor.is_initialized());
}

TEST_F(RealtimeExecutorTest, InitializationWithBatchModeExpectedException) {
  // Note: This test documents expected behavior but implementation may vary
  // Currently RealtimeExecutor might accept BATCH mode and delegate to
  // BatchExecutor We test current behavior here.
  RealtimeExecutor executor;

  ExecutorConfig batch_config = config_;
  batch_config.mode = ExecutorConfig::ExecutionMode::BATCH;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.batch})
                     .add_fft()
                     .build();

  // Current implementation requires STREAMING or LOW_LATENCY
  EXPECT_THROW(executor.initialize(batch_config, std::move(stages)),
               std::runtime_error);
}

TEST_F(RealtimeExecutorTest, Reset) {
  RealtimeExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.batch})
                     .add_fft()
                     .build();
  executor.initialize(config_, std::move(stages));
  EXPECT_TRUE(executor.is_initialized());

  executor.reset();
  EXPECT_FALSE(executor.is_initialized());
}

// ============================================================================
//  Processing Tests (Delegated to BatchExecutor)
// ============================================================================

TEST_F(RealtimeExecutorTest, BasicProcessing) {
  RealtimeExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.batch})
                     .add_window(StageConfig::WindowType::HANN)
                     .add_fft()
                     .add_magnitude()
                     .build();
  executor.initialize(config_, std::move(stages));

  const size_t input_size = config_.nfft * config_.batch;
  const size_t output_size = config_.num_output_bins() * config_.batch;
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

TEST_F(RealtimeExecutorTest, SubmitAsync) {
  RealtimeExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.batch})
                     .add_window(StageConfig::WindowType::HANN)
                     .add_fft()
                     .add_magnitude()
                     .build();
  executor.initialize(config_, std::move(stages));

  const size_t input_size = config_.nfft * config_.batch;
  auto input = generate_sinusoid(input_size, 15.0f);

  bool callback_called = false;
  executor.submit_async(input.data(), input_size,
                        [&](const float* magnitude, size_t num_bins,
                            size_t batch_size, const ProcessingStats& stats) {
                          callback_called = true;
                          EXPECT_NE(magnitude, nullptr);
                        });

  // Since this is a synchronous stub, callback should be called immediately
  EXPECT_TRUE(callback_called);
}

TEST_F(RealtimeExecutorTest, StatsReporting) {
  RealtimeExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.batch})
                     .add_fft()
                     .build();
  executor.initialize(config_, std::move(stages));

  const size_t input_size = config_.nfft * config_.batch;
  const size_t output_size = config_.num_output_bins() * config_.batch * 2;
  auto input = generate_sinusoid(input_size, 10.0f);
  std::vector<float> output(output_size);

  executor.submit(input.data(), output.data(), input_size);

  auto stats = executor.get_stats();
  EXPECT_GT(stats.latency_us, 0.0f);
  EXPECT_GE(stats.frames_processed, 1);
}

// ============================================================================
//  Capability Tests (Stub Behavior)
// ============================================================================

TEST_F(RealtimeExecutorTest, SupportsStreamingReturnsFalse) {
  // v0.9.3: RealtimeExecutor is a stub and does NOT support true streaming
  RealtimeExecutor executor;
  EXPECT_FALSE(executor.supports_streaming());
}

TEST_F(RealtimeExecutorTest, MemoryUsage) {
  RealtimeExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.batch})
                     .add_fft()
                     .build();

  // Before initialization
  EXPECT_EQ(executor.get_memory_usage(), 0);

  executor.initialize(config_, std::move(stages));

  // After initialization (delegates to BatchExecutor)
  size_t memory = executor.get_memory_usage();
  EXPECT_GT(memory, 0);
}

// ============================================================================
//  Move Semantics Tests
// ============================================================================

TEST_F(RealtimeExecutorTest, MoveConstruction) {
  RealtimeExecutor executor1;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.batch})
                     .add_fft()
                     .build();
  executor1.initialize(config_, std::move(stages));

  RealtimeExecutor executor2(std::move(executor1));
  EXPECT_TRUE(executor2.is_initialized());
}

TEST_F(RealtimeExecutorTest, MoveAssignment) {
  RealtimeExecutor executor1;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.batch})
                     .add_fft()
                     .build();
  executor1.initialize(config_, std::move(stages));

  RealtimeExecutor executor2;
  executor2 = std::move(executor1);
  EXPECT_TRUE(executor2.is_initialized());
}

// ============================================================================
//  Limitations Documentation Tests
// ============================================================================

/**
 * @test DocumentedLimitations
 * @brief This test documents the current limitations of RealtimeExecutor.
 *
 * The following features are NOT implemented in v0.9.3:
 * - Ring buffer for input accumulation
 * - Frame-by-frame processing as data arrives
 * - True asynchronous, non-blocking behavior
 * - Overlap handling for continuous streams
 * - Background processing with callbacks
 *
 * All of these will be added in v0.10.0+.
 */
TEST_F(RealtimeExecutorTest, DocumentedLimitations) {
  // This test exists to document limitations for reviewers and future devs
  SUCCEED() << "RealtimeExecutor v0.9.3 is a STUB implementation.\n"
            << "It delegates to BatchExecutor and does NOT support:\n"
            << "  - True streaming (supports_streaming() == false)\n"
            << "  - Ring buffers\n"
            << "  - Input accumulation\n"
            << "  - Background processing\n"
            << "\nFull implementation planned for v0.10.0+";
}
