# Claude Code Quick Reference - Direct Toolchain Usage

## Quick Start (Most Common Commands)

```bash
# Quick testing (fastest way to validate)
python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency

# Ionosphere streaming (real-time VLF/ULF monitoring)
python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency
python benchmarks/run_throughput.py experiment=ionosphere_streaming_throughput +benchmark=throughput

# Run full benchmark suite and view dashboard
snakemake --cores 4 --snakefile experiments/Snakefile
sigx dashboard

# 100kHz baseline (Methods Paper data)
python benchmarks/run_latency.py experiment=baseline_streaming_100k_latency +benchmark=latency
python benchmarks/run_throughput.py experiment=baseline_batch_100k_throughput +benchmark=throughput
```

## Native Tool Commands (Recommended)

### Ionosphere Research Experiments (48kHz, 2-channel VLF/ULF)
```bash
# Quick testing (lightweight config, fast validation)
python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency

# Streaming mode experiments (real-time monitoring)
python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency
python benchmarks/run_latency.py experiment=ionosphere_streaming_hires +benchmark=latency
python benchmarks/run_latency.py experiment=ionosphere_streaming_latency +benchmark=latency
python benchmarks/run_throughput.py experiment=ionosphere_streaming_throughput +benchmark=throughput

# Batch mode experiments (offline processing)
python benchmarks/run_throughput.py experiment=ionosphere_batch_throughput +benchmark=throughput

# Specialized ionosphere configuration
python benchmarks/run_latency.py experiment=ionosphere_specialized +benchmark=latency
```

### Baseline Experiments (General Performance Characterization)
```bash
# 100kHz baseline (Methods Paper positioning - academic soft real-time)
python benchmarks/run_latency.py experiment=baseline_batch_100k_latency +benchmark=latency
python benchmarks/run_throughput.py experiment=baseline_batch_100k_throughput +benchmark=throughput
python benchmarks/run_latency.py experiment=baseline_streaming_100k_latency +benchmark=latency
python benchmarks/run_throughput.py experiment=baseline_streaming_100k_throughput +benchmark=throughput

# 48kHz baseline (Ionosphere application data)
python benchmarks/run_latency.py experiment=baseline_batch_48k_latency +benchmark=latency
python benchmarks/run_throughput.py experiment=baseline_batch_48k_throughput +benchmark=throughput
python benchmarks/run_latency.py experiment=baseline_streaming_48k_latency +benchmark=latency

# High NFFT throughput baseline
python benchmarks/run_throughput.py experiment=baseline_batch_high_nfft_throughput +benchmark=throughput
```

### Analysis & Validation Experiments
```bash
# Execution mode comparison (BATCH vs STREAMING)
python benchmarks/run_latency.py experiment=execution_mode_comparison +benchmark=latency

# Full parameter grid sweeps (comprehensive analysis)
python benchmarks/run_latency.py --multirun experiment=full_parameter_grid_100k +benchmark=latency
python benchmarks/run_latency.py --multirun experiment=full_parameter_grid_48k +benchmark=latency

# Specialized analysis
python benchmarks/run_latency.py experiment=low_nfft_scaling +benchmark=latency
python benchmarks/run_latency.py experiment=accuracy_validation +benchmark=accuracy
python benchmarks/run_throughput.py experiment=stress_test +benchmark=throughput
```

### Direct Hydra Usage (Custom Parameter Sweeps)
```bash
# Native Hydra multirun syntax (IMPORTANT: specify +benchmark=throughput for throughput tests)
python benchmarks/run_latency.py --multirun engine.nfft=1024,2048,4096,8192 +benchmark=latency experiment=ionosphere_streaming
python benchmarks/run_throughput.py --multirun engine.overlap=0.5,0.75,0.875 +benchmark=throughput experiment=ionosphere_streaming

# Single experiments with parameter overrides
python benchmarks/run_latency.py experiment=baseline_100k engine.nfft=8192 +benchmark=latency
python benchmarks/run_throughput.py experiment=ionosphere_streaming engine.nfft=8192 engine.overlap=0.9 +benchmark=throughput

# Quick testing with lightweight config
python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency
```

