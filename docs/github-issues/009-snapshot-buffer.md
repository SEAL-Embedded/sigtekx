# Add Snapshot Buffer for Async Control Plane Data Access (Phase 3 Task 3.1)

## Problem

There is **no way to retrieve latest frame without blocking the data plane**. GUI updates, plotting, and monitoring would stall the entire pipeline if they tried to read output directly. This prevents real-time operation with observability.

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 3 Task 3.1):
- Control plane decoupling: slow operations (GUI, I/O) don't block fast path (DSP)
- Snapshot buffer: copy latest frame every 16ms (60 Hz GUI updates)
- Lock-free read: `engine.latest_frame` property (non-blocking)
- Target overhead: <5µs for snapshot copy

**Impact:**
- Cannot build real-time GUIs (reading output blocks pipeline)
- Cannot update plots at 60 Hz without frame drops
- No way to monitor live data during experiments
- Control plane and data plane are coupled (anti-pattern for real-time systems)

## Current Implementation

**No snapshot mechanism exists.** User would need to:
1. Stop pipeline
2. Read output buffer
3. Restart pipeline

This breaks continuous streaming (defeats real-time purpose).

## Proposed Solution

**Add `PinnedHostBuffer` snapshot buffer with periodic async copy:**

```cpp
// cpp/src/executors/streaming_executor.cpp (ENHANCED)
class StreamingExecutor::Impl {
public:
    void process_frame() {
        // ... existing processing ...

        // Periodically copy to snapshot (every 16ms = 60 Hz)
        auto now = std::chrono::steady_clock::now();
        auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            now - last_snapshot_time_
        ).count();

        if (elapsed_ms >= snapshot_interval_ms_) {
            // Async copy to pinned host memory (non-blocking)
            CUDA_CHECK(cudaMemcpyAsync(
                snapshot_buffer_.data(),
                d_output_buffers_[ping_pong_idx_].data(),
                output_size_ * sizeof(float),
                cudaMemcpyDeviceToHost,
                snapshot_stream_  // Separate stream!
            ));

            last_snapshot_time_ = now;
        }
    }

    // Lock-free read (Python calls this)
    const float* get_latest_frame() const {
        // Sync snapshot stream (only waits for async copy, not data plane)
        CUDA_CHECK(cudaStreamSynchronize(snapshot_stream_));
        return snapshot_buffer_.data();
    }

private:
    PinnedHostBuffer<float> snapshot_buffer_;  // Host-side copy
    cudaStream_t snapshot_stream_;             // Separate stream for copies
    std::chrono::steady_clock::time_point last_snapshot_time_;
    int snapshot_interval_ms_ = 16;  // 60 Hz default
};
```

```python
# Python API (src/sigtekx/core/engine.py)
class Engine:
    # ... existing methods ...

    @property
    def latest_frame(self) -> np.ndarray:
        """
        Get latest output frame (non-blocking).

        Returns snapshot from most recent snapshot copy (60 Hz default).
        Safe to call from GUI thread while pipeline runs.

        Returns:
            np.ndarray: Latest frame (CPU memory)

        Example:
            >>> engine = Engine(config)
            >>> while True:
            >>>     frame = engine.latest_frame  # Non-blocking
            >>>     update_plot(frame)
            >>>     time.sleep(1/60)  # 60 Hz GUI
        """
        # C++ binding returns pointer to snapshot buffer
        return self._executor.get_latest_frame()
```

## Additional Technical Insights

- **Separate Stream**: Snapshot copy uses `snapshot_stream_`, not main processing stream. Prevents blocking data plane.

- **Pinned Memory**: `PinnedHostBuffer` enables async D2H copy (faster than pageable memory).

- **60 Hz Default**: 16ms interval matches typical GUI refresh rate. Configurable via `snapshot_interval_ms`.

- **Overhead**: Async copy takes ~5µs to launch, actual transfer overlaps with GPU compute (no blocking).

- **Sync Point**: `get_latest_frame()` syncs snapshot stream only (not data plane stream). User waits for copy, not processing.

- **Data Staleness**: Snapshot may be 1-2 frames behind (acceptable for GUI). For exact latest, user must sync data plane (blocking).

## Implementation Tasks

