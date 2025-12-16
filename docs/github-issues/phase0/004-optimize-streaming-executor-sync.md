# Optimize Redundant Synchronization in StreamingExecutor

## Problem

The StreamingExecutor's `process_one_batch()` method performs **redundant dual-stream synchronization** on every frame after the initial warmup period. This synchronization blocks the CPU unnecessarily, waiting for both compute and D2H streams to complete, even though only specific buffer availability needs to be ensured.

**Impact:**
- Extra GPU-CPU synchronization overhead on every streaming frame
- Reduced pipeline throughput in streaming mode
- CPU thread blocked waiting for GPU work that may already be complete
- Performance regression compared to event-based synchronization

**Measured Overhead:**
- Estimated 5-15µs per frame on RTX 3090 Ti
- Blocks async processing benefits in real-time mode

## Current Implementation

**File:** `cpp/src/executors/streaming_executor.cpp` (lines 595-601)

```cpp
// INEFFICIENT: Synchronizes BOTH streams on every frame reuse
if (frame_counter_ >= static_cast<uint64_t>(config_.pinned_buffer_count)) {
  SIGTEKX_NVTX_RANGE("Wait for Buffer Availability", profiling::colors::YELLOW);

  // ❌ Synchronizes compute stream (even if compute already done)
  SIGTEKX_CUDA_CHECK(cudaStreamSynchronize(streams_[compute_stream_idx].get()));

  // ❌ Synchronizes D2H stream (even if transfer already done)
  SIGTEKX_CUDA_CHECK(cudaStreamSynchronize(streams_[d2h_stream_idx].get()));
}
```

**Why This Is Inefficient:**

1. **Dual synchronization is overly conservative:**
   - Only need to ensure **specific buffer** at `buffer_idx` is available
   - Current code waits for **all** work on both streams

2. **Misses pipelining opportunities:**
   - Frame N may be in compute while frame N-1 is in D2H transfer
   - Dual sync forces serial execution instead of overlapped pipeline

3. **No per-buffer tracking:**
   - Doesn't track which buffer is currently in use
   - Can't wait on specific buffer's completion event

## Proposed Solution

Replace dual-stream synchronization with **per-buffer event-based synchronization** to only wait for the specific buffer being reused.

### Implementation Strategy

**Add per-buffer completion events:**

```cpp
// streaming_executor.hpp (around line 813, after existing stream declarations)
std::vector<CudaEvent> buffer_completion_events_;  // One event per buffer
```

**Initialize events (in initialize() method, around line 661):**

```cpp
// After pinned buffer allocation (line 650-660)
buffer_completion_events_.clear();
buffer_completion_events_.reserve(config_.pinned_buffer_count);

for (int i = 0; i < config_.pinned_buffer_count; ++i) {
  buffer_completion_events_.push_back(CudaEvent());
}
```

**Record event after D2H transfer completes:**

```cpp
// In process_one_batch(), after D2H copy (around line 689)
// Record completion of this specific buffer's D2H transfer
SIGTEKX_CUDA_CHECK(cudaEventRecord(
    buffer_completion_events_[buffer_idx].get(),
    streams_[d2h_stream_idx].get()));
```

**Wait only for specific buffer's event:**

```cpp
// OPTIMIZED: Replace lines 595-601 with:
if (frame_counter_ >= static_cast<uint64_t>(config_.pinned_buffer_count)) {
  SIGTEKX_NVTX_RANGE("Wait for Buffer Availability", profiling::colors::YELLOW);

  const int buffer_idx = static_cast<int>(frame_counter_ % config_.pinned_buffer_count);

  // ✅ Wait ONLY for this specific buffer's completion
  SIGTEKX_CUDA_CHECK(cudaEventSynchronize(
      buffer_completion_events_[buffer_idx].get()));

  // Event ensures both compute AND D2H completed for this buffer
  // (event recorded on D2H stream, which implicitly waits for compute via stream ordering)
}
```

### Stream Dependency Explanation

**Why event on D2H stream is sufficient:**