### Complete Research Workflow
```bash
# 1. Run benchmark experiments (FULL - takes 30+ minutes)
snakemake --cores 4 --snakefile experiments/Snakefile

# 2. Launch interactive dashboard to view results
streamlit run experiments/streamlit/app.py --server.port 8501
# OR: sigx dashboard (alias for above)

# 3. View experiment tracking (optional)
mlflow ui --backend-store-uri file://./artifacts/mlruns

# 4. Data versioning (optional)
dvc status
dvc repro
```

### Targeted Snakemake Runs (Faster Development)

```bash
# === BATCH MODE ONLY ===
# Run all BATCH baseline experiments (~10-15 min)
snakemake --cores 4 --snakefile experiments/Snakefile \
  run_baseline_batch_100k_latency \
  run_baseline_batch_100k_throughput \
  run_baseline_batch_48k_latency \
  run_baseline_batch_48k_throughput

# === STREAMING MODE ONLY ===
# Run all STREAMING baseline experiments (~10-15 min)
snakemake --cores 4 --snakefile experiments/Snakefile \
  run_baseline_streaming_100k_latency \
  run_baseline_streaming_100k_throughput \
  run_baseline_streaming_100k_realtime \
  run_baseline_streaming_48k_latency \
  run_baseline_streaming_48k_realtime

# === QUICK COVERAGE FILL ===
# Fill missing 100kHz STREAMING experiments (latency + throughput)
snakemake --cores 4 --snakefile experiments/Snakefile \
  run_baseline_streaming_100k_latency \
  run_baseline_streaming_100k_throughput

# === SINGLE EXPERIMENT ===
# Run one specific experiment
snakemake --cores 4 --snakefile experiments/Snakefile run_baseline_streaming_100k_latency
snakemake --cores 4 --snakefile experiments/Snakefile run_baseline_streaming_100k_throughput
snakemake --cores 4 --snakefile experiments/Snakefile run_baseline_streaming_100k_realtime

# === REGENERATE AFTER CODE CHANGES ===
# Delete marker and re-run specific experiment
rm artifacts/data/baseline_streaming_100k_latency.done
snakemake --cores 4 --snakefile experiments/Snakefile run_baseline_streaming_100k_latency
```

## Report Generation Architecture

SigTekX uses **two complementary reporting solutions**:

| Solution | Type | Purpose | Command |
|----------|------|---------|---------|
| **Streamlit** | Interactive | Daily analysis, exploration | `sigx dashboard` |
| **Quarto** | Static | Publications, archival | `snakemake quarto_reports` |

Both solutions share core analysis modules from `experiments/analysis/`.

### 1. Streamlit Dashboard (Interactive)

Primary tool for daily exploration and analysis.

```bash
# Launch dashboard (recommended)
sigx dashboard

# OR launch manually
streamlit run experiments/streamlit/app.py

# Access at http://localhost:8501
```

**Features:**
- **Three Interactive Pages**:
  - General Performance: Throughput, latency, accuracy, scaling (6 tabs)
  - Ionosphere Research: VLF/ULF phenomena detection, RTF analysis, resolution trade-offs (7 tabs)
  - Configuration Explorer: Interactive filtering and comparison
- **Real-time Data**: Loads from `artifacts/data/` automatically
- **Interactive Filtering**: Multi-select by NFFT, channels, overlap, mode
- **Side-by-side Comparison**: Compare configurations with delta metrics
- **CSV Export**: Download filtered results
- **Dynamic Charts**: User-selectable axes and parameters

**Typical Workflow:**
```bash
# 1. Run benchmarks (generates CSV data)
snakemake --cores 4 --snakefile experiments/Snakefile

# 2. Launch dashboard
sigx dashboard

# 3. Explore interactively
#    - Navigate between pages
#    - Filter by parameters
#    - Compare configurations
#    - Export results
```

### 2. Quarto Reports (Static)

Publication-quality reports for papers and presentations (coming soon).

```bash
# Generate publication reports (future)
snakemake quarto_reports

# Outputs: artifacts/reports/general_performance.pdf
#          artifacts/reports/ionosphere_research.pdf
```

