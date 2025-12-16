# Add Error Logging to MLflow Tracking

## Problem

When benchmark iterations fail, the `BaseBenchmark` class collects errors in an `errors` list but **never logs them to MLflow**. Only summary CSV files capture success metrics, causing partial iteration failures to be invisible in experiment tracking. This hides valuable diagnostic information about failure modes, flaky tests, and edge cases.

**Impact:**
- Failed iterations not tracked in MLflow UI
- No visibility into failure patterns across experiments
- Debugging requires manual log inspection
- Can't query for "experiments with >5% failure rate"
- Lost opportunity for automated anomaly detection

**Example Scenario:**
```python
# Benchmark runs 100 iterations
# 5 iterations fail due to intermittent CUDA error
# 95 iterations succeed

# Current behavior:
# - MLflow logs: mean_latency=42.3µs (from 95 successful iterations)
# - MLflow artifacts: summary.csv with aggregated stats
# - Errors list: 5 error messages ❌ NOT LOGGED TO MLFLOW

# User has no idea 5% of iterations failed!
```

## Current Implementation

**File:** `src/sigtekx/benchmarks/base.py` (lines 480-510)

```python
def run(self) -> BenchmarkResult:
    """Execute benchmark with warmup and error handling."""
    errors = []

    # Warmup phase
    for _ in range(self.config.warmup_iterations):
        try:
            self.execute()
        except Exception as e:
            logger.debug(f"Warmup iteration failed: {e}")
            # Warmup failures not counted

    # Measurement phase
    for i in range(self.config.iterations):
        try:
            self.execute()
        except Exception as e:
            errors.append(str(e))  # ❌ Stored but never logged to MLflow
            logger.warning(f"Iteration {i} failed: {e}")

    # Error threshold check
    if len(errors) > self.config.iterations * 0.1:
        raise RuntimeError(
            f"Too many failed iterations ({len(errors)}/{self.config.iterations})"
        )

    # Calculate statistics (from successful iterations only)
    stats = self.calculate_statistics()

    # ❌ Errors list not included in result or MLflow logging
    return BenchmarkResult(statistics=stats, metadata={...})
```

**File:** `benchmarks/run_latency.py` (lines 57-90)

```python
@hydra.main(...)
def main(cfg: DictConfig):
    with mlflow.start_run():
        # ... run benchmark ...
        result = benchmark.run()

        # Log metrics
        if 'latency_us' in result.statistics:
            stats = result.statistics['latency_us']
            mlflow.log_metric('mean_latency', stats.get('mean', 0))
            mlflow.log_metric('p99_latency', stats.get('p99', 0))
            # ... more metrics ...

        # ❌ result.errors not logged!
        # ❌ Failure count not logged!

        # Save artifacts
        mlflow.log_artifact(str(parquet_path))
        mlflow.log_artifact(str(summary_path))
```

**What's Missing:**

1. **Error count metric** - Number of failed iterations
2. **Failure rate metric** - Percentage of failures
3. **Error artifact** - Text file with error messages
4. **Per-error-type counts** - Breakdown by exception type

## Proposed Solution

Add error logging as MLflow metrics and artifacts in both `BaseBenchmark` and benchmark runner scripts.

### Solution Part 1: BaseBenchmark Error Tracking

**File:** `src/sigtekx/benchmarks/base.py`

**Add error metadata to BenchmarkResult:**

```python
# Around line 460 - Modify BenchmarkResult return
def run(self) -> BenchmarkResult:
    """Execute benchmark with warmup and error handling."""
    errors = []

    # ... existing warmup and measurement code ...

    # Calculate statistics
    stats = self.calculate_statistics()

    # ✅ NEW: Add error metadata to result
    error_metadata = {
        'total_errors': len(errors),
        'error_rate': len(errors) / self.config.iterations if self.config.iterations > 0 else 0,
        'error_messages': errors[:10],  # First 10 errors (don't overwhelm)
        'unique_error_types': list(set([type(e).__name__ for e in errors]))  # If errors are exceptions
    }

    # Merge error metadata into result metadata
    metadata = {
        **self._get_metadata(),
        **error_metadata
    }

    return BenchmarkResult(
        statistics=stats,
        metadata=metadata,
        raw_data=self.raw_data
    )
```

### Solution Part 2: MLflow Error Logging

**File:** `benchmarks/run_latency.py` (and similar for throughput/accuracy)

**Add error logging after benchmark run:**

