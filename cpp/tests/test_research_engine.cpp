/**
 * @file test_research_engine.cpp
 * @version 1.0
 * @date 2025-09-01
 * @author [Kevin Rahsaz]
 *
 * @brief Unit and integration tests for the ResearchEngine class.
 *
 * This test suite validates the functionality of the ResearchEngine, covering
 * initialization, processing, state management, and utility functions. It uses
 * the Google Test framework to ensure correctness and robustness of the core
 * engine.
 */

#include <gtest/gtest.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <thread>
#include <vector>

#include "ionosense/core/processing_stage.hpp"
#include "ionosense/engines/research_engine.hpp"
// Ensure CUDA runtime symbols are available to this test
#include "ionosense/core/cuda_wrappers.hpp"

// IEEE Std 1003.1-2001 compliance for mathematical constants
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

using namespace ionosense;

/**
 * @class ResearchEngineTest
 * @brief Test fixture for the ResearchEngine.
 *
 * Sets up a default engine configuration and helper methods for signal
 * generation. Skips tests if no CUDA-capable device is available.
 */
class ResearchEngineTest : public ::testing::Test {
 protected:
  /**
   * @brief Sets up the test environment before each test case.
   */
  void SetUp() override {
    // Pre-condition: A CUDA-capable device must be available.
    int device_count = 0;
    cudaError_t err = cudaGetDeviceCount(&device_count);
    if (err != cudaSuccess || device_count == 0) {
      GTEST_SKIP() << "No CUDA devices available for testing.";
    }

    // Initialize a standard configuration for tests.
    config_.nfft = 512;
    config_.batch = 2;
    config_.overlap = 0.5f;
    config_.sample_rate_hz = 48000;
    config_.stream_count = 3;
    config_.pinned_buffer_count = 2;
    config_.warmup_iters = 1;
  }

  /**
   * @brief Generates a sinusoidal test signal.
   * @param size Number of samples to generate.
   * @param frequency Normalized frequency of the sinusoid.
   * @return A std::vector<float> containing the signal.
   */
  std::vector<float> generate_sinusoid(int size, float frequency) {
    std::vector<float> signal(size);
    for (int i = 0; i < size; ++i) {
      signal[i] = std::sin(2.0f * M_PI * frequency * i / size);
    }
    return signal;
  }

  /**
   * @brief Generates a white noise signal.
   * @param size Number of samples to generate.
   * @return A std::vector<float> containing the noise.
   */
  std::vector<float> generate_noise(int size) {
    std::vector<float> signal(size);
    srand(0);  // Ensure reproducibility
    for (int i = 0; i < size; ++i) {
      signal[i] = (static_cast<float>(rand()) / RAND_MAX) * 2.0f - 1.0f;
    }
    return signal;
  }

 protected:
  EngineConfig config_;  ///< Default configuration for the engine tests.
};

// ============================================================================
// Basic Functionality Tests
// ============================================================================

/**
 * @test ResearchEngineTest.Construction
 * @brief Verifies that the ResearchEngine can be constructed without throwing
 * exceptions.
 */
TEST_F(ResearchEngineTest, Construction) {
  EXPECT_NO_THROW(ResearchEngine engine);
}

/**
 * @test ResearchEngineTest.Initialization
 * @brief Ensures the engine initializes and transitions to an initialized state
 * correctly.
 */
TEST_F(ResearchEngineTest, Initialization) {
  ResearchEngine engine;
  EXPECT_FALSE(engine.is_initialized());
  EXPECT_NO_THROW(engine.initialize(config_));
  EXPECT_TRUE(engine.is_initialized());
}

/**
 * @test ResearchEngineTest.DoubleInitialization
 * @brief Validates that re-initializing an already initialized engine is a safe
 * operation.
 */
TEST_F(ResearchEngineTest, DoubleInitialization) {
  ResearchEngine engine;
  engine.initialize(config_);
  EXPECT_NO_THROW(engine.initialize(config_));
  EXPECT_TRUE(engine.is_initialized());
}

/**
 * @test ResearchEngineTest.Reset
 * @brief Checks if the reset method correctly returns the engine to a
 * non-initialized state.
 */
TEST_F(ResearchEngineTest, Reset) {
  ResearchEngine engine;
  engine.initialize(config_);
  EXPECT_TRUE(engine.is_initialized());
  engine.reset();
  EXPECT_FALSE(engine.is_initialized());
}

