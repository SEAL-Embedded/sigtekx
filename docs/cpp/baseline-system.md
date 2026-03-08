# C++ Baseline System Documentation

## Overview

The C++ baseline system provides production-grade benchmark result tracking with collision safety, rich metadata, CSV export, and statistical comparison for regression detection. It complements the Python baseline system by focusing on C++ kernel development workflows.

**Key Features:**
- **Collision Safety**: File-locked manifest prevents data loss during concurrent benchmark saves
- **Rich Metadata**: Automatic capture of hardware (GPU, CPU, RAM), git info, and configuration
- **CSV Export**: Analysis-ready CSV files for each baseline
- **Statistical Comparison**: Automated regression detection with threshold-based classification
- **CLI Integration**: Intuitive `sigxc baseline` commands for management

## Architecture

### Storage Structure

Baselines are stored in `baselines/cpp/` (persistent location, survives `sigx clean`):

```
baselines/cpp/
├── latency_iono_full/
│   ├── metadata.json         # Configuration + hardware + git + metrics summary
│   ├── results.json          # Detailed benchmark results
│   ├── results.csv           # CSV export for analysis
│   └── README.md             # Human-readable summary (future)
├── throughput_ionox_full/
│   ├── metadata.json
│   ├── results.json
│   └── results.csv
└── .baseline_manifest.json   # Global manifest (file-locked)
```

### Metadata Schema

Each baseline includes comprehensive metadata in `metadata.json`:

```json
{
  "name": "latency_iono_full",
  "created": "2025-01-20T10:30:00Z",

  "config": {
    "preset": "latency",
    "run_mode": "full",
    "iono_variant": "iono",
    "nfft": 4096,
    "channels": 2,
    "overlap": 0.75,
    "sample_rate_hz": 48000,
    "exec_mode": "streaming"
  },

  "git": {
    "commit": "abc123def456...",
    "branch": "phase1",
    "dirty": false
  },

  "hardware": {
    "gpu": {
      "name": "NVIDIA GeForce RTX 3090 Ti",
      "memory_gb": 24,
      "compute_capability": "8.6",
      "cuda_runtime": "12.6",
      "cuda_driver": "561.09"
    },
    "cpu": {
      "model": "AMD Ryzen 9 5950X",
      "cores": 16,
      "threads": 32
    },
    "system": {
      "os": "Windows",
      "os_version": "11 23H2",
      "ram_gb": 64
    }
  },

  "metrics": {
    "mean_latency_us": 42.3,
    "p95_latency_us": 48.2,
    "p99_latency_us": 52.1,
    "cv": 0.076,
    "frames_processed": 5000
  }
}
```

### CSV Format

Each baseline includes a CSV export with configuration and metrics:

```csv
preset,iono_variant,mode,nfft,channels,overlap,sample_rate_hz,mean_latency_us,p50_latency_us,p95_latency_us,p99_latency_us,min_latency_us,max_latency_us,std_latency_us,cv,frames_processed,timestamp,git_commit
latency,iono,full,4096,2,0.75,48000,42.3,41.5,48.2,52.1,38.1,65.2,3.2,0.076,5000,2025-01-20T10:30:00Z,abc123
```

## Usage

### Saving Baselines

Baselines are automatically saved when using `--save-baseline` flag:

```powershell
# Run benchmark and save baseline
sigxc bench --preset latency --full --save-baseline

# With GPU clock locking for stable results
sigxc bench --preset latency --full --save-baseline --lock-clocks

# Custom configuration
sigxc bench --preset throughput --nfft 8192 --save-baseline

# All ionosphere variants save baselines
sigxc bench --preset latency --iono --save-baseline
sigxc bench --preset throughput --ionox --save-baseline
```

**Baseline naming convention:**
- Format: `{preset}_{iono_variant}_{mode}`
- Example: `latency_iono_full`, `throughput_ionox_quick`
- Automatically derived from benchmark configuration

### Listing Baselines

View all saved baselines:

```powershell
# List all baselines
sigxc baseline list

# Output:
# ========================================
#   C++ Baselines
# ========================================
#
# Name                            Preset          Mode         Variant    Created
# ---------------------------------------------------------------------------------------
# latency_iono_full               latency         full         iono       2025-01-20T10:30:00Z
# throughput_ionox_full           throughput      full         ionox      2025-01-20T11:15:00Z
#
# Total: 2 baseline(s)

# Filter by preset
sigxc baseline list --preset latency
```