```python
@hydra.main(...)
def main(cfg: DictConfig):
    with mlflow.start_run():
        # ... existing setup ...

        result = benchmark.run()

        # ✅ NEW: Log error metrics
        error_count = result.metadata.get('total_errors', 0)
        error_rate = result.metadata.get('error_rate', 0.0)

        mlflow.log_metric('error_count', error_count)
        mlflow.log_metric('error_rate', error_rate)

        if error_count > 0:
            # ✅ NEW: Save error log as artifact
            error_log_path = output_dir / "errors.txt"
            with open(error_log_path, 'w') as f:
                f.write(f"Total errors: {error_count}\n")
                f.write(f"Error rate: {error_rate:.2%}\n\n")
                f.write("Error messages:\n")
                for i, msg in enumerate(result.metadata.get('error_messages', []), 1):
                    f.write(f"{i}. {msg}\n")

            mlflow.log_artifact(str(error_log_path))

            # ✅ NEW: Log warning if error rate high
            if error_rate > 0.05:  # More than 5% failures
                logger.warning(
                    f"High error rate detected: {error_rate:.1%} "
                    f"({error_count}/{cfg.benchmark.iterations} iterations failed)"
                )

        # ... existing metric and artifact logging ...
```

### Solution Part 3: Error Type Breakdown (Optional Enhancement)

**For advanced diagnostics:**

```python
# In BaseBenchmark.run(), collect errors as exception objects
errors = []  # List of tuples: (exception_type, message)

try:
    self.execute()
except Exception as e:
    errors.append((type(e).__name__, str(e)))

# Later, create error type breakdown
from collections import Counter
error_types = Counter([err[0] for err in errors])

metadata['error_type_counts'] = dict(error_types)
# e.g., {'RuntimeError': 3, 'ValueError': 2}

# In run_*.py, log per-type metrics
for error_type, count in result.metadata.get('error_type_counts', {}).items():
    mlflow.log_metric(f'errors_{error_type}', count)
```

## Additional Technical Insights

### MLflow Metrics vs Artifacts

| Data Type | Storage | Queryable | Best For |
|-----------|---------|-----------|----------|
| **Metrics** | Numeric values in DB | ✅ Yes (e.g., `metrics.error_rate < 0.05`) | Aggregates, comparisons |
| **Artifacts** | Files in object store | ❌ No | Detailed logs, stack traces |
| **Params** | String key-values | ✅ Yes | Config values |

**Recommendation:**
- `error_count`, `error_rate` → **Metrics** (for querying)
- `errors.txt` → **Artifact** (for detailed inspection)
- Per-type counts → **Metrics** (`errors_RuntimeError`, etc.)

### MLflow UI Queries

After implementation, users can query:

```python
import mlflow

# Find experiments with high error rates
runs = mlflow.search_runs(
    filter_string="metrics.error_rate > 0.05",
    order_by=["metrics.error_rate DESC"]
)

# Find runs with specific error types
runs = mlflow.search_runs(
    filter_string="metrics.errors_RuntimeError > 0"
)

# Find perfect runs (no errors)
runs = mlflow.search_runs(
    filter_string="metrics.error_count = 0"
)
```

### Error Thresholding Strategy

**Current behavior (line 488-491):**
```python
if len(errors) > self.config.iterations * 0.1:
    raise RuntimeError(...)  # Fail if >10% errors
```

**Proposed enhancement:**
```python
if len(errors) > self.config.iterations * 0.1:
    # Log metrics BEFORE raising
    mlflow.log_metric('error_count', len(errors))
    mlflow.log_metric('error_rate', len(errors) / self.config.iterations)

    # Save error log
    # ... (as above) ...

    # Then fail
    raise RuntimeError(...)
```

This ensures failed runs still log error metrics to MLflow.

## Implementation Tasks

### Phase 1: BaseBenchmark Error Tracking
- [ ] Open `src/sigtekx/benchmarks/base.py`
- [ ] Modify `run()` method to collect error metadata
- [ ] Add `total_errors` to result metadata
- [ ] Add `error_rate` to result metadata
- [ ] Add `error_messages` (first 10) to result metadata
- [ ] Add `error_type_counts` (optional) to result metadata

### Phase 2: MLflow Error Logging (All Benchmarks)
- [ ] Open `benchmarks/run_latency.py`
- [ ] After `benchmark.run()`, extract error metadata
- [ ] Log `error_count` metric to MLflow
- [ ] Log `error_rate` metric to MLflow
- [ ] If errors > 0, create `errors.txt` artifact
- [ ] Log `errors.txt` to MLflow
- [ ] Add warning log if `error_rate > 0.05`
- [ ] Repeat for `benchmarks/run_throughput.py`
- [ ] Repeat for `benchmarks/run_accuracy.py`
- [ ] Repeat for `benchmarks/run_realtime.py`

### Phase 3: Testing
- [ ] Add unit test: `test_benchmark_error_metadata()`
- [ ] Add integration test: Inject failures, verify MLflow metrics
- [ ] Manually run benchmark with forced failures
- [ ] Verify `errors.txt` appears in MLflow UI artifacts
- [ ] Verify `error_count` and `error_rate` queryable in MLflow
- [ ] Commit: `feat(benchmarks): log error metrics and artifacts to MLflow`

## Edge Cases to Handle

