// src/ops_fft.cu
#include <cuda_runtime.h>
#include <cufft.h>
#include <cuda_fp16.h>
#include <cmath>
#include <algorithm>

namespace ionosense {
namespace kernels {

// Constants for kernel configuration
constexpr int WARP_SIZE = 32;
constexpr int MAX_THREADS_PER_BLOCK = 256;

// Apply window function to input signal (in-place or out-of-place)
// Uses vectorized loads for coalesced memory access
__global__ void apply_window_kernel(const float* __restrict__ input,
                                   float* __restrict__ output,
                                   const float* __restrict__ window,
                                   int nfft,
                                   int batch,
                                   int stride) {
    // Grid-stride loop for scalability
    const int tid = blockIdx.x * blockDim.x + threadIdx.x;
    const int total_elements = nfft * batch;

    for (int idx = tid; idx < total_elements; idx += blockDim.x * gridDim.x) {
        const int sample_idx = idx % nfft;
        const int channel_idx = idx / nfft;

        // Coalesced read from input
        const float sample = input[channel_idx * stride + sample_idx];
        const float window_val = window[sample_idx];

        // Apply window and write (coalesced)
        output[channel_idx * stride + sample_idx] = sample * window_val;
    }
}

// Optimized window kernel using float2 for better memory throughput
__global__ void apply_window_complex_kernel(const float2* __restrict__ input,
                                           float2* __restrict__ output,
                                           const float* __restrict__ window,
                                           int nfft,
                                           int batch) {
    const int tid = blockIdx.x * blockDim.x + threadIdx.x;
    const int total_elements = nfft * batch;

    for (int idx = tid; idx < total_elements; idx += blockDim.x * gridDim.x) {
        const int sample_idx = idx % nfft;
        const int channel_idx = idx / nfft;
        const int linear_idx = channel_idx * nfft + sample_idx;

        // Load complex sample (real, imag)
        float2 sample = input[linear_idx];
        const float window_val = window[sample_idx];

        // Apply window to both real and imaginary parts
        sample.x *= window_val;
        sample.y *= window_val;

        // Store windowed sample
        output[linear_idx] = sample;
    }
}

// Convert real signal to complex format for FFT input
__global__ void real_to_complex_kernel(const float* __restrict__ input,
                                      float2* __restrict__ output,
                                      int nfft,
                                      int batch,
                                      int input_stride) {
    const int tid = blockIdx.x * blockDim.x + threadIdx.x;
    const int total_elements = nfft * batch;

    for (int idx = tid; idx < total_elements; idx += blockDim.x * gridDim.x) {
        const int sample_idx = idx % nfft;
        const int channel_idx = idx / nfft;

        // Read real value
        const float real_val = input[channel_idx * input_stride + sample_idx];

        // Write as complex (real, 0)
        float2 complex_val;
        complex_val.x = real_val;
        complex_val.y = 0.0f;

        output[channel_idx * nfft + sample_idx] = complex_val;
    }
}

// Apply window and convert to complex in one kernel (fused operation)
__global__ void window_and_convert_kernel(const float* __restrict__ input,
                                         float2* __restrict__ output,
                                         const float* __restrict__ window,
                                         int nfft,
                                         int batch,
                                         int input_stride) {
    const int tid = blockIdx.x * blockDim.x + threadIdx.x;
    const int total_elements = nfft * batch;

    for (int idx = tid; idx < total_elements; idx += blockDim.x * gridDim.x) {
        const int sample_idx = idx % nfft;
        const int channel_idx = idx / nfft;

        // Read and window in one step
        const float sample = input[channel_idx * input_stride + sample_idx];
        const float window_val = window[sample_idx];

        // Create windowed complex value
        float2 complex_val;
        complex_val.x = sample * window_val;
        complex_val.y = 0.0f;

        output[channel_idx * nfft + sample_idx] = complex_val;
    }
}

// Compute magnitude from complex FFT output (packed, no stride)
__global__ void magnitude_kernel(const float2* __restrict__ input,
                                float* __restrict__ output,
                                int num_bins,
                                int batch,
                                float scale) {
    const int tid = blockIdx.x * blockDim.x + threadIdx.x;
    const int total_elements = num_bins * batch;

    for (int idx = tid; idx < total_elements; idx += blockDim.x * gridDim.x) {
        const float2 complex_val = input[idx];

        // Compute magnitude: sqrt(real^2 + imag^2)
        const float magnitude = sqrtf(complex_val.x * complex_val.x +
                                     complex_val.y * complex_val.y) * scale;

        output[idx] = magnitude;
    }
}

// Compute magnitude from strided complex FFT output
__global__ void magnitude_strided_kernel(const float2* __restrict__ input,
                                         float* __restrict__ output,
                                         int num_bins,
                                         int batch,
                                         int input_stride,
                                         float scale) {
    const int tid = blockIdx.x * blockDim.x + threadIdx.x;
    const int total = num_bins * batch;

    for (int idx = tid; idx < total; idx += blockDim.x * gridDim.x) {
        const int b = idx / num_bins;  // frame index
        const int k = idx % num_bins;  // bin within frame
        const float2 v = input[b * input_stride + k];
        output[idx] = sqrtf(v.x * v.x + v.y * v.y) * scale;
    }
}

// Compute magnitude squared (power) - faster, no sqrt
__global__ void magnitude_squared_kernel(const float2* __restrict__ input,
                                        float* __restrict__ output,
                                        int num_bins,
                                        int batch,
                                        float scale) {
    const int tid = blockIdx.x * blockDim.x + threadIdx.x;
    const int total_elements = num_bins * batch;

    for (int idx = tid; idx < total_elements; idx += blockDim.x * gridDim.x) {
        const float2 complex_val = input[idx];

        // Compute power: real^2 + imag^2
        const float power = (complex_val.x * complex_val.x +
                            complex_val.y * complex_val.y) * scale * scale;

        output[idx] = power;
    }
}

// Convert magnitude to dB scale
__global__ void magnitude_to_db_kernel(const float* __restrict__ input,
                                      float* __restrict__ output,
                                      int num_bins,
                                      int batch,
                                      float ref_level,
                                      float min_db) {
    const int tid = blockIdx.x * blockDim.x + threadIdx.x;
    const int total_elements = num_bins * batch;

    for (int idx = tid; idx < total_elements; idx += blockDim.x * gridDim.x) {
        const float magnitude = input[idx];

        // Avoid log(0) with small epsilon
        const float epsilon = 1e-10f;
        const float db = 20.0f * log10f(fmaxf(magnitude, epsilon) / ref_level);

        // Clamp to minimum dB
        output[idx] = fmaxf(db, min_db);
    }
}

// Scale FFT output by 1/N for normalized transform
__global__ void scale_fft_output_kernel(float2* __restrict__ data,
                                       int num_elements,
                                       float scale) {
    const int tid = blockIdx.x * blockDim.x + threadIdx.x;

    for (int idx = tid; idx < num_elements; idx += blockDim.x * gridDim.x) {
        float2 val = data[idx];
        val.x *= scale;
        val.y *= scale;
        data[idx] = val;
    }
}

// Helper functions for kernel launches
void launch_apply_window(const float* input, float* output, const float* window,
                        int nfft, int batch, int stride, cudaStream_t stream) {
    const int total_elements = nfft * batch;
    const int threads = std::min(MAX_THREADS_PER_BLOCK, total_elements);
    const int blocks = (total_elements + threads - 1) / threads;

    apply_window_kernel<<<blocks, threads, 0, stream>>>(
        input, output, window, nfft, batch, stride);
}

void launch_real_to_complex(const float* input, float2* output,
                            int nfft, int batch, int stride, cudaStream_t stream) {
    const int total_elements = nfft * batch;
    const int threads = std::min(MAX_THREADS_PER_BLOCK, total_elements);
    const int blocks = (total_elements + threads - 1) / threads;

    real_to_complex_kernel<<<blocks, threads, 0, stream>>>(
        input, output, nfft, batch, stride);
}

void launch_window_and_convert(const float* input, float2* output, const float* window,
                              int nfft, int batch, int stride, cudaStream_t stream) {
    const int total_elements = nfft * batch;
    const int threads = std::min(MAX_THREADS_PER_BLOCK, total_elements);
    const int blocks = (total_elements + threads - 1) / threads;

    window_and_convert_kernel<<<blocks, threads, 0, stream>>>(
        input, output, window, nfft, batch, stride);
}

// 6-arg (packed) path
void launch_magnitude(const float2* input, float* output, int num_bins, int batch,
                     float scale, cudaStream_t stream) {
    const int total_elements = num_bins * batch;
    const int threads = std::min(MAX_THREADS_PER_BLOCK, total_elements);
    const int blocks = (total_elements + threads - 1) / threads;

    magnitude_kernel<<<blocks, threads, 0, stream>>>(
        input, output, num_bins, batch, scale);
}

// 7-arg (strided) path
void launch_magnitude(const float2* input, float* output,
                      int num_bins, int batch, int input_stride,
                      float scale, cudaStream_t stream) {
    const int total_elements = num_bins * batch;
    const int threads = std::min(MAX_THREADS_PER_BLOCK, total_elements);
    const int blocks = (total_elements + threads - 1) / threads;

    magnitude_strided_kernel<<<blocks, threads, 0, stream>>>(
        input, output, num_bins, batch, input_stride, scale);
}

void launch_magnitude_squared(const float2* input, float* output, int num_bins, int batch,
                             float scale, cudaStream_t stream) {
    const int total_elements = num_bins * batch;
    const int threads = std::min(MAX_THREADS_PER_BLOCK, total_elements);
    const int blocks = (total_elements + threads - 1) / threads;

    magnitude_squared_kernel<<<blocks, threads, 0, stream>>>(
        input, output, num_bins, batch, scale);
}

void launch_scale_fft(float2* data, int num_elements, float scale, cudaStream_t stream) {
    const int threads = std::min(MAX_THREADS_PER_BLOCK, num_elements);
    const int blocks = (num_elements + threads - 1) / threads;

    scale_fft_output_kernel<<<blocks, threads, 0, stream>>>(data, num_elements, scale);
}

// Generate Hann window on CPU (called once during initialization)
void generate_hann_window_cpu(float* window, int size, bool sqrt_norm) {
    const float pi = 3.14159265358979323846f;

    for (int i = 0; i < size; ++i) {
        float val = 0.5f * (1.0f - cosf(2.0f * pi * i / (size - 1)));
        window[i] = sqrt_norm ? sqrtf(val) : val;
    }
}

}  // namespace kernels
}  // namespace ionosense
