# Claude Code Quick Reference - Direct Toolchain Usage

## Native Tool Commands (Recommended)

### Ionosphere Research Configurations
```bash
# High-resolution analysis (nfft=4096-32768)
python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput

# Temporal characteristics study (overlap optimization)
python benchmarks/run_throughput.py --multirun experiment=ionosphere_temporal +benchmark=throughput

# Comprehensive multi-scale analysis
python benchmarks/run_latency.py experiment=ionosphere_multiscale +benchmark=latency

# Single experiment runs
python benchmarks/run_latency.py experiment=ionosphere_resolution +benchmark=latency
```

### Direct Hydra Usage
```bash
# Native Hydra multirun syntax (IMPORTANT: specify +benchmark=throughput for throughput tests)
python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput
python benchmarks/run_latency.py --multirun engine.nfft=1024,2048,4096,8192 +benchmark=latency

# Single experiments with parameter overrides
python benchmarks/run_latency.py experiment=baseline engine.nfft=8192 +benchmark=latency
python benchmarks/run_throughput.py experiment=ionosphere_temporal +benchmark=throughput

# Quick testing with lightweight config
python benchmarks/run_throughput.py --multirun experiment=ionosphere_test +benchmark=throughput
```

### Complete Research Workflow
```bash
# Run experiments (IMPORTANT: add +benchmark=throughput)
python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput

# Execute analysis pipeline
snakemake --cores 4 --snakefile experiments/Snakefile
snakemake --cores 4 generate_figures --snakefile experiments/Snakefile

# View results
mlflow ui --backend-store-uri file://./artifacts/mlruns

# Data versioning
dvc status
dvc repro
```

## Available Engine Configurations

| Engine | NFFT | Overlap | Batch | Use Case |
|--------|------|---------|-------|----------|
| `ionosphere_realtime` | 2048 | 0.625 | 8 | Real-time processing |
| `ionosphere_hires` | 8192 | 0.75 | 16 | High-resolution analysis |
| `ionosphere_longterm` | 4096 | 0.875 | 64 | Long-duration studies |

## Available Experiment Configurations

| Experiment | Description | Parameter Sweeps |
|------------|-------------|------------------|
| `ionosphere_resolution` | NFFT resolution study | nfft: 4096-32768, overlap: 0.5-0.875 |
| `ionosphere_temporal` | Temporal characteristics | overlap: 0.25-0.9375, batch: 16-128 |
| `ionosphere_multiscale` | Comprehensive analysis | Multi-engine, cross-scale sweeps |

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

**Important:** This workflow is for C++ development iteration only. For production profiling, always use `iprof` with Python benchmarks (see GPU Profiling section below).

### Quick Start with `ionoc`

The `ionoc` command provides a dedicated CLI for C++ benchmarking with preset configurations:

```powershell
# Quick validation (default: dev preset, 20 iter, ~10s)
ionoc bench

# Production latency benchmark
ionoc bench --preset latency --full

# Ionosphere realtime profiling
ionoc bench --preset realtime --ionosphere --profile
ionoc profile nsys --stats

# Custom experimentation
ionoc bench --preset throughput --nfft 4096 --batch 16 --quick

# Save baseline for regression tracking
ionoc bench --preset latency --full --save-baseline

# Full help
ionoc bench --help
```

### Build C++ Benchmark Executable
```bash
# Build both tests and benchmark executable
iono build   # or: ./scripts/cli.ps1 build
```

### Benchmark Presets

Multiple presets matching Python configurations:

```powershell
# dev (default): Quick validation
ionoc bench                                    # 20 iter, ~10s

# latency: Latency measurement
ionoc bench --preset latency --full            # 5000 iter, ~2min
ionoc bench --preset latency --ionosphere      # Higher resolution

# throughput: Throughput measurement
ionoc bench --preset throughput --full         # 10s duration
ionoc bench --preset throughput --ionosphere   # High-res batch processing

# realtime: Real-time streaming
ionoc bench --preset realtime --full           # 10s stream
ionoc bench --preset realtime --ionosphere     # Balanced, strict timing

# accuracy: Accuracy validation
ionoc bench --preset accuracy --full           # 10 iter, 8 signals
ionoc bench --preset accuracy --ionosphere     # High-res validation
```

### Profile C++ Directly (Development Only)

**Nsight Systems (Timeline Analysis)**
```powershell
# Basic profiling (auto-creates artifacts\profiling directory)
ionoc profile nsys

# With statistics
ionoc profile nsys --stats

# Custom mode and traces
ionoc profile nsys --mode quick --trace cuda,nvtx

# Custom output path
ionoc profile nsys --output my_profile --stats
```

