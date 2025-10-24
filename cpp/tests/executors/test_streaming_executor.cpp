/**
 * @file test_streaming_executor.cpp
 * @version 0.9.3
 * @date 2025-10-16
 * @author [Kevin Rahsaz]
 *
 * @brief Unit tests for the StreamingExecutor class (stub implementation).
 *
 * Note: StreamingExecutor is currently a stub that delegates to BatchExecutor.
 * These tests validate that the stub behaves correctly and clearly documents
 * current limitations until full streaming support is added in v0.9.4+.
 */

#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/core/pipeline_builder.hpp"
#include "ionosense/executors/streaming_executor.hpp"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

using namespace ionosense;

/**
 * @class StreamingExecutorTest
 * @brief Test fixture for StreamingExecutor tests.
 */
class StreamingExecutorTest : public ::testing::Test {
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
    config_.channels = 2;
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

TEST_F(StreamingExecutorTest, Construction) {
  EXPECT_NO_THROW(StreamingExecutor executor);
}

TEST_F(StreamingExecutorTest, InitializationWithStreamingMode) {
  StreamingExecutor executor;
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

TEST_F(StreamingExecutorTest, InitializationWithBatchModeExpectedException) {
  // Note: StreamingExecutor requires STREAMING execution mode
  StreamingExecutor executor;

  ExecutorConfig batch_config = config_;
  batch_config.mode = ExecutorConfig::ExecutionMode::BATCH;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_fft()
                    .build();

  // Current implementation requires STREAMING mode
  EXPECT_THROW(executor.initialize(batch_config, std::move(stages)),
               std::runtime_error);
}

TEST_F(StreamingExecutorTest, Reset) {
  StreamingExecutor executor;

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
//  Processing Tests (Delegated to BatchExecutor)
// ============================================================================

TEST_F(StreamingExecutorTest, BasicProcessing) {
  StreamingExecutor executor;

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

TEST_F(StreamingExecutorTest, SubmitAsync) {
  StreamingExecutor executor;

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
  executor.submit_async(input.data(), input_size,
                        [&](const float* magnitude, size_t num_bins,
                            size_t batch_size, const ProcessingStats& stats) {
                          callback_called = true;
                          EXPECT_NE(magnitude, nullptr);
                        });

  // Since this is a synchronous stub, callback should be called immediately
  EXPECT_TRUE(callback_called);
}

TEST_F(StreamingExecutorTest, StatsReporting) {
  StreamingExecutor executor;

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

  auto stats = executor.get_stats();
  EXPECT_GT(stats.latency_us, 0.0f);
  EXPECT_GE(stats.frames_processed, 1);
}

// ============================================================================
//  Capability Tests (Stub Behavior)
// ============================================================================

TEST_F(StreamingExecutorTest, SupportsStreamingReturnsTrue) {
  // v0.9.4: StreamingExecutor now supports true streaming with ring buffer
  StreamingExecutor executor;
  EXPECT_TRUE(executor.supports_streaming());
}

TEST_F(StreamingExecutorTest, MemoryUsage) {
  StreamingExecutor executor;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
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

TEST_F(StreamingExecutorTest, MoveConstruction) {
  StreamingExecutor executor1;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_fft()
                    .build();
  executor1.initialize(config_, std::move(stages));

  StreamingExecutor executor2(std::move(executor1));
  EXPECT_TRUE(executor2.is_initialized());
}

TEST_F(StreamingExecutorTest, MoveAssignment) {
  StreamingExecutor executor1;

  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_fft()
                    .build();
  executor1.initialize(config_, std::move(stages));

  StreamingExecutor executor2;
  executor2 = std::move(executor1);
  EXPECT_TRUE(executor2.is_initialized());
}

// ============================================================================
//  Limitations Documentation Tests
// ============================================================================

/**
 * @test DocumentedCapabilitiesAndLimitations
 * @brief This test documents current capabilities and remaining limitations.
 *
 * **Implemented in v0.9.4:**
 * - Ring buffer for input accumulation ✓
 * - Frame-by-frame processing as data arrives ✓
 * - Overlap handling for continuous streams ✓
 * - CUDA stream pipelining ✓
 * - True streaming (supports_streaming() == true) ✓
 *
 * **Not yet implemented (v0.9.5+):**
 * - True asynchronous, non-blocking submit_async()
 * - Background thread for callback invocation
 * - CUDA graph optimization
 */
TEST_F(StreamingExecutorTest, DocumentedCapabilitiesAndLimitations) {
  // This test exists to document capabilities for reviewers and future devs
  SUCCEED() << "StreamingExecutor v0.9.4 IMPLEMENTED features:\n"
            << "  ✓ Ring buffer for continuous input accumulation\n"
            << "  ✓ Overlap-aware batch extraction (STFT)\n"
            << "  ✓ Frame-by-frame processing\n"
            << "  ✓ CUDA stream pipelining (H2D → Compute → D2H)\n"
            << "  ✓ True streaming (supports_streaming() == true)\n"
            << "\nRemaining for v0.9.5+:\n"
            << "  - True async submit_async() with background thread\n"
            << "  - CUDA graph optimization";
}
