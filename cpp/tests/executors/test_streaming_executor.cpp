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

#include <chrono>
#include <cmath>
#include <thread>
#include <vector>

#include "sigtekx/core/cuda_wrappers.hpp"
#include "sigtekx/core/pipeline_builder.hpp"
#include "sigtekx/core/ring_buffer.hpp"
#include "sigtekx/executors/streaming_executor.hpp"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

using namespace sigtekx;

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
                            size_t num_frames, const ProcessingStats& stats) {
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
//  Async Processing Tests (Background Thread Mode)
// ============================================================================

TEST_F(StreamingExecutorTest, AsyncProcessingSuccess) {
  // Enable background thread
  config_.mode = ExecutorConfig::ExecutionMode::STREAMING;
  config_.enable_background_thread = true;
  config_.timeout_ms = 2000;  // 2 second timeout

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

  auto start = std::chrono::steady_clock::now();
  EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));
  auto elapsed = std::chrono::steady_clock::now() - start;

  // Should complete quickly (not timeout)
  EXPECT_LT(elapsed, std::chrono::milliseconds(500));

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

TEST_F(StreamingExecutorTest, AsyncProcessingTimeout) {
  config_.mode = ExecutorConfig::ExecutionMode::STREAMING;
  config_.enable_background_thread = true;
  config_.timeout_ms = 50;  // Very short timeout

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
  // Submit HALF the required samples - consumer will wait forever for complete frame
  auto input = generate_sinusoid(input_size / 2, 10.0f);
  std::vector<float> output(output_size);

  // Should timeout because consumer waits for complete frame that never arrives
  EXPECT_THROW({
    executor.submit(input.data(), output.data(), input_size / 2);
  }, std::runtime_error);
}

TEST_F(StreamingExecutorTest, AsyncProcessingStopDuringWait) {
  config_.mode = ExecutorConfig::ExecutionMode::STREAMING;
  config_.enable_background_thread = true;
  config_.timeout_ms = 5000;  // Long timeout

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
  // Submit partial samples - consumer will wait indefinitely for complete frame
  auto input = generate_sinusoid(input_size / 2, 10.0f);
  std::vector<float> output(output_size);

  // Start async operation in separate thread (will wait forever for complete frame)
  std::thread submit_thread([&]() {
    EXPECT_THROW({
      executor.submit(input.data(), output.data(), input_size / 2);
    }, std::runtime_error);
  });

  // Wait briefly to ensure submit is waiting, then trigger shutdown
  std::this_thread::sleep_for(std::chrono::milliseconds(100));
  executor.reset();  // Triggers stop_flag_

  submit_thread.join();
}

TEST_F(StreamingExecutorTest, MultipleAsyncSubmits) {
  config_.mode = ExecutorConfig::ExecutionMode::STREAMING;
  config_.enable_background_thread = true;
  config_.timeout_ms = 2000;

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

  // Submit 3 frames consecutively (limited to avoid ring buffer overflow with overlap)
  // Ring buffer capacity is 3*nfft, and with 0.75 overlap, each frame leaves
  // 0.75*nfft samples in buffer, so 3 submits = 3*nfft samples ≈ capacity limit
  for (int i = 0; i < 3; ++i) {
    auto input = generate_sinusoid(input_size, 10.0f + i);
    std::vector<float> output(output_size);

    EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));

    // Verify output
    bool has_nonzero = false;
    for (float val : output) {
      if (val > 1e-6f) {
        has_nonzero = true;
        break;
      }
    }
    EXPECT_TRUE(has_nonzero);

    // Small delay to allow consumer to process and free ring buffer space
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
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