**Features:**
- **Professional Output**: PDF/HTML/Word with LaTeX typesetting
- **Publication-ready**: Cross-references, bibliographies, equations
- **Reproducible**: Git-tracked templates
- **Shared Analysis**: Reuses same modules as Streamlit

**Location:** `experiments/quarto/` (placeholder structure ready)

## Available Experiment Configurations (26 total)

**📖 For comprehensive experiment documentation, design principles, and selection guide, see:**
**[docs/benchmarking/experiment-guide.md](docs/benchmarking/experiment-guide.md)**

The guide explains:
- Why experiments are designed this way (mode separation, complementary coverage)
- When to use each experiment (decision tree, time budget guide)
- Design rationale (zero redundancy, self-documenting)
- Complete experiment details with parameter sweeps

**Quick reference below:**

### Ionosphere Experiments (48kHz, 2-channel VLF/ULF)
| Experiment | Mode | Description | Key Parameters |
|------------|------|-------------|----------------|
| `ionosphere_test` | - | Lightweight quick testing | Minimal config for fast validation |
| `ionosphere_streaming` | STREAMING | Standard streaming config | 48kHz, 2-ch, real-time monitoring |
| `ionosphere_streaming_hires` | STREAMING | High-resolution streaming | Higher NFFT for better freq resolution |
| `ionosphere_streaming_latency` | STREAMING | Latency-optimized streaming | Minimal latency configuration |
| `ionosphere_streaming_throughput` | STREAMING | Throughput-optimized streaming | Max throughput configuration |
| `ionosphere_batch_throughput` | BATCH | Batch mode throughput | Offline processing optimization |
| `ionosphere_specialized` | - | Specialized ionosphere config | Custom specialized parameters |

### Baseline Experiments (General Performance)
| Experiment | Sample Rate | Mode | Description |
|------------|-------------|------|-------------|
| `baseline_100k` | 100kHz | Mixed | General 100kHz baseline |
| `baseline_batch_100k_latency` | 100kHz | BATCH | Batch latency baseline |
| `baseline_batch_100k_throughput` | 100kHz | BATCH | Batch throughput baseline |
| `baseline_streaming_100k_latency` | 100kHz | STREAMING | Streaming latency baseline |
| `baseline_streaming_100k_throughput` | 100kHz | STREAMING | Streaming throughput baseline |
| `baseline_streaming_100k_realtime` | 100kHz | STREAMING | Real-time factor baseline |
| `baseline_48k` | 48kHz | Mixed | General 48kHz baseline |
| `baseline_batch_48k_latency` | 48kHz | BATCH | Batch latency baseline |
| `baseline_batch_48k_throughput` | 48kHz | BATCH | Batch throughput baseline |
| `baseline_streaming_48k_latency` | 48kHz | STREAMING | Streaming latency baseline |
| `baseline_streaming_48k_realtime` | 48kHz | STREAMING | Real-time factor baseline |
| `baseline_batch_high_nfft_throughput` | - | BATCH | High NFFT throughput study |

### Analysis & Validation Experiments
| Experiment | Description | Use Case |
|------------|-------------|----------|
| `execution_mode_comparison` | BATCH vs STREAMING comparison | Mode selection analysis |
| `full_parameter_grid_100k` | Exhaustive 100kHz parameter sweep | Comprehensive 100kHz analysis |
| `full_parameter_grid_48k` | Exhaustive 48kHz parameter sweep | Comprehensive 48kHz analysis |
| `low_nfft_scaling` | Low NFFT performance study | Low-latency optimization |
| `accuracy_validation` | Accuracy validation tests | Correctness verification |
| `stress_test` | Stress testing configuration | Stability and limits testing |
| `profiling` | GPU profiling configuration | Performance profiling |

## Essential CLI Commands (Development Only)

