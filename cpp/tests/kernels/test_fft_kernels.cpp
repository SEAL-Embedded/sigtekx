/**
 * @file test_fft_kernels.cpp
 * @version 0.9.3
 * @date 2025-10-28
 * @author [Kevin Rahsaz]
 *
 * @brief Unit tests for FFT kernel launch wrappers.
 *
 * This test suite validates individual CUDA kernel launchers from
 * fft_wrapper.cu that are not covered by integration tests. Tests kernel
 * correctness with known inputs and outputs to improve code coverage.
 */

#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "ionosense/core/cuda_wrappers.hpp"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

using namespace ionosense;

// Forward declarations of kernel launch functions from fft_wrapper.cu
namespace ionosense {
namespace kernels {

extern void launch_real_to_complex(const float* input, float2* output, int nfft,
                                   int batch, int stride, cudaStream_t stream);

extern void launch_window_and_convert(const float* input, float2* output,
                                      const float* window, int nfft, int batch,
                                      int stride, cudaStream_t stream);

extern void launch_magnitude(const float2* input, float* output, int num_bins,
                             int batch, float scale, cudaStream_t stream);

extern void launch_magnitude_squared(const float2* input, float* output,
                                     int num_bins, int batch, float scale,
                                     cudaStream_t stream);

extern void launch_scale_fft(float2* data, int num_elements, float scale,
                             cudaStream_t stream);

}  // namespace kernels
}  // namespace ionosense

/**
 * @class FFTKernelsTest
 * @brief Test fixture for FFT kernel tests.
 */
class FFTKernelsTest : public ::testing::Test {
 protected:
  void SetUp() override {
    // Check for CUDA device availability
    int device_count = 0;
    cudaError_t err = cudaGetDeviceCount(&device_count);
    if (err != cudaSuccess || device_count == 0) {
      GTEST_SKIP() << "No CUDA devices available for testing.";
    }

    // Create CUDA stream
    stream_ = std::make_unique<CudaStream>();
  }

  std::unique_ptr<CudaStream> stream_;
};

// ============================================================================
//  Real to Complex Conversion Tests
// ============================================================================

TEST_F(FFTKernelsTest, RealToComplexBasic) {
  const int nfft = 8;
  const int batch = 2;
  const int stride = nfft;  // Channel stride (contiguous layout)

  // Create input: channel 0: [1-8], channel 1: [9-16]
  std::vector<float> host_input(nfft * batch);
  for (int i = 0; i < nfft * batch; ++i) {
    host_input[i] = static_cast<float>(i + 1);
  }

  // Allocate device memory
  DeviceBuffer<float> d_input(nfft * batch);
  DeviceBuffer<float2> d_output(nfft * batch);

  d_input.copy_from_host(host_input.data(), host_input.size(), stream_->get());

  // Launch kernel
  kernels::launch_real_to_complex(d_input.get(), d_output.get(), nfft, batch,
                                  stride, stream_->get());

  // Copy result back
  std::vector<float2> host_output(nfft * batch);
  d_output.copy_to_host(host_output.data(), host_output.size(), stream_->get());
  stream_->synchronize();

  // Verify: real part should match input, imaginary should be 0
  // Output is also in contiguous channel layout
  for (int i = 0; i < nfft * batch; ++i) {
    EXPECT_FLOAT_EQ(host_output[i].x, host_input[i]);
    EXPECT_FLOAT_EQ(host_output[i].y, 0.0f);
  }
}

TEST_F(FFTKernelsTest, RealToComplexWithStride) {
  const int nfft = 4;
  const int batch = 2;
  const int stride = 6;  // Non-contiguous channels (gap between channels)

  // Input layout with stride=6:
  // Channel 0: positions 0-3 (values 1-4)
  // Gap: positions 4-5 (values 99, 99 - unused)
  // Channel 1: positions 6-9 (values 5-8)
  std::vector<float> host_input(stride + nfft);  // 10 elements total
  // Channel 0
  for (int i = 0; i < nfft; ++i) {
    host_input[i] = static_cast<float>(i + 1);  // 1, 2, 3, 4
  }
  // Gap
  host_input[4] = 99.0f;
  host_input[5] = 99.0f;
  // Channel 1
  for (int i = 0; i < nfft; ++i) {
    host_input[stride + i] = static_cast<float>(i + 5);  // 5, 6, 7, 8
  }

  DeviceBuffer<float> d_input(stride + nfft);
  DeviceBuffer<float2> d_output(nfft * batch);

  d_input.copy_from_host(host_input.data(), host_input.size(), stream_->get());

  kernels::launch_real_to_complex(d_input.get(), d_output.get(), nfft, batch,
                                  stride, stream_->get());

  std::vector<float2> host_output(nfft * batch);
  d_output.copy_to_host(host_output.data(), host_output.size(), stream_->get());
  stream_->synchronize();

  // Verify: Channel 0 should have values 1-4, Channel 1 should have values 5-8
  for (int b = 0; b < batch; ++b) {
    for (int i = 0; i < nfft; ++i) {
      int output_idx = b * nfft + i;
      float expected = static_cast<float>((b * nfft) + i + 1);
      EXPECT_FLOAT_EQ(host_output[output_idx].x, expected);
      EXPECT_FLOAT_EQ(host_output[output_idx].y, 0.0f);
    }
  }
}