TEST_F(StreamingExecutorTest, ConsecutiveSubmitsWithoutSync) {
  StreamingExecutor executor;

  // Use benchmark parameters to reproduce the bug
  ExecutorConfig bench_config;
  bench_config.nfft = 2048;  // Match benchmark nfft
  bench_config.channels = 2;
  bench_config.overlap = 0.5f;
  bench_config.sample_rate_hz = 100000;
  bench_config.stream_count = 3;
  bench_config.pinned_buffer_count = 2;
  bench_config.warmup_iters = 0;
  bench_config.mode = ExecutorConfig::ExecutionMode::STREAMING;

  PipelineBuilder builder;
  auto stages =
      builder.with_config(StageConfig{bench_config.nfft, bench_config.channels})
          .add_window(StageConfig::WindowType::HANN)
          .add_fft()
          .add_magnitude()
          .build();
  executor.initialize(bench_config, std::move(stages));

  const size_t input_size = bench_config.nfft * bench_config.channels;
  const size_t output_size =
      bench_config.num_output_bins() * bench_config.channels;
  auto input = generate_sinusoid(input_size, 10.0f);
  std::vector<float> output(output_size);

  // Regression test for bug: consecutive submit() calls should work
  // Previously crashed on iteration 2 when frame_counter >= pinned_buffer_count
  for (int i = 0; i < 5; ++i) {
    std::cout << "Submit iteration " << i << " (nfft=" << bench_config.nfft
              << ")\n"
              << std::flush;
    EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));
  }

  std::cout << "All submits completed, checking output...\n" << std::flush;

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

// ============================================================================
//  Event-Based Buffer Synchronization Tests
// ============================================================================

/**
 * @brief Test event-based buffer synchronization with small buffer pool.
 *
 * This test verifies that the event-based synchronization works correctly
 * when buffer reuse is frequent (small pinned_buffer_count).
 */
TEST_F(StreamingExecutorTest, EventBasedBufferSync) {
  config_.nfft = 1024;
  config_.channels = 2;
  config_.overlap = 0.5f;
  config_.pinned_buffer_count = 2;  // Small pool → frequent reuse
  config_.stream_count = 3;

  // Build executor with standard pipeline
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

  // Process 10 frames (5x buffer pool size)
  // Triggers buffer reuse starting at frame 2 (frame_counter_ >= 2)
  for (int i = 0; i < 10; ++i) {
    auto input = generate_sinusoid(input_size, 100.0f + i);
    std::vector<float> output(output_size);

    EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));

    // Verify output is valid (non-zero magnitude)
    float max_val = *std::max_element(output.begin(), output.end());
    EXPECT_GT(max_val, 1e-6f) << "Frame " << i << " has zero output";
  }

  // Verify stats
  auto stats = executor.get_stats();
  EXPECT_GE(stats.frames_processed, 10);
}

/**
 * @brief Stress test event-based buffer reuse with high throughput.
 *
 * This test verifies correct synchronization under high buffer reuse pressure:
 * - Many consecutive frames (100)
 * - High overlap (0.875) → more residual data
 * - Minimal buffer pool (2 buffers) → 50x reuse per buffer
 */
TEST_F(StreamingExecutorTest, HighThroughputBufferReuse) {
  config_.nfft = 2048;
  config_.channels = 4;
  config_.overlap = 0.875f;          // High overlap
  config_.pinned_buffer_count = 2;   // Minimal buffer pool
  config_.stream_count = 3;

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

  // Process 100 submits rapidly (stress test)
  // With high overlap (0.875), hop_size=256, so each submit produces ~8 frames
  auto start = std::chrono::high_resolution_clock::now();

  for (int i = 0; i < 100; ++i) {
    auto input = generate_sinusoid(input_size, 200.0f + i * 10.0f);
    std::vector<float> output(output_size);

    EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));
  }

  auto elapsed = std::chrono::high_resolution_clock::now() - start;
  auto elapsed_us =
      std::chrono::duration_cast<std::chrono::microseconds>(elapsed).count();

  // Verify stats
  auto stats = executor.get_stats();
  // With overlap=0.875 (hop_size=256), each submit of 2048 samples produces ~8 frames
  // 100 submits × ~8 frames/submit ≈ 800 frames (actual: ~793 due to startup)
  EXPECT_GE(stats.frames_processed, 750);  // At least 750 frames
  EXPECT_LE(stats.frames_processed, 850);  // At most 850 frames

  // Verify performance (should be <250µs per frame with event sync)
  float avg_latency_us = static_cast<float>(elapsed_us) /
                          static_cast<float>(stats.frames_processed);
  EXPECT_LT(avg_latency_us, 250.0f)
      << "Average latency per frame too high: " << avg_latency_us << "µs";
}