### Comparing Baselines

Compare two baselines for regression detection:

```powershell
# Compare baselines
sigxc baseline compare pre_optimization post_optimization

# Output:
# ========================================
#   Baseline Comparison
# ========================================
#
# Baseline: pre_optimization
# Current:  post_optimization
#
# Metric                          Baseline      Current         Delta    % Change  Status
# ----------------------------------------------------------------------------------------
# Mean Latency (µs)                  42.30        38.50         -3.80      -9.0%    ↑
# P95 Latency (µs)                   48.20        43.10         -5.10     -10.6%    ↑
# P99 Latency (µs)                   52.10        47.80         -4.30      -8.3%    ↑
# Coefficient of Variation           0.076        0.082          0.01       7.9%    ⚠
#
# ✓ No significant regressions
```

**Status Indicators:**
- `=` (gray): No change (`< 1%`)
- `↑` (green): Improvement (better performance)
- `⚠` (yellow): Slight regression (`1-5%` worse)
- `↓` (red): Regression (`5-10%` worse)
- `🔴` (bright red): Major regression (`> 10%` worse)

**Exit Codes:**
- `0`: No regressions detected
- `1`: Regression detected (useful for CI/CD automation)

### Deleting Baselines

Remove obsolete baselines:

```powershell
# Delete with confirmation prompt
sigxc baseline delete old_baseline

# Delete without confirmation
sigxc baseline delete old_baseline --force
```

## Collision Safety

### File Locking Mechanism

The baseline system uses **file-locked manifest** to prevent data corruption during concurrent benchmark saves:

1. **Atomic Locking**: Platform-specific file locks (`LockFileEx` on Windows, `flock` on Linux)
2. **RAII Pattern**: Automatic lock release on completion, error, or crash
3. **Timeout Handling**: 10-second timeout with clear error messages
4. **Atomic Writes**: Manifest updates use temp file + rename pattern

### Concurrency Test

Verified safe for concurrent access:

```powershell
# Run 3 benchmarks in parallel (safe)
Start-Job { sigxc bench --preset latency --save-baseline }
Start-Job { sigxc bench --preset throughput --save-baseline }
Start-Job { sigxc bench --preset realtime --save-baseline }
Get-Job | Wait-Job

# Verify: 3 baseline directories exist, manifest has 3 entries, no corruption
ls baselines/cpp/
cat baselines/cpp/.baseline_manifest.json
```

## Regression Detection

### Threshold Classification

Comparison engine classifies changes using these thresholds:

| Change         | Threshold | Status               | Indicator |
|----------------|-----------|----------------------|-----------|
| No Change      | `< 1%`    | `NO_CHANGE`          | `=` (gray) |
| Slight Regression | `1-5%` | `SLIGHT_REGRESSION`  | `⚠` (yellow) |
| Regression     | `5-10%`   | `REGRESSION`         | `↓` (red) |
| Major Regression | `> 10%` | `MAJOR_REGRESSION`   | `🔴` (bright red) |
| Improvement    | Better    | `IMPROVEMENT`        | `↑` (green) |

### Directionality

The comparison engine understands metric directionality:

- **Lower is Better**: Latency metrics (mean, P95, P99), jitter, MAE, RMSE
- **Higher is Better**: Throughput metrics (FPS, GB/s, samples/s), compliance rate, pass rate, SNR

## Comparison by Benchmark Type

### Latency Comparison

Metrics compared:
- Mean Latency (µs) - lower is better
- P95 Latency (µs) - lower is better
- P99 Latency (µs) - lower is better
- Coefficient of Variation - lower is better

### Throughput Comparison

Metrics compared:
- Frames per Second - higher is better
- GB per Second - higher is better
- Samples per Second - higher is better

### Realtime Comparison

Metrics compared:
- Compliance Rate - higher is better
- Mean Latency (ms) - lower is better
- P99 Latency (ms) - lower is better
- Mean Jitter (ms) - lower is better

### Accuracy Comparison

Metrics compared:
- Pass Rate - higher is better
- Mean SNR (dB) - higher is better
- Mean MAE - lower is better
- Mean RMSE - lower is better

## Typical Workflows

### Development Iteration