// ============================================================================
//  Fused Window and Convert Tests
// ============================================================================

TEST_F(FFTKernelsTest, WindowAndConvertBasic) {
  const int nfft = 8;
  const int batch = 1;
  const int stride = 1;

  // Input: all ones
  std::vector<float> host_input(nfft, 1.0f);

  // Window: Hann window (simplified: 0.5 * (1 - cos(2*pi*i/N)))
  std::vector<float> host_window(nfft);
  for (int i = 0; i < nfft; ++i) {
    host_window[i] =
        0.5f * (1.0f - std::cos(2.0f * M_PI * i / static_cast<float>(nfft)));
  }

  DeviceBuffer<float> d_input(nfft);
  DeviceBuffer<float> d_window(nfft);
  DeviceBuffer<float2> d_output(nfft);

  d_input.copy_from_host(host_input.data(), host_input.size(), stream_->get());
  d_window.copy_from_host(host_window.data(), host_window.size(),
                          stream_->get());

  // Launch fused kernel
  kernels::launch_window_and_convert(d_input.get(), d_output.get(),
                                     d_window.get(), nfft, batch, stride,
                                     stream_->get());

  std::vector<float2> host_output(nfft);
  d_output.copy_to_host(host_output.data(), host_output.size(), stream_->get());
  stream_->synchronize();

  // Verify: real part should be input * window, imaginary should be 0
  for (int i = 0; i < nfft; ++i) {
    float expected = host_input[i] * host_window[i];
    EXPECT_NEAR(host_output[i].x, expected, 1e-6f);
    EXPECT_FLOAT_EQ(host_output[i].y, 0.0f);
  }
}

// ============================================================================
//  Magnitude (Non-Strided) Tests
// ============================================================================

TEST_F(FFTKernelsTest, MagnitudeNonStridedBasic) {
  const int num_bins = 5;
  const int batch = 2;
  const float scale = 1.0f;

  // Create complex input with known magnitudes
  // (3, 4) -> magnitude 5, (0, 0) -> magnitude 0, (1, 0) -> magnitude 1
  std::vector<float2> host_input = {
      {3.0f, 4.0f}, {0.0f, 0.0f}, {1.0f, 0.0f}, {5.0f, 12.0f}, {0.0f, 1.0f},
      {6.0f, 8.0f}, {1.0f, 1.0f}, {0.0f, 0.0f}, {3.0f, 4.0f},  {2.0f, 0.0f}};

  DeviceBuffer<float2> d_input(num_bins * batch);
  DeviceBuffer<float> d_output(num_bins * batch);

  d_input.copy_from_host(host_input.data(), host_input.size(), stream_->get());

  // Launch non-strided magnitude kernel
  kernels::launch_magnitude(d_input.get(), d_output.get(), num_bins, batch,
                            scale, stream_->get());

  std::vector<float> host_output(num_bins * batch);
  d_output.copy_to_host(host_output.data(), host_output.size(), stream_->get());
  stream_->synchronize();

  // Verify magnitudes
  std::vector<float> expected = {
      5.0f, 0.0f, 1.0f, 13.0f, 1.0f, 10.0f, std::sqrt(2.0f), 0.0f, 5.0f, 2.0f};

  for (size_t i = 0; i < expected.size(); ++i) {
    EXPECT_NEAR(host_output[i], expected[i], 1e-5f);
  }
}

// ============================================================================
//  Magnitude Squared (Power Spectrum) Tests
// ============================================================================