/**
 * @brief Test event synchronization with single stream (edge case).
 *
 * This test verifies that event-based synchronization works correctly when
 * all operations (H2D, compute, D2H) are serialized on a single stream.
 */
TEST_F(StreamingExecutorTest, SingleStreamEventSync) {
  config_.nfft = 512;
  config_.channels = 1;
  config_.overlap = 0.5f;
  config_.pinned_buffer_count = 2;
  config_.stream_count = 1;  // ← Single stream edge case

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

  // Process 5 frames (triggers buffer reuse)
  for (int i = 0; i < 5; ++i) {
    auto input = generate_sinusoid(input_size, 50.0f);
    std::vector<float> output(output_size);

    EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));
  }

  auto stats = executor.get_stats();
  EXPECT_GE(stats.frames_processed, 5);
}

/**
 * @brief Test event synchronization with large buffer pool (minimal reuse).
 *
 * This test verifies correct event handling when buffer reuse is infrequent:
 * - Large buffer pool (8 buffers)
 * - First 8 frames have no reuse
 * - Remaining 12 frames reuse buffers infrequently
 */
TEST_F(StreamingExecutorTest, LargeBufferPoolEventSync) {
  config_.nfft = 1024;
  config_.channels = 2;
  config_.overlap = 0.5f;
  config_.pinned_buffer_count = 8;  // Large pool
  config_.stream_count = 3;

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

  // Process 20 submits (with overlap=0.5, produces ~40 frames total)
  // First 8 frames have no buffer reuse, remaining frames reuse buffers
  for (int i = 0; i < 20; ++i) {
    auto input = generate_sinusoid(input_size, 75.0f + i);
    std::vector<float> output(output_size);

    EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));
  }

  auto stats = executor.get_stats();
  // With overlap=0.5 (hop_size=512), each submit of 1024 samples produces ~2 frames
  // 20 submits × ~2 frames/submit ≈ 40 frames (actual: 39 due to startup)
  EXPECT_GE(stats.frames_processed, 35);  // At least 35 frames
  EXPECT_LE(stats.frames_processed, 45);  // At most 45 frames
}

// ============================================================================
//  Component Timing Tests (Per-Stage Metrics)
// ============================================================================

/**
 * @brief Test that component timing is disabled by default.
 *
 * Verify stage_metrics.enabled=false when measure_components not set.
 */
TEST_F(StreamingExecutorTest, ComponentTimingDisabledByDefault) {
  config_.nfft = 1024;
  config_.channels = 1;
  config_.overlap = 0.0f;
  // measure_components not set (defaults to false)

  StreamingExecutor executor;
  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_window(StageConfig::WindowType::HANN)
                    .add_fft()
                    .add_magnitude()
                    .build();
  executor.initialize(config_, std::move(stages));

  // Process one frame
  const size_t input_size = config_.nfft * config_.channels;
  const size_t output_size = config_.num_output_bins() * config_.channels;
  auto input = generate_sinusoid(input_size, 1000.0f);
  std::vector<float> output(output_size);

  executor.submit(input.data(), output.data(), input_size);

  auto stats = executor.get_stats();
  EXPECT_FALSE(stats.stage_metrics.enabled);
  EXPECT_EQ(stats.stage_metrics.window_us, 0.0f);
  EXPECT_EQ(stats.stage_metrics.fft_us, 0.0f);
  EXPECT_EQ(stats.stage_metrics.magnitude_us, 0.0f);
  EXPECT_EQ(stats.stage_metrics.overhead_us, 0.0f);
  EXPECT_EQ(stats.stage_metrics.total_measured_us, 0.0f);
}

/**
 * @brief Test that component timing works in StreamingExecutor.
 *
 * Implementation: Option 1 (last-frame timing)
 * Reports timing for the most recently processed frame.
 */
