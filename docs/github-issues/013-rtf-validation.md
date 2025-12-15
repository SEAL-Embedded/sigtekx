# Run RTF Validation Experiments Across Ionosphere Parameter Space (Phase 4 Task 4.2)

## Problem

We need to **prove RTF < 0.3** for primary ionosphere configurations. Without validation, the real-time performance claim lacks scientific evidence for the methods paper.

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 4 Task 4.2):
- Test matrix: NFFT 2048/4096/8192 × 2 channels, NFFT 4096 × 8 channels
- Target: RTF < 0.3 for all configs
- 10-second streams per config
- Critical for v1.0 paper: validates soft real-time claim

**Impact:**
- Cannot claim "RTF < 0.3" in paper without experimental proof
- Real-time performance unvalidated across parameter space
- Missing key metric for Table 1 and Figure 2 in methods paper

## Current Implementation

**File:** `benchmarks/run_realtime.py` exists but needs enhancement.

## Proposed Solution

**Enhance existing realtime benchmark with ionosphere validation sweep:**

```python
# benchmarks/run_realtime.py (ENHANCED)
"""Real-Time Factor (RTF) validation for ionosphere workloads."""

import hydra
from omegaconf import DictConfig
import numpy as np
from sigtekx import Engine, EngineConfig

@hydra.main(config_path="../experiments/conf", config_name="config", version_base="1.3")
def main(cfg: DictConfig):
    """
    Run RTF validation experiment.

    Test matrix:
    - NFFT: 2048, 4096, 8192
    - Channels: 2, 8
    - Overlap: 0.75
    - Duration: 10 seconds
    - Target: RTF < 0.3
    """
    # Extract config
    engine_cfg = cfg.engine
    benchmark_cfg = cfg.benchmark

    print("=" * 80)
    print(f"RTF Validation: NFFT={engine_cfg.nfft}, Channels={engine_cfg.channels}")
    print("=" * 80)

    # Lock GPU clocks for stable measurements
    if benchmark_cfg.lock_gpu_clocks:
        lock_gpu_clocks()

    try:
        # Create engine
        engine = Engine(EngineConfig(
            nfft=engine_cfg.nfft,
            channels=engine_cfg.channels,
            overlap=engine_cfg.overlap,
            mode=engine_cfg.mode
        ))

        # Run streaming for 10 seconds
        duration_s = benchmark_cfg.duration
        hop_size = int(engine_cfg.nfft * (1 - engine_cfg.overlap))
        sample_rate = 32000  # Ionosphere sampling rate
        frame_period_s = hop_size / sample_rate  # Time per frame

        rtf_samples = []
        frame_count = 0
        start_time = time.time()

        while time.time() - start_time < duration_s:
            # Measure frame latency
            frame_start = time.perf_counter()
            engine.process_frame()
            frame_end = time.perf_counter()

            frame_latency_s = frame_end - frame_start
            rtf = frame_latency_s / frame_period_s

            rtf_samples.append(rtf)
            frame_count += 1

        elapsed = time.time() - start_time

        # Compute statistics
        rtf_mean = np.mean(rtf_samples)
        rtf_std = np.std(rtf_samples)
        rtf_p50 = np.percentile(rtf_samples, 50)
        rtf_p95 = np.percentile(rtf_samples, 95)
        rtf_p99 = np.percentile(rtf_samples, 99)
        rtf_max = np.max(rtf_samples)

        # Deadline compliance (RTF < 1.0 = no frame drops)
        deadline_compliance = np.sum(np.array(rtf_samples) < 1.0) / len(rtf_samples) * 100

        # Print results
        print()
        print("Results:")
        print("-" * 80)
        print(f"{'Metric':<25} {'Value':<15}")
        print("-" * 80)
        print(f"{'Frames processed':<25} {frame_count:<15}")
        print(f"{'Duration (s)':<25} {elapsed:<15.2f}")
        print(f"{'RTF (mean)':<25} {rtf_mean:<15.4f}")
        print(f"{'RTF (std)':<25} {rtf_std:<15.4f}")
        print(f"{'RTF (p50)':<25} {rtf_p50:<15.4f}")
        print(f"{'RTF (p95)':<25} {rtf_p95:<15.4f}")
        print(f"{'RTF (p99)':<25} {rtf_p99:<15.4f}")
        print(f"{'RTF (max)':<25} {rtf_max:<15.4f}")
        print(f"{'Deadline compliance (%)':<25} {deadline_compliance:<15.2f}")
        print("-" * 80)
        print()

        # Verdict
        if rtf_mean < 0.3 and rtf_p99 < 0.4:
            print("✓ SUCCESS: RTF < 0.3 (target met)")
            status = "SUCCESS"
        elif rtf_mean < 0.4:
            print("⚠ ACCEPTABLE: RTF < 0.4 (close to target)")
            status = "ACCEPTABLE"
        else:
            print("✗ FAILURE: RTF > 0.4 (optimization needed)")
            status = "FAILURE"

        # Log to MLflow
        if cfg.get("mlflow_enabled", True):
            import mlflow
            mlflow.log_params({
                "nfft": engine_cfg.nfft,
                "channels": engine_cfg.channels,
                "overlap": engine_cfg.overlap,
                "duration": duration_s
            })
            mlflow.log_metrics({
                "rtf_mean": rtf_mean,
                "rtf_p50": rtf_p50,
                "rtf_p95": rtf_p95,
                "rtf_p99": rtf_p99,
                "deadline_compliance": deadline_compliance
            })
            mlflow.set_tag("status", status)

    finally:
        if benchmark_cfg.lock_gpu_clocks:
            unlock_gpu_clocks()


if __name__ == "__main__":
    main()
```