/**
 * @test ResearchEngineTest.MoveSemantics
 * @brief Verifies that move construction and move assignment work as expected.
 */
TEST_F(ResearchEngineTest, MoveSemantics) {
  ResearchEngine engine1;
  engine1.initialize(config_);

  ResearchEngine engine2(std::move(engine1));
  EXPECT_TRUE(engine2.is_initialized());

  ResearchEngine engine3;
  engine3 = std::move(engine2);
  EXPECT_TRUE(engine3.is_initialized());
}

// ============================================================================
// Processing Tests
// ============================================================================

/**
 * @test ResearchEngineTest.BasicProcessing
 * @brief Performs a basic processing run to ensure the pipeline executes and
 * produces output.
 */
TEST_F(ResearchEngineTest, BasicProcessing) {
  ResearchEngine engine;
  engine.initialize(config_);

  const size_t input_size = config_.nfft * config_.batch;
  const size_t output_size = config_.num_output_bins() * config_.batch;

  auto input = generate_sinusoid(input_size, 10.0f);
  std::vector<float> output(output_size);

  EXPECT_NO_THROW(engine.process(input.data(), output.data(), input_size));

  // Verify that the output is not all zeros, indicating some processing
  // occurred.
  bool has_nonzero = false;
  for (float val : output) {
    if (val > 1e-6f) {
      has_nonzero = true;
      break;
    }
  }
  EXPECT_TRUE(has_nonzero);
}

/**
 * @test ResearchEngineTest.DCSignalProcessing
 * @brief Tests the engine's response to a DC signal (all ones).
 */
TEST_F(ResearchEngineTest, DCSignalProcessing) {
  ResearchEngine engine;
  engine.initialize(config_);

  const size_t input_size = config_.nfft * config_.batch;
  const size_t output_size = config_.num_output_bins() * config_.batch;

  std::vector<float> input(input_size, 1.0f);
  std::vector<float> output(output_size);

  engine.process(input.data(), output.data(), input_size);

  // The DC bin (index 0) should have the maximum energy.
  for (size_t ch = 0; ch < static_cast<size_t>(config_.batch); ++ch) {
    size_t offset = ch * config_.num_output_bins();
    float dc_magnitude = output[offset];
    for (size_t bin = 1; bin < static_cast<size_t>(config_.num_output_bins());
         ++bin) {
      EXPECT_GT(dc_magnitude, output[offset + bin]);
    }
  }
}

/**
 * @test ResearchEngineTest.SinusoidProcessing
 * @brief Validates that a single-frequency sinusoid produces a peak at the
 * correct frequency bin.
 */
TEST_F(ResearchEngineTest, SinusoidProcessing) {
  ResearchEngine engine;
  engine.initialize(config_);

  const size_t input_size = config_.nfft * config_.batch;
  const size_t output_size = config_.num_output_bins() * config_.batch;
  const int freq_bin = 20;

  std::vector<float> input(input_size);
  for (size_t ch = 0; ch < static_cast<size_t>(config_.batch); ++ch) {
    for (size_t i = 0; i < static_cast<size_t>(config_.nfft); ++i) {
      input[ch * config_.nfft + i] =
          std::sin(2.0f * M_PI * freq_bin * i / config_.nfft);
    }
  }

  std::vector<float> output(output_size);
  engine.process(input.data(), output.data(), input_size);

  // Verify that the peak magnitude is located at the expected frequency bin.
  for (size_t ch = 0; ch < static_cast<size_t>(config_.batch); ++ch) {
    size_t offset = ch * config_.num_output_bins();
    float max_magnitude = 0.0f;
    int peak_bin = -1;

    for (size_t bin = 0; bin < static_cast<size_t>(config_.num_output_bins());
         ++bin) {
      if (output[offset + bin] > max_magnitude) {
        max_magnitude = output[offset + bin];
        peak_bin = bin;
      }
    }

    EXPECT_EQ(peak_bin, freq_bin);
    EXPECT_GT(max_magnitude,
              0.1f);  // Expect a noticeable peak with normalized scaling.
  }
}

/**
 * @test ResearchEngineTest.MultipleFrameProcessing
 * @brief Ensures the engine can process multiple sequential frames correctly.
 */
