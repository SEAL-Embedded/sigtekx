# Add 1-Hour Stress Test for Stability Validation (Phase 4 Task 4.3)

## Problem

Current tests run for **maximum 10 seconds** - there is no validation of long-term stability (buffer overflows, memory leaks, thermal throttling). Cannot claim "production-ready real-time" without hours-long stress testing.

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 4 Task 4.3):
- Run streaming executor for 1 hour minimum (target: 24 hours)
- Monitor: buffer overflows, memory leaks, deadline misses
- Record: temperature, GPU clocks, RTF over time
- Success: Zero overflows, stable RTF (CV < 10%)

**Impact:**
- Cannot claim stability for continuous operation
- Unknown: memory leaks, thermal steady-state, long-duration reliability
- Missing validation for production deployment (antenna system runs 24/7)

## Current Implementation

**No long-duration stress test exists.** Longest test: 10 seconds (Issue #013).

## Proposed Solution

**Create 1-hour stress test with continuous monitoring:**

```python
# benchmarks/stress_test.py (NEW FILE)
"""
Long-duration stress test for stability validation.

Runs streaming executor for 1+ hours, monitors:
- Buffer overflows
- Memory usage
- RTF stability
- GPU temperature
- Deadline compliance
"""

import time
import argparse
import psutil
import numpy as np
import pynvml
from sigtekx import Engine, EngineConfig
from sigtekx.benchmarks.utils import lock_gpu_clocks, unlock_gpu_clocks


class StressTestMonitor:
    """Monitor system metrics during stress test."""

    def __init__(self, gpu_index=0):
        self.gpu_index = gpu_index

        # Initialize NVML (NVIDIA Management Library)
        pynvml.nvmlInit()
        self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)

        # Metrics storage
        self.rtf_samples = []
        self.memory_samples = []
        self.temp_samples = []
        self.clock_samples = []
        self.timestamps = []

    def record(self, rtf):
        """Record current system state."""
        # RTF
        self.rtf_samples.append(rtf)

        # Memory usage (GB)
        memory_info = psutil.virtual_memory()
        self.memory_samples.append(memory_info.used / 1e9)

        # GPU temperature (C)
        temp = pynvml.nvmlDeviceGetTemperature(
            self.gpu_handle, pynvml.NVML_TEMPERATURE_GPU
        )
        self.temp_samples.append(temp)

        # GPU clocks (MHz)
        clock = pynvml.nvmlDeviceGetClock(
            self.gpu_handle, pynvml.NVML_CLOCK_SM, pynvml.NVML_CLOCK_ID_CURRENT
        )
        self.clock_samples.append(clock)

        # Timestamp
        self.timestamps.append(time.time())

    def get_summary(self):
        """Get summary statistics."""
        return {
            'rtf_mean': np.mean(self.rtf_samples),
            'rtf_cv': np.std(self.rtf_samples) / np.mean(self.rtf_samples) * 100,
            'rtf_max': np.max(self.rtf_samples),
            'memory_mean_gb': np.mean(self.memory_samples),
            'memory_delta_gb': np.max(self.memory_samples) - np.min(self.memory_samples),
            'temp_mean_c': np.mean(self.temp_samples),
            'temp_max_c': np.max(self.temp_samples),
            'clock_mean_mhz': np.mean(self.clock_samples),
            'deadline_compliance_%': np.sum(np.array(self.rtf_samples) < 1.0) / len(self.rtf_samples) * 100
        }

    def shutdown(self):
        """Cleanup NVML."""
        pynvml.nvmlShutdown()


def run_stress_test(duration_hours=1.0, sample_interval_s=60):
    """
    Run long-duration stress test.

    Args:
        duration_hours: Test duration in hours
        sample_interval_s: Metric sampling interval in seconds
    """
    print("=" * 80)
    print(f"Stress Test: {duration_hours} hour(s)")
    print("=" * 80)
    print(f"Config: Ionosphere realtime (NFFT=4096, 2 channels, 0.75 overlap)")
    print(f"Sampling interval: {sample_interval_s}s")
    print()

    # Lock GPU clocks
    print("Locking GPU clocks...")
    lock_gpu_clocks()

    # Create engine
    config = EngineConfig(nfft=4096, channels=2, overlap=0.75, mode='streaming')
    engine = Engine(config)
    monitor = StressTestMonitor()

    duration_s = duration_hours * 3600
    hop_size = int(config.nfft * (1 - config.overlap))
    sample_rate = 32000
    frame_period_s = hop_size / sample_rate

    start_time = time.time()
    last_sample_time = start_time
    frame_count = 0
    overflow_count = 0

    print("Starting stress test...")
    print()

    try:
        while time.time() - start_time < duration_s:
            # Process frame
            frame_start = time.perf_counter()
            result = engine.process_frame()
            frame_end = time.perf_counter()

            # Check for buffer overflow (if result indicates error)
            if result.get('overflow', False):
                overflow_count += 1

            # Calculate RTF
            frame_latency_s = frame_end - frame_start
            rtf = frame_latency_s / frame_period_s

            # Sample metrics every interval
            if time.time() - last_sample_time >= sample_interval_s:
                monitor.record(rtf)
                last_sample_time = time.time()

                # Print progress
                elapsed_h = (time.time() - start_time) / 3600
                summary = monitor.get_summary()
                print(f"[{elapsed_h:.2f}h] RTF: {summary['rtf_mean']:.3f} (CV: {summary['rtf_cv']:.1f}%), "
                      f"Temp: {summary['temp_mean_c']:.1f}°C, "
                      f"Memory: {summary['memory_mean_gb']:.1f} GB, "
                      f"Overflows: {overflow_count}")

            frame_count += 1

    except KeyboardInterrupt:
        print("\nTest interrupted by user")

    finally:
        # Cleanup
        elapsed = time.time() - start_time
        print()
        print("=" * 80)
        print("Stress Test Complete")
        print("=" * 80)

        summary = monitor.get_summary()
        print(f"Duration: {elapsed / 3600:.2f} hours ({frame_count} frames)")
        print(f"Buffer overflows: {overflow_count}")
        print()
        print("RTF Statistics:")
        print(f"  Mean: {summary['rtf_mean']:.4f}")
        print(f"  CV: {summary['rtf_cv']:.2f}%")
        print(f"  Max: {summary['rtf_max']:.4f}")
        print(f"  Deadline compliance: {summary['deadline_compliance_%']:.2f}%")
        print()
        print("System Statistics:")
        print(f"  Memory (mean): {summary['memory_mean_gb']:.2f} GB")
        print(f"  Memory (delta): {summary['memory_delta_gb']:.3f} GB")
        print(f"  Temperature (mean): {summary['temp_mean_c']:.1f}°C")
        print(f"  Temperature (max): {summary['temp_max_c']:.1f}°C")
        print(f"  GPU Clock (mean): {summary['clock_mean_mhz']:.0f} MHz")
        print()

        # Verdict
        if (overflow_count == 0 and
            summary['rtf_cv'] < 10.0 and
            summary['memory_delta_gb'] < 0.5 and
            summary['deadline_compliance_%'] > 99.0):
            print("✓ SUCCESS: Stable operation (no leaks, no overflows, RTF stable)")
        else:
            print("✗ FAILURE: Stability issues detected")
            if overflow_count > 0:
                print(f"  - Buffer overflows: {overflow_count}")
            if summary['rtf_cv'] >= 10.0:
                print(f"  - RTF unstable (CV={summary['rtf_cv']:.1f}% > 10%)")
            if summary['memory_delta_gb'] >= 0.5:
                print(f"  - Memory leak suspected (delta={summary['memory_delta_gb']:.2f} GB)")
            if summary['deadline_compliance_%'] <= 99.0:
                print(f"  - Deadline misses ({100-summary['deadline_compliance_%']:.2f}%)")

        # Cleanup
        monitor.shutdown()
        unlock_gpu_clocks()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SigTekX Long-Duration Stress Test")
    parser.add_argument("--duration", type=float, default=1.0, help="Duration in hours (default: 1.0)")
    parser.add_argument("--interval", type=int, default=60, help="Sampling interval in seconds (default: 60)")
    args = parser.parse_args()

    run_stress_test(duration_hours=args.duration, sample_interval_s=args.interval)
```

## Additional Technical Insights

- **Memory Leak Detection**: Track memory delta over time. Acceptable: <0.5 GB growth in 1 hour.

- **Thermal Steady-State**: First 10 minutes: temp rises, then plateaus. Monitor mean temp after 10min.

- **RTF Stability**: CV (coefficient of variation) < 10% indicates stable performance.

- **GPU Clock Stability**: With locked clocks, should be constant. Variations indicate driver issues.

## Implementation Tasks

- [ ] Create `benchmarks/stress_test.py`
- [ ] Implement `StressTestMonitor` class (NVML, psutil)
- [ ] Implement `run_stress_test()` main loop
- [ ] Add metrics: RTF, memory, temperature, clocks, overflows
- [ ] Add sampling every 60 seconds (configurable)
- [ ] Add progress printing (every sample)
- [ ] Add verdict logic (no overflows, CV < 10%, memory delta < 0.5GB)
- [ ] Add `--duration` and `--interval` CLI args
- [ ] Add requirements: `pynvml`, `psutil` to `pyproject.toml`
- [ ] Run 1-hour test: `python benchmarks/stress_test.py --duration 1.0`
- [ ] Verify: No overflows, stable RTF
- [ ] Generate plots: RTF vs time, temp vs time, memory vs time
- [ ] (Optional) Run 24-hour test for extended validation
- [ ] Update documentation: `docs/performance/stress-test-results.md`
- [ ] Commit: `feat(benchmarks): add long-duration stress test`

## Edge Cases to Handle

- **Keyboard Interrupt**: User stops test early
  - Mitigation: Catch `KeyboardInterrupt`, print partial results

- **GPU Clock Unlock Failure**: If script crashes, clocks stay locked
  - Mitigation: Use `try/finally` to ensure unlock

- **NVML Unavailable**: On non-NVIDIA systems
  - Mitigation: Graceful fallback, skip GPU metrics

## Testing Strategy

```bash
# Quick validation (10 minutes)
python benchmarks/stress_test.py --duration 0.17  # 10 minutes

# 1-hour stress test
python benchmarks/stress_test.py --duration 1.0

# 24-hour stress test (optional, for paper supplement)
python benchmarks/stress_test.py --duration 24.0

# Expected output (1 hour):
# [1.00h] RTF: 0.27 (CV: 8.2%), Temp: 68.5°C, Memory: 12.3 GB, Overflows: 0
# ✓ SUCCESS: Stable operation (no leaks, no overflows, RTF stable)
```

## Acceptance Criteria

- [ ] `StressTestMonitor` class implemented
- [ ] Tracks RTF, memory, temperature, GPU clocks
- [ ] Runs for 1 hour minimum
- [ ] Samples metrics every 60 seconds
- [ ] Prints progress every sample
- [ ] Zero buffer overflows
- [ ] RTF CV < 10%
- [ ] Memory delta < 0.5 GB
- [ ] Deadline compliance > 99%
- [ ] Plots generated: RTF/temp/memory vs time
- [ ] Documentation includes stress test results

## Benefits

- **Stability Validated**: Proven continuous operation for hours
- **Memory Leak Detection**: Identifies leaks before production deployment
- **Thermal Characterization**: Understand steady-state temperature behavior
- **Production Confidence**: Validates 24/7 antenna system deployment
- **Methods Paper**: Demonstrates reliability for real-time claim

---

**Labels:** `task`, `team-4-research`, `research`, `reliability`

**Estimated Effort:** 4-6 hours (implement + 1hr test runtime)

**Priority:** Medium (Important for production, not critical for v1.0 paper)

**Roadmap Phase:** Phase 4 (v1.0)

**Dependencies:** Issue #009 (snapshot buffer), Issue #013 (RTF validation)

**Blocks:** None (validation task)