- [ ] Open `cpp/src/executors/streaming_executor.cpp`
- [ ] Add `snapshot_buffer_` member (`PinnedHostBuffer<float>`)
- [ ] Add `snapshot_stream_` member (`cudaStream_t`)
- [ ] Add `last_snapshot_time_` member (`std::chrono::steady_clock::time_point`)
- [ ] Add `snapshot_interval_ms_` member (int, default 16)
- [ ] In constructor: allocate `snapshot_buffer_`, create `snapshot_stream_`
- [ ] In `process_frame()`: add snapshot copy logic (if elapsed > interval)
- [ ] Implement `get_latest_frame()` method (sync snapshot stream, return pointer)
- [ ] In destructor: destroy `snapshot_stream_`
- [ ] Open `cpp/bindings/bindings.cpp`
- [ ] Expose `get_latest_frame()` to Python (returns numpy array)
- [ ] Open `src/sigtekx/core/engine.py`
- [ ] Add `@property latest_frame` (calls C++ binding)
- [ ] Create test: `tests/test_snapshot_buffer.py`
  - Test: Snapshot updates at 60 Hz
  - Test: `latest_frame` doesn't block pipeline
  - Test: Multiple reads return consistent data
- [ ] Measure overhead: <5µs for async copy
- [ ] Update documentation: `docs/api/control-plane.md`
- [ ] Build: `./scripts/cli.ps1 build`
- [ ] Test: `./scripts/cli.ps1 test cpp && ./scripts/cli.ps1 test python`
- [ ] Commit: `feat(executor): add snapshot buffer for async control plane access`

## Edge Cases to Handle

- **Snapshot Allocation Failure**: Out of pinned memory
  - Mitigation: PinnedHostBuffer throws on allocation failure (user handles OOM)

- **Stream Synchronization Overhead**: Sync may block if copy still in progress
  - Mitigation: Acceptable (user waits for copy, not processing). Document staleness.

- **High-Frequency Access**: Calling `latest_frame` at >1kHz may cause contention
  - Mitigation: Document recommended max poll rate (100-1000 Hz)

- **Snapshot During Shutdown**: Reading snapshot after executor destroyed
  - Mitigation: Check executor validity, return null or raise exception

## Testing Strategy

**Integration Test (Python):**

```python
# tests/test_snapshot_buffer.py
import time
import numpy as np
from sigtekx import Engine, EngineConfig

def test_snapshot_non_blocking():
    """Test that snapshot access doesn't block pipeline."""
    config = EngineConfig(nfft=4096, channels=2)
    engine = Engine(config)

    engine.start()

    # Read snapshots for 1 second
    frames_read = 0
    start_time = time.time()

    while time.time() - start_time < 1.0:
        frame = engine.latest_frame  # Non-blocking
        assert frame.shape == (2049,)  # RFFT output size
        frames_read += 1
        time.sleep(1/120)  # 120 Hz poll rate

    engine.stop()

    # Should read ~120 frames (some may be duplicates due to 60 Hz snapshot)
    assert frames_read >= 100

def test_snapshot_updates():
    """Test that snapshot updates over time."""
    engine = Engine(EngineConfig(nfft=4096))
    engine.start()

    frame1 = engine.latest_frame.copy()
    time.sleep(0.05)  # Wait 50ms (3 snapshot updates at 60 Hz)
    frame2 = engine.latest_frame.copy()

    # Frames should differ (different input data)
    assert not np.array_equal(frame1, frame2)

    engine.stop()
```

**Performance Validation:**

```bash
# Profile to verify no blocking
sxp nsys realtime
# Verify: cudaMemcpyAsync on snapshot_stream_, no sync on main stream
```

## Acceptance Criteria

- [ ] `snapshot_buffer_` allocated in `StreamingExecutor`
- [ ] `snapshot_stream_` created (separate from main stream)
- [ ] Snapshot copy executes every 16ms (or configured interval)
- [ ] `get_latest_frame()` exposed to Python
- [ ] `engine.latest_frame` property works (non-blocking)
- [ ] Test: Snapshot doesn't block pipeline (frame rate maintained)
- [ ] Test: Snapshot updates at expected rate (60 Hz)
- [ ] Overhead < 5µs (measured via profiling)
- [ ] Documentation includes GUI example
- [ ] All tests pass

## Benefits

- **Control Plane Decoupling**: GUI/plotting doesn't block DSP pipeline
- **60 Hz Observability**: Real-time monitoring without frame drops
- **Non-Blocking API**: `latest_frame` property is safe to call from any thread
- **Minimal Overhead**: <5µs async copy (doesn't impact RTF)
- **Foundation for Callbacks**: Enables Issue #011 (callback stages)
- **Production-Ready**: Matches real-time systems best practice (observer pattern)

---

**Labels:** `feature`, `team-1-cpp`, `team-3-python`, `c++`, `python`, `architecture`

**Estimated Effort:** 6-8 hours (stream management, async copy, Python binding)

**Priority:** High (Control Plane Foundation - Phase 3 Task 3.1)

**Roadmap Phase:** Phase 3 (v0.9.8)

**Dependencies:** Issue #003 (zero-copy optimization), Issue #004 (per-stage timing)

**Blocks:** Issue #010 (event queue), Issue #011 (callback stage)
