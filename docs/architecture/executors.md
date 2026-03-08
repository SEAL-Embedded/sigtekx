# Executor Architecture - BatchExecutor vs StreamingExecutor

**Version:** 0.9.5
**Status:** Production
**Last Updated:** March 2026

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [BatchExecutor Deep Dive](#2-batchexecutor-deep-dive)
3. [StreamingExecutor Deep Dive](#3-streamingexecutor-deep-dive)
4. [Performance Comparison](#4-performance-comparison)
5. [Current Implementation (v0.9.4)](#5-current-implementation-v094)
6. [Future Roadmap (v0.9.5+)](#6-future-roadmap-v095)
7. [Optimization Opportunities](#7-optimization-opportunities)
8. [Technical Details](#8-technical-details)

---

## 1. Executive Summary

### 1.1 Quick Comparison

| Characteristic | BatchExecutor | StreamingExecutor |
|----------------|---------------|-------------------|
| **Primary Use Case** | High-throughput research | Low-latency streaming |
| **Mean Latency** (NFFT=2048) | **86.79 µs** | 122.25 µs |
| **P95 Latency** (NFFT=2048) | **105.47 µs** | 153.82 µs |
| **Performance** | **40% faster** | Baseline |
| **Input Flexibility** | Fixed batch size | Arbitrary chunk sizes |
| **Memory Overhead** | Minimal | Ring buffers (3× NFFT per channel) |
| **CPU Overhead** | Low (direct copy) | Higher (ring buffer ops) |
| **Channel Handling** | Batch-oriented | Per-channel independent |
| **Threading** | Single-threaded | Optional background thread (v0.9.5) |
| **Async Support** | Not planned | Background thread foundation in v0.9.5 |

### 1.2 When to Use Each

**Use BatchExecutor when:**
- ✅ Maximum throughput is critical
- ✅ Input arrives in fixed-size batches
- ✅ Processing pre-recorded datasets
- ✅ Running research experiments
- ✅ You need the lowest possible latency

**Use StreamingExecutor when:**
- ✅ Input arrives in variable-size chunks
- ✅ Continuous real-time streaming required
- ✅ Per-channel independent processing needed
- ✅ Future async/zero-copy streaming planned
- ✅ Sensor integration (future)

### 1.3 Performance Context

The **40% performance gap** is architectural overhead, not a bug:
- Ring buffer operations: 2× memcpy per frame per channel
- Multiple frame processing during warmup
- Per-channel loop overhead

This overhead enables **critical streaming functionality** that BatchExecutor cannot provide. Zero-copy DMA from the ring buffer (Phase 1.1) eliminated the largest source of overhead. Future optimizations (GPU-resident ring buffers, GPU overlap windowing) will further reduce the gap.

---

## 2. BatchExecutor Deep Dive

### 2.1 Architecture Philosophy

**Design Goal:** Maximum throughput with minimal CPU overhead.

BatchExecutor implements a **direct pipeline** architecture where input data flows straight into GPU device memory with zero intermediate buffering. This design prioritizes:
- Raw performance (lowest latency)
- Simplicity (minimal CPU operations)
- Batch-oriented workflows (research, offline processing)

### 2.2 Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│ BatchExecutor Data Flow                                      │
└──────────────────────────────────────────────────────────────┘

┌────────────┐      H2D       ┌────────────┐     Compute     ┌────────────┐      D2H       ┌────────────┐
│   input    │───────────────>│  d_input   │───────────────>│ d_pipeline │───────────────>│   output   │
│  (host)    │   cudaMemcpy   │  (device)  │   FFT/Window   │  (device)  │   cudaMemcpy   │  (host)    │
└────────────┘                └────────────┘                 └────────────┘                └────────────┘
     ▲                                                                                           │
     │                                                                                           │
     └───────────────────────────────────── User calls submit() ─────────────────────────────┘
```

**Flow Steps:**
1. **submit()** receives `input` pointer and `num_samples`
2. **H2D Transfer:** Direct copy `input → d_input` (single memcpy)
3. **Compute Pipeline:** Window → FFT → Magnitude (all on GPU)
4. **D2H Transfer:** Direct copy `d_output → output` (single memcpy)
5. **Return** to caller with results ready

**Key Characteristics:**
- No intermediate buffering (zero CPU memory overhead)
- Exactly ONE batch processed per `submit()` call
- Synchronous execution (blocks until D2H complete)
- Round-robin device buffer reuse for pipelining

### 2.3 Memory Layout

```
Host Memory                    Device Memory (per buffer)
┌──────────────┐              ┌──────────────────────────┐
│              │              │  d_input                  │
│  input       │─────H2D─────>│  [nfft * channels]       │
│  [N samples] │              │                          │
└──────────────┘              └──────────────────────────┘
                                       │
                                       │ Pipeline
                                       ▼
                              ┌──────────────────────────┐
                              │  d_intermediate          │
                              │  [complex FFT output]    │
                              └──────────────────────────┘
                                       │
                                       ▼
┌──────────────┐              ┌──────────────────────────┐
│              │              │  d_output                │
│  output      │<────D2H──────│  [(nfft/2+1) * channels] │
│  [M bins]    │              │                          │
└──────────────┘              └──────────────────────────┘
```

**Buffer Allocation:**
- **pinned_buffer_count** (default: 2) round-robin device buffers
- Enables pipeline overlap: buffer N+1 H2D while buffer N computes
- No host-side staging buffers required

### 2.4 Performance Characteristics

**Latency Benchmark Results (NFFT=2048, channels=2, RTX 3090 Ti — pre-Phase 1.1 baseline):**
```
Mean Latency:    86.79 µs
P50 Latency:     89.38 µs
P95 Latency:    105.47 µs
P99 Latency:    116.74 µs
Min Latency:     49.15 µs
Max Latency:    121.86 µs
Std Dev:         13.68 µs
CV:              15.76%
```

**Throughput Characteristics (NFFT=4096, channels=32):**
```
FPS:            5255.00 frames/sec
Throughput:     3.85 GB/s
Samples/s:      688,783,680 samples/sec
```

**Performance Factors:**
- ✅ **Direct memcpy:** No intermediate copies
- ✅ **Minimal CPU overhead:** ~10-15 µs CPU time per frame
- ✅ **Efficient pipelining:** Round-robin buffers hide H2D/D2H latency
- ✅ **Single code path:** No branching for ring buffer logic

### 2.5 Ideal Use Cases

**Perfect for:**
1. **High-Throughput Research**
   - Processing large pre-recorded datasets
   - Batch experiments with fixed parameters
   - Maximum samples/second required

2. **Offline Analysis**
   - Post-processing ionospheric data
   - Reproducible research workflows
   - Batch generation of spectrograms

3. **Benchmarking**
   - Latency measurement (minimal overhead)
   - Throughput testing
   - Performance regression detection

4. **Production Batch Processing**
   - Fixed-size signal chunks
   - Predictable input patterns
   - CPU overhead is critical

**Not ideal for:**
- ❌ Variable-size input chunks
- ❌ Continuous real-time streaming
- ❌ Per-channel independent buffering
- ❌ Zero-copy sensor integration (future)

---

## 3. StreamingExecutor Deep Dive

### 3.1 Architecture Philosophy

**Design Goal:** Flexible streaming with per-channel independence and future zero-copy support.

StreamingExecutor implements a **ring buffer architecture** where input samples accumulate in per-channel circular buffers before processing. This design prioritizes:
- Input flexibility (arbitrary chunk sizes)
- Per-channel independence (multi-sensor support)
- Zero-copy H2D via pinned ring buffer `peek_frame()` (Phase 1.1)
- STFT overlap management (automatic windowing)

### 3.2 Ring Buffer Design

**What is a Ring Buffer?**

A ring buffer (circular buffer) is a fixed-size data structure that uses a single, continuous buffer as if it were connected end-to-end. Perfect for streaming because:
- Continuous input without reallocation
- Constant-time push/extract operations
- Automatic wraparound for infinite streams
- Overlap window extraction for STFT

**Ring Buffer State:**
```
        read_pos         write_pos
            │                 │
            ▼                 ▼
┌───┬───┬───┬───┬───┬───┬───┬───┐
│ 0 │ 1 │ 2 │ 3 │ 4 │ 5 │ 6 │ 7 │  Capacity = 8
└───┴───┴───┴───┴───┴───┴───┴───┘
    └───────────────┘
       available = 5

Operations:
- push(): Append at write_pos, increment write_pos, update available
- extract_frame(): Copy from read_pos (doesn't move pointer)
- advance(hop_size): Move read_pos forward, decrement available
```

**Per-Channel Independence:**

StreamingExecutor maintains **one ring buffer per channel**:
```
Channel 0:  [ring_buffer_0]  capacity = 3 × NFFT
Channel 1:  [ring_buffer_1]  capacity = 3 × NFFT
Channel N:  [ring_buffer_N]  capacity = 3 × NFFT
```

This enables:
- Independent sample arrival times per channel
- Future sensor-specific buffering
- Parallel channel processing (future)

### 3.3 Data Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ StreamingExecutor Data Flow (Phase 1.1 zero-copy)                            │
└──────────────────────────────────────────────────────────────────────────────┘

┌────────────┐   Per-Channel   ┌──────────────┐  peek_frame()  ┌──────────────┐
│   input    │     Push         │ ring_buffer  │  zero-copy     │  d_input     │
│  (host)    │─────────────────>│ [per channel]│───────────────>│  (device)    │
└────────────┘   memcpy × ch    └──────────────┘  direct DMA    └──────────────┘
                                       │                              │
                                       │ advance(hop_size)            │ Compute
                                       │ after D2H sync               ▼
┌────────────┐      D2H         ┌──────────────┐   FFT/Window  ┌──────────────┐
│   output   │<─────────────────│ d_output     │<─────────────│  d_pipeline  │
│  (host)    │   cudaMemcpy     │  (device)    │              │  (device)    │
└────────────┘                  └──────────────┘              └──────────────┘
     ▲
     │
     └─────────────── User calls submit() (may process N frames) ───┘
```

**Flow Steps:**
1. **submit()** receives `input` with arbitrary size
2. **Per-Channel Push:** Split input by channel, push to ring_buffers (memcpy × channels)
3. **Frame Check Loop (WHILE):**
   - Check if all channels have ≥ NFFT samples
   - **peek_frame():** zero-copy span into ring buffer pinned memory (no copy)
4. **H2D Transfer:** `cudaMemcpyAsync` directly from ring buffer span → `d_input` (no staging hop)
5. **Compute Pipeline:** Window → FFT → Magnitude
6. **D2H Transfer:** Copy `d_output → output` (overwrites if multiple frames)
7. **Advance** ring buffer read pointers by hop_size (after D2H sync)
8. **Repeat** step 3 until insufficient samples remain
9. **Return** to caller with LAST frame's result

**Key Characteristics:**
- Ring buffers use pinned host memory; `peek_frame()` provides zero-copy views for direct GPU DMA
- No staging buffer — H2D transfers go directly from ring buffer without an intermediate copy
- **Multiple frames may be processed per `submit()` call** (drain ring buffers)
- Only the LAST frame's output is returned (others discarded)

### 3.4 Memory Layout

```
Host Memory                              Device Memory
┌──────────────┐                        ┌──────────────────────────┐
│              │                        │                          │
│  input       │──┐                     │                          │
│  [N samples] │  │ Per-Channel Split  │                          │
└──────────────┘  │                     │                          │
                  │                     │                          │
                  ├──> ring_buffer[0]   │                          │
                  │    capacity=3×NFFT  │                          │
                  │                     │                          │
                  ├──> ring_buffer[1]   │                          │
                  │    capacity=3×NFFT  │                          │
                  │                     │                          │
                  └──> ring_buffer[N]   │                          │
                       capacity=3×NFFT  │                          │
                             │           │                          │
                             │ peek_frame() (zero-copy)             │
                             │ direct DMA │                          │
                             └───────────────────────H2D──> d_input │
                                        │  [nfft × channels]      │
                                        └──────────────────────────┘
                                                 │
                                                 │ Pipeline
                                                 ▼
                                        ┌──────────────────────────┐
                                        │  d_intermediate          │
                                        │  [complex FFT output]    │
                                        └──────────────────────────┘
                                                 │
                                                 ▼
┌──────────────┐                        ┌──────────────────────────┐
│              │                        │  d_output                │
│  output      │<──────────D2H──────────│  [(nfft/2+1) * channels] │
│  [M bins]    │                        │                          │
└──────────────┘                        └──────────────────────────┘
```

**Memory Overhead:**
- **Per-channel ring buffers:** 3× NFFT × channels × sizeof(float) — allocated in CUDA pinned memory

Example (NFFT=4096, 2 channels):
- Ring buffers: 3 × 4096 × 2 × 4 = **98 KB** (pinned host)
- No staging buffer (eliminated in Phase 1.1 zero-copy)

### 3.5 Multiple Frame Processing

**Critical Behavior:** The while loop in `submit()` processes ALL available frames.

**Example (NFFT=2048, overlap=0.5, hop_size=1024):**

```
Initial state:    ring_buffer.available() = 1024 samples (residual from previous call)

submit() called with 2048 new samples:

1. Push phase:
   ring_buffer.available() = 1024 + 2048 = 3072 samples

2. Frame extraction loop:

   Iteration 1:
   - Check: 3072 ≥ 2048? YES
   - Extract 2048 samples → process → output (overwrites buffer)
   - Advance 1024 samples
   - ring_buffer.available() = 3072 - 1024 = 2048

   Iteration 2:
   - Check: 2048 ≥ 2048? YES
   - Extract 2048 samples → process → output (overwrites buffer again)
   - Advance 1024 samples
   - ring_buffer.available() = 2048 - 1024 = 1024

   Iteration 3:
   - Check: 1024 ≥ 2048? NO
   - Exit loop

3. Return:
   - Output contains result from iteration 2 (iteration 1 discarded)
   - Ring buffer retains 1024 residual samples for next call
```

**Why this design?**
- Prevents ring buffer overflow during warmup (1500+ iterations)
- Without draining: after N iterations, buffer accumulates N × hop_size samples
- With 50% overlap and 1500 warmup: would need 750× NFFT capacity!
- Trade-off: Higher CPU overhead but prevents overflow

### 3.6 Performance Characteristics

**Latency Benchmark Results (NFFT=2048, channels=2, RTX 3090 Ti — pre-Phase 1.1 baseline):**
```
Mean Latency:    122.25 µs  (+40% vs Batch)
P50 Latency:     118.78 µs
P95 Latency:     153.82 µs  (+46% vs Batch)
P99 Latency:     177.15 µs
Min Latency:      93.31 µs
Max Latency:     221.02 µs
Std Dev:          17.44 µs
CV:              14.26%
```

**Performance Factors:**
- ❌ **Ring buffer push:** 1× memcpy per channel to write input into ring buffer (~8-12 µs)
- ✅ **Zero-copy H2D:** `peek_frame()` DMA directly from pinned ring buffer — no staging extraction (Phase 1.1)
- ❌ **Multiple frame processing:** While loop adds ~10-15 µs during warmup
- ❌ **Per-channel loops:** Loop overhead × channels (~5 µs)
- ❌ **Wraparound logic:** Conditional branches for circular buffer

**Overhead Breakdown (estimated):**
```
BatchExecutor:      86.79 µs total
  CPU operations:   ~10 µs (direct memcpy)
  GPU processing:   ~70 µs (H2D + compute + D2H)
  Overhead:         ~6 µs (buffer selection, sync checks)

StreamingExecutor:  122.25 µs total
  CPU operations:   ~20 µs (ring push + zero-copy peek + advance × channels)
  GPU processing:   ~70 µs (H2D + compute + D2H - same as Batch!)
  Overhead:         ~15 µs (ring logic, while loop, multi-frame)
  Multiple frames:  +7 µs (if 2 frames processed per submit)
  Note: Phase 1.1 eliminated staging extraction (~10 µs saved in CPU ops);
        overall latency is equivalent to pre-Phase 1.1 baseline above.

Performance gap:   +35.46 µs (40% slower)
  Ring buffer push: +10 µs (28%)
  Multi-frame:      +7 µs (20%)
  Per-channel:      +5 µs (14%)
  Misc overhead:    +13 µs (37%)
```

### 3.7 Ideal Use Cases

**Perfect for:**
1. **Real-Time Streaming**
   - Continuous data acquisition
   - Variable-size input chunks
   - Sensor integration (future)

2. **Low-Latency Applications (Future)**
   - Once async is implemented
   - Background processing while acquiring new samples
   - Sub-100µs response time required

3. **Per-Channel Independent Processing**
   - Multi-sensor systems
   - Channels with different sampling rates (future)
   - Independent channel buffering

4. **STFT Overlap Management**
   - Automatic windowing with overlap
   - Ring buffer handles frame extraction
   - No manual overlap bookkeeping

**Not ideal for:**
- ❌ Maximum throughput required (use BatchExecutor)
- ❌ Fixed-size batches with no streaming
- ❌ Ultra-low latency (<100µs) until async implemented
- ❌ Minimal memory footprint required

---

## 4. Performance Comparison

### 4.1 Head-to-Head Benchmark

**Configuration:** NFFT=2048, channels=2, overlap=0.5, 1500 warmup iterations, 5000 test iterations

| Metric | BatchExecutor | StreamingExecutor | Difference |
|--------|---------------|-------------------|------------|
| **Mean Latency** | **86.79 µs** | 122.25 µs | +40.9% |
| **Median (P50)** | **89.38 µs** | 118.78 µs | +32.9% |
| **P95 Latency** | **105.47 µs** | 153.82 µs | +45.9% |
| **P99 Latency** | **116.74 µs** | 177.15 µs | +51.7% |
| **Min Latency** | **49.15 µs** | 93.31 µs | +89.8% |
| **Max Latency** | **121.86 µs** | 221.02 µs | +81.3% |
| **Std Dev** | **13.68 µs** | 17.44 µs | +27.5% |
| **CV** | 15.76% | **14.26%** | **-9.5%** ✅ |

**Key Observations:**
- BatchExecutor is consistently 30-50% faster across all percentiles
- StreamingExecutor has slightly better stability (lower CV) - likely due to averaging multiple frames
- Minimum latency gap (89.8%) indicates ring buffer overhead is fixed cost
- Performance gap is **architectural**, not due to bugs or missing optimizations

### 4.2 Overhead Analysis

**Where does the 40% overhead come from?**

```
┌─────────────────────────────────────────────────────────────────┐
│ Latency Breakdown: BatchExecutor vs StreamingExecutor          │
└─────────────────────────────────────────────────────────────────┘

BatchExecutor (86.79 µs):
├── Direct memcpy (input → d_input):        ~5 µs   (6%)
├── H2D Transfer:                           ~15 µs  (17%)
├── GPU Compute (Window + FFT + Magnitude): ~50 µs  (58%)
├── D2H Transfer:                           ~12 µs  (14%)
└── Misc overhead (buffer select, sync):    ~5 µs   (6%)

StreamingExecutor (122.25 µs — pre-Phase 1.1 baseline; current is similar):
├── Per-channel push (input → ring_buffers × 2):     ~8 µs   (7%)
├── peek_frame() zero-copy span (no staging copy):    ~1 µs   (<1%)
├── Advance ring buffer pointers (× 2 channels):      ~2 µs   (2%)
├── H2D Transfer (direct DMA from pinned ring buf):  ~15 µs  (12%)
├── GPU Compute (Window + FFT + Magnitude):          ~50 µs  (41%)
├── D2H Transfer:                                    ~12 µs  (10%)
├── While loop overhead (check + multi-frame):       ~10 µs  (8%)
└── Misc overhead (buffer select, sync, ring logic): ~24 µs  (20%)

Overhead sources (post-Phase 1.1):
1. Ring buffer push:        ~8 µs  (23% of gap)
2. While loop multi-frame:  ~10 µs (28% of gap)
3. Additional misc:         ~17 µs (49% of gap)

Total gap: 122.25 - 86.79 = 35.46 µs (40.9% slower)
Note: Phase 1.1 eliminated staging extraction (~10 µs), but overall
latency is equivalent to the pre-Phase 1.1 baseline shown above.
```

**Dominant factors:**
1. **Ring buffer push overhead (~8 µs, 23%):** Every frame requires:
   - Push: memcpy from input to ring buffer (per channel)
   - `peek_frame()` gives a zero-copy span — no staging extraction memcpy
   - H2D goes directly from pinned ring buffer memory via DMA

2. **While loop multi-frame processing (10 µs, 28%):**
   - During warmup with overlap, submit() may process 2-3 frames
   - Each additional frame incurs ring buffer extraction overhead
   - Only the last frame's result is kept (earlier frames wasted)

3. **Additional overhead (10 µs, 28%):**
   - Per-channel loop iterations (2 channels)
   - Wraparound boundary checking
   - Ring buffer state management
   - Extra NVTX profiling ranges

### 4.3 GPU Performance is Identical

**Important:** The GPU processing time is the SAME for both executors (~50 µs).

The performance gap is **entirely CPU-side overhead**:
- BatchExecutor: Minimal CPU time (direct memcpy)
- StreamingExecutor: Higher CPU time (ring buffer operations)

**Evidence from profiling:**
- H2D transfer time: ~15 µs (same)
- GPU compute time: ~50 µs (same)
- D2H transfer time: ~12 µs (same)
- Total GPU pipeline: ~77 µs (same)

**Implication:** Optimizing the GPU kernels will improve BOTH executors equally. The 40% gap is CPU-bound and requires CPU-side optimization (zero-copy, reduced memcpy).

### 4.4 Scaling Characteristics

**How does the gap change with parameters?**

| Configuration | Batch Latency | Stream Latency | Gap | Notes |
|---------------|---------------|----------------|-----|-------|
| NFFT=256, ch=2 | 159.52 µs | ~220 µs (est) | ~38% | Smaller NFFT → overhead % similar |
| NFFT=2048, ch=2 | 86.79 µs | 122.25 µs | 40.9% | Baseline |
| NFFT=4096, ch=2 | ~180 µs | ~250 µs (est) | ~39% | Larger NFFT → overhead % similar |
| NFFT=2048, ch=32 | N/A (batch mode) | N/A | N/A | Need throughput test |

**Observation:** The overhead percentage remains relatively constant (~40%) across NFFT values because:
- Ring buffer overhead scales with channels, not NFFT
- GPU compute time scales with NFFT (both executors)
- The fixed 20 µs ring buffer cost becomes similar % of total

**Channel scaling:** With more channels, ring buffer overhead increases linearly:
- Push cost: ~4 µs per channel
- Extract cost: ~5 µs per channel
- Total per-channel overhead: ~9 µs

For 32 channels (ionosphere high-throughput):
- Ring buffer overhead: ~9 × 32 = 288 µs
- This would be UNACCEPTABLE for latency-critical applications
- **Solution:** Future GPU-resident ring buffers eliminate this

---

## 5. Current Implementation (v0.9.4)

### 5.1 Threading Model

**Both executors are currently single-threaded synchronous implementations.**

```cpp
// BatchExecutor::submit() - v0.9.4
void submit(const float* input, float* output, size_t num_samples) {
    // 1. H2D transfer (blocks)
    d_input.copy_from_host(input, num_samples, stream);

    // 2. GPU compute (blocks via stream sync)
    cudaStreamSynchronize(stream);

    // 3. D2H transfer (blocks)
    d_output.copy_to_host(output, output_size, stream);
    cudaStreamSynchronize(stream);

    // Returns only after ALL work complete
}

// StreamingExecutor::submit() - v0.9.4
void submit(const float* input, float* output, size_t num_samples) {
    // 1. Ring buffer operations (CPU, blocking)
    for (int ch = 0; ch < channels; ++ch) {
        ring_buffers[ch]->push(input + offset, samples_per_ch);
    }

    // 2. Frame extraction loop (CPU, blocking)
    while (can_extract_frame()) {
        extract_and_advance();  // memcpy operations

        // 3. GPU processing (blocks via stream sync)
        cudaStreamSynchronize(stream);
    }

    // Returns only after ALL frames processed
}
```

**Key characteristics:**
- ❌ No `std::thread`, `std::async`, or threading primitives
- ❌ No mutexes, atomics, or synchronization primitives
- ❌ No background processing
- ✅ submit() blocks until ALL GPU work completes
- ✅ Thread-safe when called from single thread
- ⚠️ **NOT thread-safe** for multi-threaded callers (no mutex protection)

### 5.2 Synchronization Model

**CUDA Stream Synchronization:**

Both executors use **explicit stream synchronization** for correctness:

```cpp
// Buffer reuse guard (both executors)
if (frame_counter >= pinned_buffer_count) {
    // Wait for previous buffer to finish D2H before reusing
    cudaStreamSynchronize(compute_stream);
    cudaStreamSynchronize(d2h_stream);
}
```

**Why synchronization is needed:**
- Round-robin buffer reuse (e.g., 2 pinned buffers)
- Buffer N+2 must wait for buffer N to complete D2H
- Prevents reading buffer while GPU is writing to it

**Current approach (v0.9.4):**
- Synchronous: submit() blocks until D2H complete
- Safe but not optimal for latency

**Future approach (v0.9.5+):**
- Asynchronous: submit() returns immediately
- Callback invoked when results ready
- Requires background thread + mutex protection

### 5.3 Memory Management

**Pinned Memory:**

Both executors use CUDA pinned (page-locked) host memory for efficient H2D/D2H transfers. For `StreamingExecutor`, the ring buffers themselves are allocated in pinned memory (`PinnedHostBuffer<T>`), enabling zero-copy DMA via `peek_frame()` — no separate staging buffer is needed.

**Device Memory:**

Round-robin buffer pool for pipeline overlap:

```cpp
// Device buffers (both executors)
std::vector<DeviceBuffer<float>> d_input_buffers_;     // nfft × channels × pinned_buffer_count
std::vector<DeviceBuffer<float>> d_output_buffers_;    // output_bins × channels × pinned_buffer_count
std::vector<DeviceBuffer<float>> d_intermediate_buffers_;  // complex FFT × pinned_buffer_count
```

**Ring Buffers (StreamingExecutor only):**

Host-side ring buffers for per-channel streaming:

```cpp
std::vector<std::unique_ptr<RingBuffer<float>>> input_ring_buffers_;  // channels × [3 × nfft capacity]
```

**Memory overhead comparison (NFFT=4096, channels=2, pinned_buffer_count=2):**

```
BatchExecutor memory usage:
├── d_input_buffers (2 buffers):         2 × 4096 × 2 × 4 = 65 KB
├── d_output_buffers (2 buffers):        2 × 2049 × 2 × 4 = 33 KB
├── d_intermediate_buffers (2 buffers):  2 × 2049 × 2 × 8 = 66 KB  (complex)
└── Total device memory:                 164 KB

StreamingExecutor memory usage:
├── d_input_buffers (2 buffers):         2 × 4096 × 2 × 4 = 65 KB
├── d_output_buffers (2 buffers):        2 × 2049 × 2 × 4 = 33 KB
├── d_intermediate_buffers (2 buffers):  2 × 2049 × 2 × 8 = 66 KB
├── ring_buffers (2 ch, pinned host):    2 × 3 × 4096 × 4 = 98 KB
└── Total memory:                        262 KB

Overhead: 262 - 164 = 98 KB (60% more)
Note: Staging buffer eliminated in Phase 1.1; ring buffers are pinned and serve directly as H2D DMA source.
```

**Still very reasonable** - modern GPUs have 24 GB VRAM, so 131 KB overhead is negligible.

### 5.4 Thread Safety

**Current thread safety guarantees (v0.9.4):**

```
┌────────────────────────────────────────────────────────────┐
│ Thread Safety Matrix - v0.9.4                              │
├────────────────────────┬──────────────┬────────────────────┤
│ Operation              │ Single Thread│ Multi-Thread       │
├────────────────────────┼──────────────┼────────────────────┤
│ initialize()           │ ✅ Safe      │ ❌ Unsafe          │
│ submit()               │ ✅ Safe      │ ❌ Unsafe          │
│ submit_async()         │ ✅ Safe      │ ❌ Unsafe          │
│ synchronize()          │ ✅ Safe      │ ❌ Unsafe          │
│ get_stats()            │ ✅ Safe      │ ⚠️ Racy (benign)   │
│ reset()                │ ✅ Safe      │ ❌ Unsafe          │
└────────────────────────┴──────────────┴────────────────────┘
```

**Why currently unsafe for multi-threading:**

1. **No mutex protection on:**
   - Ring buffers (StreamingExecutor)
   - Device buffer selection (both)
   - Statistics updates (both)
   - Frame counters (both)

2. **Data races possible:**
   - Two threads call submit() simultaneously
   - Both select same round-robin buffer
   - Corrupt ring buffer state
   - Undefined behavior

3. **CUDA stream safety:**
   - CUDA streams are thread-safe at driver level
   - But HOST-SIDE state (counters, pointers) is NOT protected

**Mitigation (v0.9.4):**
- **ASSERT:** User must ensure single-threaded access
- Document in API: "Not thread-safe for concurrent submit() calls"
- Python GIL provides implicit protection in Python layer

**v0.9.5 (StreamingExecutor):**
- Optional background consumer thread (`enable_background_thread = true`)
- Producer/consumer separation via ring buffer lock-free atomics (SPSC)
- Result queued and returned to caller with timeout

**Note:** `BatchExecutor` remains single-threaded; thread safety for concurrent callers is not planned.

---

## 6. Roadmap

### 6.1 Completed: Zero-Copy Ring Buffers (Phase 1.1)

**Status: Implemented**

Ring buffers are allocated in CUDA pinned memory (`PinnedHostBuffer<T>`). `peek_frame()` returns a zero-copy `FrameView` spanning directly into that pinned memory. The streaming executor issues `cudaMemcpyAsync` directly from the ring buffer pointer — no staging buffer required.

```
Before Phase 1.1:
  input → ring_buffer (memcpy) → staging (memcpy) → d_input (H2D)

After Phase 1.1:
  input → ring_buffer (push) ──peek_frame()──> d_input (H2D, direct DMA)
```

Wraparound frames (two spans) issue two `cudaMemcpyAsync` calls. `advance()` is called after D2H sync to keep pointers valid during DMA.

### 6.2 Completed: Background Thread Foundation (v0.9.5)

**Status: Implemented (opt-in)**

`ExecutorConfig::enable_background_thread = true` starts a consumer thread in `StreamingExecutor`. The producer calls `submit()`, notifies the consumer, and waits for the result with a configurable timeout (`config_.timeout_ms`). The ring buffer's lock-free SPSC atomics handle the producer/consumer handoff without mutex overhead on the data path.

### 6.3 GPU-Resident Ring Buffers (Planned)

**Goal:** Move ring buffers entirely to GPU memory.

**Current:**
```
input (host) → ring_buffer (pinned, peek_frame) → d_input (device, direct DMA)
```

**Future:**
```
input (host) → d_ring_buffer (device) → d_input (device)
              └─ H2D once ──┘          └─ memcpy on GPU ──┘
```

**Implementation:**
- Allocate ring buffers in device memory
- Push: H2D transfer directly to ring buffer on GPU
- Extract: CUDA kernel copies frame to d_input (on-device memcpy)
- Advance: Update read pointer on GPU

**Performance impact:**
- ✅ Eliminate ALL CPU ring buffer overhead (~20 µs saved)
- ✅ Parallel per-channel extraction (CUDA kernel)
- ✅ Enables future GPU-based overlap windowing
- ⚠️ Requires custom CUDA kernels for ring buffer ops
- ⚠️ More complex debugging (GPU-side state)

**Expected latency reduction:**
- StreamingExecutor: 122 µs → **95 µs** (~22% faster)
- Only ~9% slower than Batch (95 vs 87 µs)

**Challenge:** Ring buffer logic (wraparound, advance) must be implemented as CUDA kernels.

### 6.4 GPU Overlap Windowing (Planned)

**Goal:** Perform STFT overlap entirely on GPU.

**Current:**
```
CPU: Push samples to pinned ring buffer, peek_frame, advance by hop_size
GPU: Window → FFT → Magnitude (process single frame)
```

**Future (v0.9.8+):**
```
CPU: Push continuous stream to GPU ring buffer
GPU: Extract overlapping windows, window, FFT, magnitude (all on device)
```

**Implementation:**
- Persistent CUDA kernel for streaming STFT
- Kernel monitors ring buffer fill level
- Extracts windows with overlap directly on GPU
- Processes multiple frames in parallel (if NFFT < GPU occupancy)

**Performance impact:**
- ✅ Zero CPU overhead for frame extraction
- ✅ Parallel multi-frame processing
- ✅ Enables true sub-100µs latency
- ⚠️ Complex kernel development
- ⚠️ Requires careful synchronization

**Expected latency reduction:**
- StreamingExecutor: 122 µs → **85 µs** (~30% faster)
- **Matches or beats BatchExecutor!**

**This is the end-game architecture for StreamingExecutor.**

### 6.5 Roadmap Timeline

```
┌──────────────────────────────────────────────────────────────┐
│ StreamingExecutor Performance Roadmap                        │
└──────────────────────────────────────────────────────────────┘

Phase 1.1 / v0.9.4 ✅ DONE:
├─ + Zero-copy ring buffers (pinned memory, peek_frame)
├─ + Staging buffer eliminated
├─ Baseline latency: ~122 µs (pre-Phase 1.1 measurement; current is similar)
└─ Gap vs Batch: ~40% (CPU push overhead remains)

v0.9.5 ✅ DONE:
├─ + Optional background consumer thread (enable_background_thread)
├─ + Lock-free SPSC ring buffer atomics
└─ Latency: unchanged (opt-in async path)

Future — GPU-resident ring buffers:
├─ + H2D directly to device-side ring buffer
├─ + CUDA kernels for ring buffer ops
├─ Expected latency: ~95 µs (~22% faster)
└─ Overhead vs Batch: ~9%

Future — GPU overlap windowing:
├─ + Persistent streaming STFT kernel
├─ + Parallel multi-frame processing on GPU
├─ Expected latency: ~85 µs (~30% faster)
└─ Overhead vs Batch: negligible
```

**Current state (v0.9.5):**
- Zero-copy DMA from pinned ring buffer is live
- Background thread opt-in is available
- Remaining gap is CPU push overhead (per-channel memcpy into ring buffer)

---

## 7. Optimization Opportunities

### 7.1 Current Optimizations

**What CAN be optimized now:**

1. **Ring Buffer Capacity Tuning**
   - Current: 3× NFFT
   - Could reduce to 2.5× NFFT for some overlap values
   - Saves ~16 KB memory per channel
   - Risk: Overflow with unusual warmup patterns

2. **Reduce Multi-Frame Processing**
   - Current: Process ALL available frames
   - Alternative: Process max 2 frames per submit()
   - Trades ring buffer capacity for lower CPU time
   - Risk: Need larger ring buffers (4× NFFT)

3. **Channel Loop Unrolling**
   - Current: for (ch = 0; ch < channels; ++ch)
   - Unroll for common cases (2, 4, 8 channels)
   - Saves ~1-2 µs per submit()
   - Trade-off: Code size vs performance

4. **SIMD for Ring Buffer Operations**
   - Use AVX2/AVX-512 for memcpy in ring buffer
   - Potential 2-4× speedup on extract/push
   - Save ~5-10 µs per submit()
   - Requires careful alignment

**Expected impact of current optimizations:**
- Combined: Save ~10-15 µs
- StreamingExecutor: 122 µs → **110 µs** (~10% improvement)
- Still ~27% slower than Batch

**Worth it?**
- ⚠️ Marginal gains for significant code complexity
- ✅ Better to wait for v0.9.6+ architectural improvements

### 7.2 Near-Term Optimizations (v0.9.5-0.9.6)

**Async submission (v0.9.5):**
- Adds ~2 µs overhead (mutex, queueing)
- But enables overlapping compute with next submit()
- **Net result:** Higher throughput, better CPU utilization
- **Recommended:** Implement first before zero-copy

**Zero-copy ring buffers (v0.9.6):**
- Eliminate staging buffer memcpy (~10 µs)
- Straightforward implementation (allocate in pinned memory)
- **High impact, low risk**
- **Recommended:** Priority optimization

**Validation:**
```bash
# Benchmark streaming latency (C++ layer)
sigxc bench --preset latency --full
# Mean: ~122 µs (pre-Phase 1.1 baseline; zero-copy already applied)
```

### 7.3 Long-Term Optimizations (v0.9.7+)

**GPU-resident ring buffers (v0.9.7):**
- Requires CUDA kernel development
- High impact (~20 µs saved)
- Moderate risk (GPU state management)
- **Recommended:** After v0.9.6 validated

**GPU overlap windowing (v0.9.8):**
- Requires persistent kernel architecture
- Very high impact (~30 µs saved, match/beat Batch)
- High complexity and risk
- **Recommended:** Research project, careful validation

### 7.4 BatchExecutor Optimizations

**Current state:** Already highly optimized.

**Possible improvements:**
1. **Reduce synchronization overhead**
   - Use CUDA events instead of cudaStreamSynchronize
   - Save ~2-3 µs
   - Low risk

2. **Pipeline overlap**
   - Increase pinned_buffer_count to 3-4
   - Better H2D/compute/D2H overlap
   - Diminishing returns (already well-pipelined)

3. **Kernel fusion**
   - Fuse window + FFT into single kernel
   - Save ~5-10 µs (avoid intermediate write)
   - High complexity (custom FFT kernel)

**Expected impact:**
- Combined: Save ~5-10 µs
- BatchExecutor: 87 µs → **80 µs** (~8% improvement)

**Worth it?**
- ✅ For latency-critical applications (<100 µs target)
- ⚠️ Diminishing returns (already near-optimal)

---

## 8. Technical Details

### 8.1 Ring Buffer Implementation

**Ring Buffer Interface** (`cpp/include/sigtekx/core/ring_buffer.hpp`):

```cpp
template <typename T>
class RingBuffer {
public:
    explicit RingBuffer(size_t capacity);  // Allocates CUDA pinned memory

    void push(const T* data, size_t count);           // Producer: write samples
    void extract_frame(T* output, size_t frame_size); // Copy frame to buffer
    FrameView peek_frame(size_t frame_size) const;    // Zero-copy: return span(s)
    void advance(size_t samples);                      // Consumer: move read ptr
    bool can_extract_frame(size_t frame_size) const;
    size_t available() const;
    void reset();

    // FrameView: one or two ReadSpans pointing into pinned memory
    struct FrameView {
        ReadSpan first;   // Always valid
        ReadSpan second;  // Non-null only on wraparound
        bool is_contiguous() const noexcept;
    };

private:
    size_t capacity_;
    PinnedHostBuffer<T> buffer_;     // CUDA page-locked memory
    std::atomic<size_t> write_pos_;  // Lock-free SPSC
    std::atomic<size_t> read_pos_;
    std::atomic<size_t> available_;
};
```

**Wraparound Logic** (simplified; actual uses atomics with acquire/release semantics):

```cpp
void push(const T* data, size_t count) {
    if (available_.load() + count > capacity_)
        throw std::overflow_error("Ring buffer overflow");

    size_t wp = write_pos_.load();
    if (wp + count <= capacity_) {
        std::memcpy(buffer_.get() + wp, data, count * sizeof(T));
    } else {
        size_t first = capacity_ - wp;
        std::memcpy(buffer_.get() + wp, data, first * sizeof(T));
        std::memcpy(buffer_.get(), data + first, (count - first) * sizeof(T));
    }
    write_pos_.store((wp + count) % capacity_);
    available_.fetch_add(count);
}
```

**Extract without advance (for overlap):**

```cpp
void extract_frame(T* output, size_t frame_size) const {
    if (available_ < frame_size) {
        throw std::underflow_error("Insufficient samples");
    }

    // Handle wraparound
    size_t read_end = read_pos_ + frame_size;
    if (read_end <= capacity_) {
        // Contiguous read
        std::memcpy(output, &buffer_[read_pos_], frame_size * sizeof(T));
    } else {
        // Split read (wraparound)
        size_t first_part = capacity_ - read_pos_;
        std::memcpy(output, &buffer_[read_pos_], first_part * sizeof(T));
        std::memcpy(output + first_part, &buffer_[0], (frame_size - first_part) * sizeof(T));
    }
}
```

**Advance for overlap:**

```cpp
void advance(size_t count) {
    if (count > available_) {
        throw std::underflow_error("Cannot advance beyond available samples");
    }

    read_pos_ = (read_pos_ + count) % capacity_;
    available_ -= count;
}
```

**STFT overlap pattern:**

```
Initial state: empty ring buffer

Step 1: Push NFFT samples
├─ write_pos: 0 → NFFT
├─ available: 0 → NFFT
└─ Can extract first frame

Step 2: Extract NFFT samples (doesn't move read_pos)
├─ Copies samples [0..NFFT-1]
└─ available: still NFFT

Step 3: Advance by hop_size (e.g., NFFT/2 for 50% overlap)
├─ read_pos: 0 → NFFT/2
├─ available: NFFT → NFFT/2
└─ Cannot extract frame yet (need NFFT)

Step 4: Push NFFT samples again
├─ write_pos: NFFT → 2×NFFT
├─ available: NFFT/2 → 3×NFFT/2
└─ Can extract second frame

Step 5: Extract NFFT samples
├─ Copies samples [NFFT/2 .. 3×NFFT/2-1]
└─ Note: 50% overlap with previous frame!

Step 6: Advance by hop_size
├─ read_pos: NFFT/2 → NFFT
├─ available: 3×NFFT/2 → NFFT
└─ Can extract immediately (already have NFFT)

Step 7: Extract NFFT samples
├─ Copies samples [NFFT .. 2×NFFT-1]
└─ 50% overlap with previous frame

...pattern continues...
```

This is how STFT overlap is implemented with zero CPU bookkeeping overhead!

### 8.2 CUDA Stream Synchronization

**Three-Stream Pipeline:**

Both executors use 3 CUDA streams for parallel H2D, compute, and D2H:

```cpp
// Stream assignment
const int h2d_stream_idx = 0;        // Host-to-device transfers
const int compute_stream_idx = 1;    // GPU kernels (window, FFT, magnitude)
const int d2h_stream_idx = 2;        // Device-to-host transfers
```

**Pipeline overlap pattern:**

```
Frame N:
├─ H2D (stream 0):    [============]
├─ Compute (stream 1):               [====================]
└─ D2H (stream 2):                                         [============]

Frame N+1:
├─ H2D (stream 0):                                                       [============]
├─ Compute (stream 1):                                                                  [====================]
└─ D2H (stream 2):                                                                                            [============]

Overlap:
└─ Frame N+1 H2D starts while Frame N compute is running (pipeline parallelism)
```

**Event-based dependencies:**

```cpp
// H2D Transfer
d_input.copy_from_host(input, num_samples, streams_[h2d_stream_idx].get());
events_[buffer_idx * 2 + 0].record(streams_[h2d_stream_idx].get());

// Wait for H2D before compute
cudaStreamWaitEvent(streams_[compute_stream_idx].get(),
                    events_[buffer_idx * 2 + 0].get(), 0);

// Compute Pipeline
for (auto& stage : stages_) {
    stage->process(current_input, current_output, size,
                   streams_[compute_stream_idx].get());
}
events_[buffer_idx * 2 + 1].record(streams_[compute_stream_idx].get());

// Wait for compute before D2H
cudaStreamWaitEvent(streams_[d2h_stream_idx].get(),
                    events_[buffer_idx * 2 + 1].get(), 0);

// D2H Transfer
d_output.copy_to_host(output, output_size, streams_[d2h_stream_idx].get());
```

**Buffer reuse synchronization:**

```cpp
// Guard against reusing buffer before D2H completes
if (frame_counter >= static_cast<uint64_t>(config_.pinned_buffer_count)) {
    // Wait for oldest in-flight buffer to complete
    cudaStreamSynchronize(streams_[compute_stream_idx].get());
    cudaStreamSynchronize(streams_[d2h_stream_idx].get());
}
```

**Why this matters:**
- Without sync: Could overwrite buffer while GPU still reading
- With sync: Safe buffer reuse, but adds ~5-10 µs latency
- Future: Use more buffers (pinned_buffer_count=3-4) to reduce sync frequency

### 8.3 NVTX Profiling Ranges

**Both executors are heavily instrumented with NVTX ranges for Nsight profiling.**

**Example ranges:**

```cpp
// Top-level function
IONO_NVTX_RANGE_FUNCTION(profiling::colors::NVIDIA_BLUE);

// Memory operations
IONO_NVTX_RANGE("Push to Per-Channel Ring Buffers", profiling::colors::CYAN);
IONO_NVTX_RANGE("Extract Per-Channel Frames", profiling::colors::GREEN);

// Transfers
const std::string h2d_msg = profiling::format_memory_range("H2D Transfer", bytes);
IONO_NVTX_RANGE(h2d_msg.c_str(), profiling::colors::GREEN);

// Compute
IONO_NVTX_RANGE("Compute Pipeline", profiling::colors::PURPLE);
IONO_NVTX_RANGE("Stage: FFTStage", profiling::colors::MAGENTA);

// Synchronization
IONO_NVTX_RANGE("Wait for Buffer Availability", profiling::colors::YELLOW);
```

**Color scheme:**
- **Blue:** Top-level functions
- **Green:** Memory transfers
- **Cyan:** Ring buffer operations
- **Purple:** Compute pipeline
- **Magenta:** Individual stages
- **Yellow:** Synchronization waits

**Profiling workflow:**

```bash
# Profile StreamingExecutor
iprof nsys latency

# View in Nsight Systems
nsys-ui artifacts/profiling/latency.nsys-rep

# Look for:
# - "Push to Per-Channel Ring Buffers" (should be ~8 µs)
# - "Extract Per-Channel Frames" (should be ~10 µs)
# - "H2D Transfer" (should be ~15 µs)
# - "Compute Pipeline" (should be ~50 µs)
# - "Wait for Buffer Availability" (should be rare)
```

**Debugging with NVTX:**
- Identify bottlenecks (which range takes longest?)
- Verify pipeline overlap (do H2D/compute/D2H overlap?)
- Find synchronization stalls (yellow ranges = bad)

### 8.4 Buffer Reuse and Round-Robin

**Round-robin buffer selection:**

```cpp
const int buffer_idx = static_cast<int>(frame_counter_ % config_.pinned_buffer_count);
```

**Example with pinned_buffer_count=2:**

```
Frame 0: buffer_idx = 0 % 2 = 0 (use buffer 0)
Frame 1: buffer_idx = 1 % 2 = 1 (use buffer 1)
Frame 2: buffer_idx = 2 % 2 = 0 (reuse buffer 0, must sync first)
Frame 3: buffer_idx = 3 % 2 = 1 (reuse buffer 1, must sync first)
...
```

**Why round-robin?**
- Enables pipeline overlap (H2D for buffer 1 while buffer 0 computes)
- Reduces memory allocation overhead (reuse buffers)
- Typical: 2-3 buffers sufficient for full overlap

**Synchronization requirement:**

```cpp
// Frame 2: Reusing buffer 0
if (frame_counter >= 2) {
    // Wait for frame 0 to complete D2H before overwriting
    cudaStreamSynchronize(compute_stream);
    cudaStreamSynchronize(d2h_stream);
}
```

**Trade-off:**
- More buffers (pinned_buffer_count=3-4): Less sync, more memory
- Fewer buffers (pinned_buffer_count=2): More sync, less memory
- Default=2 is well-balanced for most use cases

---

## Summary

### Key Takeaways

1. **BatchExecutor is 40% faster** due to minimal CPU overhead (direct memcpy, no ring buffers)
2. **StreamingExecutor trades performance for flexibility** (arbitrary input sizes, per-channel streaming)
3. **The gap is architectural**, not due to bugs or missing threading/async
4. **Both are single-threaded synchronous** in v0.9.4 (no mutexes needed yet)
5. **Future optimizations will close the gap**: zero-copy (v0.9.6), GPU-resident buffers (v0.9.7), GPU overlap windowing (v0.9.8)
6. **By v0.9.8, StreamingExecutor will match or beat BatchExecutor** through GPU parallelism

### When to Use Which

- **BatchExecutor:** Latency-critical, fixed batch sizes, maximum throughput
- **StreamingExecutor:** Real-time streaming, variable inputs, future async/zero-copy

### Next Steps

1. **Validate current performance** with profiling (nsys)
2. **Plan v0.9.5 async implementation** (background thread + callbacks)
3. **Prototype zero-copy ring buffers** (v0.9.6)
4. **Research GPU-resident ring buffers** (v0.9.7-0.9.8)

---

**Questions or need clarification?** See [Architecture Overview](overview.md) or [Contributing Guidelines](../guides/contributing.md).