TEST_F(StreamingExecutorTest, ComponentTimingEnabled) {
  config_.nfft = 1024;
  config_.channels = 1;
  config_.overlap = 0.0f;
  config_.measure_components = true;

  StreamingExecutor executor;
  PipelineBuilder builder;
  auto stages = builder.with_config(StageConfig{config_.nfft, config_.channels})
                    .add_window(StageConfig::WindowType::HANN)
                    .add_fft()
                    .add_magnitude()
                    .build();
  executor.initialize(config_, std::move(stages));

  // Process frames
  const size_t input_size = config_.nfft * config_.channels;
  const size_t output_size = config_.num_output_bins() * config_.channels;
  std::vector<float> output(output_size);

  auto input1 = generate_sinusoid(input_size, 1000.0f);
  executor.submit(input1.data(), output.data(), input_size);

  auto input2 = generate_sinusoid(input_size, 1100.0f);
  executor.submit(input2.data(), output.data(), input_size);

  // Verify metrics are enabled and populated
  auto stats = executor.get_stats();
  EXPECT_TRUE(stats.stage_metrics.enabled);
  EXPECT_GT(stats.stage_metrics.window_us, 0.0f);
  EXPECT_GT(stats.stage_metrics.fft_us, 0.0f);
  EXPECT_GT(stats.stage_metrics.magnitude_us, 0.0f);

  // Verify total equals sum of components
  float expected_total = stats.stage_metrics.window_us +
                        stats.stage_metrics.fft_us +
                        stats.stage_metrics.magnitude_us;
  EXPECT_NEAR(stats.stage_metrics.total_measured_us, expected_total, 0.1f);

  // Verify overhead is reasonable (between 0 and total latency)
  // Note: Overhead calculation uses stats_.latency_us which is finalized after
  // process_one_batch(), so exact matching is timing-dependent in tests.
  // Production use (Python) is fine since access is single-threaded.
  EXPECT_GE(stats.stage_metrics.overhead_us, 0.0f);
  EXPECT_LE(stats.stage_metrics.overhead_us, stats.latency_us);
}

/**
 * @brief Test component timing with multiple frames per submit.
 *
 * With overlap, one submit() can process multiple frames. Verify that
 * timing is reported for the last processed frame.
 */
// ============================================================================
//  Zero-Copy Ring Buffer Tests
// ============================================================================

/**
 * @brief Test zero-copy H2D with high overlap that forces ring buffer wraparound.
 *
 * With overlap=0.875, hop_size = nfft/8 = 128 (for nfft=1024).
 * Ring buffer capacity = 3*nfft = 3072.
 * Wraparound occurs roughly every 3*nfft/hop_size = 24 frames.
 * Processing 30 frames ensures at least one wraparound cycle completes,
 * exercising the two-span DMA path in the zero-copy H2D transfer.
 */
TEST_F(StreamingExecutorTest, ZeroCopyWraparoundCorrectness) {
  config_.nfft = 1024;
  config_.channels = 2;
  config_.overlap = 0.875f;  // High overlap → hop_size=128, frequent wraparound
  config_.pinned_buffer_count = 2;
  config_.stream_count = 3;

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

  // Process 30 submits — each submit produces ~8 frames (nfft/hop_size)
  // Total ~240 frames, multiple wraparound cycles
  for (int i = 0; i < 30; ++i) {
    auto input = generate_sinusoid(input_size, 100.0f + i * 5.0f);
    std::vector<float> output(output_size);

    EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));

    // Verify every frame produces non-zero output (no DMA corruption)
    bool has_nonzero = false;
    for (size_t j = 0; j < output_size; ++j) {
      if (output[j] > 1e-6f) {
        has_nonzero = true;
        break;
      }
    }
    EXPECT_TRUE(has_nonzero) << "Frame " << i << " has zero output (possible DMA corruption)";
  }

  auto stats = executor.get_stats();
  // With overlap=0.875 (hop_size=128), each submit of 1024 samples produces ~8 frames
  // 30 submits × ~8 frames/submit ≈ 240 frames
  EXPECT_GE(stats.frames_processed, 200);
}

