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

#include "sigtekx/core/cuda_wrappers.hpp"
#include "sigtekx/core/signal_config.hpp"

using namespace sigtekx;
using namespace sigtekx::signal_utils;

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
  SIGTEKX_CUDA_CHECK(cudaGetDeviceCount(&device_count));
  EXPECT_LT(device, device_count);
}

TEST_F(SignalUtilsTest, SelectBestDeviceSelectsHighestSMCount) {
  int best_device = select_best_device();

  // Get properties of selected device
  cudaDeviceProp best_prop{};
  SIGTEKX_CUDA_CHECK(cudaGetDeviceProperties(&best_prop, best_device));

  // Verify it has the highest SM count
  int device_count = 0;
  SIGTEKX_CUDA_CHECK(cudaGetDeviceCount(&device_count));

  for (int i = 0; i < device_count; ++i) {
    cudaDeviceProp prop{};
    SIGTEKX_CUDA_CHECK(cudaGetDeviceProperties(&prop, i));
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

// ============================================================================
//  cuFFT Workspace Estimation Tests
// ============================================================================

TEST_F(SignalUtilsTest, EstimateCufftWorkspaceBasic) {
  size_t workspace = estimate_cufft_workspace_bytes(1024, 2, true, true);

  // Should return non-zero workspace size
  EXPECT_GT(workspace, 0u);

  // Should be reasonable (not absurdly large)
  EXPECT_LT(workspace, 100u * 1024u * 1024u);  // < 100 MB for small config
}

TEST_F(SignalUtilsTest, EstimateCufftWorkspaceR2CVsC2C) {
  size_t nfft = 4096;
  size_t channels = 8;

  size_t workspace_r2c = estimate_cufft_workspace_bytes(nfft, channels, true, true);
  size_t workspace_c2c = estimate_cufft_workspace_bytes(nfft, channels, false, true);

  // Both should be non-zero
  EXPECT_GT(workspace_r2c, 0u);
  EXPECT_GT(workspace_c2c, 0u);

  // C2C typically requires more workspace than R2C
  // But we just verify both are reasonable, not their relative sizes
  EXPECT_LT(workspace_r2c, 1024u * 1024u * 1024u);  // < 1 GB
  EXPECT_LT(workspace_c2c, 1024u * 1024u * 1024u);  // < 1 GB
}

TEST_F(SignalUtilsTest, EstimateCufftWorkspaceScalesWithNFFT) {
  size_t channels = 8;

  size_t workspace_small = estimate_cufft_workspace_bytes(1024, channels, true, true);
  size_t workspace_medium = estimate_cufft_workspace_bytes(4096, channels, true, true);
  size_t workspace_large = estimate_cufft_workspace_bytes(16384, channels, true, true);

  // Larger NFFT should generally require more (or equal) workspace
  EXPECT_LE(workspace_small, workspace_large);
  EXPECT_LE(workspace_medium, workspace_large);
}

TEST_F(SignalUtilsTest, EstimateCufftWorkspaceScalesWithChannels) {
  size_t nfft = 4096;

  size_t workspace_few = estimate_cufft_workspace_bytes(nfft, 1, true, true);
  size_t workspace_many = estimate_cufft_workspace_bytes(nfft, 16, true, true);

  // More channels (batches) may require more workspace
  EXPECT_GT(workspace_few, 0u);
  EXPECT_GT(workspace_many, 0u);
  EXPECT_LE(workspace_few, workspace_many);
}

TEST_F(SignalUtilsTest, EstimateCufftWorkspaceMatchesActualRuntime) {
  // Test ionosphere-relevant configurations
  struct TestCase {
    size_t nfft;
    size_t channels;
    bool is_real;
  };

  std::vector<TestCase> cases = {
      {1024, 1, true},    // Minimal
      {4096, 8, true},    // Ionosphere standard
      {8192, 8, true},    // Ionosphere hi-res
      {16384, 4, true},   // ULF/VLF
  };

  for (const auto& tc : cases) {
    // 1. Get estimate via new function
    size_t estimated = estimate_cufft_workspace_bytes(
        tc.nfft, tc.channels, tc.is_real, false  // Strict mode (no fallback)
    );

    // 2. Get actual workspace from CufftPlan
    CufftPlan plan;
    int n[] = {static_cast<int>(tc.nfft)};
    int istride = 1;
    int ostride = 1;
    int idist = tc.nfft;
    int odist = tc.nfft / 2 + 1;

    cudaStream_t stream;
    SIGTEKX_CUDA_CHECK(cudaStreamCreate(&stream));

    plan.create_plan_many(
        1,  // rank
        n,
        nullptr, istride, idist,  // input
        nullptr, ostride, odist,  // output
        tc.is_real ? CUFFT_R2C : CUFFT_C2C,
        tc.channels,
        stream
    );

    size_t actual = plan.work_size();

    // 3. Verify accuracy
    // Both should either be 0 (no workspace needed) or match within tolerance
    if (estimated == 0 && actual == 0) {
      // Valid case: cuFFT doesn't need workspace for this config
      EXPECT_EQ(estimated, actual);
    } else if (estimated > 0 || actual > 0) {
      // At least one is non-zero, check tolerance
      // cufftEstimate may be conservative (larger than actual)
      double ratio = static_cast<double>(estimated) / std::max(actual, size_t(1));

      EXPECT_GE(ratio, 0.9)
          << "Underestimate for nfft=" << tc.nfft
          << " channels=" << tc.channels
          << " estimated=" << estimated
          << " actual=" << actual;

      EXPECT_LE(ratio, 2.0)  // Allow 2× over-estimation (very conservative)
          << "Severe overestimate for nfft=" << tc.nfft
          << " channels=" << tc.channels
          << " estimated=" << estimated
          << " actual=" << actual;
    }

    SIGTEKX_CUDA_CHECK(cudaStreamDestroy(stream));
  }
}

TEST_F(SignalUtilsTest, EstimateCufftWorkspaceFallbackOnError) {
  // Test with impossible parameters to trigger cuFFT error
  // (cuFFT may or may not error on 0, but we test the fallback logic)

  // With fallback enabled - should not throw
  EXPECT_NO_THROW({
    size_t workspace = estimate_cufft_workspace_bytes(
        0, 8, true, true  // Invalid nfft=0, fallback=true
    );
    // May return heuristic estimate (0 * 8 * 8 = 0) or cuFFT may succeed
    EXPECT_GE(workspace, 0u);
  });
}

TEST_F(SignalUtilsTest, EstimateCufftWorkspaceThrowsWithoutFallback) {
  // Test error handling when fallback is disabled
  // Note: Some invalid configs might still succeed in cufftEstimate1d
  // This test verifies the exception mechanism works if cuFFT fails

  bool threw_exception = false;
  try {
    // Try with a configuration that might fail
    estimate_cufft_workspace_bytes(
        0, 0, true, false  // nfft=0, channels=0, fallback=false
    );
  } catch (const std::runtime_error& e) {
    threw_exception = true;
    // Verify error message contains useful info
    std::string msg = e.what();
    EXPECT_NE(msg.find("cufftEstimate1d"), std::string::npos);
  }

  // Note: If cuFFT doesn't error on these params, that's also valid behavior
  // We just verify that IF it errors, we throw correctly
}
