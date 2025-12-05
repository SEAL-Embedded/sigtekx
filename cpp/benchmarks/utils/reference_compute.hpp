/**
 * @file reference_compute.hpp
 * @brief Pipeline-matching reference computation for accuracy validation.
 *
 * This reference implementation EXACTLY mirrors the production pipeline:
 * 1. Apply Hann window (PERIODIC symmetry, UNITY normalization)
 * 2. cuFFT R2C transform
 * 3. Compute magnitude with 1/N scaling
 *
 * **Hardcoded to current pipeline** - if pipeline changes, update this reference!
 *
 * For comprehensive cross-validation with scipy, use Python tests:
 *   pytest tests/test_accuracy.py
 */

#pragma once

#include <cmath>
#include <vector>

#include <cuda_runtime.h>
#include <cufft.h>

#include "sigtekx/profiling/nvtx.hpp"
#include "sigtekx/core/window_functions.hpp"

namespace sigtekx {
namespace benchmark {

/**
 * @brief Compute reference output that EXACTLY matches production pipeline.
 *
 * Pipeline stages:
 * 1. Window: Hann, PERIODIC symmetry, UNITY normalization
 * 2. FFT: cuFFT R2C
 * 3. Magnitude: sqrt(real^2 + imag^2) * (1/N) scaling
 *
 * This is NOT meant to be general-purpose - it's hardcoded to match the
 * current pipeline configuration exactly.
 *
 * @param input Input signal (time domain)
 * @param nfft FFT size
 * @param batch Number of frames
 * @param window_type Window function type (default: Hann)
 * @param scale_factor FFT output scaling (default: 1/N)
 * @return Vector containing magnitude spectrum matching pipeline output
 */
inline std::vector<float> compute_pipeline_reference(
    const std::vector<float>& input,
    int nfft,
    int batch,
    window_functions::WindowKind window_type = window_functions::WindowKind::HANN,
    float scale_factor = -1.0f  // -1 means auto (1/N)
) {
  IONO_NVTX_RANGE("Pipeline Reference Computation", profiling::colors::PURPLE);

  const size_t num_bins = static_cast<size_t>(nfft / 2 + 1);
  const size_t complex_output_size = num_bins * batch;
  const size_t magnitude_output_size = complex_output_size;

  // Auto-calculate scaling if not provided
  if (scale_factor < 0.0f) {
    scale_factor = 1.0f / static_cast<float>(nfft);
  }

  // Step 1: Generate window coefficients (PERIODIC symmetry, no sqrt)
  std::vector<float> window_coeffs(nfft);
  {
    IONO_NVTX_RANGE("Generate Window Coefficients", profiling::colors::CYAN);
    window_functions::fill_window(
        window_coeffs.data(),
        nfft,
        window_type,
        false,  // sqrt_norm = false (UNITY normalization)
        window_functions::WindowSymmetry::PERIODIC
    );
  }

  // Step 2: Apply window to input on CPU
  std::vector<float> windowed_input(input.size());
  {
    IONO_NVTX_RANGE("Apply Window", profiling::colors::CYAN);
    for (int b = 0; b < batch; ++b) {
      for (int i = 0; i < nfft; ++i) {
        const int idx = b * nfft + i;
        windowed_input[idx] = input[idx] * window_coeffs[i];
      }
    }
  }

  // Step 3: Allocate device memory for GPU computation
  float* d_input = nullptr;
  cufftComplex* d_complex_output = nullptr;

  cudaMalloc(&d_input, windowed_input.size() * sizeof(float));
  cudaMalloc(&d_complex_output, complex_output_size * sizeof(cufftComplex));

  // Copy windowed input to device
  cudaMemcpy(d_input, windowed_input.data(), windowed_input.size() * sizeof(float),
             cudaMemcpyHostToDevice);

  // Step 4: Create cuFFT plan and execute R2C transform
  cufftHandle plan;
  int n[1] = {nfft};
  {
    IONO_NVTX_RANGE("Create cuFFT Plan", profiling::colors::DARK_GRAY);
    cufftPlanMany(&plan, 1, n, nullptr, 1, nfft, nullptr, 1, num_bins,
                  CUFFT_R2C, batch);
  }

  {
    IONO_NVTX_RANGE("Execute cuFFT R2C", profiling::colors::PURPLE);
    cufftExecR2C(plan, d_input, d_complex_output);
  }

  // Step 5: Copy complex result back to host
  std::vector<cufftComplex> complex_output(complex_output_size);
  cudaMemcpy(complex_output.data(), d_complex_output,
             complex_output_size * sizeof(cufftComplex),
             cudaMemcpyDeviceToHost);

  // Step 6: Compute magnitude with 1/N scaling on CPU
  std::vector<float> output(magnitude_output_size);
  {
    IONO_NVTX_RANGE("Compute Magnitude", profiling::colors::CYAN);
    for (size_t i = 0; i < complex_output_size; ++i) {
      const float real = complex_output[i].x;
      const float imag = complex_output[i].y;
      const float magnitude = std::sqrt(real * real + imag * imag);
      output[i] = magnitude * scale_factor;  // Apply 1/N scaling
    }
  }

  // Cleanup
  cufftDestroy(plan);
  cudaFree(d_input);
  cudaFree(d_complex_output);

  return output;
}

/**
 * @brief Compute maximum absolute error between two vectors.
 *
 * @param output Test output
 * @param reference Reference output
 * @return Maximum absolute difference
 */
inline float compute_max_error(const std::vector<float>& output,
                                const std::vector<float>& reference) {
  if (output.size() != reference.size()) {
    return std::numeric_limits<float>::infinity();
  }

  float max_error = 0.0f;
  for (size_t i = 0; i < output.size(); ++i) {
    const float error = std::abs(output[i] - reference[i]);
    max_error = std::max(max_error, error);
  }
  return max_error;
}

/**
 * @brief Compute relative error (RMS error normalized by RMS signal).
 *
 * @param output Test output
 * @param reference Reference output
 * @return Relative RMS error
 */
inline float compute_relative_error(const std::vector<float>& output,
                                     const std::vector<float>& reference) {
  if (output.size() != reference.size()) {
    return std::numeric_limits<float>::infinity();
  }

  double sum_sq_error = 0.0;
  double sum_sq_signal = 0.0;

  for (size_t i = 0; i < output.size(); ++i) {
    const float error = output[i] - reference[i];
    sum_sq_error += error * error;
    sum_sq_signal += reference[i] * reference[i];
  }

  if (sum_sq_signal < 1e-20) {
    return 0.0f;  // Avoid division by zero
  }

  return std::sqrt(static_cast<float>(sum_sq_error / sum_sq_signal));
}

}  // namespace benchmark
}  // namespace sigtekx