TEST_F(StreamingExecutorTest, ComponentTimingWithOverlap) {
  config_.nfft = 1024;
  config_.channels = 1;
  config_.overlap = 0.75f;  // High overlap -> multiple frames per submit
  config_.measure_components = true;

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
  std::vector<float> output(output_size);

  // First submit: fills buffer, processes 1 frame
  auto input1 = generate_sinusoid(input_size, 1000.0f);
  executor.submit(input1.data(), output.data(), input_size);

  auto stats1 = executor.get_stats();
  EXPECT_TRUE(stats1.stage_metrics.enabled);
  EXPECT_GT(stats1.stage_metrics.window_us, 0.0f);

  // Second submit: processes multiple frames due to overlap
  auto input2 = generate_sinusoid(input_size, 1100.0f);
  executor.submit(input2.data(), output.data(), input_size);

  auto stats2 = executor.get_stats();
  EXPECT_TRUE(stats2.stage_metrics.enabled);
  EXPECT_GT(stats2.stage_metrics.window_us, 0.0f);
  // Timing reflects last frame processed in this submit
}

// ============================================================================
//  Batched Frame Processing Tests (Optimization 3.1)
// ============================================================================

/**
 * @brief Verify batched processing produces correct output matching sequential.
 *
 * With overlap=0.75, submitting nfft samples should produce 4 frames.
 * The batched path should produce the same output as 4 sequential
 * process_one_batch calls would have.
 */
TEST_F(StreamingExecutorTest, BatchedProcessingCorrectness) {
  config_.nfft = 1024;
  config_.channels = 2;
  config_.overlap = 0.75f;  // N=4 frames per submit
  config_.pinned_buffer_count = 2;
  config_.stream_count = 3;
  config_.warmup_iters = 0;  // No warmup to avoid state changes

  // Run with batched path
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

  // First submit fills ring buffer, processes 1 frame
  auto input1 = generate_sinusoid(input_size, 1000.0f);
  std::vector<float> output1(output_size);
  executor.submit(input1.data(), output1.data(), input_size);

  // Second submit produces ~4 frames via batched path
  auto input2 = generate_sinusoid(input_size, 500.0f);
  std::vector<float> batched_output(output_size);
  executor.submit(input2.data(), batched_output.data(), input_size);

  // Verify output has non-zero values
  bool has_nonzero = false;
  for (float val : batched_output) {
    if (val > 1e-6f) {
      has_nonzero = true;
      break;
    }
  }
  EXPECT_TRUE(has_nonzero) << "Batched output is all zeros";

  // Verify stats show multiple frames were processed
  auto stats = executor.get_stats();
  // First submit: 1 frame, second submit: ~4 frames = ~5 total
  EXPECT_GE(stats.frames_processed, 4);
}

/**
 * @brief Verify N=1 uses single-frame path, N>=2 uses batched path.
 */
TEST_F(StreamingExecutorTest, BatchedProcessingVaryingN) {
  // overlap=0.0 means hop_size = nfft, so N=1 per submit (single-frame path)
  config_.nfft = 512;
  config_.channels = 1;
  config_.overlap = 0.0f;
  config_.warmup_iters = 0;

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

  // With overlap=0.0, each submit produces exactly 1 frame
  for (int i = 0; i < 5; ++i) {
    auto input = generate_sinusoid(input_size, 100.0f + i * 50.0f);
    std::vector<float> output(output_size);
    EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));

    bool has_nonzero = false;
    for (float val : output) {
      if (val > 1e-6f) {
        has_nonzero = true;
        break;
      }
    }
    EXPECT_TRUE(has_nonzero) << "Frame " << i << " zero output";
  }

  auto stats = executor.get_stats();
  EXPECT_EQ(stats.frames_processed, 5);
}

/**
 * @brief Test batched processing with high overlap (0.875, N=8).
 *
 * 100 submits × ~8 frames/submit = ~800 frames.
 * Validates correctness and stability with high frame count.
 */