TEST_F(ResearchEngineTest, MultipleFrameProcessing) {
  ResearchEngine engine;
  engine.initialize(config_);

  const size_t input_size = config_.nfft * config_.batch;
  const size_t output_size = config_.num_output_bins() * config_.batch;
  const int num_frames = 10;

  for (int frame = 0; frame < num_frames; ++frame) {
    auto input = generate_noise(input_size);
    std::vector<float> output(output_size);
    EXPECT_NO_THROW(engine.process(input.data(), output.data(), input_size));
  }

  auto stats = engine.get_stats();
  EXPECT_EQ(stats.frames_processed, static_cast<size_t>(num_frames));
}

// ============================================================================
// Async Processing Tests
// ============================================================================

/**
 * @test ResearchEngineTest.AsyncProcessing
 * @brief Verifies the asynchronous processing path with a callback function.
 */
TEST_F(ResearchEngineTest, AsyncProcessing) {
  ResearchEngine engine;
  engine.initialize(config_);

  const size_t input_size = config_.nfft * config_.batch;
  auto input = generate_sinusoid(input_size, 15.0f);

  bool callback_called = false;
  size_t received_bins = 0;
  size_t received_batch = 0;

  engine.process_async(input.data(), input_size,
                       [&](const float* magnitude, size_t num_bins,
                           size_t batch_size, const ProcessingStats& stats) {
                         callback_called = true;
                         received_bins = num_bins;
                         received_batch = batch_size;
                         EXPECT_NE(magnitude, nullptr);
                         EXPECT_GT(stats.latency_us, 0.0f);
                       });

  EXPECT_TRUE(callback_called);
  EXPECT_EQ(received_bins, static_cast<size_t>(config_.num_output_bins()));
  EXPECT_EQ(received_batch, static_cast<size_t>(config_.batch));
}

// ============================================================================
// Statistics and Runtime Info Tests
// ============================================================================

/**
 * @test ResearchEngineTest.ProcessingStatistics
 * @brief Checks if the engine correctly reports processing statistics.
 */
TEST_F(ResearchEngineTest, ProcessingStatistics) {
  ResearchEngine engine;
  engine.initialize(config_);

  const size_t input_size = config_.nfft * config_.batch;
  const size_t output_size = config_.num_output_bins() * config_.batch;

  auto input = generate_noise(input_size);
  std::vector<float> output(output_size);

  engine.process(input.data(), output.data(), input_size);

  auto stats = engine.get_stats();
  EXPECT_GT(stats.latency_us, 0.0f);
  EXPECT_LT(stats.latency_us, 10000.0f);  // Sanity check: should be < 10ms.
  EXPECT_GT(stats.throughput_gbps, 0.0f);
  EXPECT_GE(stats.frames_processed, 1);
  EXPECT_FALSE(stats.is_warmup);
}

/**
 * @test ResearchEngineTest.RuntimeInfo
 * @brief Validates that runtime information can be successfully queried.
 */
TEST_F(ResearchEngineTest, RuntimeInfo) {
  ResearchEngine engine;
  engine.initialize(config_);

  auto info = engine.get_runtime_info();

  EXPECT_FALSE(info.cuda_version.empty());
  EXPECT_FALSE(info.device_name.empty());
  EXPECT_GE(info.device_compute_capability_major, 3);
  EXPECT_GT(info.device_memory_total_mb, 0);
  EXPECT_GT(info.device_memory_free_mb, 0);
  EXPECT_GT(info.cuda_runtime_version, 0);
  EXPECT_GT(info.cuda_driver_version, 0);
}

// ============================================================================
// Configuration Tests
// ============================================================================

// NOTE: StageConfiguration and ProfilingToggle tests removed in v0.9.3
// The new architecture manages stage configuration internally via the pipeline,
// and profiling is controlled through EngineConfig.enable_profiling.

// ============================================================================
// Performance Tests
// ============================================================================

/**
 * @test ResearchEngineTest.LatencyRequirement
 * @brief Checks if the engine meets basic performance latency requirements.
 */
