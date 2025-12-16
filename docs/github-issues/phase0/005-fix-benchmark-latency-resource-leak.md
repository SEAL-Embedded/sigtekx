# Fix Resource Leak in benchmark_latency() Convenience Function

## Problem

The `benchmark_latency()` convenience function in `src/sigtekx/core/engine.py` does not use a context manager to ensure proper resource cleanup. If an exception occurs during benchmarking, the Engine's CUDA resources (device memory, streams, events) may not be properly released.

**Impact:**
- GPU memory leak if exception occurs during benchmark
- CUDA context not properly cleaned up
- Violates Python best practices for resource management
- Inconsistent with other convenience functions

**Affected Code Path:**
```python
def benchmark_latency(...):
    engine = Engine(preset=preset, **kwargs)  # Resources allocated
    # ... benchmark code that may raise ...
    engine.close()  # Only called if no exception ❌
```

**Failure Scenario:**
```python
import numpy as np
from sigtekx import benchmark_latency

# Create invalid input that will raise during processing
input_data = np.random.randn(10, 512).astype(np.float32)  # Wrong size

try:
    result = benchmark_latency(
        input_data=input_data,
        preset='default'  # Expects nfft=1024, got 512
    )
except ValueError:
    # Exception raised, but engine.close() never called
    # GPU memory leaked! ☠️
    pass
```

## Current Implementation

**File:** `src/sigtekx/core/engine.py` (lines 875-948)

```python
def benchmark_latency(
    input_data: FloatArray,
    preset: str = "default",
    iterations: int = 1000,
    warmup_iterations: int = 100,
    **kwargs: Any,
) -> dict[str, Any]:
    """Benchmark latency for a given configuration.

    Convenience function for quick latency measurements.

    Args:
        input_data: Input signal array [channels, samples]
        preset: Configuration preset name
        iterations: Number of benchmark iterations
        warmup_iterations: Number of warmup iterations
        **kwargs: Additional config overrides

    Returns:
        Dictionary with benchmark results
    """
    # ❌ RESOURCE LEAK: No context manager
    engine = Engine(preset=preset, **kwargs)

    # Warmup phase
    for _ in range(warmup_iterations):
        _ = engine.process(input_data)

    # Measurement phase
    latencies = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        result = engine.process(input_data)
        end = time.perf_counter_ns()
        latencies.append((end - start) / 1000.0)  # Convert to microseconds

    stats = {
        "mean_us": np.mean(latencies),
        "std_us": np.std(latencies),
        "min_us": np.min(latencies),
        "max_us": np.max(latencies),
        "p50_us": np.percentile(latencies, 50),
        "p95_us": np.percentile(latencies, 95),
        "p99_us": np.percentile(latencies, 99),
    }

    engine.close()  # ❌ Only called if no exception above
    return stats
```

**What's Wrong:**
1. `engine.close()` only called if no exception raised
2. If `engine.process()` throws, cleanup never happens
3. GPU memory and CUDA resources leaked
4. Violates RAII/context manager best practice

**Comparison with process_signal():**

The `process_signal()` function (lines 875-910) **correctly** uses context manager:
```python
def process_signal(...):
    with Engine(preset=preset, **kwargs) as engine:  # ✅ Proper cleanup
        result = engine.process(input_data)
    return result
```

## Proposed Solution

Refactor `benchmark_latency()` to use context manager pattern, ensuring cleanup always occurs.

### Fixed Implementation