TEST_F(FFTKernelsTest, MagnitudeSquaredBasic) {
  const int num_bins = 4;
  const int batch = 1;
  const float scale = 1.0f;

  // Complex input: (3, 4), (1, 0), (0, 1), (5, 12)
  // Expected power: 25, 1, 1, 169
  std::vector<float2> host_input = {
      {3.0f, 4.0f}, {1.0f, 0.0f}, {0.0f, 1.0f}, {5.0f, 12.0f}};

  DeviceBuffer<float2> d_input(num_bins);
  DeviceBuffer<float> d_output(num_bins);

  d_input.copy_from_host(host_input.data(), host_input.size(), stream_->get());

  kernels::launch_magnitude_squared(d_input.get(), d_output.get(), num_bins,
                                    batch, scale, stream_->get());

  std::vector<float> host_output(num_bins);
  d_output.copy_to_host(host_output.data(), host_output.size(), stream_->get());
  stream_->synchronize();

  // Verify power spectrum
  EXPECT_NEAR(host_output[0], 25.0f, 1e-5f);
  EXPECT_NEAR(host_output[1], 1.0f, 1e-5f);
  EXPECT_NEAR(host_output[2], 1.0f, 1e-5f);
  EXPECT_NEAR(host_output[3], 169.0f, 1e-5f);
}

TEST_F(FFTKernelsTest, MagnitudeSquaredWithScaling) {
  const int num_bins = 3;
  const int batch = 1;
  const float scale = 2.0f;

  // Complex input: (1, 1), (2, 0), (0, 3)
  // Power: 2, 4, 9
  // Scaled: power * scale * scale = power * 4
  // Result: 8, 16, 36
  std::vector<float2> host_input = {{1.0f, 1.0f}, {2.0f, 0.0f}, {0.0f, 3.0f}};

  DeviceBuffer<float2> d_input(num_bins);
  DeviceBuffer<float> d_output(num_bins);

  d_input.copy_from_host(host_input.data(), host_input.size(), stream_->get());

  kernels::launch_magnitude_squared(d_input.get(), d_output.get(), num_bins,
                                    batch, scale, stream_->get());

  std::vector<float> host_output(num_bins);
  d_output.copy_to_host(host_output.data(), host_output.size(), stream_->get());
  stream_->synchronize();

  // Note: kernel applies scale * scale (line 248 in fft_wrapper.cu)
  EXPECT_NEAR(host_output[0], 8.0f, 1e-5f);   // 2 * 2 * 2
  EXPECT_NEAR(host_output[1], 16.0f, 1e-5f);  // 4 * 2 * 2
  EXPECT_NEAR(host_output[2], 36.0f, 1e-5f);  // 9 * 2 * 2
}

// ============================================================================
//  FFT Output Scaling Tests
// ============================================================================

TEST_F(FFTKernelsTest, ScaleFFTBasic) {
  const int num_elements = 6;
  const float scale = 0.5f;

  // Complex data: (2, 4), (6, 8), (10, 12)
  std::vector<float2> host_data = {{2.0f, 4.0f},   {6.0f, 8.0f},
                                   {10.0f, 12.0f}, {14.0f, 16.0f},
                                   {18.0f, 20.0f}, {22.0f, 24.0f}};

  DeviceBuffer<float2> d_data(num_elements);
  d_data.copy_from_host(host_data.data(), host_data.size(), stream_->get());

  // Scale in-place
  kernels::launch_scale_fft(d_data.get(), num_elements, scale, stream_->get());

  std::vector<float2> host_output(num_elements);
  d_data.copy_to_host(host_output.data(), host_output.size(), stream_->get());
  stream_->synchronize();

  // Verify scaling
  for (size_t i = 0; i < host_data.size(); ++i) {
    EXPECT_NEAR(host_output[i].x, host_data[i].x * scale, 1e-5f);
    EXPECT_NEAR(host_output[i].y, host_data[i].y * scale, 1e-5f);
  }
}

TEST_F(FFTKernelsTest, ScaleFFTZeroScale) {
  const int num_elements = 4;
  const float scale = 0.0f;

  std::vector<float2> host_data = {
      {1.0f, 2.0f}, {3.0f, 4.0f}, {5.0f, 6.0f}, {7.0f, 8.0f}};

  DeviceBuffer<float2> d_data(num_elements);
  d_data.copy_from_host(host_data.data(), host_data.size(), stream_->get());

  kernels::launch_scale_fft(d_data.get(), num_elements, scale, stream_->get());

  std::vector<float2> host_output(num_elements);
  d_data.copy_to_host(host_output.data(), host_output.size(), stream_->get());
  stream_->synchronize();

  // All values should be zero
  for (int i = 0; i < num_elements; ++i) {
    EXPECT_FLOAT_EQ(host_output[i].x, 0.0f);
    EXPECT_FLOAT_EQ(host_output[i].y, 0.0f);
  }
}