TEST_F(ResearchEngineTest, LatencyRequirement) {
  ResearchEngine engine;
  engine.initialize(config_);

  const size_t input_size = config_.nfft * config_.batch;
  const size_t output_size = config_.num_output_bins() * config_.batch;

  auto input = generate_noise(input_size);
  std::vector<float> output(output_size);

  // Warmup
  for (int i = 0; i < 5; ++i) {
    engine.process(input.data(), output.data(), input_size);
  }

  // Measure steady-state latency
  std::vector<float> latencies;
  for (int i = 0; i < 100; ++i) {
    engine.process(input.data(), output.data(), input_size);
    latencies.push_back(engine.get_stats().latency_us);
  }

  std::sort(latencies.begin(), latencies.end());
  float p50 = latencies[latencies.size() / 2];
  float p99 = latencies[latencies.size() * 99 / 100];

  EXPECT_LT(p50, 200.0f);  // Target median latency < 200µs.
  EXPECT_LT(p99, 500.0f);  // Target P99 latency < 500µs.
}

/**
 * @test ResearchEngineTest.Synchronization
 * @brief Verifies that the global synchronize method executes without error.
 */
TEST_F(ResearchEngineTest, Synchronization) {
  ResearchEngine engine;
  engine.initialize(config_);

  const size_t input_size = config_.nfft * config_.batch;
  const size_t output_size = config_.num_output_bins() * config_.batch;

  for (int i = 0; i < 5; ++i) {
    auto input = generate_noise(input_size);
    std::vector<float> output(output_size);
    engine.process(input.data(), output.data(), input_size);
  }

  EXPECT_NO_THROW(engine.synchronize());
}

// ============================================================================
// Factory and Utility Tests
// ============================================================================

// NOTE: EngineFactory test removed in v0.9.3
// The new architecture doesn't use a factory function. Users instantiate
// specific engines directly (ResearchEngine, RealtimeIonoEngine, etc.).

/**
 * @test ResearchEngineTest.GetAvailableDevices
 * @brief Ensures device utility functions correctly report available devices.
 */
TEST_F(ResearchEngineTest, GetAvailableDevices) {
  auto devices = engine_utils::get_available_devices();
  EXPECT_GT(devices.size(), 0);

  for (const auto& device : devices) {
    EXPECT_FALSE(device.empty());
    EXPECT_NE(device.find("["), std::string::npos);
    EXPECT_NE(device.find("]"), std::string::npos);
  }
}

/**
 * @test ResearchEngineTest.SelectBestDevice
 * @brief Verifies that the device selection utility returns a valid device ID.
 */
TEST_F(ResearchEngineTest, SelectBestDevice) {
  int device = engine_utils::select_best_device();
  EXPECT_GE(device, 0);

  int device_count = 0;
  cudaGetDeviceCount(&device_count);
  EXPECT_LT(device, device_count);
}

/**
 * @test ResearchEngineTest.ConfigValidation
 * @brief Tests the configuration validation utility with both valid and invalid
 * configs.
 */
TEST_F(ResearchEngineTest, ConfigValidation) {
  std::string error_msg;

  EXPECT_TRUE(engine_utils::validate_config(config_, error_msg));
  EXPECT_TRUE(error_msg.empty());

  EngineConfig bad_config = config_;
  bad_config.nfft = 1000;  // Not a power of 2
  EXPECT_FALSE(engine_utils::validate_config(bad_config, error_msg));
  EXPECT_FALSE(error_msg.empty());

  bad_config = config_;
  bad_config.batch = 0;  // Not positive
  EXPECT_FALSE(engine_utils::validate_config(bad_config, error_msg));

  bad_config = config_;
  bad_config.overlap = 1.5f;  // Out of range
  EXPECT_FALSE(engine_utils::validate_config(bad_config, error_msg));

  bad_config = config_;
  bad_config.stream_count = 0;  // Not positive
  EXPECT_FALSE(engine_utils::validate_config(bad_config, error_msg));
}

/**
 * @test ResearchEngineTest.MemoryEstimation
 * @brief Verifies the memory estimation utility provides reasonable results.
 */
TEST_F(ResearchEngineTest, MemoryEstimation) {
  size_t estimated = engine_utils::estimate_memory_usage(config_);

  // Sanity check: Should be > 1KB and < 1GB for a typical config.
  EXPECT_GT(estimated, 1024);
  EXPECT_LT(estimated, 1024 * 1024 * 1024);

  EngineConfig large_config = config_;
  large_config.nfft = 4096;
  large_config.batch = 8;

  size_t large_estimated = engine_utils::estimate_memory_usage(large_config);
  EXPECT_GT(large_estimated, estimated);
}
