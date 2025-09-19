/**
 * @file test_processing_stage.cpp
 * @version 1.0
 * @date 2025-09-01
 * @author [Kevin Rahsaz]
 *
 * @brief Unit tests for the individual processing stages (Window, FFT,
 * Magnitude).
 *
 * This suite validates the correctness of each component in the signal
 * processing pipeline, ensuring they initialize correctly and produce the
 * expected output for known signals. It relies on the Google Test framework.
 */

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <complex>
#include <numeric>
#include <vector>

#include "ionosense/cuda_wrappers.hpp"
#include "ionosense/processing_stage.hpp"

// IEEE Std 1003.1-2001 compliance for mathematical constants
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

using namespace ionosense;

/**
 * @class ProcessingStageTest
 * @brief Test fixture for processing stage tests.
 *
 * Sets up a CUDA stream and a default StageConfig. Skips tests if no
 * CUDA device is found.
 */
class ProcessingStageTest : public ::testing::Test {
 protected:
  /**
   * @brief Sets up resources before each test.
   */
  void SetUp() override {
    int device_count = 0;
    cudaError_t err = cudaGetDeviceCount(&device_count);
    if (err != cudaSuccess || device_count == 0) {
      GTEST_SKIP() << "No CUDA devices available for testing.";
    }

    stream_ = std::make_unique<CudaStream>();

    config_.nfft = 256;
    config_.batch = 2;
    config_.overlap = 0.5f;
    config_.sample_rate_hz = 48000;
  }

  /**
   * @brief Tears down resources after each test.
   */
  void TearDown() override {
    if (stream_) {
      stream_->synchronize();
    }
  }

  /**
   * @brief Generates a simple test signal.
   * @param size Number of samples.
   * @param frequency Normalized frequency.
   * @return std::vector<float> of the signal.
   */
  std::vector<float> generate_test_signal(int size, float frequency = 1.0f) {
    std::vector<float> signal(size);
    for (int i = 0; i < size; ++i) {
      signal[i] = std::sin(2.0f * M_PI * frequency * i / size);
    }
    return signal;
  }

 protected:
  std::unique_ptr<CudaStream> stream_;  ///< CUDA stream for test operations.
  StageConfig config_;                  ///< Default configuration for stages.
};

// ============================================================================
// WindowStage Tests
// ============================================================================

/**
 * @test ProcessingStageTest.WindowStageInitialization
 * @brief Verifies that the WindowStage initializes correctly.
 */
TEST_F(ProcessingStageTest, WindowStageInitialization) {
  WindowStage stage;
  EXPECT_NO_THROW(stage.initialize(config_, stream_->get()));
  EXPECT_EQ(stage.name(), "WindowStage");
  EXPECT_TRUE(stage.supports_inplace());
  EXPECT_GT(stage.get_workspace_size(), 0);
}

/**
 * @test ProcessingStageTest.WindowStageProcess
 * @brief Tests the out-of-place windowing operation.
 */
TEST_F(ProcessingStageTest, WindowStageProcess) {
  WindowStage stage;
  stage.initialize(config_, stream_->get());

  const size_t total_samples = config_.nfft * config_.batch;
  auto host_input = generate_test_signal(total_samples);

  DeviceBuffer<float> d_input(total_samples);
  DeviceBuffer<float> d_output(total_samples);

  d_input.copy_from_host(host_input.data(), total_samples, stream_->get());

  stage.process(d_input.get(), d_output.get(), total_samples, stream_->get());

  std::vector<float> host_output(total_samples);
  d_output.copy_to_host(host_output.data(), total_samples, stream_->get());
  stream_->synchronize();

  // Output should be different from input.
  bool all_same =
      std::equal(host_input.begin(), host_input.end(), host_output.begin());
  EXPECT_FALSE(all_same);

  // Edges of the windowed signal should be close to zero.
  EXPECT_NEAR(host_output[0], 0.0f, 1e-3f);
  EXPECT_NEAR(host_output[config_.nfft - 1], 0.0f, 1e-3f);
}

/**
 * @test ProcessingStageTest.WindowStageInPlace
 * @brief Tests the in-place windowing operation.
 */
