/**
 * @file test_signal_utils.cpp
 * @version 0.9.4
 * @date 2025-10-28
 * @author [Kevin Rahsaz]
 *
 * @brief Unit tests for signal utility functions.
 *
 * This test suite validates configuration validation, device enumeration,
 * and memory estimation utilities to improve code coverage.
 */

#include <gtest/gtest.h>

#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/core/signal_config.hpp"

using namespace ionosense;
using namespace ionosense::signal_utils;

/**
 * @class SignalUtilsTest
 * @brief Test fixture for signal utility tests.
 */
class SignalUtilsTest : public ::testing::Test {
 protected:
  void SetUp() override {
    // Check for CUDA device availability
    int device_count = 0;
    cudaError_t err = cudaGetDeviceCount(&device_count);
    if (err != cudaSuccess || device_count == 0) {
      GTEST_SKIP() << "No CUDA devices available for testing.";
    }

    // Standard valid configuration
    valid_config_.nfft = 1024;
    valid_config_.channels = 2;
    valid_config_.overlap = 0.5f;
    valid_config_.sample_rate_hz = 48000;
    valid_config_.stream_count = 3;
    valid_config_.pinned_buffer_count = 2;
  }

  SignalConfig valid_config_;
};

// ============================================================================
//  Device Enumeration Tests
// ============================================================================

TEST_F(SignalUtilsTest, GetAvailableDevicesReturnsNonEmpty) {
  auto devices = get_available_devices();
  EXPECT_FALSE(devices.empty());
}

TEST_F(SignalUtilsTest, GetAvailableDevicesContainsDeviceInfo) {
  auto devices = get_available_devices();
  ASSERT_FALSE(devices.empty());

  // Each device string should contain index and name
  for (const auto& device : devices) {
    EXPECT_NE(device.find("["), std::string::npos);
    EXPECT_NE(device.find("]"), std::string::npos);
    EXPECT_NE(device.find("CC"), std::string::npos);  // Compute capability
  }
}

// ============================================================================
//  Device Selection Tests
// ============================================================================

TEST_F(SignalUtilsTest, SelectBestDeviceReturnsValidIndex) {
  int device = select_best_device();
  EXPECT_GE(device, 0);

  // Verify device index is valid
  int device_count = 0;
  IONO_CUDA_CHECK(cudaGetDeviceCount(&device_count));
  EXPECT_LT(device, device_count);
}

TEST_F(SignalUtilsTest, SelectBestDeviceSelectsHighestSMCount) {
  int best_device = select_best_device();

  // Get properties of selected device
  cudaDeviceProp best_prop{};
  IONO_CUDA_CHECK(cudaGetDeviceProperties(&best_prop, best_device));

  // Verify it has the highest SM count
  int device_count = 0;
  IONO_CUDA_CHECK(cudaGetDeviceCount(&device_count));

  for (int i = 0; i < device_count; ++i) {
    cudaDeviceProp prop{};
    IONO_CUDA_CHECK(cudaGetDeviceProperties(&prop, i));
    EXPECT_LE(prop.multiProcessorCount, best_prop.multiProcessorCount);
  }
}

// ============================================================================
//  Configuration Validation Tests - Success Cases
// ============================================================================

TEST_F(SignalUtilsTest, ValidateConfigSuccess) {
  std::string error_msg;
  EXPECT_TRUE(validate_config(valid_config_, error_msg));
  EXPECT_TRUE(error_msg.empty());
}

TEST_F(SignalUtilsTest, ValidateConfigZeroOverlap) {
  SignalConfig config = valid_config_;
  config.overlap = 0.0f;  // Valid: no overlap

  std::string error_msg;
  EXPECT_TRUE(validate_config(config, error_msg));
  EXPECT_TRUE(error_msg.empty());
}

TEST_F(SignalUtilsTest, ValidateConfigHighOverlap) {
  SignalConfig config = valid_config_;
  config.overlap = 0.99f;  // Valid: very high overlap

  std::string error_msg;
  EXPECT_TRUE(validate_config(config, error_msg));
  EXPECT_TRUE(error_msg.empty());
}

// ============================================================================
//  Configuration Validation Tests - NFFT Errors
// ============================================================================

TEST_F(SignalUtilsTest, ValidateConfigInvalidNFFTNegative) {
  SignalConfig config = valid_config_;
  config.nfft = -1024;

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("nfft"), std::string::npos);
  EXPECT_NE(error_msg.find("power of 2"), std::string::npos);
}

TEST_F(SignalUtilsTest, ValidateConfigInvalidNFFTZero) {
  SignalConfig config = valid_config_;
  config.nfft = 0;

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("nfft"), std::string::npos);
}

TEST_F(SignalUtilsTest, ValidateConfigInvalidNFFTNotPowerOfTwo) {
  SignalConfig config = valid_config_;
  config.nfft = 1000;  // Not a power of 2

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("nfft"), std::string::npos);
  EXPECT_NE(error_msg.find("power of 2"), std::string::npos);
}

// ============================================================================
//  Configuration Validation Tests - Channels Errors
// ============================================================================

TEST_F(SignalUtilsTest, ValidateConfigInvalidChannelsZero) {
  SignalConfig config = valid_config_;
  config.channels = 0;

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("channels"), std::string::npos);
  EXPECT_NE(error_msg.find("positive"), std::string::npos);
}

