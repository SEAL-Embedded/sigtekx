/**
 * @file ops_fft.cu
 * @brief CUDA kernels and launch wrappers for FFT operations
 * 
 * This file contains only CUDA kernels and their thin host-side launch
 * wrappers. All complex orchestration logic lives in fft_engine.cpp.
 */

#include <cuda_runtime.h>
#include <cufft.h>
#include <math_constants.h> // For CUDART_PI_F

namespace ionosense::ops {

// -----------------------------------------------------------------------------
// Device Kernels
// -----------------------------------------------------------------------------

/**
 * @kernel applyWindowKernel
 * @brief Applies a window function to FFT input data
 * 
 * Processes a contiguous batch of FFT frames, applying the window
 * function element-wise to each frame.
 */
__global__ void applyWindowKernel(float* data, const float* window, int nfft, int batch) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= nfft * batch) return;
    
    int sample_idx = idx % nfft;  // Sample index within each FFT frame
    data[idx] *= window[sample_idx];
}

/**
 * @kernel magnitudeKernel  
 * @brief Computes magnitude from complex FFT output
 * 
 * Calculates magnitude = sqrt(re² + im²) for each frequency bin
 * across all FFTs in the batch.
 */
__global__ void magnitudeKernel(const cufftComplex* spec, float* mag, int nfft, int batch) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    int num_bins = (nfft / 2 + 1);
    if (idx >= num_bins * batch) return;
    
    int fft_idx = idx / num_bins;    // Which FFT in the batch
    int bin_idx = idx % num_bins;    // Which bin in the FFT
    
    int spec_idx = fft_idx * num_bins + bin_idx;
    
    float re = spec[spec_idx].x;
    float im = spec[spec_idx].y;
    mag[idx] = sqrtf(re * re + im * im);
}

// -----------------------------------------------------------------------------
// Host-side Launch Wrappers
// -----------------------------------------------------------------------------

/**
 * @brief Launch window application kernel
 * @param d_data Device pointer to input/output data
 * @param d_window Device pointer to window coefficients
 * @param nfft FFT size
 * @param batch Number of FFTs in batch
 * @param stream CUDA stream for async execution
 */
void apply_window_async(float* d_data, const float* d_window, int nfft, int batch, cudaStream_t stream) {
    dim3 threads(256);
    dim3 blocks((nfft * batch + threads.x - 1) / threads.x);
    
    applyWindowKernel<<<blocks, threads, 0, stream>>>(d_data, d_window, nfft, batch);
    
    // Check for kernel launch errors (in debug builds)
    #ifdef DEBUG
    cudaError_t err = cudaGetLastError();
    if (err != cudaSuccess) {
        fprintf(stderr, "Window kernel launch failed: %s\n", cudaGetErrorString(err));
    }
    #endif
}

/**
 * @brief Launch magnitude computation kernel
 * @param d_spec Device pointer to complex spectrum
 * @param d_mag Device pointer to output magnitude buffer
 * @param bins Number of frequency bins per FFT
 * @param batch Number of FFTs in batch
 * @param stream CUDA stream for async execution
 */
void magnitude_async(const cufftComplex* d_spec, float* d_mag, int bins, int batch, cudaStream_t stream) {
    dim3 threads(256);
    dim3 blocks((bins * batch + threads.x - 1) / threads.x);
    
    magnitudeKernel<<<blocks, threads, 0, stream>>>(d_spec, d_mag, bins * 2 - 2, batch);
    
    // Check for kernel launch errors (in debug builds)
    #ifdef DEBUG
    cudaError_t err = cudaGetLastError();
    if (err != cudaSuccess) {
        fprintf(stderr, "Magnitude kernel launch failed: %s\n", cudaGetErrorString(err));
    }
    #endif
}

} // namespace ionosense::ops