```python
def benchmark_latency(
    input_data: FloatArray,
    preset: str = "default",
    iterations: int = 1000,
    warmup_iterations: int = 100,
    **kwargs: Any,
) -> dict[str, Any]:
    """Benchmark latency for a given configuration.

    Convenience function for quick latency measurements.

    Args:
        input_data: Input signal array [channels, samples]
        preset: Configuration preset name
        iterations: Number of benchmark iterations
        warmup_iterations: Number of warmup iterations
        **kwargs: Additional config overrides

    Returns:
        Dictionary with benchmark results

    Raises:
        ValueError: If input_data shape incompatible with config
        RuntimeError: If CUDA operations fail

    Example:
        >>> import numpy as np
        >>> from sigtekx import benchmark_latency
        >>> input_data = np.random.randn(2, 1024).astype(np.float32)
        >>> stats = benchmark_latency(input_data, preset='default')
        >>> print(f"Mean latency: {stats['mean_us']:.2f} µs")
    """
    # ✅ FIXED: Use context manager for automatic cleanup
    with Engine(preset=preset, **kwargs) as engine:
        # Warmup phase
        for _ in range(warmup_iterations):
            _ = engine.process(input_data)

        # Measurement phase
        latencies = []
        for _ in range(iterations):
            start = time.perf_counter_ns()
            result = engine.process(input_data)
            end = time.perf_counter_ns()
            latencies.append((end - start) / 1000.0)  # µs

        # Calculate statistics before context exit
        stats = {
            "mean_us": np.mean(latencies),
            "std_us": np.std(latencies),
            "min_us": np.min(latencies),
            "max_us": np.max(latencies),
            "p50_us": np.percentile(latencies, 50),
            "p95_us": np.percentile(latencies, 95),
            "p99_us": np.percentile(latencies, 99),
        }

    # Context manager ensures engine.__exit__() called here
    # Resources cleaned up even if exception occurred above
    return stats
```

## Additional Technical Insights

### Context Manager Protocol

The Engine class implements `__enter__` and `__exit__`:

```python
# engine.py lines 177-186
def __enter__(self) -> "Engine":
    """Context manager entry."""
    return self

def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc_val: BaseException | None,
    exc_tb: Any,
) -> None:
    """Context manager exit with guaranteed cleanup."""
    self.close()  # ✅ Always called, even on exception
```

**Guarantees:**
- `__exit__` called even if exception raised in `with` block
- GPU memory freed via `close()` → `reset()` → CUDA cleanup
- No resource leaks regardless of exception type

### Exception Propagation

Context manager does NOT suppress exceptions:
```python
def __exit__(self, exc_type, exc_val, exc_tb) -> None:
    self.close()
    # Return None → exception propagates to caller
```

Caller still receives original exception after cleanup.

### Resource Cleanup Order

When `close()` is called (lines 532-643 in engine.py):
1. Synchronize CUDA streams (line 557)
2. Destroy executor (line 561)
3. Track GPU memory state (lines 564-603)
4. Validate no memory leaks (lines 614-643)

All steps wrapped in try-except to ensure each cleanup attempt.

## Implementation Tasks

- [ ] Open `src/sigtekx/core/engine.py`
- [ ] Locate `benchmark_latency()` function (line 911)
- [ ] Replace `engine = Engine(...)` with `with Engine(...) as engine:` (line 938)
- [ ] Indent benchmark code block (lines 940-946) inside `with` statement
- [ ] Move `stats = {...}` calculation inside `with` block (before context exit)
- [ ] Remove explicit `engine.close()` call (line 947) - context manager handles it
- [ ] Verify proper indentation of `return stats` (outside `with` block)
- [ ] Add "Raises" section to docstring documenting exceptions
- [ ] Add docstring example showing typical usage
- [ ] Run Python tests to verify no regressions
- [ ] Add specific test for exception handling (see Testing Strategy)
- [ ] Commit: `fix(api): use context manager in benchmark_latency() for resource safety`

## Edge Cases to Handle

- **Exception during warmup:**
  - Context manager ensures cleanup ✓
  - Exception propagates to caller ✓

- **Exception during measurement:**
  - Partial `latencies` list discarded
  - Cleanup still happens ✓

- **Exception during stats calculation:**
  - `stats` dict never created
  - Cleanup still happens ✓

- **User Ctrl+C (KeyboardInterrupt):**
  - Context manager catches ALL exceptions
  - Cleanup happens, then KeyboardInterrupt propagates ✓

- **Empty iterations (iterations=0):**
  - `np.mean([])` raises warning but doesn't crash
  - Could add validation: `if iterations < 1: raise ValueError`

## Testing Strategy

### Unit Test (Add to `tests/test_engine.py`)