The pipeline has ordered dependencies:
```
H2D stream → Compute stream → D2H stream
```

Recording event on D2H stream guarantees:
1. H2D transfer completed (compute stream waits for H2D via cudaStreamWaitEvent)
2. Compute completed (D2H stream waits for compute via cudaStreamWaitEvent)
3. D2H transfer completed (event recorded on D2H stream)

Therefore, waiting on D2H event **implicitly** ensures all prior stages finished.

## Additional Technical Insights

### Event vs Stream Synchronization

| Method | Scope | Overhead | Use Case |
|--------|-------|----------|----------|
| `cudaStreamSynchronize()` | All work on stream | High (~10-20µs) | Full stream drain |
| `cudaEventSynchronize()` | Work up to event | Low (~2-5µs) | Specific operation completion |

**Current code:** Uses stream sync (high overhead, broad scope)
**Proposed:** Use event sync (low overhead, precise scope)

### Buffer Round-Robin Pattern

With `pinned_buffer_count = N`:
```
Frame 0 → Buffer 0
Frame 1 → Buffer 1
...
Frame N-1 → Buffer N-1
Frame N → Buffer 0  ← Need to wait for frame 0 completion
Frame N+1 → Buffer 1  ← Need to wait for frame 1 completion
```

Only wait when **reusing** a buffer (frame ≥ N).

### NVTX Profiling Visibility

The existing NVTX range "Wait for Buffer Availability" will show reduced duration after optimization:
- **Before:** 10-20µs (dual stream sync)
- **After:** 2-5µs (single event sync)

## Implementation Tasks

- [ ] Open `cpp/include/sigtekx/executors/streaming_executor.hpp`
- [ ] Add `std::vector<CudaEvent> buffer_completion_events_;` member (line ~813)
- [ ] Open `cpp/src/executors/streaming_executor.cpp`
- [ ] In `initialize()` method:
  - [ ] Allocate `buffer_completion_events_` vector (after line 660)
  - [ ] Initialize one event per buffer
- [ ] In `process_one_batch()` method:
  - [ ] Record event after D2H copy (after line 689)
  - [ ] Replace dual stream sync (lines 595-601) with single event sync
- [ ] In `reset()` method:
  - [ ] Clear `buffer_completion_events_` (around line 251)
- [ ] Update NVTX range comment to reflect event-based waiting
- [ ] Add comment explaining stream dependency chain
- [ ] Build and test with existing streaming tests
- [ ] Profile with Nsight Systems to verify reduction in sync overhead
- [ ] Commit: `perf(executor): use event-based sync for streaming buffer reuse`

## Edge Cases to Handle

- **First N frames (no reuse yet):**
  - `frame_counter_ < pinned_buffer_count` → Skip wait entirely ✓ (already handled)

- **Buffer index wraparound:**
  - `frame_counter_ % pinned_buffer_count` handles correctly ✓

- **Event recording failure:**
  - CUDA error check will throw exception ✓ (already wrapped in SIGTEKX_CUDA_CHECK)

- **Event synchronization timeout:**
  - CUDA will hang if GPU deadlocked (same as current code)
  - Not a new risk ✓

- **Multiple events per buffer:**
  - Only one event per buffer needed - previous frame's event replaced
  - Safe: old event implicitly complete before new frame reuses buffer ✓

## Testing Strategy

### Unit Test (Add to `cpp/tests/executors/test_streaming_executor.cpp`)