```powershell
# 1. Save baseline before modifications
sigxc bench --preset latency --full --lock-clocks --save-baseline

# 2. Modify C++ executor/kernel code
# ... edit code ...

# 3. Rebuild
sigx build

# 4. Run benchmark again (overwrites baseline)
sigxc bench --preset latency --full --lock-clocks --save-baseline

# 5. Compare (if you saved separate named baselines)
sigxc baseline compare before_changes after_changes
```

### Phase Milestone Tracking

```powershell
# Before Phase 1 work
sigxc bench --preset latency --full --save-baseline
# Baseline saved as: latency_iono_full

# ... Phase 1 development work ...

# After Phase 1 work
sigxc bench --preset latency --full --save-baseline
# Overwrites baseline: latency_iono_full

# For tracking across phases, manually rename baselines:
# baselines/cpp/latency_iono_full -> baselines/cpp/phase1_latency_iono_full
```

### CI/CD Integration

```powershell
# Save reference baseline (one-time setup)
sigxc bench --preset latency --full --save-baseline
mv baselines/cpp/latency_iono_full baselines/cpp/latency_reference

# In CI pipeline
sigxc bench --preset latency --full --save-baseline
sigxc baseline compare latency_reference latency_iono_full

# Exit code 1 if regression detected
if ($LASTEXITCODE -ne 0) {
    Write-Error "Performance regression detected!"
    exit 1
}
```

## Implementation Details

### Core Components

**`cpp/benchmarks/utils/file_lock.hpp`**
- Cross-platform RAII file locking wrapper
- Platform-specific: `LockFileEx` (Windows), `flock` (Linux)
- Automatic cleanup on destruction

**`cpp/benchmarks/utils/hardware_info.hpp`**
- GPU detection: Device name, memory, compute capability, CUDA versions
- CPU detection: Brand string, cores, threads
- System detection: OS, OS version, RAM size

**`cpp/benchmarks/utils/git_info.hpp`**
- Git commit: `git rev-parse HEAD`
- Git branch: `git branch --show-current`
- Dirty flag: `git status --porcelain`
- Graceful fallback if git not available

**`cpp/benchmarks/utils/csv_writer.hpp`**
- CSV export functions for each benchmark type
- Proper escaping for quotes, commas, newlines
- Includes config, metrics, timestamp, git commit

**`cpp/benchmarks/utils/baseline_comparison.hpp`**
- Statistical comparison engine
- Regression detection logic
- Formatted output printer with ANSI color codes

**`cpp/benchmarks/core/persistence.hpp`**
- Manifest management (load/update/remove)
- Directory-based baseline storage
- Metadata generation
- CSV export integration

**`cpp/benchmarks/baseline_cli.cpp`**
- Standalone CLI helper executable
- Commands: list, compare, delete
- Integration with PowerShell wrapper

**`scripts/cli-cpp.ps1`**
- PowerShell wrapper for user-friendly CLI
- `sigxc baseline` command handler
- Forwards to `sigtekx_baseline_cli.exe`

### Testing

**Unit Tests** (`cpp/tests/benchmark/test_baseline_system.cpp` - future):
```cpp
// File locking
TEST(FileLockTest, AcquisitionAndRelease)
TEST(FileLockTest, ConcurrentAccess)
TEST(FileLockTest, TimeoutHandling)

// Manifest management
TEST(ManifestTest, LoadAndUpdate)
TEST(ManifestTest, ConcurrentUpdates)
TEST(ManifestTest, CorruptionRecovery)

// CSV generation
TEST(CSVWriterTest, LatencyFormat)
TEST(CSVWriterTest, ThroughputFormat)
TEST(CSVWriterTest, Escaping)

// Comparison
TEST(ComparisonTest, DeltaCalculation)
TEST(ComparisonTest, RegressionDetection)
TEST(ComparisonTest, ImprovementDetection)

// Hardware detection
TEST(HardwareInfoTest, GPUDetection)
TEST(HardwareInfoTest, CPUDetection)
TEST(HardwareInfoTest, SystemInfo)

// Git integration
TEST(GitInfoTest, CommitExtraction)
TEST(GitInfoTest, GracefulFallback)
```