```bash
# Environment and build (use CLI for these)
./scripts/cli.ps1 setup                   # Environment setup
./scripts/cli.ps1 build                   # Build project
./scripts/cli.ps1 test                    # Run tests
./scripts/cli.ps1 test python -Coverage   # Run Python tests with coverage
./scripts/cli.ps1 test cpp -Coverage      # Run C++ tests with coverage
./scripts/cli.ps1 coverage                # Run C++ tests with coverage (standalone)
./scripts/cli.ps1 format                  # Format code
./scripts/cli.ps1 lint                    # Lint code
./scripts/cli.ps1 doctor                  # System health check
```

## C++ Development Workflow (Pre-Python Integration)

**Use Case:** Developing and validating new C++ kernels/executors BEFORE Python integration.

**Important:** This workflow is for C++ development iteration only. For production profiling, always use `sxp` with Python benchmarks (see GPU Profiling section below).

### Quick Start with `sigxc`

The `sigxc` command provides a dedicated CLI for C++ benchmarking with preset configurations:

```powershell
# Quick validation (default: dev preset, 20 iter, ~10s)
sigxc bench

# Production latency benchmark
sigxc bench --preset latency --full

# Stable benchmarking with locked GPU clocks (CV reduction: 20% → 5-10%)
sigxc bench --preset latency --full --lock-clocks
sigxc bench --preset realtime --iono --lock-clocks

# Standard ionosphere realtime profiling
sigxc bench --preset realtime --iono --profile
sigxc profile nsys --stats

# Extreme ionosphere throughput (missile detection)
sigxc bench --preset throughput --ionox --full

# Custom experimentation
sigxc bench --preset throughput --nfft 4096 --batch 16 --quick

# Save baseline for regression tracking
sigxc bench --preset latency --full --save-baseline

# Full help
sigxc bench --help
```

### Build C++ Benchmark Executable
```bash
# Build both tests and benchmark executable
sigx build   # or: ./scripts/cli.ps1 build
```

### Benchmark Presets

Multiple presets matching Python configurations:

```powershell
# dev (default): Quick validation
sigxc bench                                    # 20 iter, ~10s

# latency: Latency measurement
sigxc bench --preset latency --full            # 5000 iter, ~2min
sigxc bench --preset latency --iono            # Standard ionosphere (4096, 0.75)
sigxc bench --preset latency --ionox           # Extreme ionosphere (8192, 0.9)

# throughput: Throughput measurement
sigxc bench --preset throughput --full         # 10s duration
sigxc bench --preset throughput --iono         # Ionosphere ULF/VLF (16384, 0.75)
sigxc bench --preset throughput --ionox        # Extreme missile detection (32768, 0.9375)

# realtime: Real-time streaming
sigxc bench --preset realtime --full           # 10s stream
sigxc bench --preset realtime --iono           # Standard ionosphere (4096, 0.75)
sigxc bench --preset realtime --ionox          # Extreme ionosphere (8192, 0.9)

# accuracy: Accuracy validation
sigxc bench --preset accuracy --full           # Single reference test
sigxc bench --preset accuracy --iono           # Iono reference (4096, 0.75)
sigxc bench --preset accuracy --ionox          # Ionox reference (8192, 0.9)
```

### Profile C++ Directly (Development Only)

**Nsight Systems (Timeline Analysis)**
```powershell
# Basic profiling (auto-creates artifacts\profiling directory)
sigxc profile nsys

# With statistics
sigxc profile nsys --stats

# Custom mode and traces
sigxc profile nsys --mode quick --trace cuda,nvtx

# Custom output path
sigxc profile nsys --output my_profile --stats
```

**Nsight Compute (Kernel Analysis)**
```powershell
# Basic profiling (⚠️ slow - 5-15 minutes)
sigxc profile ncu

# Roofline analysis
sigxc profile ncu --set roofline

# Specific kernel only (faster)
sigxc profile ncu --kernel-name "fft_kernel"

# Full metrics (very slow)
sigxc profile ncu --set full --mode profile
```

**Advanced Options:**
```powershell
# All sigxc profile commands support:
# --mode <quick|profile|full>   Benchmark mode
# --output <path>                Custom output path
# Plus all native nsys/ncu flags (passthrough)

# Examples:
sigxc profile nsys --mode quick --duration 5
sigxc profile ncu --kernel-name "magnitude" --metrics sm__throughput
```