```python
import numpy as np
import pytest
from sigtekx import benchmark_latency
from sigtekx.exceptions import SigtekxConfigError

def test_benchmark_latency_resource_cleanup_on_exception():
    """Test that benchmark_latency cleans up resources even when exception occurs."""
    # Create input with wrong shape (will raise during processing)
    input_data = np.random.randn(2, 512).astype(np.float32)

    # This should raise due to size mismatch, but still cleanup
    with pytest.raises((ValueError, SigtekxConfigError)):
        benchmark_latency(
            input_data=input_data,
            preset='default',  # Expects nfft=1024, got 512
            iterations=10
        )

    # After exception, GPU memory should be released
    # (Can't easily test this directly, but no crash is good sign)
    # If resources leaked, subsequent tests would fail or slow down

def test_benchmark_latency_success_case():
    """Test that benchmark_latency works correctly in success case."""
    input_data = np.random.randn(2, 1024).astype(np.float32)

    stats = benchmark_latency(
        input_data=input_data,
        preset='default',
        iterations=100,
        warmup_iterations=10
    )

    # Verify all expected keys present
    assert 'mean_us' in stats
    assert 'std_us' in stats
    assert 'min_us' in stats
    assert 'max_us' in stats
    assert 'p50_us' in stats
    assert 'p95_us' in stats
    assert 'p99_us' in stats

    # Sanity check values
    assert stats['mean_us'] > 0
    assert stats['min_us'] <= stats['mean_us'] <= stats['max_us']
    assert stats['p50_us'] <= stats['p95_us'] <= stats['p99_us']

def test_benchmark_latency_with_overrides():
    """Test that config overrides work correctly."""
    input_data = np.random.randn(1, 2048).astype(np.float32)

    stats = benchmark_latency(
        input_data=input_data,
        preset='default',
        nfft=2048,  # Override default nfft
        channels=1,
        iterations=50
    )

    assert stats['mean_us'] > 0  # Should complete successfully
```

### Integration Test (Manual)

```python
# Test script: test_benchmark_leak.py
import numpy as np
import psutil
import os
from sigtekx import benchmark_latency

def get_gpu_memory_mb():
    """Get current GPU memory usage (requires nvidia-smi)."""
    import subprocess
    result = subprocess.run(
        ['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
        capture_output=True, text=True
    )
    return int(result.stdout.strip())

# Baseline memory
baseline_memory = get_gpu_memory_mb()
print(f"Baseline GPU memory: {baseline_memory} MB")

# Run benchmark 100 times with exceptions
for i in range(100):
    input_data = np.random.randn(2, 512).astype(np.float32)  # Wrong size

    try:
        benchmark_latency(input_data, preset='default', iterations=10)
    except Exception:
        pass  # Expected exception

# Check for memory leak
final_memory = get_gpu_memory_mb()
print(f"Final GPU memory: {final_memory} MB")
print(f"Memory delta: {final_memory - baseline_memory} MB")

assert final_memory - baseline_memory < 50, "GPU memory leaked!"
print("✅ No memory leak detected")
```

```bash
# Run manual test
python test_benchmark_leak.py

# Expected output:
# Baseline GPU memory: 234 MB
# Final GPU memory: 238 MB
# Memory delta: 4 MB
# ✅ No memory leak detected
```

## Acceptance Criteria

- [ ] `benchmark_latency()` uses `with Engine(...) as engine:` context manager
- [ ] All benchmark code indented inside `with` block
- [ ] Explicit `engine.close()` call removed
- [ ] `stats` calculation happens inside `with` block
- [ ] `return stats` outside `with` block (after cleanup)
- [ ] Docstring updated with "Raises" section
- [ ] Docstring includes usage example
- [ ] Unit test `test_benchmark_latency_resource_cleanup_on_exception` passes
- [ ] Unit test `test_benchmark_latency_success_case` passes
- [ ] Unit test `test_benchmark_latency_with_overrides` passes
- [ ] All existing Engine tests pass (no regressions)
- [ ] Manual memory leak test shows no significant increase
- [ ] Code review confirms context manager usage is correct

## Benefits

- **Guaranteed Cleanup:** GPU resources always freed, even on exception
- **Memory Safety:** No GPU memory leaks in error paths
- **Best Practices:** Follows Python context manager idiom
- **Consistency:** Matches `process_signal()` implementation pattern
- **User Confidence:** Safe to use in scripts without manual cleanup
- **Production Readiness:** Robust error handling for real-world usage

---

**Labels:** `bug`, `team-3-python`, `python`, `resource-management`

**Estimated Effort:** 30 minutes (simple refactor + tests)

**Priority:** MEDIUM-HIGH (reliability issue, easy fix)

**Roadmap Phase:** Phase 0 (prerequisite for safe Python API usage)

**Dependencies:** None

**Blocks:** None (but improves API reliability)
