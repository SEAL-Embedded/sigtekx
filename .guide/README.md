# Ionosense CUDA FFT Pipeline 1.0 — Integrated Reading Map (PG + BP + FFT, v13.0)

**Goal:** ramp new teammates on the Ionosense ULF/VLF FFT pipeline fast, using NVIDIA’s three core docs — **Programming Guide (PG)**, **Best Practices (BP)**, and **cuFFT Guide (FFT)** — in a clean learning order. **PG is the backbone**; BP and FFT add tactics and library details.

> Target GPU: **RTX 4000 Ada (SM 8.9)**. Use `-arch=sm_89`. \*\*Skip all CC 9.0 features — e.g., **PG §5.2.1 Thread Block Clusters**.

### Docs & Links

- **Programming Guide (PG):** [PDF](./CUDA_C_Programming_Guide.pdf) • [Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)
- **Best Practices (BP):** [PDF](./CUDA_C_Best_Practices_Guide.pdf) • [Web](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/)
- **cuFFT Guide (FFT):** [PDF](./CUFFT_Library.pdf) • [Web](https://docs.nvidia.com/cuda/cufft/index.html)

> Section numbers are from Toolkit 13.0 PDFs; website headings may shift slightly between minor versions.

---

## 0) On‑ramp (30–45 min)

- **PG §1 Overview** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)) — what CUDA is and why it exists.
- **PG §3.1–3.3 Introduction** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/#introduction)) — kernels/threads/blocks/grids; the scalable model.
- **BP §3 Heterogeneous Computing** ([Web](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/#heterogeneous-computing)) — CPU↔GPU split; separate memory spaces.

---

## 1) Core mental model (you’ll use this daily)

- **PG §5.1 Kernels** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/#kernels)) — GPU entry points (`__global__`).

  ```cpp
  // Kernel we actually ship
  __global__ void applyWindow(float* data, const float* window, int nfft, int batch) {
      int idx = blockIdx.x * blockDim.x + threadIdx.x;
      if (idx >= nfft * batch) return;
      int sample_idx = idx % nfft;
      data[idx] *= window[sample_idx];
  }
  // src: cuda_fft.cu:L28–L35
  ```

- **PG §5.2 Thread Hierarchy** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/#thread-hierarchy)) — map work to grids/blocks/threads. **(Skip §5.2.1 clusters)**

  ```cpp
  // One thread per sample across the whole batch
  dim3 threads(256);
  dim3 blocks((nfft_ * batch_ + threads.x - 1) / threads.x);
  applyWindow<<<blocks, threads, 0, stream>>>(d_in, d_window_[idx], nfft_, batch_);
  // src: cuda_fft.cu:L203–L212
  ```

### Primer — Our 1D Mental Model

For current work, we operate on a **strictly 1D mental model**: batches of 1D time‑series from two antenna channels. Kernels only use the `threadIdx.x and blockIdx.x`, `y` and `z` are ignored. This maps threads directly to a linear array and keeps reasoning simple. We’ll expand to **2D** (spectrograms) and **3D** (future sims) later.

```cpp
// 1D thread mapping (only .x is used)
int idx = blockIdx.x * blockDim.x + threadIdx.x;
// src: cuda_fft.cu:L28–L31
```

- **PG §5.3 Memory Hierarchy** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/#memory-hierarchy)) — registers/shared/global and why coalescing matters.

  ```cpp
  // Coalesced pattern: thread i touches data[i]
  int idx = blockIdx.x * blockDim.x + threadIdx.x;
  data[idx] *= window[idx % nfft];
  // src: cuda_fft.cu:L29–L35
  ```

- **PG §10.1 C++ Execution Space Specifiers** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/#function-execution-space-specifiers)) — where code runs/can be called from. *(Read for vocabulary; our kernels/use-sites above already reflect this.)*

- **PG §7.1–7.2 SIMT & Multithreading** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/#hardware-implementation)) — warps, divergence, latency hiding. *(Concepts you’ll need to reason about perf.)*

---

## 2) cuFFT pipeline (plan → execute, batched R2C)

- **FFT §2 Using the cuFFT API** ([Web](https://docs.nvidia.com/cuda/cufft/#using-the-cufft-api)) — plan-then-exec model.

  ```cpp
  // Create plans for each stream
  cufftCreate(&plans_[i]);
  // src: cuda_fft.cu:L143
  ```

- **FFT §2.4 Data Layout** ([Web](https://docs.nvidia.com/cuda/cufft/#data-layout)) — R2C output has `(nfft/2+1)` bins per FFT.

  ```cpp
  const size_t bins = (nfft_ / 2 + 1);
  // src: cuda_fft.cu:L191
  ```

- **FFT §2.6 Advanced Layout** ([Web](https://docs.nvidia.com/cuda/cufft/#advanced-data-layout)) — batched FFTs via `cufftPlanMany`.

  ```cpp
  const int rank = 1; int n[] = { nfft_ }; int istride=1, ostride=1;
  int idist = nfft_, odist = (nfft_ / 2 + 1);
  cufftPlanMany(&plans_[i], rank, n,
      nullptr, istride, idist,
      nullptr, ostride, odist,
      CUFFT_R2C, batch_);
  // src: cuda_fft.cu:L145–L154
  ```

- **FFT §2.11 CUDA Graphs Support** / **FFT §1.14 Caller Allocated Work Area** ([Web](https://docs.nvidia.com/cuda/cufft/#cuda-graphs-support)) — graph‑friendly plans need user workspace.

  ```cpp
  cufftSetAutoAllocation(plans_[idx], 0);
  cufftSetWorkArea(plans_[idx], cufft_workspaces_[idx]);
  // src: cuda_fft.cu:L182–L183
  ```

---

## 3) Memory & transfers (feed the GPU efficiently)

- **PG §6.2.6 Page‑Locked Host Memory** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/#page-locked-host-memory)) — pin buffers so copies can be async.

  ```cpp
  cudaHostAlloc(&h_inputs_[i],  in_bytes,  cudaHostAllocDefault);
  cudaHostAlloc(&h_outputs_[i], out_bytes, cudaHostAllocDefault);
  // src: cuda_fft.cu:L132–L133
  ```

- **BP §10.1.1 Pinned Memory & §10.1.2 Overlap** ([Web](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/#pinned-memory)) — minimize copies; overlap with compute.

  ```cpp
  // Async H2D then D2H around kernels in the same stream
  cudaMemcpyAsync(d_in,  h_in,  in_bytes,  cudaMemcpyHostToDevice, stream);
  // ... kernels ...
  cudaMemcpyAsync(h_out, d_mag, out_bytes, cudaMemcpyDeviceToHost, stream);
  // src: cuda_fft.cu:L208 and L223
  ```

- **PG §6.2.10 UVA** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/#unified-virtual-address-space)) — saner pointer handling across host/device. *(Read before debugging ptr math.)*

---

## 4) Concurrency & overlap (real‑time backbone)

- **PG §6.2.8 Asynchronous Concurrent Execution** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/#asynchronous-concurrent-execution)) — the rules of overlap.

  **Streams** — independent work queues.

  ```cpp
  // Three lanes: copy-in / compute / copy-out
  static constexpr int kNumStreams = 3; // header
  cudaStream_t streams_[kNumStreams];   // header
  // src: cuda_fft.h:L171 (kNumStreams), cuda_fft.h:decl of streams_
  ```

  ```cpp
  // Create and bind streams to cuFFT plans
  cudaStreamCreate(&streams_[i]);
  cufftSetStream(plans_[i], streams_[i]);
  // src: cuda_fft.cu:L122 and L156
  ```

  **Events** — mark ready points & measure.

  ```cpp
  cudaEventRecord(prof_start_[idx], streams_[idx]);
  cudaEventRecord(events_[idx],     streams_[idx]);
  // src: cuda_fft.cu:L259 and L268
  ```

  ```cpp
  // Host waits for stream idx to finish its stage
  cudaEventSynchronize(events_[idx]);
  // src: cuda_fft.cu:L333
  ```

- **BP §11.1 Occupancy** ([Web](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/#occupancy)) — enough threads in flight to hide latency. *(Use 256‑thread blocks as a sane default; profile and adjust.)*

---

## 5) CUDA Graphs (stabilize launch overhead)

- **PG §6.2.8.7 CUDA Graphs** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/#cuda-graphs)) — capture the whole pipeline once, replay cheaply.
  ```cpp
  cudaStreamBeginCapture(streams_[idx], cudaStreamCaptureModeGlobal);
  execute_pipeline_operations(idx);
  cudaStreamEndCapture(streams_[idx], &graphs_[idx]);
  // src: cuda_fft.cu:L233–L239
  ```
  ```cpp
  // Fast launches after instantiation
  cudaGraphLaunch(graphs_execs_[idx], streams_[idx]);
  // src: cuda_fft.cu:L279
  ```

---

## 6) Practical glue (compile, errors, sanity)

- **PG §6.2.12 Error Checking** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/#error-checking)) — never skip checks (async errors surface later).

  ```cpp
  #define CUDA_CHECK(err) do { \
      cudaError_t _e = (err); \
      if (_e != cudaSuccess) { /* log + abort */ } \
  } while(0)
  // src: cuda_fft.h:L27–L31
  ```

- **PG §6.1 NVCC Compilation** ([Web](https://docs.nvidia.com/cuda/cuda-c-programming-guide/#compilation-with-nvcc)) — compile host+device code correctly. *(Project build files already pass **`-arch=sm_89`**; confirm before release.)*

---

## Profiling & Optimization (data‑first workflow)

Effective CUDA work is an **iterate–measure–fix** loop: profile → optimize the top bottleneck → benchmark → repeat. **Order matters** (optimization isn’t associative): removing a memory bottleneck can expose **CPU launch overhead**, changing what you fix next. Always let data (Nsight/metrics) pick the next target.
Currently the codes state is a "blank canvas". It's very standard and performing in real-time. It is CRUCIAL now that optimizations to the core engine are coordinated and data driven.

```cpp
// Lightweight, per‑stream timing hooks with events
cudaEventRecord(prof_start_[idx], streams_[idx]);
cudaEventRecord(events_[idx],     streams_[idx]);
// src: cuda_fft.cu:L259 and L268
```

## 7) Reading flow

1. **PG §1**, **PG §3.1–3.3**, **BP §3**
2. **PG §5.1 → §5.2 (skip §5.2.1) → §5.3 → PG §10.1 → PG §7.1–7.2**
3. **FFT §1, §1.4, §1.6, §1.11, §1.14**
4. **PG §6.2.6 → BP §10.1.1–§10.1.2 → PG §6.2.10**
5. **PG §6.2.8 (streams/events/overlap)**
6. **PG §6.2.8.7 (graphs)**
7. **BP §11.1 (occupancy)**