### Typical C++ Development Workflow
```powershell
# 1. Save baseline before modifications (with locked clocks for stability)
sigxc bench --preset latency --full --lock-clocks --save-baseline

# 2. Modify C++ executor/kernel code
vim cpp\src\executors\batch_executor.cpp

# 3. Rebuild
sigx build

# 4. Quick validation (~10 seconds, compares to baseline)
sigxc bench

# 5. Full validation if quick looks good (locked clocks for stable comparison)
sigxc bench --preset latency --full --lock-clocks
# Performance card shows: ✓ NO CHANGE / ⚠ SLIGHT REGRESSION / ✗ REGRESSION

# 6. Profile if needed
sigxc bench --preset latency --profile
sigxc profile nsys --stats

# 7. View results
nsys-ui artifacts\profiling\cpp_dev.nsys-rep

# 8. Deep kernel analysis if needed (~5-15 minutes)
sigxc profile ncu --kernel-name "fft_kernel" --set roofline

# 9. Iterate until satisfied, then integrate with Python

# 10. Production profiling (end-to-end Python workflow)
sxp nsys latency    # Full Python end-to-end workflow
```

### When to Use Each Tool

| Tool | Purpose | Duration | Use When |
|------|---------|----------|----------|
| `sigxc bench` | Fast validation (dev preset) | 10s | Quick sanity check after code changes |
| `sigxc bench --preset <name> --profile` | Profile-ready benchmark | 30s-1min | Before running nsys/ncu profiling |
| `sigxc bench --preset <name> --full` | Production equivalent | 1-10min | Matching Python benchmark results |
| `sigxc profile nsys` | Timeline, API calls, NVTX | 30-60s | Understanding execution flow, bottlenecks |
| `sigxc profile ncu` | Kernel metrics, roofline | 5-15min | Optimizing specific kernel performance |
| `sxp` (Python) | **Production profiling** | Varies | **Final end-to-end validation** |

### Troubleshooting

#### Character Encoding Issues (PowerShell)

**Note:** If you're using `scripts/init_pwsh.ps1` to start your dev session, UTF-8 encoding is **automatically configured** for you.

If you see garbled characters like `┬╡s` instead of `µs` in benchmark output (when NOT using `init_pwsh.ps1`):

```powershell
# Fix for current PowerShell session
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Then run benchmark
./build/windows-rel/sigtekx_benchmark.exe --full
```

**Best solution:** Use `scripts/init_pwsh.ps1` to start your dev session (handles this automatically).

**Alternative:** Use Windows Terminal (has proper UTF-8 support by default) instead of legacy PowerShell console.

#### Profiling Directory Not Found

If `nsys profile` fails with "No such file or directory", the issue is usually:
1. Directory doesn't exist
2. Mixed path separators (forward/backslashes)

**Solution - use Windows backslashes consistently:**

```powershell
# Create directory first (Windows path with backslashes)
New-Item -ItemType Directory -Path artifacts\profiling -Force | Out-Null

# Then profile (all backslashes)
nsys profile -o artifacts\profiling\cpp_dev .\build\windows-rel\sigtekx_benchmark.exe --profile
```

**Important:** On Windows, always use `\` (backslashes) in paths, not `/` (forward slashes).

The `.gitignore` already excludes `artifacts/` from version control.

## Code Coverage

### C++ Coverage (gcovr)
```bash
# Run C++ tests with coverage report (builds with windows-coverage preset)
./scripts/cli.ps1 test cpp -Coverage      # Runs tests and opens HTML report
./scripts/cli.ps1 coverage                # Alternative standalone command

# Coverage report location
# Terminal: Color-coded coverage summary
# HTML: artifacts/reports/coverage-cpp/index.html

# Manual coverage workflow (if needed)
./scripts/cli.ps1 build -Preset windows-coverage    # Build with coverage
./build/windows-coverage/sigtekx_tests.exe            # Run tests
gcovr --root . --filter "cpp/.*" --html-details artifacts/reports/coverage-cpp/index.html
```

### Python Coverage (pytest-cov)
```bash
# Run Python tests with coverage (like you're used to)
./scripts/cli.ps1 test python -Coverage   # Runs tests with coverage report