```cpp
TEST_F(StreamingExecutorTest, EventBasedBufferSync) {
  // Config with small buffer count to trigger reuse quickly
  ExecutorConfig config = create_test_config();
  config.mode = ExecutorMode::STREAMING;
  config.pinned_buffer_count = 2;  // Force reuse after 2 frames

  executor_.initialize(config, std::move(stages));

  std::vector<float> input(config.nfft * config.channels, 1.0f);

  // First 2 frames: no wait (buffer reuse not yet needed)
  EXPECT_NO_THROW(executor_.submit(input.data(), config.nfft));
  EXPECT_NO_THROW(executor_.submit(input.data(), config.nfft));

  // Frame 3: should wait on buffer 0's event
  EXPECT_NO_THROW(executor_.submit(input.data(), config.nfft));

  // Frame 4: should wait on buffer 1's event
  EXPECT_NO_THROW(executor_.submit(input.data(), config.nfft));

  // All frames should produce valid results
  auto stats = executor_.get_stats();
  EXPECT_EQ(stats.frames_processed, 4);
}

TEST_F(StreamingExecutorTest, HighThroughputBufferReuse) {
  // Stress test: many frames with small buffer pool
  ExecutorConfig config = create_test_config();
  config.mode = ExecutorMode::STREAMING;
  config.pinned_buffer_count = 3;

  executor_.initialize(config, std::move(stages));

  std::vector<float> input(config.nfft * config.channels, 1.0f);

  // Process 100 frames - heavy buffer reuse
  for (int i = 0; i < 100; ++i) {
    EXPECT_NO_THROW(executor_.submit(input.data(), config.nfft));
  }

  auto stats = executor_.get_stats();
  EXPECT_EQ(stats.frames_processed, 100);
}
```

### Performance Benchmark (Manual)

```bash
# Build with profiling enabled
cmake --build build --config Release

# Run streaming benchmark
./build/sigtekx_benchmark --preset realtime --iono --profile

# Profile with Nsight Systems
nsys profile -o artifacts/profiling/streaming_sync_before.nsys-rep \
  ./build/sigtekx_benchmark --preset realtime --full

# Apply fix, rebuild, re-profile
nsys profile -o artifacts/profiling/streaming_sync_after.nsys-rep \
  ./build/sigtekx_benchmark --preset realtime --full

# Compare NVTX ranges in nsys-ui:
# Look for "Wait for Buffer Availability" duration reduction
# Expected: 10-20µs → 2-5µs (50-75% reduction)
```

### Validation Checklist

- [ ] Existing `StreamingExecutorTest` suite passes (no regressions)
- [ ] New event-based tests pass
- [ ] Nsight Systems shows reduced sync overhead in "Wait for Buffer Availability"
- [ ] Throughput benchmark shows improvement (frames/sec increase)
- [ ] Latency benchmark shows no regression (p99 latency same or better)
- [ ] No CUDA errors or warnings during stress test

## Acceptance Criteria

- [ ] `buffer_completion_events_` vector added to class
- [ ] Events initialized in `initialize()` method (one per buffer)
- [ ] Event recorded after D2H copy in `process_one_batch()`
- [ ] Dual stream sync replaced with single event sync
- [ ] Events cleared in `reset()` method
- [ ] Unit tests pass: `EventBasedBufferSync`, `HighThroughputBufferReuse`
- [ ] Streaming executor tests pass (no regressions)
- [ ] Nsight Systems profiling shows sync overhead reduction
- [ ] Code review confirms correctness of stream dependencies
- [ ] Comments added explaining event-based synchronization strategy

## Benefits

- **Performance Improvement:** 50-75% reduction in sync overhead (~10-15µs → 2-5µs per frame)
- **Better Pipelining:** Allows overlapped execution of multiple frames
- **Scalability:** Lower overhead enables higher frame rates in streaming mode
- **Precise Synchronization:** Only waits for necessary buffer availability
- **Profiling Clarity:** NVTX ranges show exact buffer wait times
- **Phase 1 Readiness:** Streaming mode optimized for real-time workloads

---

**Labels:** `performance`, `team-1-cpp`, `c++`, `optimization`

**Estimated Effort:** 3-4 hours (implementation + testing + profiling)

**Priority:** MEDIUM (performance optimization, not correctness fix)

**Roadmap Phase:** Phase 0 (recommended before Phase 1)

**Dependencies:** None (independent optimization)

**Blocks:** None (but improves streaming performance for Phase 1)

**Related Issues:** #001 (StreamingExecutor correctness), #003 (thread-safety documentation)