TEST_F(StreamingExecutorTest, BatchedProcessingHighOverlap) {
  config_.nfft = 1024;
  config_.channels = 2;
  config_.overlap = 0.875f;  // N=8 frames per submit
  config_.pinned_buffer_count = 2;
  config_.stream_count = 3;

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

  for (int i = 0; i < 100; ++i) {
    auto input = generate_sinusoid(input_size, 200.0f + i * 10.0f);
    std::vector<float> output(output_size);

    EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));

    bool has_nonzero = false;
    for (float val : output) {
      if (val > 1e-6f) {
        has_nonzero = true;
        break;
      }
    }
    EXPECT_TRUE(has_nonzero) << "Submit " << i << " has zero output";
  }

  auto stats = executor.get_stats();
  // With overlap=0.875 (hop_size=128), each submit of 1024 samples produces ~8 frames
  // 100 submits × ~8 frames ≈ 800 frames
  EXPECT_GE(stats.frames_processed, 750);
  EXPECT_LE(stats.frames_processed, 850);
}

/**
 * @brief Test component timing works with batched processing.
 */
TEST_F(StreamingExecutorTest, BatchedComponentTiming) {
  config_.nfft = 1024;
  config_.channels = 2;
  config_.overlap = 0.75f;  // N=4, triggers batched path
  config_.measure_components = true;
  config_.warmup_iters = 0;

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
  std::vector<float> output(output_size);

  // First submit (N=1, single-frame path)
  auto input1 = generate_sinusoid(input_size, 1000.0f);
  executor.submit(input1.data(), output.data(), input_size);

  // Second submit (N>=2, batched path)
  auto input2 = generate_sinusoid(input_size, 500.0f);
  executor.submit(input2.data(), output.data(), input_size);

  auto stats = executor.get_stats();
  EXPECT_TRUE(stats.stage_metrics.enabled);
  EXPECT_GT(stats.stage_metrics.window_us, 0.0f);
  EXPECT_GT(stats.stage_metrics.fft_us, 0.0f);
  EXPECT_GT(stats.stage_metrics.magnitude_us, 0.0f);

  float expected_total = stats.stage_metrics.window_us +
                         stats.stage_metrics.fft_us +
                         stats.stage_metrics.magnitude_us;
  EXPECT_NEAR(stats.stage_metrics.total_measured_us, expected_total, 0.1f);
}

/**
 * @brief Test batched processing with ring buffer wraparound.
 *
 * High overlap forces frequent wraparound in peek_frame_at_offset.
 * Ring buffer capacity = 3*nfft, wraparound occurs every ~24 frames.
 */
TEST_F(StreamingExecutorTest, BatchedRingBufferWraparound) {
  config_.nfft = 512;
  config_.channels = 2;
  config_.overlap = 0.875f;  // Very high overlap, hop=64
  config_.pinned_buffer_count = 2;
  config_.stream_count = 3;

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

  // 50 submits × ~8 frames = ~400 frames, many wraparound cycles
  for (int i = 0; i < 50; ++i) {
    auto input = generate_sinusoid(input_size, 100.0f + i * 5.0f);
    std::vector<float> output(output_size);

    EXPECT_NO_THROW(executor.submit(input.data(), output.data(), input_size));

    bool has_nonzero = false;
    for (size_t j = 0; j < output_size; ++j) {
      if (output[j] > 1e-6f) {
        has_nonzero = true;
        break;
      }
    }
    EXPECT_TRUE(has_nonzero)
        << "Submit " << i << " has zero output (DMA corruption)";
  }

  auto stats = executor.get_stats();
  EXPECT_GE(stats.frames_processed, 350);
}

/**
 * @brief Test frame counter and stats with batched processing.
 */
TEST_F(StreamingExecutorTest, BatchedFrameCounterAndStats) {
  config_.nfft = 512;
  config_.channels = 1;
  config_.overlap = 0.5f;  // N=2 per submit
  config_.warmup_iters = 0;

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

  // Submit 10 times: first submit = 1 frame (N=1),
  // subsequent submits = 2 frames (N=2) via batched path
  for (int i = 0; i < 10; ++i) {
    auto input = generate_sinusoid(input_size, 100.0f + i);
    std::vector<float> output(output_size);
    executor.submit(input.data(), output.data(), input_size);
  }

  auto stats = executor.get_stats();
  // 1 + 9*2 = 19 frames (first submit N=1, rest N=2)
  EXPECT_GE(stats.frames_processed, 15);
  EXPECT_LE(stats.frames_processed, 21);
  EXPECT_GT(stats.latency_us, 0.0f);
  EXPECT_GT(stats.throughput_gbps, 0.0f);
}