TEST_F(SignalUtilsTest, ValidateConfigInvalidChannelsNegative) {
  SignalConfig config = valid_config_;
  config.channels = -5;

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("channels"), std::string::npos);
}

// ============================================================================
//  Configuration Validation Tests - Overlap Errors
// ============================================================================

TEST_F(SignalUtilsTest, ValidateConfigInvalidOverlapNegative) {
  SignalConfig config = valid_config_;
  config.overlap = -0.1f;

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("overlap"), std::string::npos);
  EXPECT_NE(error_msg.find("[0.0, 1.0)"), std::string::npos);
}

TEST_F(SignalUtilsTest, ValidateConfigInvalidOverlapTooHigh) {
  SignalConfig config = valid_config_;
  config.overlap = 1.0f;  // Invalid: must be < 1.0

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("overlap"), std::string::npos);
}

TEST_F(SignalUtilsTest, ValidateConfigInvalidOverlapGreaterThanOne) {
  SignalConfig config = valid_config_;
  config.overlap = 1.5f;

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("overlap"), std::string::npos);
}

// ============================================================================
//  Configuration Validation Tests - Sample Rate Errors
// ============================================================================

TEST_F(SignalUtilsTest, ValidateConfigInvalidSampleRateZero) {
  SignalConfig config = valid_config_;
  config.sample_rate_hz = 0;

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("sample_rate_hz"), std::string::npos);
  EXPECT_NE(error_msg.find("positive"), std::string::npos);
}

TEST_F(SignalUtilsTest, ValidateConfigInvalidSampleRateNegative) {
  SignalConfig config = valid_config_;
  config.sample_rate_hz = -48000;

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("sample_rate_hz"), std::string::npos);
}

// ============================================================================
//  Configuration Validation Tests - Stream Count Errors
// ============================================================================

TEST_F(SignalUtilsTest, ValidateConfigInvalidStreamCountZero) {
  SignalConfig config = valid_config_;
  config.stream_count = 0;

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("stream_count"), std::string::npos);
  EXPECT_NE(error_msg.find("positive"), std::string::npos);
}

TEST_F(SignalUtilsTest, ValidateConfigInvalidStreamCountNegative) {
  SignalConfig config = valid_config_;
  config.stream_count = -3;

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("stream_count"), std::string::npos);
}

// ============================================================================
//  Configuration Validation Tests - Pinned Buffer Count Errors
// ============================================================================

TEST_F(SignalUtilsTest, ValidateConfigInvalidPinnedBufferCountZero) {
  SignalConfig config = valid_config_;
  config.pinned_buffer_count = 0;

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("pinned_buffer_count"), std::string::npos);
  EXPECT_NE(error_msg.find("at least 2"), std::string::npos);
}

TEST_F(SignalUtilsTest, ValidateConfigInvalidPinnedBufferCountOne) {
  SignalConfig config = valid_config_;
  config.pinned_buffer_count = 1;  // Invalid: need >= 2 for double buffering

  std::string error_msg;
  EXPECT_FALSE(validate_config(config, error_msg));
  EXPECT_FALSE(error_msg.empty());
  EXPECT_NE(error_msg.find("pinned_buffer_count"), std::string::npos);
  EXPECT_NE(error_msg.find("at least 2"), std::string::npos);
}

// ============================================================================
//  Memory Estimation Tests
// ============================================================================

TEST_F(SignalUtilsTest, EstimateMemoryUsageNonZero) {
  size_t mem = estimate_memory_usage(valid_config_);
  EXPECT_GT(mem, 0u);
}

TEST_F(SignalUtilsTest, EstimateMemoryUsageScalesWithNFFT) {
  SignalConfig config_small = valid_config_;
  config_small.nfft = 512;

  SignalConfig config_large = valid_config_;
  config_large.nfft = 4096;

  size_t mem_small = estimate_memory_usage(config_small);
  size_t mem_large = estimate_memory_usage(config_large);

  // Larger NFFT should require more memory
  EXPECT_GT(mem_large, mem_small);
}

TEST_F(SignalUtilsTest, EstimateMemoryUsageScalesWithChannels) {
  SignalConfig config_few = valid_config_;
  config_few.channels = 1;

  SignalConfig config_many = valid_config_;
  config_many.channels = 16;

  size_t mem_few = estimate_memory_usage(config_few);
  size_t mem_many = estimate_memory_usage(config_many);

  // More channels should require more memory
  EXPECT_GT(mem_many, mem_few);
}

TEST_F(SignalUtilsTest, EstimateMemoryUsageScalesWithBufferCount) {
  SignalConfig config_few = valid_config_;
  config_few.pinned_buffer_count = 2;

  SignalConfig config_many = valid_config_;
  config_many.pinned_buffer_count = 8;

  size_t mem_few = estimate_memory_usage(config_few);
  size_t mem_many = estimate_memory_usage(config_many);

  // More buffers should require more memory
  EXPECT_GT(mem_many, mem_few);
}

TEST_F(SignalUtilsTest, EstimateMemoryUsageReasonableSize) {
  size_t mem = estimate_memory_usage(valid_config_);

  // For nfft=1024, channels=2, pinned_buffer_count=2:
  // Should be in the range of a few MB, definitely < 1 GB
  EXPECT_LT(mem, 1024u * 1024u * 1024u);  // < 1 GB
  EXPECT_GT(mem, 1024u);                  // > 1 KB
}
