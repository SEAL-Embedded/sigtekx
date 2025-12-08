# SigTekX Methods Paper Development Roadmap

**Last Updated**: 2025-12-07
**Status**: Architecture Planning Phase
**Target**: Novel, custom, and fast real-time signal processing in Python

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [Project Goals and Needs](#project-goals-and-needs)
- [Current State Analysis](#current-state-analysis)
- [The Dual-Plane Architecture](#the-dual-plane-architecture)
- [Priority Task Roadmap](#priority-task-roadmap)
- [Metrics for Paper Defense](#metrics-for-paper-defense)
- [Experiments for Paper Defense](#experiments-for-paper-defense)
- [Target Hardware Considerations](#target-hardware-considerations)
- [Development Timeline Strategy](#development-timeline-strategy)
- [Publication Strategy and Venues](#publication-strategy-and-venues)
- [Risk Mitigation](#risk-mitigation)
- [Success Criteria for v1.0 Paper](#success-criteria-for-v10-paper)
- [Critical Files Reference](#critical-files-reference)
- [Conclusion](#conclusion)

## Executive Summary

### The Core Value Proposition

**Market Gap**: There is no Python-native solution for **soft real-time continuous signal processing** that bridges the gap between:
- **Low end**: NumPy/SciPy/CuPy (offline batch processing, no real-time guarantees)
- **High end**: FPGA/VHDL (hard real-time, months of development time, no Python)

**SigTekX fills this gap** by enabling researchers to:
1. Prototype complex DSP pipelines in Python with custom stages (Numba kernels, PyTorch models, I/O callbacks)
2. Achieve soft real-time performance (RTF < 0.3) suitable for continuous monitoring applications
3. Deploy on accessible hardware (gaming/workstation GPUs, not data centers)
4. Iterate in seconds/minutes instead of weeks/months

**First Application**: Dual-channel antenna system for ionosphere monitoring (VLF/ULF phenomena, missile detection)

### Critical Performance Target

**Real-Time Factor (RTF) < 0.3**
- Process 1 second of data in <300ms
- 3× safety headroom for burst loads, thermal throttling
- Aggressive but achievable with planned optimizations

---

## Project Goals and Needs

### Primary Goals (v1.0 - Methods Paper)

1. **Streaming Architecture Validation**
   - Demonstrate stable continuous processing (hours/days, not just seconds)
   - Achieve RTF < 0.3 for ionosphere workloads (NFFT 2048-8192, 2-8 channels)
   - Zero buffer overflows, predictable latency (low jitter)

2. **Custom Stage Ecosystem (THE CORE NOVELTY)**
   - **Data Plane Integration**: Numba CUDA kernels run inline with <10µs overhead
   - **Control Plane Decoupling**: Python callbacks (I/O, plotting, APIs) don't block pipeline
   - **Hybrid Compute**: PyTorch models in pipeline (GPU inference without Python bottleneck)
   - Scientists can add custom functionality without C++ knowledge

3. **Performance Validation**
   - Prove competitive with CuPy for throughput (batch mode)
   - Prove superior to CuPy for continuous streaming (real-time mode)
   - Demonstrate scaling: 2→8 channels, 2048→8192 NFFT

4. **Hardware Accessibility**
   - Target consumer/workstation GPUs (RTX 3090 Ti, RTX 4000 Ada)
   - NOT data center cards (A100/H100 - overkill and expensive)
   - Path to embedded (Jetson) for remote deployment

### Secondary Goals (Future Work - Mentioned in Paper)

- Multi-GPU scaling (distribute channels across devices)
- Mobile optimization (RTX Ada laptop - power constrained)
- Jetson deployment (ARM, thermal limits)
- Long-duration stress tests (weeks of continuous operation)

---

## Current State Analysis

### What Works Well ✅

1. **Benchmark Infrastructure**
   - 4 benchmark types: latency, throughput, realtime, accuracy
   - MLflow tracking, Snakemake orchestration
   - Streamlit dashboard for interactive analysis
   - 11 ionosphere-specific experiments configured

2. **Thread Safety**
   - Comprehensive documentation (`docs/architecture/thread-safety.md`)
   - Thread-compatible design (per-process instances safe)
   - Lock-free ring buffers (SPSC pattern)

3. **Processing Pipeline**
   - Window → FFT → Magnitude stages working
   - cuFFT integration, CUDA kernels optimized
   - Configurable via Hydra configs

4. **Statistical Analysis**
   - Confidence intervals, outlier detection
   - Distribution analysis (skewness, kurtosis, bimodality)
   - GPU clock locking for stability (CV: 20% → 5-10%)

### Critical Gaps ❌

1. **Memory Architecture (28% performance overhead)**
   - `h_batch_staging_` buffer is unnecessary technical debt
   - Adds 10µs memcpy (H2H) before H2D transfer
   - StreamingExecutor: 122µs vs BatchExecutor: 87µs (+35µs gap)
   - **Impact**: Wastes 28% of performance budget

2. **Custom Stage Support (MISSING - Core Novelty)**
   - No `CustomStage` C++ class
   - No Numba/CuPy integration
   - No Python → C++ kernel bridge
   - PipelineBuilder in Python is cosmetic (doesn't control actual C++ pipeline)
   - **Impact**: Cannot demonstrate core value proposition

3. **Dual-Plane Architecture (MISSING)**
   - No separation of fast path (data plane) vs slow path (control plane)
   - No snapshot buffer for async GUI updates
   - No event queue for I/O callbacks
   - **Impact**: Python I/O would block entire pipeline

4. **Persistent State Support (MISSING)**
   - ProcessingStage interface is stateless
   - No mechanism for IIR filters, running statistics, etc.
   - **Impact**: Limited to FIR-style algorithms

5. **Per-Stage Timing (MISSING)**
   - Cannot measure custom stage overhead
   - Benchmarks have `measure_components=false` (placeholder)
   - **Impact**: Cannot validate <10µs overhead claim

6. **Long-Duration Validation (MISSING)**
   - Current tests: 10 seconds maximum
   - No 24hr+ stress tests
   - No thermal steady-state validation
   - **Impact**: Cannot claim "production-ready" real-time

---

## The Dual-Plane Architecture

### Design Philosophy

**Problem**: Python is too slow for real-time DSP, but scientists need Python's flexibility.

**Solution**: Separate fast and slow operations into two parallel planes:

```
┌─────────────────────────────────────────────────────────────────┐
│ CONTROL PLANE (Python)                                          │
│ - Configuration, monitoring, I/O                                │
│ - Runs at human speed (Hz to seconds)                           │
│ - Flexible, easy to modify                                      │
└─────────────────────────────────────────────────────────────────┘
         ↕ (Config, events, snapshots - minimal data transfer)
┌─────────────────────────────────────────────────────────────────┐
│ DATA PLANE (C++/CUDA)                                           │
│ - Signal processing, GPU compute                                │
│ - Runs at real-time (kHz)                                       │
│ - Optimized, lock-free, zero-copy                               │
└─────────────────────────────────────────────────────────────────┘
```

### Data Plane (Fast Path)

**Runs at**: kHz (e.g., 5000 frames/sec for NFFT=4096, overlap=0.75, fs=32kHz)
**Latency budget**: 200µs per frame (for RTF < 0.3)
**Operations**:
- Ring buffer management (lock-free)
- H2D transfer
- GPU kernels (window, FFT, magnitude, **custom Numba kernels**)
- D2H transfer (optional)
- State updates (persistent buffers)

**Design constraints**:
- No Python GIL (pure C++/CUDA)
- No dynamic allocation (pre-allocated buffers)
- No I/O, no logging (NVTX ranges only)
- Zero-copy memory architecture

### Control Plane (Slow Path)

**Runs at**: Hz to seconds (e.g., 60 Hz GUI updates, 1 Hz Slack alerts)
**Latency budget**: Unbounded (doesn't block data plane)
**Operations**:
- Configuration changes
- Snapshot retrieval (latest N frames)
- Event consumption (threshold triggers, anomalies)
- I/O callbacks (database writes, API calls)
- Plotting, GUI updates
- PyTorch model inference (if too slow for data plane)

**Design constraints**:
- Decoupled from data plane (lock-free queues, snapshot buffers)
- Python GIL is fine
- Can block, allocate, do I/O freely

### Hybrid Operations

Some operations straddle both planes:

1. **Fast Custom Stages** (Numba CUDA kernels)
   - Compiled once in Python → device function pointer
   - Runs inline in data plane (same latency as built-in stages)
   - Target overhead: <10µs

2. **Medium Custom Stages** (PyTorch models)
   - If fast enough (<50µs): run inline in data plane
   - If too slow (>100µs): offload to control plane with snapshot
   - Adaptive threshold based on RTF

3. **Sink Stages** (Output taps)
   - Copy data to snapshot buffer every N frames
   - Control plane polls snapshot (no blocking)
   - Example: Streamlit plot updates at 60 Hz

---

## Priority Task Roadmap

**Ordering Principle**: Build foundation → add functionality → optimize → validate

### Phase 1: Foundation (Memory Architecture) - v0.9.6

**Goal**: Eliminate performance overhead before adding custom stages
**Duration**: 1-2 weeks
**Prevents regression**: If we add custom stages before fixing memory, we'll optimize the wrong bottleneck

#### Task 1.1: Zero-Copy Ring Buffer Extraction
**File**: `cpp/src/executors/streaming_executor.cpp`
**Action**:
1. Remove `h_batch_staging_` buffer (line 137-139)
2. Implement direct H2D from ring buffer memory
3. Add `cudaStreamSynchronize()` before `advance()` (prevent DMA race)

**Expected improvement**: 122µs → 114µs (-7%)

**Validation**:
- Run `python benchmarks/run_latency.py +benchmark=profiling` before/after
- Confirm <10µs improvement
- Verify no accuracy regression (`run_accuracy.py`)

**Risk**: Medium - requires careful sync management, wraparound edge case

#### Task 1.2: Per-Stage Timing Infrastructure
**Files**:
- `cpp/include/sigtekx/core/processing_stage.hpp`
- `cpp/bindings/bindings.cpp`
- `benchmarks/latency.py`

**Action**:
1. Add CUDA event timers to `ProcessingStage::process()`
2. Expose `get_stage_metrics()` to Python bindings
3. Enable `measure_components=true` in latency benchmark
4. Update dashboard to show stage breakdown

**Expected metrics**:
- Window: ~5-10µs
- FFT: ~30-40µs
- Magnitude: ~5-10µs
- Custom stage: <10µs (target for Phase 2)

**Validation**:
- Sum of stage times ≈ total latency (within 10%)
- Overhead (non-stage time) < 20µs

**Risk**: Low - additive feature, doesn't change behavior

---

### Phase 2: Custom Stage Integration (THE CORE NOVELTY) - v0.9.7

**Goal**: Enable Python users to inject custom CUDA kernels, PyTorch models, and callbacks
**Duration**: 3-4 weeks
**Prevents regression**: Memory is optimized, so custom stage overhead is accurately measured

#### Task 2.1: CustomStage C++ Class (Data Plane Fast Path)
**File**: `cpp/src/core/processing_stage.cpp`
**Action**:
1. Create `CustomStage` class accepting:
   - `CUfunction` pointer (from Numba)
   - Grid/block dimensions
   - Workspace size (for persistent state)
2. Implement `process()` to call `cuLaunchKernel()`
3. Add persistent state buffer allocation

**Interface**:
```cpp
class CustomStage : public ProcessingStage {
public:
    CustomStage(CUfunction kernel_func,
                dim3 grid, dim3 block,
                size_t workspace_bytes);
    void process(...) override;
private:
    CUfunction kernel_;
    dim3 grid_, block_;
    DeviceBuffer<uint8_t> workspace_;
};
```

**Validation**:
- Unit test: Launch simple kernel (element-wise multiply)
- Verify workspace allocation/deallocation
- Measure overhead vs built-in stage

**Risk**: Medium - CUDA driver API is low-level

#### Task 2.2: Numba Integration (Python → C++ Bridge)
**Files**:
- `cpp/bindings/bindings.cpp`
- `src/sigtekx/core/builder.py`
- `src/sigtekx/stages/custom.py` (new)

**Action**:
1. Expose `CustomStage` to pybind11
2. Create `NumbaStageAdapter`:
   - Accept `@cuda.jit` decorated function
   - Extract `kernel_func.driver_function.handle.value` (device pointer)
   - Pass to C++ as `CUfunction`
3. Add `PipelineBuilder.add_custom(kernel_func, workspace_mb=0)`

**Example user code**:
```python
from numba import cuda
from sigtekx import PipelineBuilder

@cuda.jit
def my_filter(input, output, n):
    i = cuda.grid(1)
    if i < n:
        output[i] = input[i] * 0.9  # Simple gain

pipeline = (PipelineBuilder()
    .add_window('hann')
    .add_fft()
    .add_custom(my_filter)  # ← User-defined stage!
    .add_magnitude()
    .build())
```

**Validation**:
- Integration test: Custom stage in pipeline
- Measure overhead: should be <10µs vs built-in
- Accuracy: verify custom stage computes correctly

**Risk**: High - Numba internals may change, need version pinning

#### Task 2.3: PyTorch Model Integration (Hybrid Path)
**Files**:
- `src/sigtekx/stages/pytorch.py` (new)
- `cpp/src/core/processing_stage.cpp`

**Action**:
1. Create `TorchStage` wrapper:
   - Accepts `torch.nn.Module`
   - Converts to TorchScript for faster inference
   - Copies data to torch.Tensor (shares GPU memory, no H2D)
2. Add adaptive routing:
   - If inference time <50µs: inline in data plane
   - If >100µs: offload to control plane (snapshot)

**Example user code**:
```python
import torch
from sigtekx import PipelineBuilder

class Denoiser(torch.nn.Module):
    def forward(self, x):
        return torch.relu(x - 0.1)  # Threshold denoiser

model = Denoiser().cuda().eval()

pipeline = (PipelineBuilder()
    .add_fft()
    .add_torch_model(model)  # ← PyTorch in pipeline!
    .add_magnitude()
    .build())
```

**Validation**:
- Benchmark: Measure model inference time
- Compare: Inline vs snapshot latency
- Verify: No accuracy degradation

**Risk**: Medium - PyTorch/CUDA memory interop

#### Task 2.4: Persistent State Support
**Files**:
- `cpp/include/sigtekx/core/processing_stage.hpp`
- `cpp/src/core/processing_stage.cpp`

**Action**:
1. Add `virtual void* get_state_ptr() { return nullptr; }` to interface
2. Extend `StageConfig` to support `workspace_bytes`
3. Allocate persistent `DeviceBuffer` in `initialize()`
4. Example: IIR filter with state buffer

**Example user code**:
```python
@cuda.jit
def iir_filter(input, output, state, n, alpha):
    i = cuda.grid(1)
    if i < n:
        state[0] = alpha * input[i] + (1-alpha) * state[0]
        output[i] = state[0]

pipeline = (PipelineBuilder()
    .add_custom(iir_filter, workspace_mb=0.001)  # 1 KB state
    .build())
```

**Validation**:
- Test: State persists across frames
- Test: Multiple stages with independent state
- Benchmark: No overhead vs stateless

**Risk**: Low - simple buffer allocation

---

### Phase 3: Control Plane Decoupling (Async I/O) - v0.9.8

**Goal**: Enable slow operations (plotting, I/O) without blocking data plane
**Duration**: 2-3 weeks
**Prevents regression**: Data plane is fast and custom stages work; now add observability

#### Task 3.1: Snapshot Buffer (Polling Sink)
**File**: `cpp/src/executors/streaming_executor.cpp`
**Action**:
1. Add `PinnedHostBuffer<float> snapshot_buffer_`
2. In hot loop: `if (timer > 16ms) { copy_to_snapshot(d_output); }`
3. Expose `get_latest_frame()` to Python (lock-free read)

**Python API**:
```python
engine = Engine(...)
while True:
    frame = engine.latest_frame  # Non-blocking
    update_plot(frame)
    time.sleep(1/60)  # 60 Hz GUI
```

**Validation**:
- Test: 5 kHz data plane + 60 Hz snapshot retrieval
- Verify: No frame drops, no latency increase
- Measure: Snapshot overhead <5µs

**Risk**: Low - simple async copy

#### Task 3.2: Event Queue (Callback Sink)
**Files**:
- `cpp/include/sigtekx/core/event_queue.hpp` (new)
- `cpp/src/executors/streaming_executor.cpp`

**Action**:
1. Create lock-free MPSC queue for events
2. Stages can `emit_event(type, data)` (threshold trigger, anomaly)
3. Python polls queue: `engine.get_events(timeout=0.1)`
4. Example: Slack alert when magnitude > threshold

**Python API**:
```python
# In custom stage (Numba)
if magnitude > threshold:
    emit_event('anomaly', {'time': timestamp, 'mag': magnitude})

# In control plane (Python)
for event in engine.get_events():
    if event['type'] == 'anomaly':
        send_slack_alert(event['data'])
```

**Validation**:
- Test: 1000 events/sec generated, no data plane slowdown
- Test: Event order preserved
- Measure: Event emission overhead <2µs

**Risk**: Medium - lock-free queue complexity

#### Task 3.3: Callback Stage (I/O Sink)
**Files**:
- `src/sigtekx/stages/callback.py` (new)

**Action**:
1. Create `CallbackStage`:
   - Runs in separate thread pool
   - Receives snapshot every N frames
   - Calls user-defined Python function
2. Example: Database write, file logging

**Python API**:
```python
def log_to_db(frame):
    db.insert({'timestamp': time.time(), 'data': frame})

pipeline = (PipelineBuilder()
    .add_fft()
    .add_magnitude()
    .add_callback(log_to_db, every_n_frames=100)  # Every 100th frame
    .build())
```

**Validation**:
- Test: Slow callback (100ms) doesn't block pipeline
- Test: Exception in callback doesn't crash executor
- Measure: Callback dispatch overhead <5µs

**Risk**: Medium - thread pool management

---

### Phase 4: Scientific Validation (Paper Defense) - v1.0

**Goal**: Prove the claims with rigorous experiments
**Duration**: 2-3 weeks
**Prevents regression**: All features implemented; now validate they work as claimed

#### Task 4.1: Custom Stage Overhead Benchmark
**File**: `benchmarks/custom_stage_overhead.py` (new)
**Action**:
1. Compare pipelines:
   - Baseline: Window → FFT → Magnitude (built-in)
   - Custom: Window → FFT → **Custom Magnitude (Numba)** → (verify same result)
2. Measure latency difference
3. **Success metric**: <10µs overhead

**Expected results**:
- Built-in pipeline: ~85µs (after v0.9.6 optimization)
- Custom pipeline: <95µs
- Overhead: <10µs (12% increase acceptable)

**Validation**:
- Run 5000 iterations with GPU clocks locked
- Report: mean, p50, p95, p99
- Confidence interval: 95%

#### Task 4.2: Real-Time Factor (RTF) Validation
**File**: `benchmarks/run_realtime.py` (enhance existing)
**Action**:
1. Run ionosphere workloads (NFFT 2048-8192, 2-8 channels)
2. Measure RTF for each configuration
3. **Success metric**: RTF < 0.3 for primary configs

**Test matrix**:
| NFFT | Channels | Overlap | Target RTF | Expected Latency |
|------|----------|---------|------------|------------------|
| 2048 | 2 | 0.75 | <0.3 | <77µs |
| 4096 | 2 | 0.75 | <0.3 | <96µs |
| 8192 | 2 | 0.75 | <0.3 | <134µs |
| 4096 | 8 | 0.75 | <0.3 | <120µs |

**Validation**:
- 10 second streams for each config
- Report: mean RTF, p99 RTF, deadline compliance
- Plot: RTF vs NFFT (scaling analysis)

#### Task 4.3: Long-Duration Stress Test
**File**: `benchmarks/stress_test.py` (new)
**Action**:
1. Run streaming executor for 1 hour minimum (target: 24 hours)
2. Monitor: buffer overflows, memory leaks, deadline misses
3. Record: temperature, GPU clocks, RTF over time
4. **Success metric**: Zero overflows, stable RTF (CV < 10%)

**Validation**:
- Ionosphere realtime config (NFFT=4096, 2 channels)
- Log metrics every 60 seconds
- Plot: RTF vs time, temperature vs time
- Verify: No degradation after thermal steady-state

#### Task 4.4: CuPy Comparison Benchmark
**File**: `benchmarks/cupy_comparison.py` (new)
**Action**:
1. Implement equivalent pipeline in CuPy:
   ```python
   import cupy as cp
   # Window → FFT → Magnitude
   windowed = signal * cp.hanning(nfft)
   fft_out = cp.fft.rfft(windowed)
   magnitude = cp.abs(fft_out)
   ```
2. Compare throughput (batch mode)
3. Compare latency (streaming mode)
4. **Success metric**:
   - Batch: SigTekX ≥ 0.9× CuPy (within 10%)
   - Streaming: SigTekX > 2× CuPy (real-time advantage)

**Expected results**:
- Batch: Similar performance (both use cuFFT)
- Streaming: SigTekX wins (zero-copy ring buffers, async)

#### Task 4.5: PyTorch Integration Test
**File**: `experiments/pytorch_denoiser.py` (new)
**Action**:
1. Train simple denoiser model (1D CNN)
2. Insert in pipeline: FFT → Denoiser → Magnitude
3. Measure inference time
4. **Success metric**: Inline if <50µs, else snapshot mode

**Validation**:
- Compare accuracy: with/without denoiser
- Measure latency: built-in vs PyTorch pipeline
- Verify: No accuracy degradation

---

## Metrics for Paper Defense

### Performance Metrics (Table 1 in Paper)

| Metric | Target | Measurement Method | Config |
|--------|--------|-------------------|--------|
| **Latency (mean)** | <100µs | LatencyBenchmark, GPU events | NFFT=4096, 2ch, 0.75 overlap |
| **Latency (p99)** | <150µs | LatencyBenchmark | Same |
| **RTF** | <0.3 | RealtimeBenchmark | Multiple NFFT/channels |
| **Throughput** | >5000 FPS | ThroughputBenchmark | NFFT=4096, 2ch |
| **Custom stage overhead** | <10µs | Custom benchmark | Numba magnitude stage |
| **Jitter (CV)** | <10% | RealtimeBenchmark, GPU clocks locked | Streaming mode |
| **Deadline compliance** | >99% | RealtimeBenchmark | 10s stream |
| **Accuracy (SNR)** | >60dB | AccuracyBenchmark | vs scipy double precision |

### Scalability Metrics (Figure 2 in Paper)

**Plot**: RTF vs NFFT (2048, 4096, 8192, 16384)
**Expected**: Linear scaling, all <0.3 RTF
**Config**: 2 channels, 0.75 overlap, streaming mode

**Plot**: RTF vs Channels (2, 4, 8, 16)
**Expected**: Sub-linear scaling (GPU parallelism)
**Config**: NFFT=4096, 0.75 overlap

### Comparison Metrics (Table 2 in Paper)

| Solution | Throughput (FPS) | Latency (µs) | RTF | Custom Stages | Real-Time |
|----------|------------------|--------------|-----|---------------|-----------|
| **SigTekX** | 5000+ | <100 | <0.3 | ✅ Python/Numba | ✅ Continuous |
| CuPy | 6000+ | ~150 | 0.5 | ❌ No pipeline | ❌ Batch only |
| NumPy | 50 | N/A | 40 | ❌ | ❌ CPU only |
| FPGA/VHDL | 10000+ | <10 | <0.01 | ❌ Months | ✅ Hard RT |

### Memory Metrics (Table 3 in Paper)

| Buffer | Size (NFFT=4096, 2ch) | Purpose |
|--------|----------------------|---------|
| Ring buffers | 98 KB | Lock-free input staging |
| Device input | 32 KB × 2 | Round-robin GPU buffers |
| Device output | 16 KB × 2 | Round-robin GPU buffers |
| Snapshot | 16 KB | Control plane tap |
| **Total** | ~210 KB | Minimal footprint |

---

## Experiments for Paper Defense

### Experiment 1: Ionosphere Real-Time Performance
**Goal**: Validate RTF < 0.3 for target application

**Setup**:
- Configs: ionosphere_realtime, ionosphere_hires
- Duration: 10 seconds per run, 5 runs
- Hardware: RTX 3090 Ti (desktop primary)

**Procedure**:
1. Run `python benchmarks/run_realtime.py experiment=ionosphere_realtime +benchmark=realtime`
2. Collect: RTF, deadline compliance, jitter
3. Generate plots: RTF vs time, latency distribution

**Success criteria**:
- Mean RTF < 0.3 for all configs
- p99 RTF < 0.4
- Deadline compliance > 99%

**When to run**: After Phase 1 (baseline), after Phase 2 (with custom stages)

### Experiment 2: Custom Stage Overhead Isolation
**Goal**: Prove custom stages add <10µs overhead

**Setup**:
- Pipeline A: Built-in stages only
- Pipeline B: Replace magnitude with Numba custom
- Iterations: 5000, GPU clocks locked

**Procedure**:
1. Run baseline: `python benchmarks/run_latency.py experiment=baseline +benchmark=latency`
2. Run custom: `python benchmarks/custom_stage_overhead.py`
3. Compare latency distributions

**Success criteria**:
- Mean overhead < 10µs
- p99 overhead < 15µs
- Accuracy identical (SNR > 60dB)

**When to run**: After Phase 2 (custom stages implemented)

### Experiment 3: Long-Duration Stability
**Goal**: Prove no degradation over time (thermal, memory)

**Setup**:
- Duration: 1 hour (target 24 hours if time permits)
- Config: ionosphere_realtime
- Monitoring: GPU temp, clocks, RTF every 60s

**Procedure**:
1. Run `python benchmarks/stress_test.py --duration 3600`
2. Log metrics to MLflow
3. Plot: RTF vs time, temperature vs time

**Success criteria**:
- Zero buffer overflows
- RTF CV < 10% (stable)
- No memory leaks (constant memory usage)
- Performance stable after thermal steady-state (~10 min)

**When to run**: After Phase 3 (full pipeline stable)

### Experiment 4: CuPy Competitive Analysis
**Goal**: Show SigTekX is competitive for batch, superior for streaming

**Setup**:
- Batch mode: SigTekX BatchExecutor vs CuPy
- Streaming mode: SigTekX StreamingExecutor vs CuPy (if possible)
- NFFT: 4096, channels: 2

**Procedure**:
1. Implement equivalent CuPy pipeline
2. Benchmark both: throughput, latency
3. Compare results

**Success criteria**:
- Batch: SigTekX ≥ 90% of CuPy throughput
- Streaming: SigTekX demonstrates continuous processing (CuPy cannot)

**When to run**: After Phase 1 (fair comparison)

### Experiment 5: PyTorch Model Integration
**Goal**: Demonstrate hybrid compute (ML in pipeline)

**Setup**:
- Model: Simple 1D CNN denoiser (trained on synthetic data)
- Pipeline: FFT → Denoiser → Magnitude
- Measure: Inference time, accuracy

**Procedure**:
1. Train model: `python experiments/train_denoiser.py`
2. Benchmark pipeline: `python experiments/pytorch_denoiser.py`
3. Compare: with/without denoiser

**Success criteria**:
- Inference time <50µs (inline) OR snapshot mode works
- Accuracy improvement measurable (SNR +3dB)
- RTF still <0.3 (doesn't break real-time)

**When to run**: After Phase 2 (PyTorch integration complete)

### Experiment 6: Scaling Analysis
**Goal**: Characterize performance across parameter space

**Setup**:
- NFFT sweep: 1024, 2048, 4096, 8192, 16384
- Channel sweep: 1, 2, 4, 8, 16
- Generate heatmap: RTF(NFFT, channels)

**Procedure**:
1. Run `python benchmarks/run_throughput.py --multirun experiment=ionosphere_nfft_channels_grid +benchmark=throughput`
2. Analyze: `python experiments/analysis/scaling.py`
3. Generate figure for paper

**Success criteria**:
- Identify "sweet spot" (max NFFT × channels while RTF < 0.3)
- Linear scaling with NFFT (expected)
- Sub-linear scaling with channels (GPU parallelism)

**When to run**: After Phase 1 (baseline scaling)

---

## Target Hardware Considerations

### Primary Development Platform (Phase 1-3)
**Hardware**: Desktop RTX 3090 Ti
**Justification**:
- Personal dev machine
- High performance for validation
- 24 GB VRAM (headroom for large models)

**Optimizations**:
- GPU clock locking for stable benchmarks
- PCIe Gen4 for bandwidth
- Focus on latency over power efficiency

### Secondary Platform (Phase 2-3, parallel development)
**Hardware**: Laptop RTX 4000 Ada
**Justification**:
- Target deployment for antenna system
- Mobile/field research
- Power-constrained (65-115W TDP)

**Optimizations**:
- Power budget aware (adaptive NFFT based on thermal state)
- Battery life considerations
- Validate RTF targets hold under thermal throttling

### Future Platform (Phase 4+, post-paper)
**Hardware**: NVIDIA Jetson (Orin, Xavier)
**Justification**:
- Remote deployment (embedded antenna system)
- ARM architecture (aarch64)
- Extreme power constraint (15-30W)

**Challenges**:
- Cross-compilation required
- Limited memory (8-32 GB shared)
- Thermal throttling aggressive
- May require reduced NFFT or channels

**Strategy**: Validate architecture on desktop/laptop first, then port to Jetson with adaptive performance targets.

---

## Development Timeline Strategy

**Philosophy**: Sprint development, no hard deadlines, but aim for 1-4 months total.

### Suggested Sequencing

**Weeks 1-2**: Phase 1 (Foundation)
- Zero-copy optimization
- Per-stage timing
- Baseline benchmarks

**Weeks 3-6**: Phase 2 (Custom Stages - THE CORE)
- CustomStage C++ class
- Numba integration
- PyTorch integration
- Persistent state

**Weeks 7-9**: Phase 3 (Control Plane)
- Snapshot buffer
- Event queue
- Callback stages

**Weeks 10-12**: Phase 4 (Validation)
- Custom stage overhead experiment
- RTF validation
- Long-duration stress test
- CuPy comparison
- PyTorch integration demo
- Scaling analysis

**Weeks 13-14**: Paper Writing
- Results compilation
- Figure generation (Streamlit + manual plots)
- Draft, review, submit

**Total**: ~3.5 months (14 weeks) - within target range

### Interleaving Experiments with Development

**Don't wait until the end** - run experiments incrementally:

| After Phase | Run Experiment | Purpose |
|-------------|----------------|---------|
| Phase 1 | Baseline RTF, scaling | Quantify improvement opportunity |
| Phase 2 | Custom stage overhead | Validate core novelty |
| Phase 2 | PyTorch integration | Validate hybrid compute |
| Phase 3 | Long-duration stress | Validate stability |
| Phase 4 | CuPy comparison | Competitive positioning |
| Phase 4 | Full scaling analysis | Paper Figure 2 |

**Benefit**: Early experiments guide optimization priorities, prevent late surprises.

---

## Publication Strategy and Venues

**Objective**: Convert roadmap milestones into citable artifacts while maintaining IEEE 1074 traceability. The plan deliberately staggers architecture, software, and domain-facing narratives so each submission reinforces the others.

| Venue | Focus | Deadline / Cadence | Gate Deliverables |
|-------|-------|--------------------|-------------------|
| [IEEE HPEC](https://ieee-hpec.org/call-for-papers/) | High-performance + embedded architectures | 14 Jul 2025 (extended “midnight AoE”) | Phase 1-4 benchmarks, split-plane diagrams, PCIe saturation metrics |
| [SC Workshops - PyHPC](https://sc24.supercomputing.org/program/workshops/) | Python in production HPC workflows | Align with SC camera-ready (~Sep) | Demo notebooks + control-plane decoupling story |
| [JOSS](https://github.com/openjournals/joss) | Open-source software quality (docs, CI, tests, DOI) | Rolling review (2–4 weeks typical) | Tagged v1.0 release, CLI walkthroughs, reproducible config snapshots |
| [Radio Science](https://en.wikipedia.org/wiki/Radio_Science) / [IEEE GRSL](https://www.ieeegrss.org/publications/geoscience-remote-sensing-letters/) | Applied geophysics / remote sensing letters | Rolling, but expect 8–12 week review loops | Ionosphere case study, anomaly catalog, field validation logs |

### Primary push — IEEE HPEC (architecture spotlight)
- HPEC’s Embedded HPC track explicitly calls for efficiency-focused architectures; the 2025 CFP emphasizes convergence of HPC and embedded deployments plus quantitative benchmarking, which mirrors the dual-plane story and the “95% PCIe saturation” proof point.
- Target content: zero-copy memory redesign, per-stage GPU timing, and the comparative latency/RTF plots produced at the end of Phase 4.
- Prep actions:
  1. Convert Phase 1–3 design notes into a 6-page IEEE format manuscript with NVTX timelines and CUDA occupancy charts.
  2. Capture deterministic benchmark scripts under `benchmarks/hpec/` so reviewers can replay the headline numbers.
  3. Schedule dry-run talks during Weeks 10-12 to rehearse the “Python vs FPGA” narrative for the embedded audience.

### Backup visibility — PyHPC workshop at SC
- PyHPC is the natural overflow channel if HPEC slots fill; the workshop focuses on taming Python overhead in HPC pipelines, which is exactly what the split-plane + Numba bridge demonstrates.
- Because SC workshops often request concise 4-page write-ups plus live demos, emphasize the control-plane snapshots, Streamlit dashboards, and CLI ergonomics.
- Prep actions:
  1. Record a short screencast of the pipeline builder + `iono check` CLI to play during the live demo.
  2. Trim the HPEC manuscript into a workshop version that foregrounds developer experience (Numba, PyTorch, callbacks).
  3. Packaged conda environment + `scripts/cli.ps1 demo` target to ensure on-site reproducibility.

### Software credit — JOSS (code publication)
- JOSS reviews the repository itself (docs, CI, tests) and mints a DOI immediately upon acceptance, providing long-lived credit for the engineering work independently of the methods paper.
- Submission sequencing: cut a v1.0.0 release right after HPEC acceptance notifications, when Phase 4 benchmarks and documentation are frozen.
- Prep actions:
  1. Assemble the lightweight `paper.md` with problem statement, statement of need, architecture overview, and example code blocks referencing the CLI workflow.
  2. Ensure CI mirrors the “iono check” target (ruff, mypy, pytest, clang-tidy presets) so JOSS reviewers can reproduce the green badge without manual steps.
  3. Link the documentation set (`README`, `PROJECT_STRUCTURE`, `docs/architecture/*`) inside the submission to satisfy JOSS’s documentation checklist.

### Domain validation — Radio Science or IEEE GRSL
- Radio Science welcomes remote sensing methods with rigorous propagation analysis, while IEEE GRSL targets short letters on geoscience remote sensing innovations; both require demonstrating that the architecture enabled new science (e.g., transient ionosphere captures that offline batch methods missed).
- Risk: these venues demand vetted field data, so defer submission until the long-duration stress tests, anomaly catalog, and domain-specific tolerances (SNR, false-alarm rates) are signed off by the science collaborators.
- Prep actions:
  1. Build a “mission data” appendix that inventories immutable raw captures, derived spectrograms, and MLflow metadata so reviewers can audit provenance.
  2. Explicitly compare SigTekX streaming results against a CuPy (batch) baseline to prove the “previously impossible” claim.
  3. Document tolerance/uncertainty modeling (IEEE 754 rounding, denormal handling) inside `docs/validation/ionosphere.md` for citation.

### Timeline coupling
- Weeks 10–12 in the development plan already align with HPEC drafting; keep that slot focused on architecture plots and editing cycles.
- Induct a short "publication retro" gate at the end of each phase to update tables, figures, and appendices while data is fresh, which reduces thrash when multiple submissions overlap.
- Maintain a shared `publications/` directory with checklists (LaTeX template, figure sources, reviewer feedback) so future venues inherit the same rigor with minimal overhead.

---

## Risk Mitigation

### Technical Risks

1. **Numba API instability**
   - **Risk**: Numba internals change, breaking kernel extraction
   - **Mitigation**: Pin Numba version (0.58+), document workarounds, fall back to CuPy RawKernel

2. **RTF < 0.3 not achievable**
   - **Risk**: Even with optimizations, can't hit target
   - **Mitigation**: Phase 1 baseline shows current gap (122→87µs = 35µs budget). Zero-copy saves 8µs, GPU-resident buffers save 17µs. Total: -25µs → 97µs latency. At 256µs hop duration (4096, 0.75), RTF = 97/256 = 0.38. Close! Further optimization: reduce NVTX overhead (5µs), pipeline fusion (10µs) → 82µs → RTF=0.32. Fallback: Adjust to RTF<0.4 target.

3. **PyTorch too slow for inline**
   - **Risk**: Model inference >100µs, breaks real-time
   - **Mitigation**: Use snapshot mode (control plane). Document: "Complex models offload to async path, simple models inline."

4. **Lock-free queue bugs**
   - **Risk**: Race conditions in event queue/snapshot buffer
   - **Mitigation**: Use battle-tested library (folly::MPMCQueue, boost::lockfree), extensive testing, ThreadSanitizer

### Schedule Risks

1. **Scope creep (too many custom stage types)**
   - **Risk**: Try to support every use case, never finish
   - **Mitigation**: Phase 2 focuses on 3 types only: Numba (fast), PyTorch (medium), Callback (slow). Enough to prove concept.

2. **Hardware unavailable (RTX 4000 Ada delay)**
   - **Risk**: Can't test laptop deployment
   - **Mitigation**: Desktop validation sufficient for v1.0 paper. Laptop/Jetson mentioned as "future work, architecture validated."

3. **Long-duration tests take too long**
   - **Risk**: 24hr stress test delays paper
   - **Mitigation**: 1hr test sufficient for v1.0, 24hr for journal extension

---

## Success Criteria for v1.0 Paper

### Must Have ✅
1. RTF < 0.3 for ionosphere realtime config (NFFT=4096, 2 channels)
2. Custom Numba stage working with <10µs overhead
3. PyTorch model integration (inline or snapshot)
4. Snapshot buffer for GUI updates (control plane decoupling)
5. Zero buffer overflows in 1hr stress test
6. Accuracy validation (SNR > 60dB vs scipy)
7. Desktop (RTX 3090 Ti) validation complete

### Nice to Have 🎯
1. RTF < 0.2 (extra headroom)
2. Laptop (RTX 4000 Ada) validation
3. 24hr stress test
4. CuPy benchmark showing 2× streaming advantage
5. GPU-resident ring buffers (v0.9.7 - major optimization)

### Future Work 📅
1. Jetson deployment
2. Multi-GPU scaling
3. Extended custom stage types (CuPy, custom C++ kernels)
4. Production hardening (error recovery, graceful degradation)
5. Weeks of continuous operation

---

## Critical Files Reference

### C++ Core (Phase 1-2)
- `cpp/include/sigtekx/core/processing_stage.hpp` - Stage interface, add persistent state
- `cpp/src/core/processing_stage.cpp` - CustomStage implementation
- `cpp/src/executors/streaming_executor.cpp` - Zero-copy, snapshot buffer
- `cpp/include/sigtekx/core/ring_buffer.hpp` - Lock-free ring buffer (already good)

### C++ Bindings (Phase 2)
- `cpp/bindings/bindings.cpp` - Expose CustomStage, stage metrics to Python

### Python API (Phase 2-3)
- `src/sigtekx/core/builder.py` - Add add_custom(), add_torch_model(), add_callback()
- `src/sigtekx/core/engine.py` - Add latest_frame, get_events() properties
- `src/sigtekx/stages/custom.py` (new) - NumbaStageAdapter
- `src/sigtekx/stages/pytorch.py` (new) - TorchStage wrapper
- `src/sigtekx/stages/callback.py` (new) - CallbackStage

### Benchmarks (Phase 1, 4)
- `benchmarks/run_latency.py` - Enable measure_components=true
- `benchmarks/custom_stage_overhead.py` (new) - Custom stage validation
- `benchmarks/stress_test.py` (new) - Long-duration validation
- `benchmarks/cupy_comparison.py` (new) - Competitive analysis

### Experiments (Phase 4)
- `experiments/pytorch_denoiser.py` (new) - PyTorch integration demo
- `experiments/analysis/scaling.py` - Scaling analysis for paper figures

### Documentation (Throughout)
- `docs/performance/zero-copy-optimization.md` (new) - Phase 1 design doc
- `docs/architecture/dual-plane-design.md` (new) - Phase 3 architecture
- `docs/api/custom-stages.md` (new) - User guide for custom stages

---

## Conclusion

This roadmap provides a **dependency-ordered** path to a novel methods paper:

1. **Phase 1** fixes the memory bottleneck (no point optimizing on top of inefficiency)
2. **Phase 2** adds the core novelty (custom stages - the main contribution)
3. **Phase 3** enables real-world use (async I/O, GUI, alerts)
4. **Phase 4** validates the claims (experiments interleaved throughout)

**Key insight**: The dual-plane architecture (data plane + control plane) is the **architectural innovation** that enables Python flexibility without sacrificing real-time performance.

**Competitive moat**: No other solution offers this combination:
- Python ease-of-use (vs FPGA/VHDL)
- Real-time continuous processing (vs NumPy/CuPy batch)
- Custom stages with minimal overhead (vs fixed-pipeline libraries)
- Accessible hardware (vs data center GPUs)

**Target contribution**: "SigTekX: A Python Framework for Soft Real-Time Signal Processing on Consumer GPUs"