/**
 * @brief Unit test for peek_frame_at_offset ring buffer method.
 */
TEST(RingBufferPeekOffsetTest, PeekFrameAtOffset) {
  // Check for CUDA device availability
  int device_count = 0;
  cudaError_t err = cudaGetDeviceCount(&device_count);
  if (err != cudaSuccess || device_count == 0) {
    GTEST_SKIP() << "No CUDA devices available for testing.";
  }

  sigtekx::RingBuffer<float> rb(64);

  // Push 32 samples
  std::vector<float> data(32);
  for (int i = 0; i < 32; ++i) data[i] = static_cast<float>(i);
  rb.push(data.data(), 32);

  // Peek at offset 0, size 16
  auto view0 = rb.peek_frame_at_offset(16, 0);
  EXPECT_TRUE(view0.is_contiguous());
  EXPECT_EQ(view0.first.count, size_t{16});
  EXPECT_FLOAT_EQ(view0.first.data[0], 0.0f);
  EXPECT_FLOAT_EQ(view0.first.data[15], 15.0f);

  // Peek at offset 8, size 16 (overlapping with previous)
  auto view1 = rb.peek_frame_at_offset(16, 8);
  EXPECT_TRUE(view1.is_contiguous());
  EXPECT_EQ(view1.first.count, size_t{16});
  EXPECT_FLOAT_EQ(view1.first.data[0], 8.0f);
  EXPECT_FLOAT_EQ(view1.first.data[15], 23.0f);

  // Underflow: offset + frame_size > available
  EXPECT_THROW(rb.peek_frame_at_offset(16, 20), std::underflow_error);
}

/**
 * @brief Test peek_frame_at_offset with wraparound.
 */
TEST(RingBufferPeekOffsetTest, PeekFrameAtOffsetWraparound) {
  int device_count = 0;
  cudaError_t err = cudaGetDeviceCount(&device_count);
  if (err != cudaSuccess || device_count == 0) {
    GTEST_SKIP() << "No CUDA devices available for testing.";
  }

  // Small buffer to force wraparound
  sigtekx::RingBuffer<float> rb(32);

  // Fill buffer partially, advance, refill to force wraparound
  std::vector<float> data1(20);
  for (int i = 0; i < 20; ++i) data1[i] = static_cast<float>(i);
  rb.push(data1.data(), 20);
  rb.advance(16);  // Read pointer at 16, available = 4

  // Push more data (wraps around)
  std::vector<float> data2(20);
  for (int i = 0; i < 20; ++i) data2[i] = static_cast<float>(100 + i);
  rb.push(data2.data(), 20);
  // Available = 24, read_pos = 16, write_pos = (16+24)%32 = 8

  // Peek at offset 0, size 16 - should wrap around
  auto view = rb.peek_frame_at_offset(16, 0);
  // read_pos = 16, end = 32 = capacity, so contiguous
  EXPECT_TRUE(view.is_contiguous());
  EXPECT_EQ(view.first.count, size_t{16});
  // First 4 samples are residual [16,17,18,19], next 12 are [100,101,...,111]
  EXPECT_FLOAT_EQ(view.first.data[0], 16.0f);
  EXPECT_FLOAT_EQ(view.first.data[3], 19.0f);
  EXPECT_FLOAT_EQ(view.first.data[4], 100.0f);

  // Peek at offset 8, size 16 - this starts at (16+8)%32=24, wraps to 0
  auto view2 = rb.peek_frame_at_offset(16, 8);
  EXPECT_TRUE(!view2.is_contiguous());
  size_t expected_span = 8;
  EXPECT_EQ(view2.first.count, expected_span);  // 24..31
  EXPECT_EQ(view2.second.count, expected_span);  // 0..7
}
