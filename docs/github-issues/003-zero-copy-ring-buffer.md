# Zero-Copy Ring Buffer Extraction (Phase 1 Task 1.1)

## Problem

The `StreamingExecutor` has a **28% performance overhead** due to an unnecessary host-to-host memory copy before the GPU transfer. The `h_batch_staging_` buffer adds 10µs of latency by copying data from the ring buffer to a staging buffer, then copying again to GPU device memory (H2D).

**Performance Impact:**
- StreamingExecutor: 122µs latency
- BatchExecutor: 87µs latency
- **Gap: 35µs (28% overhead)**
- 10µs is wasted on H2H memcpy

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 1 Task 1.1):
- Expected improvement: 122µs → 114µs (-7%)
- Critical before adding custom stages (Phase 2) - don't optimize the wrong bottleneck
- Target: RTF < 0.3 for ionosphere workloads

## Current Implementation

**File:** `cpp/src/executors/streaming_executor.cpp` (lines 137-168)

```cpp
void StreamingExecutor::Impl::process_frame() {
    // Extract from ring buffer to staging (UNNECESSARY H2H COPY)
    ring_buffer_.extract(h_batch_staging_.data(), nfft_);  // ← 10µs wasted here

    // H2D transfer from staging to device
    CUDA_CHECK(cudaMemcpyAsync(
        d_input_buffers_[ping_pong_idx_].data(),
        h_batch_staging_.data(),  // ← Using staging buffer
        batch_bytes_,
        cudaMemcpyHostToDevice,
        stream_
    ));

    // Process on GPU
    for (auto& stage : stages_) {
        stage->process(...);
    }
}
```

**Why the staging buffer exists:**
- Original design: ring buffer had non-contiguous memory (wraparound case)
- Fix attempt: Add staging buffer to ensure contiguous memory for H2D
- **Problem:** Ring buffer memory IS contiguous (or can be made contiguous)
- **Result:** Unnecessary extra copy

## Proposed Solution

**Direct H2D from ring buffer memory** (zero-copy):

```cpp
void StreamingExecutor::Impl::process_frame() {
    // Get pointer directly from ring buffer (NO COPY)
    const float* ring_data_ptr = ring_buffer_.get_read_ptr();

    // Direct H2D transfer from ring buffer to device
    CUDA_CHECK(cudaMemcpyAsync(
        d_input_buffers_[ping_pong_idx_].data(),
        ring_data_ptr,  // ← Direct from ring buffer
        batch_bytes_,
        cudaMemcpyHostToDevice,
        stream_
    ));

    // CRITICAL: Synchronize before advancing ring buffer
    // Prevents DMA race condition (GPU still reading while CPU advances)
    CUDA_CHECK(cudaStreamSynchronize(stream_));

    // Process on GPU
    for (auto& stage : stages_) {
        stage->process(...);
    }

    // Advance ring buffer AFTER GPU finishes reading
    ring_buffer_.advance(hop_size_);
}
```

**Key change:** Add `get_read_ptr()` to `RingBuffer` interface:

```cpp
// In cpp/include/sigtekx/core/ring_buffer.hpp
template <typename T>
class RingBuffer {
public:
    // ... existing methods ...

    const T* get_read_ptr() const {
        // Return pointer to contiguous read region
        // Handle wraparound if needed (copy internally if must)
        return buffer_.data() + read_idx_;
    }
};
```

## Additional Technical Insights

- **Zero-Copy Pattern**: Common in HPC - avoid intermediate buffers whenever possible

- **DMA Race Hazard**: Must synchronize stream before advancing ring buffer, or GPU may read garbage data (CPU advanced pointer while GPU DMA in progress)

- **Wraparound Edge Case**: If ring buffer wraparound occurs mid-frame, `get_read_ptr()` can:
  - Option A: Return pointer (only if no wraparound this frame)
  - Option B: Copy internally to contiguous temp buffer (rare, only at wraparound)
  - Recommend Option A with assertion (wraparound should be avoidable with proper sizing)

- **Latency Breakdown** (expected after fix):
  - Remove H2H copy: -10µs
  - H2D transfer: 30µs (unchanged)
  - GPU compute: 70µs (unchanged)
  - Sync overhead: +2µs (new, but necessary)
  - **Net:** 122µs → 114µs (-8µs, 7% improvement)

- **Memory Savings**: Eliminates `h_batch_staging_` buffer (32KB for NFFT=4096)

## Implementation Tasks

