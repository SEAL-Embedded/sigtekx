# C++ Standalone Benchmarking

## Quick Start with `ionoc`

The `ionoc` CLI provides a streamlined interface for C++ benchmarking and profiling:

```powershell
# Build the benchmark
iono build

# Quick validation (~10 seconds)
ionoc bench quick

# Profile with Nsight Systems (auto-creates directories)
ionoc profile nsys --stats

# View results
nsys-ui artifacts\profiling\cpp_dev.nsys-rep

# Full help
ionoc help
```

## Purpose

This standalone C++ benchmark is designed for **development-time iteration** when working on new executors, kernels, or CUDA optimizations BEFORE Python integration.

**This is NOT for production profiling.** For production profiling, always use `iprof` with Python benchmarks to validate the entire end-to-end workflow.

## Commands Overview

| Command | Purpose | Duration |
|---------|---------|----------|
| `ionoc bench quick` | Fast validation | ~10s |
| `ionoc bench profile` | Profile-ready benchmark | ~30s |
| `ionoc bench full` | Production equivalent | ~2min |
| `ionoc profile nsys` | Timeline profiling | ~1min |
| `ionoc profile ncu` | Kernel analysis | ~5-15min |

## Usage Modes

| Mode | Iterations | Duration | Use Case |
|------|-----------|----------|----------|
| `--quick` | 20 | ~10s | Quick sanity check after code changes |
| `--profile` | 100 | ~30s | Before running nsys/ncu profiling |
| `--full` | 5000 | ~2min | Production-equivalent benchmark |

## Configuration

The benchmark uses hardcoded configuration matching the Python `profiling` experiment:
- NFFT: 2048
- Batch: 4
- Overlap: 0.625
- Sample Rate: 48000 Hz
- Warmup: 5 iterations

## Output

The benchmark outputs:
1. **Console statistics**: Mean, P50, P95, P99, Min, Max, Std Dev latencies
2. **CSV line**: For scripting/automation
3. **NVTX markers**: For profiling tools to visualize phases

## Profiling Workflow

All profiling is now handled through the `ionoc` CLI, which automatically creates directories and handles path conversions.

### Nsight Systems (Timeline Analysis)
```powershell
# Basic profile (auto-creates artifacts\profiling)
ionoc profile nsys

# With statistics
ionoc profile nsys --stats

# Custom mode and traces
ionoc profile nsys --mode quick --trace cuda,nvtx

# View results
nsys-ui artifacts\profiling\cpp_dev.nsys-rep
```

### Nsight Compute (Kernel Analysis)
```powershell
# Basic profile (⚠️ slow - 5-15 minutes)
ionoc profile ncu

# Roofline analysis
ionoc profile ncu --set roofline

# Specific kernel only (faster)
ionoc profile ncu --kernel-name "fft_kernel"

# Full metrics (very slow)
ionoc profile ncu --set full --mode profile

# View results
ncu-ui artifacts\profiling\cpp_dev_ncu.ncu-rep
```

### Advanced Profiling Options

```powershell
# All profiling commands support:
# --mode <quick|profile|full>   Benchmark mode
# --output <path>                Custom output path
# Plus all native nsys/ncu flags

# Examples:
ionoc profile nsys --mode quick --duration 5
ionoc profile ncu --kernel-name "magnitude_kernel" --metrics sm__throughput
```

## Development Workflow

```powershell
# 1. Modify C++ code
vim cpp\src\executors\batch_executor.cpp

# 2. Rebuild
iono build

# 3. Quick validation
ionoc bench quick

# 4. Profile if results look good
ionoc profile nsys --stats

# 5. Analyze in GUI
nsys-ui artifacts\profiling\cpp_dev.nsys-rep

# 6. Analyze specific kernel if needed
ionoc profile ncu --kernel-name "fft_kernel" --set roofline

# 7. Iterate until satisfied

# 8. Integrate with Python and do production profiling
iprof nsys latency    # Full end-to-end Python workflow
```

## Integration with Executor Refactor

When testing your new executor architecture:

1. **Baseline**: Profile with current `ResearchEngine` implementation
2. **Modify**: Swap in new `BatchExecutor` or `RealtimeExecutor`
3. **Compare**: Run benchmark and compare latency/throughput metrics
4. **Validate**: Ensure no performance regression (<5% overhead target)

Example comparison:
```bash
# Before refactor
./build/windows-rel/benchmark_engine.exe --full > results_before.txt

# After refactor (modify engine code)
./scripts/cli.ps1 build
./build/windows-rel/benchmark_engine.exe --full > results_after.txt

# Compare
diff results_before.txt results_after.txt
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
./build/windows-rel/benchmark_engine.exe --full
```

**Best solution:** Use `scripts/init_pwsh.ps1` to start dev sessions (handles this automatically).

**Alternative:** Use Windows Terminal (proper UTF-8 support by default).

### Profiling Directory Errors

**Note:** `ionoc` automatically creates the `artifacts\profiling` directory, so this error should not occur when using the CLI.

If you're running nsys/ncu directly (not through `ionoc`) and see "No such file or directory":

```powershell
# Solution: Use ionoc instead (recommended)
ionoc profile nsys --stats

# Or manually create directory
New-Item -ItemType Directory -Path artifacts\profiling -Force | Out-Null
```

## Notes

- **No Python dependencies**: This executable is pure C++/CUDA
- **NVTX enabled**: All benchmark phases have NVTX markers for profiling
- **Deterministic**: Uses fixed random seed for reproducibility
- **Quick iteration**: Fast rebuild-test cycle for C++ development
- **UTF-8 output**: Uses proper scientific notation (µs), may need encoding fix in legacy consoles

## See Also

- Full documentation: `CLAUDE.md` → "C++ Development Workflow"
- Python profiling: `iprof nsys latency` (production workflow)
- Test suite: `./scripts/cli.ps1 test cpp`