TEST_F(ProcessingStageTest, WindowStageInPlace) {
  WindowStage stage;
  stage.initialize(config_, stream_->get());

  const size_t total_samples = config_.nfft * config_.batch;
  auto host_data = generate_test_signal(total_samples);

  DeviceBuffer<float> d_data(total_samples);
  d_data.copy_from_host(host_data.data(), total_samples, stream_->get());

  stage.process(d_data.get(), d_data.get(), total_samples, stream_->get());

  std::vector<float> result(total_samples);
  d_data.copy_to_host(result.data(), total_samples, stream_->get());
  stream_->synchronize();

  EXPECT_NEAR(result[0], 0.0f, 1e-3f);
  EXPECT_NEAR(result[config_.nfft - 1], 0.0f, 1e-3f);
}

// ============================================================================
// FFTStage Tests
// ============================================================================

/**
 * @test ProcessingStageTest.FFTStageInitialization
 * @brief Verifies correct initialization of the FFTStage.
 */
TEST_F(ProcessingStageTest, FFTStageInitialization) {
  FFTStage stage;
  EXPECT_NO_THROW(stage.initialize(config_, stream_->get()));
  EXPECT_EQ(stage.name(), "FFTStage");
  EXPECT_TRUE(stage.supports_inplace());
  EXPECT_GE(stage.get_workspace_size(), 0);
}

/**
 * @test ProcessingStageTest.FFTStageProcess
 * @brief Tests the FFT of a DC signal.
 */
TEST_F(ProcessingStageTest, FFTStageProcess) {
  FFTStage stage;
  stage.initialize(config_, stream_->get());

  const size_t total_samples = config_.nfft * config_.batch;
  std::vector<float> host_input(total_samples, 1.0f);

  DeviceBuffer<float> d_input(total_samples);
  DeviceBuffer<float2> d_output(total_samples);

  d_input.copy_from_host(host_input.data(), total_samples, stream_->get());

  stage.process(d_input.get(), d_output.get(), total_samples, stream_->get());

  std::vector<float2> host_output(total_samples);
  d_output.copy_to_host(host_output.data(), total_samples, stream_->get());
  stream_->synchronize();

  float dc_magnitude = std::sqrt(host_output[0].x * host_output[0].x +
                                 host_output[0].y * host_output[0].y);
  EXPECT_GT(dc_magnitude, config_.nfft * 0.9f);
}

/**
 * @test ProcessingStageTest.FFTStageSinusoid
 * @brief Tests the FFT of a single-frequency sinusoid.
 */
TEST_F(ProcessingStageTest, FFTStageSinusoid) {
  FFTStage stage;
  stage.initialize(config_, stream_->get());

  const int freq_bin = 10;
  const size_t total_samples = config_.nfft * config_.batch;
  std::vector<float> host_input(total_samples);

  for (size_t ch = 0; ch < static_cast<size_t>(config_.batch); ++ch) {
    for (size_t i = 0; i < static_cast<size_t>(config_.nfft); ++i) {
      host_input[ch * config_.nfft + i] =
          std::cos(2.0f * M_PI * freq_bin * i / config_.nfft);
    }
  }

  DeviceBuffer<float> d_input(total_samples);
  const size_t complex_size = (config_.nfft / 2 + 1) * config_.batch;
  DeviceBuffer<float2> d_output(total_samples);

  d_input.copy_from_host(host_input.data(), total_samples, stream_->get());
  stage.process(d_input.get(), d_output.get(), total_samples, stream_->get());

  std::vector<float2> host_output(complex_size);
  d_output.copy_to_host(host_output.data(), host_output.size(), stream_->get());
  stream_->synchronize();

  for (size_t ch = 0; ch < static_cast<size_t>(config_.batch); ++ch) {
    float max_magnitude = 0.0f;
    int max_bin = -1;

    for (size_t bin = 0; bin < static_cast<size_t>(config_.nfft / 2 + 1);
         ++bin) {
      float2 val = host_output[ch * (config_.nfft / 2 + 1) + bin];
      float mag = std::sqrt(val.x * val.x + val.y * val.y);
      if (mag > max_magnitude) {
        max_magnitude = mag;
        max_bin = bin;
      }
    }
    EXPECT_EQ(max_bin, freq_bin);
  }
}

