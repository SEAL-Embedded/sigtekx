# C++ Standalone Benchmarking

## Quick Start with `ionoc`

The `ionoc` CLI provides a comprehensive interface for C++ benchmarking and profiling with preset configurations:

```powershell
# Build the benchmark
sigx build

# Quick validation (~10 seconds)
sigxc bench

# Production latency benchmark
sigxc bench --preset latency --full

# Ionosphere realtime profiling
sigxc bench --preset realtime --ionosphere --profile
sigxc profile nsys --stats

# Custom experimentation
sigxc bench --preset throughput --nfft 4096 --batch 16 --quick

# View all options
sigxc bench --help
```

## Purpose

This standalone C++ benchmark is designed for **development-time iteration** when working on new executors, kernels, or CUDA optimizations BEFORE Python integration.

**This is NOT for production profiling.** For production profiling, always use `iprof` with Python benchmarks to validate the entire end-to-end workflow.

## Benchmark Presets

The benchmark executable supports multiple presets matching Python configurations:

| Preset | Primary Metric | Default Config | Duration | Use Case |
|--------|---------------|----------------|----------|----------|
| **dev** (default) | Latency stats | 20 iter, nfft=2048, batch=4 | ~10s | Quick validation |
| **latency** | Mean/P95/P99 latency (µs) | 5000 iter, nfft=2048, batch=4 | ~2min | Latency measurement |
| **throughput** | FPS, GB/s | 10s duration, nfft=2048, batch=8 | ~10s | Throughput measurement |
| **realtime** | Deadline compliance, jitter | 10s stream, nfft=2048, batch=4 | ~10s | Real-time streaming |
| **accuracy** | Pass/Fail (smoke test) | Single sine test, nfft=2048 | ~5s | **Smoke test only** - use Python for real accuracy |

### Ionosphere Variants

Each preset has an ionosphere variant activated with `--ionosphere`:

| Preset | Ionosphere Parameters | Use Case |
|--------|----------------------|----------|
| **latency** | nfft=4096, batch=2, overlap=0.625 | Higher resolution, lower batch |
| **throughput** | nfft=8192, batch=16, overlap=0.75 | High-res batch processing |
| **realtime** | nfft=4096, batch=2, strict timing | Balanced resolution, strict timing |
| **accuracy** | nfft=8192, batch=1 | Higher resolution smoke test |

## Run Modes

Control iteration count or duration independent of preset:

| Mode | Effect | Duration | Use Case |
|------|--------|----------|----------|
| **--quick** | 20 iter / 3s | ~10-30s | Fast validation during development |
| **--profile** | 100 iter / 5s | ~30s-1min | Before running nsys/ncu profiling |
| **--full** | Full iterations/duration | 1-10min | Production-equivalent benchmarking |

## CLI Flags Reference

### Core Flags
```powershell
--preset <name>           # dev, latency, throughput, realtime, accuracy
--ionosphere             # Apply ionosphere variant
--quick                  # Fast run mode
--profile                # Profile-ready run mode
--full                   # Full production run (default)
```

### Parameter Overrides
```powershell
--nfft <value>           # FFT size
--batch <value>          # Batch size
--overlap <value>        # Overlap ratio (0-1)
--sample-rate <hz>       # Sample rate in Hz
--iterations <n>         # Number of iterations
--duration <seconds>     # Test duration (time-based benchmarks)
--warmup <n>             # Warmup iterations
--seed <n>               # Random seed
```

### Output Control
```powershell
--csv                    # CSV output only
--json                   # JSON output
--quiet                  # Minimal output
```

### Dataset Tracking
```powershell
--save-dataset          # Save results as dataset for future comparison
```

## Statistical Validation & Dataset Tracking

The benchmark system automatically computes statistical validation metrics and supports dataset tracking for performance regression detection.

### Statistical Metrics

**Latency Benchmarks:**
- Coefficient of Variation (CV): Measures stability (CV < 10% = stable)
- 95% Confidence Interval: Statistical range for mean latency
- Warmup Effectiveness: Latency reduction after warmup
- Performance Tier: EXCELLENT / GOOD / ADEQUATE / POOR

**Throughput Benchmarks:**
- Performance Tier: Based on FPS relative to target

**Realtime Benchmarks:**
- Deadline Compliance Rate: % of frames meeting deadline
- Jitter CV: Variability in frame latencies
- Performance Tier: Based on compliance rate (>99.9% = EXCELLENT)