# Coverage report location
# Terminal: Coverage summary
# HTML: artifacts/reports/coverage/index.html
```

## Tool-Specific Quick Commands

### MLflow Experiment Tracking
```bash
# Start MLflow UI
mlflow ui --backend-store-uri file://./artifacts/mlruns --port 5000

# List experiments
mlflow experiments list --tracking-uri file://./artifacts/mlruns

# Search runs
mlflow runs search --tracking-uri file://./artifacts/mlruns --filter "metrics.latency < 100"
```

### Snakemake Workflows
```bash
# Run complete pipeline
snakemake --cores 4 --snakefile experiments/Snakefile

# Run specific targets
snakemake --cores 4 generate_figures --snakefile experiments/Snakefile
snakemake --cores 4 analyze_results --snakefile experiments/Snakefile

# Dry run to see what would execute
snakemake --dry-run --snakefile experiments/Snakefile
```

### DVC Data Management
```bash
# Check data status
dvc status

# Reproduce pipeline
dvc repro

# Sync data
dvc push
dvc pull

# View pipeline
dvc dag
```

### GPU Profiling with Nsight Tools

#### Quick Profiling (Recommended for Development)
```bash
# Fast profiling with minimal iterations - auto-selects correct config
sxp nsys latency        # Uses profiling (20 iterations)
sxp nsys throughput     # Uses profiling_throughput (3s duration)
sxp nsys realtime       # Uses profiling_realtime (3s duration)
sxp nsys accuracy       # Uses profiling_accuracy (2 iterations, 3 signals)

# NCU profiling (slower but more detailed)
sxp ncu latency
sxp ncu throughput
```

#### Full Benchmark Profiling (Research/Production)
```bash
# Full benchmark profiles (SLOW - use sparingly!)
sxp nsys latency -- experiment=profiling +benchmark=latency        # 5000 iterations
sxp nsys throughput -- experiment=profiling +benchmark=throughput  # 10s duration
sxp nsys accuracy -- experiment=profiling +benchmark=accuracy      # 10 iterations, 8 signals
```

#### Configuration Overrides (Hydra Passthrough)

Customize profiling parameters using Hydra config overrides:

**Simple Overrides (profiling config auto-loaded):**
```bash
# Override engine parameters (auto-loads profiling config + applies overrides)
sxp nsys latency engine.nfft=8192 engine.overlap=0.75
sxp nsys throughput engine.nfft=4096 engine.channels=8 engine.mode=streaming

# Override benchmark parameters (iterations, GPU clocks, etc.)
sxp nsys latency engine.nfft=4096 benchmark.iterations=100
sxp ncu latency engine.nfft=8192 benchmark.lock_gpu_clocks=true

# Combine multiple overrides
sxp nsys latency engine.nfft=4096 engine.overlap=0.875 \
  benchmark.iterations=50 benchmark.lock_gpu_clocks=true
```

**Custom Benchmark Configs (full control):**
```bash
# Use production config instead of profiling config
sxp nsys latency +benchmark=latency benchmark.lock_gpu_clocks=true

# Use custom experiment + benchmark combination
sxp nsys latency experiment=ionosphere_streaming_hires +benchmark=profiling

# Production profiling with all custom settings
sxp nsys latency +benchmark=latency \
  benchmark.lock_gpu_clocks=true benchmark.use_max_clocks=true
