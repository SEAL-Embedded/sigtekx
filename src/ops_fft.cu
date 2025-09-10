/**
 * @file ops_fft.cu
 * @version 1.0
 * @date 2025-09-01
 * @author [Kevin Rahsaz]
 *
 * @brief CUDA kernel implementations for the FFT signal processing pipeline.
 *
 * This file contains the device-side CUDA C++ code for core operations such
 * as windowing, magnitude calculation, and data type conversions. Kernels are
 * designed for high performance, adhering to best practices like coalesced
 * memory access and grid-stride loops for scalability, which are essential for
 * reproducible and efficient research engineering (RE/RSE).
 *
 * @note All kernels use the `__restrict__` keyword to indicate to the compiler
 * that pointers do not alias, enabling more aggressive optimization.
 * The grid-stride loop pattern (`for (int idx = ...; idx < total; idx +=
 * gridDim.x * blockDim.x)`) is used to ensure that kernels are flexible and can
 * process data of any size, regardless of the launch grid dimensions.
 */

#include <cuda_fp16.h>
#include <cuda_runtime.h>
#include <cufft.h>

#include <algorithm>
#include <cmath>

#include "ionosense/profiling_macros.hpp"

namespace ionosense {
namespace kernels {

// --- Kernel Configuration Constants ---

/** @brief The number of threads in a CUDA warp, a fundamental unit of execution
 * on NVIDIA GPUs. */
constexpr int WARP_SIZE = 32;
/** @brief The maximum number of threads per block, chosen as a common value for
 * good hardware occupancy. */
constexpr int MAX_THREADS_PER_BLOCK = 256;

// --- CUDA Kernels ---

/**
 * @brief Applies a window function to the input signal element-wise.
 *
 * This kernel multiplies each sample of the input signal by the corresponding
 * window coefficient. It can operate in-place (input == output) or
 * out-of-place.
 *
 * @param[in]  input       Device pointer to the input real-valued signal.
 * @param[out] output      Device pointer to the windowed output real-valued
 * signal.
 * @param[in]  window      Device pointer to the window coefficients.
 * @param nfft             The size of the FFT and the window.
 * @param batch            The number of signals in the batch.
 * @param stride           The distance (in elements) between the start of
 * consecutive signals.
 */
__global__ void apply_window_kernel(const float* __restrict__ input,
                                    float* __restrict__ output,
                                    const float* __restrict__ window, int nfft,
                                    int batch, int stride) {
  const int total_elements = nfft * batch;
  for (int idx = blockIdx.x * blockDim.x + threadIdx.x; idx < total_elements;
       idx += blockDim.x * gridDim.x) {
    const int sample_idx = idx % nfft;
    const int channel_idx = idx / nfft;

    const float sample = input[channel_idx * stride + sample_idx];
    const float window_val = window[sample_idx];

    output[channel_idx * stride + sample_idx] = sample * window_val;
  }
}

/**
 * @brief Applies a window function to a complex signal (float2).
 *
 * This version is optimized for complex data, applying the window to both
 * real and imaginary components.
 *
 * @param[in]  input    Device pointer to the input complex signal.
 * @param[out] output   Device pointer to the windowed output complex signal.
 * @param[in]  window   Device pointer to the window coefficients.
 * @param nfft          The size of the FFT frame.
 * @param batch         The number of signals in the batch.
 */
__global__ void apply_window_complex_kernel(const float2* __restrict__ input,
                                            float2* __restrict__ output,
                                            const float* __restrict__ window,
                                            int nfft, int batch) {
  const int total_elements = nfft * batch;
  for (int idx = blockIdx.x * blockDim.x + threadIdx.x; idx < total_elements;
       idx += blockDim.x * gridDim.x) {
    const int sample_idx = idx % nfft;
    const int linear_idx = idx;

    float2 sample = input[linear_idx];
    const float window_val = window[sample_idx];

    sample.x *= window_val;
    sample.y *= window_val;

    output[linear_idx] = sample;
  }
}

/**
 * @brief Converts a real-valued signal to a complex signal format for cuFFT.
 *
 * This kernel takes a real signal and converts it into a complex signal
 * by setting the imaginary part of each sample to zero.
 *
 * @param[in]  input        Device pointer to the real-valued input signal.
 * @param[out] output       Device pointer for the complex-valued output signal
 * (float2).
 * @param nfft              The size of the FFT frame.
 * @param batch             The number of signals in the batch.
 * @param input_stride      The stride of the input signal.
 */
__global__ void real_to_complex_kernel(const float* __restrict__ input,
                                       float2* __restrict__ output, int nfft,
                                       int batch, int input_stride) {
  const int total_elements = nfft * batch;
  for (int idx = blockIdx.x * blockDim.x + threadIdx.x; idx < total_elements;
       idx += blockDim.x * gridDim.x) {
    const int sample_idx = idx % nfft;
    const int channel_idx = idx / nfft;

    const float real_val = input[channel_idx * input_stride + sample_idx];

    output[channel_idx * nfft + sample_idx] = make_float2(real_val, 0.0f);
  }
}

/**
 * @brief Fused kernel that applies a window and converts to complex format.
 *
 * This kernel combines windowing and real-to-complex conversion into a single
 * operation to reduce memory bandwidth and kernel launch overhead.
 *
 * @param[in]  input        Device pointer to the real-valued input signal.
 * @param[out] output       Device pointer for the complex-valued output signal
 * (float2).
 * @param[in]  window       Device pointer to the window coefficients.
 * @param nfft              The size of the FFT frame.
 * @param batch             The number of signals in the batch.
 * @param input_stride      The stride of the input signal.
 */
__global__ void window_and_convert_kernel(const float* __restrict__ input,
                                          float2* __restrict__ output,
                                          const float* __restrict__ window,
                                          int nfft, int batch,
                                          int input_stride) {
  const int total_elements = nfft * batch;
  for (int idx = blockIdx.x * blockDim.x + threadIdx.x; idx < total_elements;
       idx += blockDim.x * gridDim.x) {
    const int sample_idx = idx % nfft;
    const int channel_idx = idx / nfft;

    const float sample = input[channel_idx * input_stride + sample_idx];
    const float window_val = window[sample_idx];

    output[channel_idx * nfft + sample_idx] =
        make_float2(sample * window_val, 0.0f);
  }
}

/**
 * @brief Computes the magnitude from a packed complex FFT output.
 *
 * This kernel calculates `sqrt(real^2 + imag^2)` for each complex element.
 *
 * @param[in]  input    Device pointer to the packed complex FFT output
 * (float2).
 * @param[out] output   Device pointer for the resulting magnitude data (float).
 * @param num_bins      The number of complex frequency bins per signal.
 * @param batch         The number of signals in the batch.
 * @param scale         A scaling factor to apply to the magnitude
 * (e.g., 1.0/nfft).
 */
__global__ void magnitude_kernel(const float2* __restrict__ input,
                                 float* __restrict__ output, int num_bins,
                                 int batch, float scale) {
  const int total_elements = num_bins * batch;
  for (int idx = blockIdx.x * blockDim.x + threadIdx.x; idx < total_elements;
       idx += blockDim.x * gridDim.x) {
    const float2 complex_val = input[idx];
    output[idx] =
        sqrtf(complex_val.x * complex_val.x + complex_val.y * complex_val.y) *
        scale;
  }
}

/**
 * @brief Computes magnitude from a strided complex FFT output.
 *
 * This version handles non-contiguous (strided) complex input data.
 *
 * @param[in]  input        Device pointer to the strided complex FFT output
 * (float2).
 * @param[out] output       Device pointer for the tightly packed magnitude data
 * (float).
 * @param num_bins          The number of complex frequency bins per signal.
 * @param batch             The number of signals in the batch.
 * @param input_stride      The distance (in elements) between the start of
 * consecutive FFTs in the input buffer.
 * @param scale             A scaling factor to apply to the magnitude.
 */
__global__ void magnitude_strided_kernel(const float2* __restrict__ input,
                                         float* __restrict__ output,
                                         int num_bins, int batch,
                                         int input_stride, float scale) {
  const int total_elements = num_bins * batch;
  const int tid = blockIdx.x * blockDim.x + threadIdx.x;

  for (int idx = tid; idx < total_elements; idx += blockDim.x * gridDim.x) {
    const int frame_idx = idx / num_bins;
    const int bin_idx = idx % num_bins;

    const float2 v = input[frame_idx * input_stride + bin_idx];
    output[idx] = sqrtf(v.x * v.x + v.y * v.y) * scale;
  }
}

/**
 * @brief Computes magnitude squared (power) from complex FFT output.
 *
 * This is faster than `magnitude_kernel` as it avoids the `sqrtf` operation.
 *
 * @param[in]  input    Device pointer to the complex FFT output (float2).
 * @param[out] output   Device pointer for the resulting power data (float).
 * @param num_bins      The number of complex frequency bins per signal.
 * @param batch         The number of signals in the batch.
 * @param scale         A scaling factor to apply. The final result is scaled by
 * `scale^2`.
 */
__global__ void magnitude_squared_kernel(const float2* __restrict__ input,
                                         float* __restrict__ output,
                                         int num_bins, int batch, float scale) {
  const int total_elements = num_bins * batch;
  for (int idx = blockIdx.x * blockDim.x + threadIdx.x; idx < total_elements;
       idx += blockDim.x * gridDim.x) {
    const float2 complex_val = input[idx];
    output[idx] =
        (complex_val.x * complex_val.x + complex_val.y * complex_val.y) *
        scale * scale;
  }
}

/**
 * @brief Converts a magnitude spectrum to a decibel (dB) scale.
 *
 * @param[in]  input     Device pointer to the magnitude spectrum.
 * @param[out] output    Device pointer for the dB-scaled spectrum.
 * @param num_bins       The number of bins per signal.
 * @param batch          The number of signals in the batch.
 * @param ref_level      The reference level for the dB calculation
 * (typically 1.0).
 * @param min_db         The minimum dB value to clamp to (e.g., -80.0f).
 */
__global__ void magnitude_to_db_kernel(const float* __restrict__ input,
                                       float* __restrict__ output, int num_bins,
                                       int batch, float ref_level,
                                       float min_db) {
  const int total_elements = num_bins * batch;
  for (int idx = blockIdx.x * blockDim.x + threadIdx.x; idx < total_elements;
       idx += blockDim.x * gridDim.x) {
    const float magnitude = input[idx];
    const float epsilon = 1e-10f;  // To avoid log(0)
    const float db = 20.0f * log10f(fmaxf(magnitude, epsilon) / ref_level);
    output[idx] = fmaxf(db, min_db);
  }
}

/**
 * @brief Scales the complex output of an FFT.
 *
 * Typically used to normalize the FFT by a factor of `1/N`.
 *
 * @param[in,out] data    Device pointer to the complex data to be scaled.
 * @param num_elements    The total number of complex elements to scale.
 * @param scale           The scaling factor.
 */
__global__ void scale_fft_output_kernel(float2* __restrict__ data,
                                        int num_elements, float scale) {
  for (int idx = blockIdx.x * blockDim.x + threadIdx.x; idx < num_elements;
       idx += blockDim.x * gridDim.x) {
    float2 val = data[idx];
    val.x *= scale;
    val.y *= scale;
    data[idx] = val;
  }
}

// --- Kernel Launch Wrappers ---

void launch_apply_window(const float* input, float* output, const float* window,
                         int nfft, int batch, int stride, cudaStream_t stream) {
  IONO_NVTX_RANGE("launch_apply_window", profiling::colors::PURPLE);
  const int total_elements = nfft * batch;
  const int threads = std::min(MAX_THREADS_PER_BLOCK, total_elements);
  const int blocks = (total_elements + threads - 1) / threads;
  apply_window_kernel<<<blocks, threads, 0, stream>>>(input, output, window,
                                                      nfft, batch, stride);
}

void launch_real_to_complex(const float* input, float2* output, int nfft,
                            int batch, int stride, cudaStream_t stream) {
  IONO_NVTX_RANGE("launch_real_to_complex", profiling::colors::PURPLE);
  const int total_elements = nfft * batch;
  const int threads = std::min(MAX_THREADS_PER_BLOCK, total_elements);
  const int blocks = (total_elements + threads - 1) / threads;
  real_to_complex_kernel<<<blocks, threads, 0, stream>>>(input, output, nfft,
                                                         batch, stride);
}

void launch_window_and_convert(const float* input, float2* output,
                               const float* window, int nfft, int batch,
                               int stride, cudaStream_t stream) {
  IONO_NVTX_RANGE("launch_window_and_convert", profiling::colors::PURPLE);
  const int total_elements = nfft * batch;
  const int threads = std::min(MAX_THREADS_PER_BLOCK, total_elements);
  const int blocks = (total_elements + threads - 1) / threads;
  window_and_convert_kernel<<<blocks, threads, 0, stream>>>(
      input, output, window, nfft, batch, stride);
}

void launch_magnitude(const float2* input, float* output, int num_bins,
                      int batch, float scale, cudaStream_t stream) {
  IONO_NVTX_RANGE("launch_magnitude", profiling::colors::PURPLE);
  const int total_elements = num_bins * batch;
  const int threads = std::min(MAX_THREADS_PER_BLOCK, total_elements);
  const int blocks = (total_elements + threads - 1) / threads;
  magnitude_kernel<<<blocks, threads, 0, stream>>>(input, output, num_bins,
                                                   batch, scale);
}

void launch_magnitude(const float2* input, float* output, int num_bins,
                      int batch, int input_stride, float scale,
                      cudaStream_t stream) {
  IONO_NVTX_RANGE("launch_magnitude_strided", profiling::colors::PURPLE);
  const int total_elements = num_bins * batch;
  const int threads = std::min(MAX_THREADS_PER_BLOCK, total_elements);
  const int blocks = (total_elements + threads - 1) / threads;
  magnitude_strided_kernel<<<blocks, threads, 0, stream>>>(
      input, output, num_bins, batch, input_stride, scale);
}

void launch_magnitude_squared(const float2* input, float* output, int num_bins,
                              int batch, float scale, cudaStream_t stream) {
  IONO_NVTX_RANGE("launch_magnitude_squared", profiling::colors::PURPLE);
  const int total_elements = num_bins * batch;
  const int threads = std::min(MAX_THREADS_PER_BLOCK, total_elements);
  const int blocks = (total_elements + threads - 1) / threads;
  magnitude_squared_kernel<<<blocks, threads, 0, stream>>>(
      input, output, num_bins, batch, scale);
}

void launch_scale_fft(float2* data, int num_elements, float scale,
                      cudaStream_t stream) {
  IONO_NVTX_RANGE("launch_scale_fft", profiling::colors::PURPLE);
  const int threads = std::min(MAX_THREADS_PER_BLOCK, num_elements);
  const int blocks = (num_elements + threads - 1) / threads;
  scale_fft_output_kernel<<<blocks, threads, 0, stream>>>(data, num_elements,
                                                          scale);
}

// --- CPU Helper Functions ---

void generate_hann_window_cpu(float* window, int size, bool sqrt_norm) {
  IONO_NVTX_RANGE("generate_hann_window_cpu", profiling::colors::DARK_GRAY);
  const float pi = 3.14159265358979323846f;
  for (int i = 0; i < size; ++i) {
    float val = 0.5f * (1.0f - cosf(2.0f * pi * i / size));
    window[i] = sqrt_norm ? sqrtf(val) : val;
  }
}

}  // namespace kernels
}  // namespace ionosense