**Concurrency Test**:
```cpp
std::vector<std::thread> threads;
for (int i = 0; i < 10; ++i) {
  threads.emplace_back([i]() {
    BenchmarkConfig config = create_latency_config();
    config.preset_name = "test_" + std::to_string(i);
    save_latency_baseline(config, results);
  });
}
for (auto& t : threads) t.join();

// Verify: manifest has exactly 10 entries
auto manifest = load_manifest();
EXPECT_EQ(manifest.baselines.size(), 10);
```

## Differences from Python Baseline System

| Feature                  | Python Baseline System | C++ Baseline System |
|--------------------------|------------------------|---------------------|
| **Storage Location**     | `baselines/`           | `baselines/cpp/`    |
| **Primary Use Case**     | Production experiment tracking | C++ kernel development iteration |
| **Phase Support**        | Yes (Phase 1, Phase 2, etc.) | No (simpler model) |
| **Scope Management**     | Yes (minimal, standard, full) | No (single scope) |
| **Integration**          | Integrated with experiment suite | Standalone C++ CLI |
| **CSV Format**           | Experiment-specific   | Benchmark-specific  |
| **Comparison Tool**      | Python-based analysis | C++ CLI tool |

**Design Philosophy**: Keep C++ baseline system **lean and focused** on C++ development workflows, avoiding over-engineering.

## Limitations and Future Work

### Current Limitations

1. **Manual Phase Tracking**: No automatic phase management (Phase 1, Phase 2, etc.)
2. **No Scope Management**: Single scope (unlike Python's minimal/standard/full)
3. **No Export Formats**: Only JSON and CSV (no HTML reports, JSON API, etc.)
4. **Network Drives**: Concurrent access on network drives not recommended (file locking limitations)

### Future Enhancements (Out of Scope)

- **Phase Support**: Add optional phase tagging (Phase 1, Phase 2, etc.)
- **Scope Management**: Add scope levels (minimal/standard/full) if needed
- **Export Formats**: HTML reports, JSON API endpoints
- **Integration**: Optional integration with Python BaselineManager
- **CI/CD**: Automated regression detection in CI pipelines
- **Web Dashboard**: Visualization of baseline trends over time

## Troubleshooting

### Baseline Not Saving

**Symptom**: `--save-baseline` flag doesn't create baseline directory

**Causes:**
1. Benchmark executable not built
2. Insufficient disk space
3. Permission issues

**Solution:**
```powershell
# Rebuild benchmark executable
sigx build

# Check disk space
Get-PSDrive C

# Check permissions (run as admin if needed)
Test-Path "baselines/cpp/" -IsValid
```

### Comparison Fails

**Symptom**: `sigxc baseline compare` fails with "Baseline not found"

**Causes:**
1. Baseline directory doesn't exist
2. Baseline name mismatch
3. Missing results.json file

**Solution:**
```powershell
# List available baselines
sigxc baseline list

# Check baseline directory structure
ls baselines/cpp/<baseline_name>/
# Should contain: results.json, metadata.json, results.csv

# Verify results.json exists
Test-Path "baselines/cpp/<baseline_name>/results.json"
```

### Cannot Compare Different Presets

**Symptom**: "Cannot compare baselines with different presets"

**Explanation**: Comparison only works for baselines of the same type (latency vs latency, throughput vs throughput, etc.)

**Solution:**
```powershell
# Verify preset types match
sigxc baseline list
# Compare only baselines with same preset column
```

### Hardware Detection Fails

**Symptom**: Hardware info shows "Unknown GPU" or "Unknown CPU"

**Causes:**
1. GPU driver issues
2. CUDA runtime not available
3. System API access issues

**Solution:**
```powershell
# Check CUDA availability
nvidia-smi

# Verify CUDA runtime
nvcc --version

# System info (should work even if GPU fails)
systeminfo
```

### Git Info Not Captured

**Symptom**: Git commit shows "unknown" in metadata

**Causes:**
1. Not in a git repository
2. Git not installed
3. Git command not in PATH

**Solution:**
```powershell
# Check git availability
git --version

# Verify repository
git status

# Manual git info query
git rev-parse HEAD
git branch --show-current
```

## See Also

- **Python Baseline System**: `src/sigtekx/utils/baseline.py`
- **GPU Clock Locking**: `docs/performance/gpu-clock-locking.md`
- **CLAUDE.md C++ Development Workflow**: Quick reference for `sigxc` commands
- **CLAUDE.md**: Quick reference for CLI commands
