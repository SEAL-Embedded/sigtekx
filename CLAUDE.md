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

Last updated: 2025-10-11 (Added window symmetry modes documentation and C++ code coverage with gcovr)