```yaml
# experiments/conf/experiment/rtf_validation_grid.yaml (NEW)
# RTF validation sweep across ionosphere parameter space

defaults:
  - override /engine: ionosphere_realtime

# Multirun sweep
engine:
  nfft: 2048, 4096, 8192  # Three resolutions
  channels: 2, 8           # Two channel counts
  overlap: 0.75            # Fixed overlap
  mode: streaming          # Real-time mode

benchmark:
  duration: 10             # 10 seconds per config
  lock_gpu_clocks: true    # Stable measurements
```

## Additional Technical Insights

- **RTF Definition**: RTF = frame_latency / frame_period. RTF < 1.0 = real-time, RTF < 0.3 = soft real-time with 3× safety margin

- **Frame Period Calculation**: frame_period = hop_size / sample_rate. Example: (1024 samples / 32000 Hz) = 32ms

- **Deadline Compliance**: % of frames with RTF < 1.0 (no drops). Target: >99%

- **Hydra Multirun**: Use `--multirun` to sweep parameter space automatically

## Implementation Tasks

- [ ] Open `benchmarks/run_realtime.py`
- [ ] Enhance with RTF calculation (frame_latency / frame_period)
- [ ] Add deadline compliance metric (% RTF < 1.0)
- [ ] Add MLflow logging (params, metrics, tags)
- [ ] Add verdict logic (SUCCESS < 0.3, ACCEPTABLE < 0.4)
- [ ] Create `experiments/conf/experiment/rtf_validation_grid.yaml`
- [ ] Define multirun sweep (NFFT × channels)
- [ ] Run experiment: `python benchmarks/run_realtime.py --multirun experiment=rtf_validation_grid +benchmark=realtime`
- [ ] Verify: All 4 configs pass (RTF < 0.3)
- [ ] Generate plots: RTF vs NFFT, RTF vs channels
- [ ] Update dashboard: add RTF tab with parameter sweep results
- [ ] Commit: `feat(benchmarks): add RTF validation across ionosphere parameter space`

## Edge Cases to Handle

- **Thermal Throttling**: GPU temperature affects RTF over time
  - Mitigation: 10-second duration captures steady-state thermal behavior

- **First-Frame Overhead**: Initialization may skew RTF
  - Mitigation: Discard first 100 frames from statistics

- **Buffer Overflows**: If RTF > 1.0, frames drop
  - Mitigation: Track deadline compliance, report as separate metric

## Testing Strategy

```bash
# Single config validation
python benchmarks/run_realtime.py experiment=ionosphere_realtime +benchmark=realtime

# Expected output:
# Metric                   Value
# -----------------------------------------------
# RTF (mean)               0.27
# RTF (p99)                0.35
# Deadline compliance (%)  100.00
# ✓ SUCCESS: RTF < 0.3 (target met)

# Full parameter sweep
python benchmarks/run_realtime.py --multirun experiment=rtf_validation_grid +benchmark=realtime

# Expected: 4 runs (2048/2ch, 4096/2ch, 8192/2ch, 4096/8ch), all SUCCESS
```

## Acceptance Criteria

- [ ] RTF calculation implemented (frame_latency / frame_period)
- [ ] Deadline compliance metric (% RTF < 1.0)
- [ ] Test matrix runs: NFFT 2048/4096/8192, channels 2/8
- [ ] All 4 configs achieve RTF < 0.3 (mean) and < 0.4 (p99)
- [ ] MLflow logging captures params and metrics
- [ ] Results table printed to console
- [ ] Plots generated: RTF vs NFFT, RTF vs channels
- [ ] Dashboard updated with RTF validation tab
- [ ] Documentation includes RTF results

## Benefits

- **Real-Time Claim Validated**: RTF < 0.3 proven across ionosphere parameter space
- **Methods Paper Ready**: Table 1 metrics, Figure 2 (RTF vs NFFT plot)
- **Performance Baseline**: Establishes RTF targets for future optimizations
- **Continuous Monitoring**: MLflow tracking enables regression detection

---

**Labels:** `task`, `team-4-research`, `research`, `performance`

**Estimated Effort:** 3-4 hours (enhance benchmark, run experiments, generate plots)

**Priority:** High (Critical for v1.0 paper metrics)

**Roadmap Phase:** Phase 4 (v1.0)

**Dependencies:** Issue #003 (zero-copy), Issue #004 (per-stage timing)

**Blocks:** Issue #014 (stress test uses RTF validation)