```

**How It Works:**
- **No overrides**: Uses fast profiling configs automatically (profiling, profiling_throughput, etc.)
- **With simple overrides**: Auto-loads profiling config, then applies your overrides
- **With +benchmark=**: Uses your specified benchmark config, ignores defaults

**Common Override Parameters:**
- **Engine**: `nfft` (1024-32768), `overlap` (0.5-0.9375), `channels` (1-8), `mode` (batch/streaming)
- **Benchmark**: `iterations`, `warmup_iterations`, `lock_gpu_clocks`, `use_max_clocks`, `gpu_index`
- **Config Groups**: `+benchmark=<config>`, `experiment=<config>`

**When to Use:**
- **Simple overrides**: Quick testing of different NFFT/overlap values
- **Custom configs**: Production profiling or full benchmark runs
- **Research**: Testing specific parameter combinations

**See Also:**
- `python scripts/prof_helper.py --help` for detailed argument documentation
- `sigx help` for quick reference

#### Expected Profiling Times

| Benchmark | Quick Config | Quick Params | nsys (quick) | ncu (quick) | Full Config | nsys (full) | ncu (full) |
|-----------|--------------|--------------|--------------|-------------|-------------|-------------|------------|
| latency | `profiling` | 20 iter | 30-60s | 5-10min | `latency` (5000 iter) | 12-15min | 2-4hrs |
| throughput | `profiling_throughput` | 3s | 20-30s | 5-8min | `throughput` (10s) | 8-10min | 1-2hrs |
| realtime | `profiling_realtime` | 3s | 20-30s | 5-8min | `realtime` (10s) | 8-10min | 1-2hrs |
| accuracy | `profiling_accuracy` | 2 iter, 3 signals | 30-45s | 8-12min | `accuracy` (10 iter, 8 signals) | 5-8min | 1-2hrs |

**Best Practices:**
- Use `+benchmark=profiling` for iterative development and kernel optimization
- Use `+benchmark=latency` only for production profiling runs
- Always start with `nsys` before moving to `ncu` (nsys is 10-50× faster)
- Use `ncu --kernel-name <pattern>` to profile specific kernels only

## GPU Clock Locking for Benchmark Stability

**Purpose**: Reduce benchmark variability (Coefficient of Variation) from 20-40% → 5-15%

### C++ Benchmarks (sigxc)

```powershell
# Lock GPU clocks for stable C++ benchmarking (requires admin - UAC prompt)
sigxc bench --preset latency --full --lock-clocks
```

### Python Benchmarks (Hydra)

```bash
# Enable GPU clock locking via Hydra config override
python benchmarks/run_latency.py +benchmark=latency benchmark.lock_gpu_clocks=true

# Or edit YAML once: experiments/conf/benchmark/latency.yaml
# lock_gpu_clocks: true
python benchmarks/run_latency.py +benchmark=latency

# Works with profiling too
sxp nsys latency  # With lock_gpu_clocks=true in YAML
```

**What it does:**
1. Auto-elevates to admin (UAC prompt on Windows)
2. Locks GPU graphics/memory clocks to stable values
3. Runs benchmark
4. **Automatically** restores original clocks (even on error/Ctrl+C)

**Expected CV improvement:**
- Latency: 20% → **5-10%** (50-75% better)
- Realtime: 40% → **10-15%** (60-75% better)

### C++ Options

```powershell
# Use recommended clocks (default, conservative)
sigxc bench --preset latency --full --lock-clocks

# Use max clocks for peak performance
sigxc bench --preset latency --full --lock-clocks --max-clocks

# Multi-GPU: select GPU 1
sigxc bench --preset latency --full --lock-clocks --gpu-index 1

# Query GPU info (no locking)
pwsh scripts/gpu-manager.ps1 -Action Query
```

### Python Options

```bash
# Use recommended clocks (default)
python benchmarks/run_latency.py +benchmark=latency \
  benchmark.lock_gpu_clocks=true

# Use max clocks for peak performance
python benchmarks/run_latency.py +benchmark=latency \
  benchmark.lock_gpu_clocks=true \
  benchmark.use_max_clocks=true

# Multi-GPU: select GPU 1
python benchmarks/run_latency.py +benchmark=latency \
  benchmark.lock_gpu_clocks=true \
  benchmark.gpu_index=1