**Nsight Compute (Kernel Analysis)**
```powershell
# Basic profiling (⚠️ slow - 5-15 minutes)
ionoc profile ncu

# Roofline analysis
ionoc profile ncu --set roofline

# Specific kernel only (faster)
ionoc profile ncu --kernel-name "fft_kernel"

# Full metrics (very slow)
ionoc profile ncu --set full --mode profile
```

**Advanced Options:**
```powershell
# All ionoc profile commands support:
# --mode <quick|profile|full>   Benchmark mode
# --output <path>                Custom output path
# Plus all native nsys/ncu flags (passthrough)

# Examples:
ionoc profile nsys --mode quick --duration 5
ionoc profile ncu --kernel-name "magnitude" --metrics sm__throughput
```

### Typical C++ Development Workflow
```powershell
# 1. Save baseline before modifications
ionoc bench --preset latency --full --save-baseline

# 2. Modify C++ executor/kernel code
vim cpp\src\executors\batch_executor.cpp

# 3. Rebuild
iono build

# 4. Quick validation (~10 seconds, compares to baseline)
ionoc bench

# 5. Full validation if quick looks good
ionoc bench --preset latency --full
# Performance card shows: ✓ NO CHANGE / ⚠ SLIGHT REGRESSION / ✗ REGRESSION

# 6. Profile if needed
ionoc bench --preset latency --profile
ionoc profile nsys --stats

# 7. View results
nsys-ui artifacts\profiling\cpp_dev.nsys-rep

# 8. Deep kernel analysis if needed (~5-15 minutes)
ionoc profile ncu --kernel-name "fft_kernel" --set roofline

# 9. Iterate until satisfied, then integrate with Python

# 10. Production profiling (end-to-end Python workflow)
iprof nsys latency    # Full Python end-to-end workflow
```

### When to Use Each Tool

| Tool | Purpose | Duration | Use When |
|------|---------|----------|----------|
| `ionoc bench` | Fast validation (dev preset) | 10s | Quick sanity check after code changes |
| `ionoc bench --preset <name> --profile` | Profile-ready benchmark | 30s-1min | Before running nsys/ncu profiling |
| `ionoc bench --preset <name> --full` | Production equivalent | 1-10min | Matching Python benchmark results |
| `ionoc profile nsys` | Timeline, API calls, NVTX | 30-60s | Understanding execution flow, bottlenecks |
| `ionoc profile ncu` | Kernel metrics, roofline | 5-15min | Optimizing specific kernel performance |
| `iprof` (Python) | **Production profiling** | Varies | **Final end-to-end validation** |

### Shortcuts

```powershell
icbench quick        # Alias for: ionoc bench quick
icprof nsys --stats  # Alias for: ionoc profile nsys --stats
```

### Troubleshooting

#### Character Encoding Issues (PowerShell)

**Note:** If you're using `scripts/init_pwsh.ps1` to start your dev session, UTF-8 encoding is **automatically configured** for you.

If you see garbled characters like `┬╡s` instead of `µs` in benchmark output (when NOT using `init_pwsh.ps1`):

```powershell
# Fix for current PowerShell session
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Then run benchmark
./build/windows-rel/benchmark_engine.exe --full
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
nsys profile -o artifacts\profiling\cpp_dev .\build\windows-rel\benchmark_engine.exe --profile
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
./build/windows-coverage/test_engine.exe            # Run tests
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
iprof nsys latency        # Uses profiling (20 iterations)
iprof nsys throughput     # Uses profiling_throughput (3s duration)
iprof nsys realtime       # Uses profiling_realtime (3s duration)
iprof nsys accuracy       # Uses profiling_accuracy (2 iterations, 3 signals)

# NCU profiling (slower but more detailed)
iprof ncu latency
iprof ncu throughput
```

#### Full Benchmark Profiling (Research/Production)
```bash
# Full benchmark profiles (SLOW - use sparingly!)
iprof nsys latency -- experiment=profiling +benchmark=latency        # 5000 iterations
iprof nsys throughput -- experiment=profiling +benchmark=throughput  # 10s duration
iprof nsys accuracy -- experiment=profiling +benchmark=accuracy      # 10 iterations, 8 signals
```

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

Last updated: 2025-10-14 (Expanded C++ benchmarking with preset system: latency, throughput, realtime, accuracy benchmarks with ionosphere variants)