### Dataset Tracking

Track performance over time and detect regressions:

```powershell
# Save a dataset (first time)
sigxc bench --preset latency --full --save-dataset

# Run benchmark (automatically compares to dataset)
sigxc bench --preset latency --full

# Update dataset after intentional changes
sigxc bench --preset latency --full --save-dataset
```

**Dataset Storage:**
- Location: `artifacts/cpp/datasets/` (C++ only - clearly separated from Python)
- Format: `<preset>_<variant>_<mode>.json`
- Example: `latency_ionosphere_full.json`

**Comparison Thresholds:**
- ±2%: No change
- 2-5%: Slight regression (warning)
- >5%: Regression (error)
- Negative: Improvement (good)

### Performance Card

Every benchmark displays a concise performance card:

```
────────────────────────────────
Performance Card
────────────────────────────────
Latency (P95):   114.30 µs  [✓ GOOD]
Stability:     CV= 4.2%   [✓ EXCELLENT]
vs Dataset:   +2.3%      [⚠ SLIGHT REGRESSION]
────────────────────────────────
```

## Usage Examples

### Quick Development Workflow
```powershell
# Default: quick dev validation
sigxc bench

# With specific preset
sigxc bench --preset latency --quick

# Profile-ready
sigxc bench --preset realtime --profile
sigxc profile nsys --stats
```

### Production Benchmarks
```powershell
# Full latency benchmark (matches Python)
sigxc bench --preset latency --full

# Ionosphere throughput
sigxc bench --preset throughput --ionosphere --full

# Real-time compliance testing
sigxc bench --preset realtime --ionosphere --full
```

### Rapid Experimentation
```powershell
# Override preset parameters
sigxc bench --preset latency --nfft 8192 --batch 16 --quick

# Blank canvas (no preset)
sigxc bench --nfft 4096 --overlap 0.875 --iterations 50

# Custom ionosphere config
sigxc bench --ionosphere --nfft 16384 --batch 32 --profile
```

### Accuracy Reference Test
```powershell
# Single pipeline-matching reference test
sigxc bench --preset accuracy

# Ionosphere reference test (higher resolution)
sigxc bench --preset accuracy --ionosphere
```

**IMPORTANT:** The C++ accuracy benchmark is a **single reference-based test** that validates the entire pipeline produces correct numerical output.

It compares engine output against a CPU reference that **exactly mirrors the pipeline**:
- Window: Hann, PERIODIC symmetry, UNITY normalization
- FFT: cuFFT R2C
- Magnitude: sqrt(real² + imag²) * (1/N) scaling

**Validation:** Tests pure sine wave input with tight numerical tolerance (max error < 1e-4).

**Hardcoded to current pipeline:** If you add/remove stages or change scaling, update `reference_compute.hpp` to match.

**For comprehensive cross-platform accuracy validation**, use Python tests:
```powershell
pytest tests/test_accuracy.py  # Full scipy reference comparison
```

## Profiling Workflow

All profiling is handled through the `ionoc` CLI, which automatically creates directories and handles path conversions.

### Nsight Systems (Timeline Analysis)
```powershell
# Run profile-ready benchmark first
sigxc bench --preset latency --profile

# Profile with nsys
sigxc profile nsys --stats

# View results
nsys-ui artifacts\profiling\cpp_dev.nsys-rep

# Custom traces
sigxc profile nsys --trace cuda,nvtx,osrt --stats
```

### Nsight Compute (Kernel Analysis)
```powershell
# Run profile-ready benchmark first
sigxc bench --preset throughput --profile

# Profile with ncu (⚠️ slow - 5-15 minutes)
sigxc profile ncu --set roofline

# Specific kernel only (faster)
sigxc profile ncu --kernel-name "fft_kernel"

# View results
ncu-ui artifacts\profiling\cpp_dev_ncu.ncu-rep
```

## Development Workflow

### Typical Iteration Cycle
```powershell
# 1. Modify C++ code
vim cpp\src\executors\batch_executor.cpp

# 2. Rebuild
sigx build

# 3. Quick validation
sigxc bench

# 4. Profile-ready run if changes look good
sigxc bench --preset latency --profile

# 5. Profile with nsys
sigxc profile nsys --stats

# 6. Analyze in GUI
nsys-ui artifacts\profiling\cpp_dev.nsys-rep

# 7. Deep kernel analysis if needed
sigxc profile ncu --kernel-name "fft_kernel" --set roofline

# 8. Iterate until satisfied

# 9. Integrate with Python and do production profiling
sxp nsys latency    # Full end-to-end Python workflow
```

