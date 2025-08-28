# Benchmark Guide

Performance testing methodology and reproducibility protocols for **ionosense-hpc-lib**.

---

## Benchmark Suite Overview

| Benchmark           | Purpose                          | Key Metrics                                           |
| ------------------- | -------------------------------- | ----------------------------------------------------- |
| `raw_throughput`    | Peak FFT capacity without pacing | FFTs/sec, GPU util, H2D/D2H overlap %                 |
| `realtime`          | Deadline-constrained latency     | p50/p95/p99/max latency, **deadline misses = 0**, FPS |
| `verify_accuracy`   | Numerical parity vs float64      | RMS/REL∞ error, dB error on bins > −60 dB             |
| `graphs_comparison` | CUDA Graphs impact               | Mean/p99 latency change, launch count reduction       |
| `batch_scaling`     | Batch size sweet spot            | Throughput vs batch curve, memory footprint           |

---

## Running Benchmarks

### Quick Run

```bash
# List available benchmarks
./scripts/cli.sh list benchmarks

# Run specific benchmark
./scripts/cli.sh bench raw_throughput -n 4096 -b 32

# Run with profiling (NVTX annotated)
./scripts/cli.sh profile nsys raw_throughput -n 4096
```

### Full Suite

```bash
# Run all benchmarks with standard parameters
python python/benchmarks/run_suite.py --output results.json
```

---

## Benchmark Protocols

### 1) Raw Throughput (`raw_throughput.py`)

**Purpose:** Measure maximum sustainable FFT/s without pacing.

**Methodology:**

* Fixed-duration run (default 5 s)
* No artificial inter-iteration delay
* 2–3 CUDA streams round‑robin (copy→window→FFT→mag→copy‑back)
* Sweep batch sizes to find saturation

**Parameters:**

```bash
./scripts/cli.sh bench raw_throughput \
  -n 4096   \
  -b 32     \
  -d 5.0    \
  --no-graphs
```

**Success Criteria (research-grounded):**

* Achieve **≥10×** the real‑time frame rate at the target N/overlap (headroom). For N=4096, fs=100 kHz, 50% overlap ⇒ \~48.83 FPS/channel ⇒ **≥1000 FFT/s** combined is a conservative headroom target.
* Show **copy/compute overlap** (nsys timeline) and minimal host idle.

---

### 2) Real-Time Latency (`realtime.py`)

**Purpose:** Measure per-frame latency under paced input and verify deadline safety.

**Frame Math:**

* Window = **N/fs**; Hop (50% overlap) = **N/(2·fs)**
* At **N=4096, fs=100 kHz** ⇒ Window **40.96 ms**, Hop **20.48 ms**
* Required: each frame’s end‑to‑end processing **< hop**; target ample margin

**Methodology:**

* Pace arrivals at hop interval; timestamp at H2D start and result ready
* Count deadline misses (any frame > hop)
* Report p50/p95/p99/max; run ≥10 s for stable stats

**Parameters:**

```bash
./scripts/cli.sh bench realtime \
  -n 4096 \
  -b 2    \
  -s 100000 \
  -o 0.5 \
  -d 10.0
```

**Latency Targets (pipeline now; room for future DSP/ML):**

* **p50 ≤ 3 ms**, **p99 ≤ 8 ms**, **max ≤ 15 ms** (per frame)
* **Deadline misses = 0** over multi‑hour stability runs

---

### 3) Accuracy Validation (`verify_accuracy.py`)

**Purpose:** Numerical parity vs CPU float64 reference.

**Methodology:**

* Signals: single tones, dual tones, chirps, white noise
* Compare GPU (FP32) vs NumPy/SciPy (FP64) on magnitude spectra
* Metrics: RMS error, REL∞ (max relative), per‑bin dB error for bins > −60 dB

**Acceptance:**

* **RMS ≤ 1e‑5**, **REL∞ ≤ 1e‑3**, **|ΔdB| ≤ 0.05 dB** (bins > −60 dB)
* Document window, scaling, and any FFT normalization so CPU/GPU match

---

### 4) CUDA Graphs Comparison (`graphs_comparison.py`)

**Purpose:** Quantify launch‑overhead reductions and jitter improvements.

**Methodology:**

* A/B: graphs **off** vs **on** at identical configs
* Capture mean/p99 latency, jitter (max−p50), kernel launch counts
* Paired t‑test or bootstrap CI on deltas

**Example Report Block:**

```
LATENCY COMPARISON (N=4096, b=8)
Metric          No Graphs    With Graphs    Δ (%)
Mean            2.10 ms      1.82 ms        −13.3
P99             4.90 ms      3.95 ms        −19.4
Launches/frame  6            2              −66.7
```

---

### 5) Batch Size Scaling (`batch_scaling.py`)

**Purpose:** Find batch sweet spot per FFT size and device.

**Methodology:**

* Sweep batch ∈ {2,4,8,…,256}; repeat K=5; report mean±2σ
* Track VRAM use and HBM/DRAM throughput

**CSV Output:**

```csv
nfft,batch_size,mean_ffts_per_s,std_ffts_per_s,mem_mb
4096,2,1250.4,31.2,96
4096,4,2231.8,28.6,112
...
```

---

## Profiling Integration

### Nsight Systems (timeline)

```bash
./scripts/cli.sh profile nsys raw_throughput -n 4096
```

