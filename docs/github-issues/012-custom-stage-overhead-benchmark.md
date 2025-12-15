# Validate Custom Stage Overhead <10µs with Numba Magnitude Stage (Phase 4 Task 4.1)

## Problem

We need to **prove the <10µs overhead claim** for custom stages. Without validation, the core novelty ("Python users can add CUDA kernels with minimal overhead") lacks scientific evidence for the methods paper.

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 4 Task 4.1):
- Compare built-in magnitude stage vs custom Numba magnitude stage
- Success metric: Overhead <10µs (latency difference)
- Critical for v1.0 paper: validates core performance claim
- Run 5000 iterations with locked GPU clocks

**Impact:**
- Cannot defend performance claims in paper reviews
- Core novelty unvalidated (custom stages may have unacceptable overhead)
- Missing key metric for Table 1 in methods paper

## Current Implementation

**No custom stage overhead benchmark exists.** Issue #006 (Numba integration) must be completed first.

## Proposed Solution

**Create benchmark comparing built-in vs custom Numba magnitude:**

```python
# benchmarks/custom_stage_overhead.py (NEW FILE)
"""
Benchmark custom stage overhead.

Compares built-in magnitude stage vs custom Numba magnitude stage.
Target: <10µs overhead for custom implementation.
"""

import time
import numpy as np
from numba import cuda
from sigtekx import PipelineBuilder, EngineConfig
from sigtekx.benchmarks.utils import lock_gpu_clocks, unlock_gpu_clocks

# Custom magnitude kernel (Numba)
@cuda.jit
def custom_magnitude_kernel(real, imag, output, n):
    """
    Compute magnitude from FFT output (custom Numba version).

    Args:
        real: Real component of FFT
        imag: Imaginary component of FFT
        output: Magnitude output
        n: Number of elements
    """
    i = cuda.grid(1)
    if i < n:
        r = real[i]
        im = imag[i]
        output[i] = cuda.sqrt(r * r + im * im)


def benchmark_built_in_pipeline(iterations=5000):
    """Benchmark built-in magnitude stage."""
    pipeline = (PipelineBuilder()
        .add_window('hann')
        .add_fft()
        .add_magnitude()  # Built-in implementation
        .build())

    config = EngineConfig(nfft=4096, channels=2, overlap=0.75)
    engine = Engine(config, pipeline)

    # Warmup
    for _ in range(100):
        engine.process_frame()

    # Benchmark
    latencies = []
    for _ in range(iterations):
        start = time.perf_counter()
        engine.process_frame()
        end = time.perf_counter()
        latencies.append((end - start) * 1e6)  # Convert to µs

    return np.array(latencies)


def benchmark_custom_pipeline(iterations=5000):
    """Benchmark custom Numba magnitude stage."""
    pipeline = (PipelineBuilder()
        .add_window('hann')
        .add_fft()
        .add_custom(custom_magnitude_kernel, grid=(128, 1, 1), block=(256, 1, 1))  # Custom!
        .build())

    config = EngineConfig(nfft=4096, channels=2, overlap=0.75)
    engine = Engine(config, pipeline)

    # Warmup
    for _ in range(100):
        engine.process_frame()

    # Benchmark
    latencies = []
    for _ in range(iterations):
        start = time.perf_counter()
        engine.process_frame()
        end = time.perf_counter()
        latencies.append((end - start) * 1e6)  # µs

    return np.array(latencies)


def main():
    """Run custom stage overhead benchmark."""
    print("=" * 80)
    print("Custom Stage Overhead Benchmark")
    print("=" * 80)
    print(f"Config: NFFT=4096, Channels=2, Overlap=0.75")
    print(f"Iterations: 5000")
    print()

    # Lock GPU clocks for stable measurements
    print("Locking GPU clocks...")
    lock_gpu_clocks()

    try:
        # Benchmark built-in
        print("Benchmarking built-in magnitude stage...")
        builtin_latencies = benchmark_built_in_pipeline()

        # Benchmark custom
        print("Benchmarking custom Numba magnitude stage...")
        custom_latencies = benchmark_custom_pipeline()

        # Compute statistics
        builtin_mean = np.mean(builtin_latencies)
        builtin_std = np.std(builtin_latencies)
        builtin_p50 = np.percentile(builtin_latencies, 50)
        builtin_p95 = np.percentile(builtin_latencies, 95)
        builtin_p99 = np.percentile(builtin_latencies, 99)

        custom_mean = np.mean(custom_latencies)
        custom_std = np.std(custom_latencies)
        custom_p50 = np.percentile(custom_latencies, 50)
        custom_p95 = np.percentile(custom_latencies, 95)
        custom_p99 = np.percentile(custom_latencies, 99)

        overhead_mean = custom_mean - builtin_mean
        overhead_p99 = custom_p99 - builtin_p99

        # Print results
        print()
        print("Results:")
        print("-" * 80)
        print(f"{'Metric':<20} {'Built-in (µs)':<15} {'Custom (µs)':<15} {'Overhead (µs)':<15}")
        print("-" * 80)
        print(f"{'Mean':<20} {builtin_mean:<15.2f} {custom_mean:<15.2f} {overhead_mean:<15.2f}")
        print(f"{'Std Dev':<20} {builtin_std:<15.2f} {custom_std:<15.2f} {'':<15}")
        print(f"{'p50':<20} {builtin_p50:<15.2f} {custom_p50:<15.2f} {'':<15}")
        print(f"{'p95':<20} {builtin_p95:<15.2f} {custom_p95:<15.2f} {'':<15}")
        print(f"{'p99':<20} {builtin_p99:<15.2f} {custom_p99:<15.2f} {overhead_p99:<15.2f}")
        print("-" * 80)
        print()

        # Verdict
        if overhead_mean < 10.0 and overhead_p99 < 15.0:
            print("✓ SUCCESS: Custom stage overhead < 10µs (target met)")
        elif overhead_mean < 15.0:
            print("⚠ ACCEPTABLE: Custom stage overhead < 15µs (close to target)")
        else:
            print("✗ FAILURE: Custom stage overhead > 15µs (optimization needed)")

    finally:
        # Unlock GPU clocks
        print("\nUnlocking GPU clocks...")
        unlock_gpu_clocks()


if __name__ == "__main__":
    main()
```