### Comparing Configurations
```powershell
# Save dataset before changes
sigxc bench --preset latency --full --save-dataset

# Make code changes...

# Run again (automatically shows comparison)
sigxc bench --preset latency --full
```

### Testing Executor Refactor
```powershell
# 1. Save dataset with current implementation
sigxc bench --preset latency --full --save-dataset

# 2. Modify executor code
# (swap in new BatchExecutor or StreamingExecutor)

# 3. Rebuild and test (automatically compares to dataset)
sigx build
sigxc bench --preset latency --full

# 4. Performance card will show regression status
# ✓ GOOD = No regression (<2%)
# ⚠ ADEQUATE = Slight regression (2-5%)
# ✗ POOR = Regression (>5%)

# 5. If satisfied, update dataset
sigxc bench --preset latency --full --save-dataset
```

## Output Formats

### Default (Table Output)
```
========================================
  Latency Benchmark Results
========================================

Configuration:
  Preset      : latency (ionosphere)
  Run Mode    : profile
  NFFT        : 4096
  Batch       : 2
  Overlap     : 0.625
  Iterations  : 100

Runtime:
  Device      : NVIDIA RTX 4090
  CUDA        : 12.3

Latency (µs):
  Mean        : 125.43
  P50         : 124.22
  P95         : 132.18
  P99         : 138.92
  Min         : 119.84
  Max         : 145.67
  Std Dev     : 6.23

========================================
```

### CSV Output
```powershell
sigxc bench --preset latency --csv

# Output:
# preset,mode,ionosphere,nfft,batch,iterations,mean_us,p50_us,p95_us,p99_us,min_us,max_us,std_us
# latency,full,yes,4096,2,5000,125.43,124.22,132.18,138.92,119.84,145.67,6.23
```

### JSON Output
```powershell
sigxc bench --preset latency --json

# Output: (not yet implemented, reserved for future use)
```

## Troubleshooting

### Character Encoding Issues

**Note:** If using `scripts/init_pwsh.ps1`, UTF-8 is **automatically configured**.

If you see garbled characters like `┬╡s` instead of `µs` in output (when NOT using `init_pwsh.ps1`):

```powershell
# Fix for current session
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Then run benchmark
sigxc bench
```

**Best solution:** Use `scripts/init_pwsh.ps1` to start dev sessions (handles this automatically).

**Alternative:** Use Windows Terminal (proper UTF-8 support by default).

### Profiling Directory Errors

**Note:** `ionoc` automatically creates the `artifacts\profiling` directory, so this error should not occur when using the CLI.

If you're running sigtekx_benchmark.exe directly (not through `ionoc`) and encounter path issues:

```powershell
# Solution: Use ionoc instead (recommended)
sigxc profile nsys --stats

# Or manually create directory
New-Item -ItemType Directory -Path artifacts\profiling -Force | Out-Null
```

### Build Errors

If sigtekx_benchmark.exe is not found:

```powershell
# Rebuild the project
sigx build

# Check if executable exists
ls build\windows-rel\sigtekx_benchmark.exe
```

## Performance Targets

When validating executor refactors, aim for:

- **Latency overhead**: <5% vs dataset
- **Throughput**: No regression
- **Real-time compliance**: >99% deadline compliance
- **Accuracy smoke test**: 100% pass rate (sine peak at correct bin)

## Notes

- **No Python dependencies**: This executable is pure C++/CUDA
- **NVTX enabled**: All benchmark phases have NVTX markers for profiling
- **Deterministic**: Uses fixed random seed for reproducibility
- **Quick iteration**: Fast rebuild-test cycle for C++ development
- **UTF-8 output**: Uses proper scientific notation (µs), may need encoding fix in legacy consoles
- **Preset system**: Matches Python benchmark configurations exactly

## See Also

- Full documentation: `CLAUDE.md` → "C++ Development Workflow"
- Python profiling: `sxp nsys latency` (production workflow)
- Test suite: `./scripts/cli.ps1 test cpp`
- Preset definitions: `cpp/benchmarks/benchmark_config.hpp`