**Check:** stream overlap, H2D/compute/D2H pipelining, graph capture regions, sync points, CPU stalls.

### Nsight Compute (kernels)

```bash
./scripts/cli.sh profile ncu realtime -n 4096
```

**Inspect:** Achieved Occupancy, DRAM bytes, L2 hit rate, warp‑stall reasons, roofline placement (compute vs memory bound).

---

## Reproducibility Protocol

### Environment Capture

```bash
nvidia-smi --query-gpu=name,driver_version,pstate,clocks.current.graphics,clocks.current.memory --format=csv > env.txt
python -c "import sys,platform; print(sys.version); print(platform.platform())" >> env.txt
python -c "import cupy, numpy; print('cupy', cupy.__version__); print('numpy', numpy.__version__)" >> env.txt
conda list | grep -E "(cuda|cudatoolkit|cufft)" >> env.txt
git rev-parse HEAD >> env.txt
```

### Statistical Rigor

1. **Warmup:** ≥10 iterations before timing
2. **Samples:** ≥100 latency samples per config
3. **CI:** Report mean ± 2σ; include p50/p95/p99
4. **Outliers:** Flag >3σ; report both with/without
5. **Clocks:** Fix clocks to reduce variance

```bash
# Example: lock clocks (adjust for device)
sudo nvidia-smi -lgc 1700
sudo nvidia-smi -lmc 9500
```

### Result Archival

```json
{
  "timestamp": "2025-08-28T00:00:00Z",
  "git_hash": "abc123def456",
  "environment": {
    "gpu": "RTX 4000 Ada (laptop)",
    "cuda": "12.6",
    "driver": "555.xx"
  },
  "configuration": {
    "fft_size": 4096,
    "batch_size": 8,
    "sample_rate": 100000,
    "overlap": 0.5,
    "use_graphs": true
  },
  "results": {
    "ffts_per_s": 2100.2,
    "latency_ms": {"p50": 2.3, "p95": 3.6, "p99": 6.9, "max": 9.8},
    "deadline_misses": 0,
    "rms_error": 8.0e-6
  }
}
```

---

## Performance Targets (Research‑informed)

### Latency Targets (dual‑channel, per frame)

| FFT Size | Hop (ms) | p50 Target | p99 Target | Max     | Goal      |
| -------- | -------- | ---------- | ---------- | ------- | --------- |
| 2048     | 10.24    | ≤ 2 ms     | ≤ 5 ms     | ≤ 8 ms  | no misses |
| 4096     | 20.48    | ≤ 3 ms     | ≤ 8 ms     | ≤ 15 ms | no misses |
| 8192     | 40.96    | ≤ 6 ms     | ≤ 12 ms    | ≤ 20 ms | no misses |

> Hop = N/(2·fs) with fs=100 kHz; adjust as fs/N change.

### Real‑Time Throughput Targets

* **Deadline safety:** sustain **100%** of required FPS with **0 misses**.
  • For N=4096, fs=100 kHz, 50% overlap ⇒ **≈48.83 FPS/channel** (≈97.66 FPS total).
* **Headroom demonstration:** run the realtime bench at **5× input rate** (e.g., simulate **500 kS/s per channel**) without misses to prove scalability. If feasible, also demo **1 MS/s per channel**.

### Raw Throughput Targets

* Report the **throughput curve** (FFTs/s vs batch) rather than a single number.
* Success: peak ≥ **10× realtime FPS** at target N, with GPU <100% busy and stable thermals.

---

## Comparison Baselines

* **CPU (FFTW / NumPy):** single‑thread and multi‑thread; report speedup vs GPU and energy/FFT where possible.
* **Library parity:** cuFFT is the reference. If comparing others (VkFFT), expect ±5–15% deltas; discuss memory traffic patterns.
* **Determinism under load:** (optional) co‑run a synthetic GPU kernel to show p99 stays < hop with proper stream design.

---

## Troubleshooting Benchmarks

| Issue                 | Diagnosis                  | Solution                                                      |
| --------------------- | -------------------------- | ------------------------------------------------------------- |
| Low throughput        | Under‑batched / sync gaps  | Increase batch; enable streams; enable graphs                 |
| High latency variance | CPU/GPU clocks scaling     | Lock clocks; disable CPU freq scaling; pin OS affinity        |
| Missed deadlines      | Transfers on critical path | Use `cudaMemcpyAsync`, double‑buffering, overlap copy/compute |
| OOM / mem errors      | Batch too large            | Reduce batch; pre‑allocate; reuse workspaces                  |
| Accuracy mismatch     | Scaling/window mismatch    | Normalize consistently; verify window and FFT conventions     |

---

## Benchmark Development

### Adding New Benchmarks

```python
# Template: python/benchmarks/template.py
from utils import CudaFftEngine, nvtx_range, print_header

def run_benchmark(cfg):
    with nvtx_range("benchmark_name"):
        eng = CudaFftEngine(cfg.nfft, cfg.batch)
        # ... do work ...
        return results

if __name__ == "__main__":
    args = parse_args()
    print_header("Benchmark Name")
    res = run_benchmark(args)
    save_json(res)
```

### Validation Checklist

* [ ] Warmup iterations included
* [ ] NVTX markers present
* [ ] p50/p95/p99 reported (not just mean)
* [ ] Outliers analyzed
* [ ] JSON export available
* [ ] Reproducible seeds & fixed clocks
* [ ] Docs updated in this file