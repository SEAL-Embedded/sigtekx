# Implement CallbackStage with Thread Pool for Python I/O (Phase 3 Task 3.3)

## Problem

There is **no way to run slow Python callbacks** (database writes, API calls, file logging) without blocking the pipeline. User-defined I/O operations would stall the data plane if executed inline.

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 3 Task 3.3):
- CallbackStage: run Python functions in separate thread pool
- Receives snapshot every N frames (configurable decimation)
- Examples: database insert, file write, Slack API call
- Target: Dispatch overhead <5µs

**Impact:**
- Cannot log data to database without blocking pipeline
- Cannot save frames to disk during continuous operation
- No way to call external APIs (Slack, webhooks) in real-time
- User must choose between observability and performance

## Current Implementation

**No callback mechanism exists.** User would need to:
1. Stop pipeline
2. Save data manually in Python
3. Restart pipeline

This breaks continuous streaming and misses transient events.

## Proposed Solution

**Create `CallbackStage` that runs Python functions in thread pool:**

```python
# src/sigtekx/stages/callback.py (NEW FILE)
"""Callback stage for async I/O operations."""

import threading
import queue
from typing import Callable, Optional
import numpy as np
from concurrent.futures import ThreadPoolExecutor

class CallbackStage:
    """
    Run Python callbacks asynchronously without blocking pipeline.

    Callbacks receive snapshot data every N frames and execute in thread pool.
    Suitable for slow I/O: database writes, API calls, file logging.

    Example:
        >>> def log_to_db(frame: np.ndarray):
        >>>     db.insert({'timestamp': time.time(), 'data': frame.tolist()})
        >>>
        >>> pipeline = (PipelineBuilder()
        >>>     .add_fft()
        >>>     .add_magnitude()
        >>>     .add_callback(log_to_db, every_n_frames=100)  # Every 100th frame
        >>>     .build())
    """

    def __init__(self,
                 callback_func: Callable[[np.ndarray], None],
                 every_n_frames: int = 1,
                 max_workers: int = 4):
        """
        Initialize callback stage.

        Args:
            callback_func: Python function(frame) -> None
            every_n_frames: Decimation factor (call every Nth frame)
            max_workers: Thread pool size (default: 4)
        """
        self.callback_func = callback_func
        self.every_n_frames = every_n_frames
        self.frame_counter = 0

        # Thread pool for async execution
        self.executor = ThreadPoolExecutor(max_workers=max_workers,
                                          thread_name_prefix="CallbackStage")

        # Track pending futures (for shutdown)
        self.futures = []

    def process(self, frame: np.ndarray):
        """
        Process frame (called from data plane).

        Submits callback to thread pool if frame counter matches decimation.

        Args:
            frame: Output from previous stage
        """
        self.frame_counter += 1

        if self.frame_counter % self.every_n_frames == 0:
            # Copy frame (async execution may outlive original)
            frame_copy = frame.copy()

            # Submit to thread pool (non-blocking)
            future = self.executor.submit(self._safe_callback, frame_copy)
            self.futures.append(future)

            # Prune completed futures (prevent unbounded growth)
            self.futures = [f for f in self.futures if not f.done()]

    def _safe_callback(self, frame: np.ndarray):
        """
        Execute callback with exception handling.

        Exceptions are logged but don't crash pipeline.
        """
        try:
            self.callback_func(frame)
        except Exception as e:
            # Log error (don't crash pipeline)
            print(f"CallbackStage error: {e}")
            # TODO: Emit event to error queue

    def shutdown(self):
        """
        Shutdown thread pool (wait for pending callbacks).

        Called when pipeline stops.
        """
        # Shutdown executor (wait for pending tasks)
        self.executor.shutdown(wait=True)

    def __repr__(self) -> str:
        return (f"CallbackStage(func={self.callback_func.__name__}, "
                f"every_n_frames={self.every_n_frames})")
```

```python
# src/sigtekx/core/builder.py (ENHANCED)
from sigtekx.stages.callback import CallbackStage

class PipelineBuilder:
    # ... existing methods ...

    def add_callback(self,
                     callback_func: Callable[[np.ndarray], None],
                     every_n_frames: int = 1,
                     max_workers: int = 4) -> Self:
        """
        Add Python callback stage for async I/O.

        Callback receives snapshot data every N frames, executes in thread pool.

        Args:
            callback_func: Function(frame) -> None to call
            every_n_frames: Call every Nth frame (default: 1)
            max_workers: Thread pool size (default: 4)

        Returns:
            Self for method chaining

        Example:
            >>> def save_to_file(frame):
            >>>     np.save(f'frame_{time.time()}.npy', frame)
            >>>
            >>> pipeline = (PipelineBuilder()
            >>>     .add_magnitude()
            >>>     .add_callback(save_to_file, every_n_frames=100)
            >>>     .build())
        """
        callback_stage = CallbackStage(callback_func, every_n_frames, max_workers)

        self._stages.append({
            'type': 'callback',
            'stage': callback_stage
        })

        return self
```

## Additional Technical Insights

- **Thread Pool**: Uses `ThreadPoolExecutor` for async execution. Default 4 workers handles typical I/O concurrency.

- **Decimation**: `every_n_frames` reduces callback frequency. Example: 5000 FPS → 50 FPS (every 100th frame) for slow I/O.

- **Frame Copy**: Snapshot copied before async execution (original may be overwritten by next frame).

- **Exception Handling**: Exceptions logged but don't crash pipeline (critical for production).

- **Graceful Shutdown**: `shutdown()` waits for pending callbacks before destroying executor.