- [ ] Open `cpp/include/sigtekx/core/ring_buffer.hpp`
- [ ] Add `const T* get_read_ptr() const` method to RingBuffer class
- [ ] Implement logic to return pointer to contiguous read region
- [ ] Add assertion if wraparound detected (should not happen with proper sizing)
- [ ] Open `cpp/src/executors/streaming_executor.cpp`
- [ ] Locate `process_frame()` method (~line 155)
- [ ] Replace `ring_buffer_.extract(h_batch_staging_.data(), nfft_)` with `const float* ptr = ring_buffer_.get_read_ptr()`
- [ ] Update `cudaMemcpyAsync` to use `ptr` instead of `h_batch_staging_.data()`
- [ ] Add `cudaStreamSynchronize(stream_)` AFTER memcpy, BEFORE `ring_buffer_.advance()`
- [ ] Remove `h_batch_staging_` member variable from StreamingExecutor::Impl (line 137)
- [ ] Remove `h_batch_staging_` allocation in constructor
- [ ] Update comments explaining zero-copy pattern
- [ ] Run accuracy benchmark: `python benchmarks/run_accuracy.py +benchmark=accuracy`
  - Verify SNR > 60dB (no regression from sync changes)
- [ ] Run latency benchmark: `python benchmarks/run_latency.py +benchmark=profiling`
  - Baseline: Record current latency (expect ~122µs)
  - After fix: Record new latency (expect ~114µs)
  - Verify improvement ≥ 5µs
- [ ] Profile with Nsight Systems: `sxp nsys latency`
  - Verify H2H copy is eliminated (no `memcpy` in timeline)
  - Verify cudaStreamSynchronize appears before advance
- [ ] Run C++ unit tests: `pytest tests/ -k streaming`
- [ ] Commit with message: `perf(executor): eliminate H2H staging buffer for zero-copy H2D`

## Edge Cases to Handle

- **Ring Buffer Wraparound Mid-Frame**: If read pointer + frame size > buffer size:
  - Option 1: Ensure buffer size prevents this (size >= nfft + hop_size)
  - Option 2: `get_read_ptr()` detects and copies to temp buffer
  - Recommend Option 1 with assertion

- **Stream Sync Overhead**: `cudaStreamSynchronize` adds ~2µs but prevents race condition. Necessary for correctness.

- **Multi-Stream Execution**: If multiple streams used, each needs its own sync point. Current design: single stream per executor.

- **Pinned Memory Requirement**: Ring buffer must use pinned memory for optimal H2D performance (already implemented via `PinnedHostBuffer`)

## Testing Strategy

**Before/After Performance Comparison:**

```bash
# Baseline (before fix)
python benchmarks/run_latency.py +benchmark=profiling
# Record mean latency from output (expect ~122µs)

# After fix
python benchmarks/run_latency.py +benchmark=profiling
# Record mean latency (expect ~114µs)

# Verify improvement
# Expected: -7% latency reduction
```

**Accuracy Validation:**

```bash
# Ensure zero-copy doesn't break correctness
python benchmarks/run_accuracy.py +benchmark=accuracy
# Verify SNR > 60dB (no accuracy regression)
```

**Nsight Systems Timeline Verification:**

```bash
# Profile before fix
sxp nsys latency
nsys-ui artifacts/profiling/latency.nsys-rep
# Look for: H2H memcpy in timeline (extract call)

# Profile after fix
sxp nsys latency
nsys-ui artifacts/profiling/latency.nsys-rep
# Verify: NO H2H memcpy, only H2D transfer
# Verify: cudaStreamSynchronize before advance
```

## Acceptance Criteria

- [ ] `RingBuffer::get_read_ptr()` method implemented
- [ ] `h_batch_staging_` buffer removed from StreamingExecutor
- [ ] `cudaMemcpyAsync` uses direct ring buffer pointer
- [ ] `cudaStreamSynchronize` added before `advance()` call
- [ ] Latency improvement ≥ 5µs (target: 122µs → 114µs)
- [ ] Accuracy maintained: SNR > 60dB
- [ ] No H2H memcpy in Nsight Systems timeline
- [ ] All C++ unit tests pass
- [ ] All Python tests pass

## Benefits

- **7% Latency Reduction**: 122µs → 114µs (8µs savings)
- **Memory Savings**: 32KB staging buffer eliminated (NFFT=4096, 2 channels)
- **RTF Improvement**: Closer to RTF < 0.3 target (Phase 1 goal)
- **Clean Foundation**: Optimized memory path before adding custom stages (Phase 2)
- **HPC Best Practice**: Zero-copy pattern is standard for high-performance GPU code

---

**Labels:** `task`, `team-1-cpp`, `c++`, `performance`, `cuda`

**Estimated Effort:** 4-6 hours (C++ memory management, requires careful testing)

**Priority:** High (Phase 1 Task 1.1 - foundational optimization)

**Roadmap Phase:** Phase 1 (v0.9.6)

**Dependencies:** None

**Blocks:** Phase 2 (should optimize memory before adding custom stages)