```

**Supported GPUs**: RTX 3090 Ti, RTX 4090, RTX 4080, RTX 4070 Ti, RTX 3080, RTX 3070, A100, V100

**Full documentation**: `docs/performance/gpu-clock-locking.md`

**Quick reference**: `docs/performance/stability-improvements.md` for executive summary

**Safety**: Auto-cleanup always runs (even on Ctrl+C or error). Manual recovery if needed:
```powershell
nvidia-smi -pm 0 && nvidia-smi -rgc && nvidia-smi -rmc
```

## Window Function Symmetry Modes

### Overview

The library supports two window symmetry modes that control endpoint behavior and spectral characteristics:

| Mode | Denominator | Endpoints | Primary Use Case | Applications |
|------|-------------|-----------|------------------|--------------|
| **PERIODIC** | N | Non-zero (except i=0) | FFT-based spectral analysis | STFT, spectrograms, ionosphere research |
| **SYMMETRIC** | N-1 | Exactly zero at both ends | Time-domain signal analysis | FIR filter design, signal tapering |

### Configuration

Window symmetry is configured via `StageConfig::window_symmetry`:

```cpp
StageConfig config;
config.window_type = StageConfig::WindowType::HANN;
config.window_symmetry = StageConfig::WindowSymmetry::PERIODIC;  // Default
```

### Mathematical Formulas

**PERIODIC Mode (default for FFT processing):**
```
Hann[i] = 0.5 * (1 - cos(2πi/N))
Blackman[i] = 0.42 - 0.5*cos(2πi/N) + 0.08*cos(4πi/N)
```

**SYMMETRIC Mode (for time-domain analysis):**
```
Hann[i] = 0.5 * (1 - cos(2πi/(N-1)))
Blackman[i] = 0.42 - 0.5*cos(2πi/(N-1)) + 0.08*cos(4πi/(N-1))
```

### When to Use Each Mode

- **Use PERIODIC (default)** for:
  - FFT-based spectral analysis
  - Short-Time Fourier Transform (STFT)
  - Spectrogram generation
  - All ionosphere research workflows

- **Use SYMMETRIC** for:
  - FIR filter coefficient windowing
  - Direct time-domain signal tapering
  - Applications requiring exact zero endpoints

### Implementation Details

All window functions in `window_functions.hpp` and `window_utils` namespace support both modes:

```cpp
// Low-level window_functions API
double coeff = window_functions::hann_base(i, size,
    window_functions::WindowSymmetry::PERIODIC);

// High-level window_utils API
window_utils::generate_window(buffer, size,
    StageConfig::WindowType::HANN,
    false,  // sqrt_norm
    StageConfig::WindowSymmetry::PERIODIC);
```

### Testing

Both modes are validated by comprehensive tests:
- `WindowFunctionsTest.PeriodicModeNumericalCorrectness` - validates PERIODIC mode IEEE-754 compliance
- `WindowFunctionsTest.SymmetricModeNumericalCorrectness` - validates SYMMETRIC mode IEEE-754 compliance
- `WindowFunctionsTest.WindowSymmetryModes` - integration test across all window types
- `ProcessingStageTest.WindowStageRespectsSymmetryConfig` - validates pipeline integration

Run tests with: `./scripts/cli.ps1 test cpp`

### References

- Full API documentation: `cpp/include/ionosense/core/window_functions.hpp`
- Pipeline integration: `cpp/include/ionosense/core/processing_stage.hpp`
- Test examples: `cpp/tests/test_window_functions.cpp`

## System Reliability Notes

### Configuration System
- All ionosphere configurations validated and working
- MLflow integration properly configured
- Direct tool access ensures full feature availability
- No artificial CLI limitations

### Critical Requirements
- **ALWAYS specify `+benchmark=throughput`** when using `run_throughput.py`
- **ALWAYS specify `+benchmark=latency`** when using `run_latency.py`
- **No default benchmark** - must be explicitly specified to prevent config conflicts
- **Use `experiment=ionosphere_test`** for quick testing with smaller parameters

### Working Command Templates
```bash
# ✅ CORRECT - includes +benchmark=throughput
python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput

# ✅ CORRECT - includes +benchmark=latency
python benchmarks/run_latency.py experiment=ionosphere_multiscale +benchmark=latency

# ❌ WRONG - no benchmark specified (will fail)
python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution
```

Last updated: 2025-10-17 (Added Python GPU clock locking support - feature parity with C++)