## Additional Technical Insights

- **Accuracy Validation**: Also verify custom magnitude produces same results as built-in (SNR > 60dB)

- **Locked GPU Clocks**: Use GPU clock locking (as in Issue #003) to reduce variability

- **Statistical Rigor**: 5000 iterations, report mean/p50/p95/p99 with confidence intervals

- **Grid/Block Tuning**: Custom kernel may need grid/block optimization to match built-in performance

## Implementation Tasks

- [ ] Create `benchmarks/custom_stage_overhead.py`
- [ ] Implement `custom_magnitude_kernel()` (Numba @cuda.jit)
- [ ] Implement `benchmark_built_in_pipeline()` (5000 iterations)
- [ ] Implement `benchmark_custom_pipeline()` (5000 iterations)
- [ ] Add statistical analysis (mean, std, percentiles)
- [ ] Add verdict logic (SUCCESS if <10µs, WARNING if <15µs, FAIL otherwise)
- [ ] Integrate GPU clock locking (import from utils)
- [ ] Add accuracy validation: compare outputs (SNR > 60dB)
- [ ] Run benchmark: `python benchmarks/custom_stage_overhead.py`
- [ ] Verify: Overhead < 10µs (if not, optimize custom kernel)
- [ ] Generate figure for paper: latency distribution histogram
- [ ] Update documentation: include results in `docs/performance/custom-stage-overhead.md`
- [ ] Commit: `feat(benchmarks): add custom stage overhead validation`

## Edge Cases to Handle

- **Kernel Not Optimized**: Custom kernel slower than built-in
  - Mitigation: Optimize grid/block dims, use shared memory if needed

- **First-Run Overhead**: JIT compilation on first launch
  - Mitigation: Warmup iterations (100) before benchmark

- **GPU Clock Variability**: Without clock locking, CV > 20%
  - Mitigation: Use locked clocks (requires admin on Windows)

## Testing Strategy

```bash
# Run benchmark
python benchmarks/custom_stage_overhead.py

# Expected output:
# Results:
# Metric               Built-in (µs)   Custom (µs)     Overhead (µs)
# ---------------------------------------------------------------------
# Mean                 85.23           92.45           7.22
# p99                  112.34          125.12          12.78
# ---------------------------------------------------------------------
# ✓ SUCCESS: Custom stage overhead < 10µs (target met)
```

## Acceptance Criteria

- [ ] `custom_magnitude_kernel()` implemented in Numba
- [ ] Benchmark script runs 5000 iterations for both pipelines
- [ ] Statistical analysis includes mean, p50, p95, p99
- [ ] Overhead < 10µs (mean) and < 15µs (p99)
- [ ] Accuracy validation: custom output matches built-in (SNR > 60dB)
- [ ] GPU clocks locked during benchmark
- [ ] Results table printed to console
- [ ] Figure generated for methods paper
- [ ] Documentation includes benchmark results

## Benefits

- **Core Claim Validated**: <10µs overhead proven with rigorous benchmark
- **Methods Paper Ready**: Table 1 metric for custom stage overhead
- **Performance Baseline**: Establishes expected overhead for custom stages
- **Debugging Tool**: Identifies performance regressions in custom stage path

---

**Labels:** `task`, `team-4-research`, `python`, `research`, `performance`

**Estimated Effort:** 4-6 hours (benchmark implementation, statistical analysis)

**Priority:** High (Critical for v1.0 paper metrics)

**Roadmap Phase:** Phase 4 (v1.0)

**Dependencies:** Issue #006 (Numba integration), Issue #004 (per-stage timing)

**Blocks:** None (validation task)