// ============================================================================
// MagnitudeStage Tests
// ============================================================================

/**
 * @test ProcessingStageTest.MagnitudeStageInitialization
 * @brief Verifies correct initialization of the MagnitudeStage.
 */
TEST_F(ProcessingStageTest, MagnitudeStageInitialization) {
  MagnitudeStage stage;
  EXPECT_NO_THROW(stage.initialize(config_, stream_->get()));
  EXPECT_EQ(stage.name(), "MagnitudeStage");
  EXPECT_FALSE(stage.supports_inplace());
  EXPECT_EQ(stage.get_workspace_size(), 0);
}

/**
 * @test ProcessingStageTest.MagnitudeStageProcess
 * @brief Tests the magnitude calculation for a known complex input.
 */
TEST_F(ProcessingStageTest, MagnitudeStageProcess) {
  config_.scale_policy = StageConfig::ScalePolicy::NONE;
  MagnitudeStage stage;
  stage.initialize(config_, stream_->get());

  const size_t num_bins = config_.nfft / 2 + 1;
  const size_t total_complex = num_bins * config_.batch;
  std::vector<float2> host_input(total_complex,
                                 {3.0f, 4.0f});  // magnitude should be 5

  DeviceBuffer<float2> d_input(total_complex);
  DeviceBuffer<float> d_output(total_complex);

  d_input.copy_from_host(host_input.data(), total_complex, stream_->get());
  stage.process(d_input.get(), d_output.get(), total_complex, stream_->get());

  std::vector<float> host_output(total_complex);
  d_output.copy_to_host(host_output.data(), total_complex, stream_->get());
  stream_->synchronize();

  for (size_t i = 0; i < total_complex; ++i) {
    EXPECT_NEAR(host_output[i], 5.0f, 1e-5f);
  }
}

/**
 * @test ProcessingStageTest.MagnitudeStageScaling
 * @brief Tests the magnitude calculation with scaling applied.
 */
TEST_F(ProcessingStageTest, MagnitudeStageScaling) {
  config_.scale_policy = StageConfig::ScalePolicy::ONE_OVER_N;
  MagnitudeStage stage;
  stage.initialize(config_, stream_->get());

  const size_t num_bins = config_.nfft / 2 + 1;
  const size_t total_complex = num_bins * config_.batch;
  std::vector<float2> host_input(total_complex,
                                 {static_cast<float>(config_.nfft), 0.0f});

  DeviceBuffer<float2> d_input(total_complex);
  DeviceBuffer<float> d_output(total_complex);

  d_input.copy_from_host(host_input.data(), total_complex, stream_->get());
  stage.process(d_input.get(), d_output.get(), total_complex, stream_->get());

  std::vector<float> host_output(total_complex);
  d_output.copy_to_host(host_output.data(), total_complex, stream_->get());
  stream_->synchronize();

  // With 1/N scaling, output should be 1.0.
  for (size_t i = 0; i < total_complex; ++i) {
    EXPECT_NEAR(host_output[i], 1.0f, 1e-5f);
  }
}

// ============================================================================
// StageFactory Tests
// ============================================================================

/**
 * @test ProcessingStageTest.StageFactoryCreate
 * @brief Verifies that the StageFactory creates the correct stage types.
 */
TEST_F(ProcessingStageTest, StageFactoryCreate) {
  auto window_stage = StageFactory::create(StageFactory::StageType::WINDOW);
  EXPECT_NE(window_stage, nullptr);
  EXPECT_EQ(window_stage->name(), "WindowStage");

  auto fft_stage = StageFactory::create(StageFactory::StageType::FFT);
  EXPECT_NE(fft_stage, nullptr);
  EXPECT_EQ(fft_stage->name(), "FFTStage");

  auto mag_stage = StageFactory::create(StageFactory::StageType::MAGNITUDE);
  EXPECT_NE(mag_stage, nullptr);
  EXPECT_EQ(mag_stage->name(), "MagnitudeStage");
}

/**
 * @test ProcessingStageTest.StageFactoryDefaultPipeline
 * @brief Ensures the factory creates the default pipeline in the correct order.
 */