- **No errors (success case):**
  - `error_count = 0`, `error_rate = 0.0`
  - No `errors.txt` artifact (don't create empty file)
  - ✓ Already handled by `if error_count > 0:` check

- **All iterations fail:**
  - Benchmark raises exception before returning result
  - Need to log errors **before** raising (see Error Thresholding above)
  - Use try-finally to ensure MLflow logging

- **Very long error messages:**
  - Limit to first 1000 characters per error
  - `error_messages.append(str(e)[:1000])`

- **Unicode in error messages:**
  - Open `errors.txt` with `encoding='utf-8'`
  - MLflow handles UTF-8 artifacts ✓

## Testing Strategy

### Unit Test (Add to `tests/test_benchmarks.py`)

```python
import pytest
from sigtekx.benchmarks.base import BaseBenchmark
from unittest.mock import MagicMock

def test_benchmark_error_metadata():
    """Test that benchmark collects error metadata."""
    # Create mock benchmark that fails 5 times
    benchmark = BaseBenchmark(config=...)
    benchmark.execute = MagicMock(side_effect=[
        None, None, None,  # 3 successes
        RuntimeError("Error 1"),
        RuntimeError("Error 2"),
        None,  # 1 success
        ValueError("Error 3"),
        None, None, None  # 3 successes
    ])

    result = benchmark.run()

    # Should have error metadata
    assert 'total_errors' in result.metadata
    assert result.metadata['total_errors'] == 3
    assert result.metadata['error_rate'] == 0.3  # 3/10

    # Should have error messages
    assert 'error_messages' in result.metadata
    assert len(result.metadata['error_messages']) == 3
```

### Integration Test (Manual with MLflow)

```bash
# Create test benchmark that fails 10% of iterations
cat > test_benchmark_errors.py << 'EOF'
import random
import mlflow
from sigtekx import Engine
import numpy as np

mlflow.set_experiment("test_error_logging")

with mlflow.start_run():
    engine = Engine(preset='default')
    engine.initialize()

    errors = []
    for i in range(100):
        try:
            if random.random() < 0.1:  # 10% failure rate
                raise RuntimeError(f"Simulated error {i}")

            # Successful iteration
            input_data = np.random.randn(2, 1024).astype(np.float32)
            output = engine.process(input_data)

        except Exception as e:
            errors.append(str(e))

    # Log error metrics (simulating fixed code)
    mlflow.log_metric('error_count', len(errors))
    mlflow.log_metric('error_rate', len(errors) / 100)

    # Log error artifact
    if errors:
        with open('errors.txt', 'w') as f:
            for msg in errors:
                f.write(f"{msg}\n")
        mlflow.log_artifact('errors.txt')

EOF

python test_benchmark_errors.py

# Check MLflow UI
mlflow ui

# Navigate to experiment "test_error_logging"
# Verify:
# - Metrics tab shows "error_count" ≈ 10
# - Metrics tab shows "error_rate" ≈ 0.1
# - Artifacts tab shows "errors.txt"
```

### Query Test (MLflow API)

```python
import mlflow

# Search for runs with errors
runs_with_errors = mlflow.search_runs(
    experiment_names=["test_error_logging"],
    filter_string="metrics.error_count > 0"
)

print(f"Runs with errors: {len(runs_with_errors)}")
print(runs_with_errors[['metrics.error_count', 'metrics.error_rate']])

# Expected output:
#    metrics.error_count  metrics.error_rate
# 0                 10.0                 0.1
```

## Acceptance Criteria

- [ ] `BaseBenchmark.run()` adds error metadata to result
- [ ] Error metadata includes: `total_errors`, `error_rate`, `error_messages`
- [ ] All benchmark runner scripts log `error_count` metric to MLflow
- [ ] All benchmark runner scripts log `error_rate` metric to MLflow
- [ ] `errors.txt` artifact created and logged when errors occur
- [ ] Warning logged if `error_rate > 0.05`
- [ ] Unit test `test_benchmark_error_metadata` passes
- [ ] Manual integration test shows errors in MLflow UI
- [ ] MLflow search query can filter by error metrics
- [ ] `errors.txt` contains first 10 error messages
- [ ] All existing benchmark tests pass (no regressions)

## Benefits

- **Failure Visibility:** Errors tracked in experiment history
- **Debugging Aid:** Error logs available in MLflow UI
- **Anomaly Detection:** Can query for high error rates
- **Production Monitoring:** Track reliability over time
- **Scientific Rigor:** Complete experimental record includes failures
- **Phase 1 Readiness:** Publication-quality experiment tracking

---

**Labels:** `feature`, `team-4-research`, `python`, `benchmarks`, `mlflow`

**Estimated Effort:** 2-3 hours (base + all runners + tests)

**Priority:** MEDIUM (improves diagnostics, not critical)

**Roadmap Phase:** Phase 0 (nice to have before Phase 1 experiments)

**Dependencies:** None

**Blocks:** None

**Related:** MLflow best practices, experiment tracking standards
