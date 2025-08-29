// src/ops_fft.cu
#include <cuda_runtime.h>
#include <cufft.h>
#include <math.h>

namespace ionosense {
namespace ops {

// -------------------------
// device kernels
// -------------------------

// Multiply each time-domain sample by the corresponding window tap.
// Layout is row-major: [batch, nfft]
__global__ void applyWindowKernel(float* __restrict__ data,
                                  const float* __restrict__ window,
                                  int nfft,
                                  int batch) {
    const size_t total = static_cast<size_t>(nfft) * static_cast<size_t>(batch);
    const size_t idx   = static_cast<size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (idx >= total) return;

    const int s = static_cast<int>(idx % nfft);   // sample index within frame
    data[idx] *= window[s];
}

// Convert complex spectrum to magnitude.
// Input layout: [batch, bins] of cufftComplex
// Output layout: [batch, bins] of float
__global__ void magnitudeKernel(const cufftComplex* __restrict__ spec,
                                float* __restrict__ mag,
                                int bins,
                                int batch) {
    const size_t total = static_cast<size_t>(bins) * static_cast<size_t>(batch);
    const size_t idx   = static_cast<size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (idx >= total) return;

    const float re = spec[idx].x;
    const float im = spec[idx].y;
    mag[idx] = sqrtf(re * re + im * im);
}

// -------------------------
// public launchers
// -------------------------

void apply_window_async(float* d_data,
                        const float* d_window,
                        int nfft,
                        int batch,
                        cudaStream_t stream) {
    const size_t total = static_cast<size_t>(nfft) * static_cast<size_t>(batch);
    if (total == 0) return;

    const int threads = 256;
    const int blocks  = static_cast<int>((total + threads - 1) / threads);
    applyWindowKernel<<<blocks, threads, 0, stream>>>(d_data, d_window, nfft, batch);
}

void magnitude_async(const cufftComplex* d_spec,
                     float* d_mag,
                     int bins,
                     int batch,
                     cudaStream_t stream) {
    const size_t total = static_cast<size_t>(bins) * static_cast<size_t>(batch);
    if (total == 0) return;

    const int threads = 256;
    const int blocks  = static_cast<int>((total + threads - 1) / threads);
    magnitudeKernel<<<blocks, threads, 0, stream>>>(d_spec, d_mag, bins, batch);
}

} // namespace ops
} // namespace ionosense