TEST_F(ProcessingStageTest, StageFactoryDefaultPipeline) {
  auto stages = StageFactory::create_default_pipeline();

  ASSERT_EQ(stages.size(), 3);
  EXPECT_EQ(stages[0]->name(), "WindowStage");
  EXPECT_EQ(stages[1]->name(), "FFTStage");
  EXPECT_EQ(stages[2]->name(), "MagnitudeStage");
}

// ============================================================================
// Window Utils Tests
// ============================================================================

/**
 * @test ProcessingStageTest.WindowUtilsHannGeneration
 * @brief Validates the correctness of the Hann window generation utility.
 */
TEST_F(ProcessingStageTest, WindowUtilsHannGeneration) {
  const int size = 64;
  std::vector<float> window(size);

  window_utils::generate_hann_window(window.data(), size, false);

  for (int i = 0; i < size; ++i) {
    float expected = 0.5f * (1.0f - std::cos(2.0f * M_PI * i / (size - 1)));
    EXPECT_NEAR(window[i], expected, 1e-5f);
  }

  EXPECT_NEAR(window[0], 0.0f, 1e-6f);
  EXPECT_NEAR(window[size - 1], 0.0f, 1e-6f);
  EXPECT_NEAR(window[size / 2], 1.0f, 0.1f);
}

// ============================================================================
// Integration Test
// ============================================================================

/**
 * @test ProcessingStageTest.FullPipelineIntegration
 * @brief An end-to-end test verifying the full sequence of processing stages.
 */
TEST_F(ProcessingStageTest, FullPipelineIntegration) {
  WindowStage window_stage;
  FFTStage fft_stage;
  MagnitudeStage mag_stage;

  window_stage.initialize(config_, stream_->get());
  fft_stage.initialize(config_, stream_->get());
  mag_stage.initialize(config_, stream_->get());

  const size_t total_samples = config_.nfft * config_.batch;
  const int test_freq_bin = 8;

  // This test was failing due to how the test signal was generated.
  // The original helper function `generate_test_signal` created a single
  // sine wave of length (nfft * batch), which meant each batch item
  // processed by the FFT was only seeing a fraction of the intended sine wave.
  // This corrected implementation generates a proper signal for each batch
  // item, ensuring the frequency content is correct for the FFT length.
  std::vector<float> host_input(total_samples);
  for (size_t ch = 0; ch < static_cast<size_t>(config_.batch); ++ch) {
    for (size_t i = 0; i < static_cast<size_t>(config_.nfft); ++i) {
      host_input[ch * config_.nfft + i] =
          std::cos(2.0f * M_PI * test_freq_bin * i / config_.nfft);
    }
  }

  DeviceBuffer<float> d_input(total_samples);
  DeviceBuffer<float> d_windowed(total_samples);
  DeviceBuffer<float2> d_fft(total_samples);
  DeviceBuffer<float> d_magnitude((config_.nfft / 2 + 1) * config_.batch);

  d_input.copy_from_host(host_input.data(), total_samples, stream_->get());

  window_stage.process(d_input.get(), d_windowed.get(), total_samples,
                       stream_->get());
  fft_stage.process(d_windowed.get(), d_fft.get(), total_samples,
                    stream_->get());
  mag_stage.process(d_fft.get(), d_magnitude.get(),
                    (config_.nfft / 2 + 1) * config_.batch, stream_->get());

  std::vector<float> magnitude((config_.nfft / 2 + 1) * config_.batch);
  d_magnitude.copy_to_host(magnitude.data(), magnitude.size(), stream_->get());
  stream_->synchronize();

  for (size_t ch = 0; ch < static_cast<size_t>(config_.batch); ++ch) {
    float max_mag = 0.0f;
    int peak_bin = -1;

    for (size_t bin = 0; bin <= static_cast<size_t>(config_.nfft / 2); ++bin) {
      float mag = magnitude[ch * (config_.nfft / 2 + 1) + bin];
      if (mag > max_mag) {
        max_mag = mag;
        peak_bin = bin;
      }
    }

    EXPECT_EQ(peak_bin, test_freq_bin);
    EXPECT_GT(max_mag, 0.1f);  // Expect a noticeable peak with normalized scaling
  }
}