- **Overhead**: Frame copy + future creation ≈ 5µs. Actual callback execution is async (doesn't block).

## Implementation Tasks

- [ ] Create `src/sigtekx/stages/callback.py`
- [ ] Implement `CallbackStage` class
- [ ] Implement `__init__()` (create thread pool)
- [ ] Implement `process()` (submit callback if frame % N == 0)
- [ ] Implement `_safe_callback()` (exception handling wrapper)
- [ ] Implement `shutdown()` (wait for pending tasks)
- [ ] Open `src/sigtekx/core/builder.py`
- [ ] Add `add_callback()` method to `PipelineBuilder`
- [ ] Update pipeline shutdown to call `callback_stage.shutdown()`
- [ ] Create test: `tests/test_callback_stage.py`
  - Test: Callback executes asynchronously
  - Test: Slow callback (100ms) doesn't block pipeline
  - Test: Exception in callback doesn't crash pipeline
  - Test: Decimation works (every_n_frames)
  - Test: Shutdown waits for pending callbacks
- [ ] Create example: `examples/callback_logging.py`
  - Database logging example
  - File save example
- [ ] Measure overhead: <5µs for dispatch
- [ ] Update documentation: `docs/api/callback-stages.md`
- [ ] Test: `./scripts/cli.ps1 test python`
- [ ] Commit: `feat(python): add CallbackStage for async I/O operations`

## Edge Cases to Handle

- **Slow Callback**: Callback takes >100ms to execute
  - Mitigation: Thread pool queues pending tasks, doesn't block data plane

- **Exception in Callback**: User function raises exception
  - Mitigation: `_safe_callback()` catches, logs, continues pipeline

- **Unbounded Futures**: Many callbacks pending, memory growth
  - Mitigation: Prune completed futures in `process()`, limit thread pool size

- **Shutdown During Callback**: Pipeline stops while callback running
  - Mitigation: `shutdown(wait=True)` blocks until callbacks finish

- **High Decimation**: `every_n_frames=1` at 5000 FPS = 5000 callbacks/sec
  - Mitigation: User responsibility to choose appropriate decimation

## Testing Strategy

**Integration Test (Python):**

```python
# tests/test_callback_stage.py
import time
import pytest
from sigtekx import PipelineBuilder

def test_callback_non_blocking():
    """Test that slow callback doesn't block pipeline."""
    callback_executed = []

    def slow_callback(frame):
        time.sleep(0.1)  # 100ms slow I/O
        callback_executed.append(len(frame))

    pipeline = (PipelineBuilder()
        .add_fft()
        .add_magnitude()
        .add_callback(slow_callback, every_n_frames=10)
        .build())

    # Process 100 frames (10 callbacks due to decimation)
    start_time = time.time()
    for _ in range(100):
        pipeline.process(np.random.randn(4096))
    elapsed = time.time() - start_time

    # Should take <1 second (not 10 seconds if blocking)
    assert elapsed < 1.0

    # Wait for callbacks to finish
    time.sleep(1.5)  # 10 * 100ms + margin

    assert len(callback_executed) == 10  # 100 frames / every_n_frames=10

def test_callback_exception_handling():
    """Test that exception in callback doesn't crash pipeline."""
    def failing_callback(frame):
        raise ValueError("Intentional error")

    pipeline = (PipelineBuilder()
        .add_magnitude()
        .add_callback(failing_callback, every_n_frames=1)
        .build())

    # Should not raise (exceptions caught)
    for _ in range(10):
        pipeline.process(np.random.randn(4096))

def test_decimation():
    """Test every_n_frames decimation."""
    callback_count = [0]

    def counting_callback(frame):
        callback_count[0] += 1

    pipeline = (PipelineBuilder()
        .add_magnitude()
        .add_callback(counting_callback, every_n_frames=5)
        .build())

    for _ in range(50):
        pipeline.process(np.random.randn(4096))

    time.sleep(0.1)  # Wait for async execution

    assert callback_count[0] == 10  # 50 frames / 5
```

## Acceptance Criteria

- [ ] `CallbackStage` class implemented
- [ ] Thread pool created in `__init__()`
- [ ] `process()` submits callback to pool (non-blocking)
- [ ] Decimation works (`every_n_frames`)
- [ ] Exception handling prevents crashes
- [ ] `shutdown()` waits for pending callbacks
- [ ] `PipelineBuilder.add_callback()` method works
- [ ] Test: Slow callback (100ms) doesn't block pipeline
- [ ] Test: Exception handling works
- [ ] Test: Decimation reduces callback frequency
- [ ] Overhead < 5µs for dispatch
- [ ] Documentation includes DB logging example
- [ ] All tests pass

## Benefits

- **Async I/O**: Database writes, API calls without blocking pipeline
- **Production Ready**: Exception handling prevents callback errors from crashing system
- **Configurable Frequency**: Decimation reduces overhead for slow I/O
- **Thread Safety**: Thread pool isolates I/O from data plane
- **Graceful Shutdown**: Waits for pending callbacks (no data loss)
- **Use Cases Enabled**: Real-time logging, alerting, continuous archival

---

**Labels:** `feature`, `team-3-python`, `python`, `architecture`

**Estimated Effort:** 6-8 hours (thread pool management, exception handling, testing)

**Priority:** Medium (Control Plane - Phase 3 Task 3.3)

**Roadmap Phase:** Phase 3 (v0.9.8)

**Dependencies:** Issue #009 (snapshot buffer), Issue #010 (event queue for error reporting)

**Blocks:** None (final Phase 3 task)
