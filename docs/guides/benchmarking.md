# Benchmarking Guide

Comprehensive guide to the ionosense-hpc benchmarking suite for performance evaluation, optimization, and research using the integrated CLI platform.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [CLI Benchmark Commands](#cli-benchmark-commands)
- [Benchmark Types](#benchmark-types)
- [Parameter Sweeps](#parameter-sweeps)
- [Research Workflows](#research-workflows)
- [Profiling with Nsight](#profiling-with-nsight)
- [Reporting and Visualization](#reporting-and-visualization)
- [Best Practices](#best-practices)
- [Interpreting Results](#interpreting-results)
 - [Output Locations](#output-locations)

## Overview

The ionosense-hpc benchmarking suite provides research-grade performance evaluation following RSE (Research Software Engineering) and IEEE standards. It ensures reproducible, statistically rigorous benchmarking with comprehensive reporting, all accessible through the unified CLI platform.

### Key Features

- **Statistical Rigor**: Confidence intervals, outlier detection, and distribution analysis
- **Reproducibility**: Environment capture, deterministic seeding, and versioning
- **CLI Integration**: Seamless workflows for all benchmarking tasks
- **Flexibility**: Custom benchmarks, parameter sweeps, and workflow orchestration
- **Visualization**: Publication-quality plots and reports
- **NVTX Integration**: Deep profiling with NVIDIA Nsight tools

## Quick Start

### Linux/WSL2

```bash
# Run default benchmark suite
./scripts/cli.sh bench suite

# Run specific benchmark
./scripts/cli.sh bench latency

# Run with custom configuration
./scripts/cli.sh bench throughput --config high_performance.yaml

# Generate report afterwards
./scripts/cli.sh report results/
```

### Windows (Enhanced Development Shell)

```powershell
# Start development shell
.\scripts\open_dev_pwsh.ps1

# Run default benchmark suite
ibench suite                    # or 'iono bench suite'

# Run specific benchmark
ibench latency                  # or 'iono bench latency'

# Run with custom configuration
ibench throughput --config high_performance.yaml

# Generate report afterwards
iono report results/
```

## CLI Benchmark Commands

### Basic Benchmarks

**Linux/WSL2:**
```bash
# Available benchmarks
./scripts/cli.sh info benchmarks      # List all available benchmarks

# Run individual benchmarks
./scripts/cli.sh bench latency        # Latency benchmark
./scripts/cli.sh bench throughput     # Throughput benchmark
./scripts/cli.sh bench accuracy       # Accuracy validation
./scripts/cli.sh bench realtime       # Real-time performance
./scripts/cli.sh bench scaling        # Scaling analysis

# Run complete suite
./scripts/cli.sh bench suite          # All benchmarks with default config
./scripts/cli.sh bench suite --config research.yaml  # Custom config
```

**Windows (Development Shell):**
```powershell
# Available benchmarks
iono info benchmarks                  # List all available benchmarks

# Run individual benchmarks
ibench latency                        # Latency benchmark
ibench throughput                     # Throughput benchmark
ibench accuracy                       # Accuracy validation
ibench realtime                       # Real-time performance
ibench scaling                        # Scaling analysis

# Run complete suite
ibench suite                          # All benchmarks with default config
ibench suite --config research.yaml  # Custom config
```

### Advanced Benchmark Options

```bash
# Linux/WSL2
./scripts/cli.sh bench latency --output results/latency_test --report
./scripts/cli.sh bench suite --config validation.yaml --output validation_run

# Windows (development shell)
ibench latency --output results/latency_test --report
ibench suite --config validation.yaml --output validation_run
```

## Benchmark Types

### 1. Latency Benchmark

Measures end-to-end processing latency with microsecond precision.

**CLI Usage:**
```bash
# Linux/WSL2
./scripts/cli.sh bench latency
./scripts/cli.sh bench latency --config latency_config.yaml

# Windows (dev shell)
ibench latency
ibench latency --config latency_config.yaml
```

**Programmatic Usage:**

**Metrics**:
- Mean, median, and percentile latencies
- Jitter analysis
- Deadline compliance
- Distribution characteristics

### 2. Throughput Benchmark

Measures sustained processing throughput and resource utilization.

**CLI Usage:**
```bash
# Linux/WSL2
./scripts/cli.sh bench throughput
./scripts/cli.sh bench throughput --config throughput_config.yaml

# Windows (dev shell)
ibench throughput
ibench throughput --config throughput_config.yaml
```

**Programmatic Usage:**

**Metrics**:
- Frames per second
- Data throughput (GB/s)
- GPU utilization
- Memory bandwidth

### 3. Accuracy Benchmark

Validates numerical accuracy against reference implementations.

**CLI Usage:**
```bash
# Linux/WSL2
./scripts/cli.sh bench accuracy
./scripts/cli.sh validate                # Alias for accuracy benchmark

# Windows (dev shell)
ibench accuracy
ival                                    # Alias for accuracy benchmark
```

**Programmatic Usage:**

**Validation Tests**:
- Spectral accuracy
- Parseval's theorem
- Linearity
- Numerical stability

### 4. Real-time Benchmark

Simulates real-time streaming with deadline constraints.

**CLI Usage:**
```bash
# Linux/WSL2
./scripts/cli.sh bench realtime

# Windows (dev shell)
ibench realtime
```

**Programmatic Usage:**
```python
from ionosense_hpc.benchmarks import RealtimeBenchmark, RealtimeBenchmarkConfig

config = RealtimeBenchmarkConfig(
    name="realtime_test",
    stream_duration_s=60.0,
    frame_deadline_ms=10.0,
    strict_timing=True
)

benchmark = RealtimeBenchmark(config)
result = benchmark.run()

print(f"Deadline compliance: {result.statistics['deadline_compliance_rate']:.1%}")
print(f"Dropped frames: {result.statistics['frames_dropped']}")
```

### 5. Scaling Benchmark

Analyzes performance scaling with different parameters.

**CLI Usage:**
```bash
# Linux/WSL2
./scripts/cli.sh bench scaling

# Windows (dev shell)
ibench scaling
```

**Programmatic Usage:**
```python
from ionosense_hpc.benchmarks import ScalingBenchmark

benchmark = ScalingBenchmark()
results = benchmark.run_scaling_analysis()

print(f"Optimal channel count: {results['channels_scaling']['optimal_batch']}")
print(f"Optimal FFT size: {results['nfft_scaling']['optimal_nfft']}")
```

## Parameter Sweeps

Parameter sweeps allow systematic exploration of configuration space using the CLI.

### CLI Parameter Sweep Commands

**Linux/WSL2:**
```bash
# Run parameter sweep
./scripts/cli.sh sweep experiment_config.yaml

# Run parallel sweep
./scripts/cli.sh sweep experiment_config.yaml --parallel --workers 4

# Specify output directory
./scripts/cli.sh sweep experiment_config.yaml --output sweep_results/
```

**Windows (Development Shell):**
```powershell
# Run parameter sweep
iono sweep experiment_config.yaml

# Run parallel sweep
iono sweep experiment_config.yaml --parallel --workers 4

# Specify output directory
iono sweep experiment_config.yaml --output sweep_results/
```

### Grid Search Example

Create `grid_search.yaml`:
```yaml
name: grid_search_experiment
benchmark_class: "ionosense_hpc.benchmarks.LatencyBenchmark"
sweep_type: grid

parameters:
  - name: "engine_config.nfft"
    values: [256, 512, 1024, 2048, 4096]
  - name: "engine_config.channels"
    range:
      start: 1
      stop: 32
      step: 1

base_config:
  iterations: 100
  warmup_iterations: 10
```

**Run:**
```bash
# Linux/WSL2
./scripts/cli.sh sweep grid_search.yaml

# Windows (dev shell)
iono sweep grid_search.yaml
```

### Random Search Example

Create `random_search.yaml`:
```yaml
name: random_search_experiment
sweep_type: random
n_samples: 100

parameters:
  - name: "engine_config.nfft"
    values: [512, 1024, 2048]
  - name: "engine_config.overlap"
    values: [0.0, 0.25, 0.5, 0.75]
```

### Latin Hypercube Sampling

Create `lhs_search.yaml`:
```yaml
name: lhs_experiment
sweep_type: latin_hypercube
n_samples: 50

parameters:
  - name: "engine_config.nfft"
    range: [256, 4096]
  - name: "engine_config.channels"
    range: [1, 16]
```

## Research Workflows

### Complete Research Pipeline

**CLI Workflow:**
```bash
# Linux/WSL2
./scripts/cli.sh bench suite --config research.yaml --output study_results/
./scripts/cli.sh sweep parameter_study.yaml --output sweep_results/
./scripts/cli.sh report study_results/ --format pdf --title "Performance Study"

# Windows (dev shell)
ibench bench latency
ibench sweep nfft_channels_sweep -Benchmark latency -Multirun
ibench report
```

**Programmatic Workflow:**
```powershell
python benchmarks/run_latency.py experiment=baseline
python benchmarks/run_latency.py --multirun experiment=nfft_channels_sweep
snakemake --cores 4 --snakefile experiments/Snakefile
```

### Reproducibility Features

**Environment Capture:**
```bash
# Linux/WSL2
./scripts/cli.sh info system > environment_snapshot.txt
./scripts/cli.sh doctor --verbose >> environment_snapshot.txt

# Windows (dev shell)
iono info system > environment_snapshot.txt
iono doctor --verbose >> environment_snapshot.txt
```

**Result Archiving:**
```python
from ionosense_hpc.utils.archiving import DataArchiver

archiver = DataArchiver()  # defaults to standardized benchmark_results/<name> paths
archiver.archive_results(
    results,
    experiment_name="optimization_study",
    metadata={
        "git_commit": "abc123",
        "hardware": "RTX 4000 Ada"
    }
)
```

## Profiling with Nsight

The CLI provides integrated profiling with NVIDIA Nsight tools.

### Nsight Systems Profiling

**Linux/WSL2:**
```bash
# Quick profile
./scripts/cli.sh profile nsys latency

# Full profile with all traces
./scripts/cli.sh profile nsys latency --full

# Profile with custom config
./scripts/cli.sh profile nsys throughput --config high_perf.yaml

# Auto-open report
./scripts/cli.sh profile nsys latency --open-report

# Auto-open in Nsight GUI
./scripts/cli.sh profile nsys latency --open-gui
```

**Windows (Development Shell):**
```powershell
# Quick profile using aliases
iprof nsys latency              # or 'iono profile nsys latency'
ipq                            # Quick profile alias

# Full profile
iprof nsys latency --full
ipf                            # Full profile alias

# Profile with custom config
iprof nsys throughput --config high_perf.yaml

# Auto-open report
iprof nsys latency --open-report

# Auto-open in Nsight GUI
iprof nsys latency --open-gui
```

### Nsight Compute Profiling

**Linux/WSL2:**
```bash
# Kernel-level profiling
./scripts/cli.sh profile ncu latency

# Full metrics set
./scripts/cli.sh profile ncu latency --full
```

**Windows (Development Shell):**
```powershell
# Kernel-level profiling
iprof ncu latency              # or 'iono profile ncu latency'

# Full metrics set
iprof ncu latency --full
```

### Profile Output

Profiling reports are saved to `build/nsight_reports/`:
```
build/nsight_reports/
├── nsys_reports/
│   ├── latency_quick_20250101_120000.nsys-rep
│   └── throughput_full_20250101_121500.nsys-rep
└── ncu_reports/
    ├── latency_basic_20250101_120300.ncu-rep
    └── latency_full_20250101_120800.ncu-rep
```

## Reporting and Visualization

### Generate Reports with CLI

**Linux/WSL2:**
```bash
# Basic report
./scripts/cli.sh report results/ --format pdf

# Comprehensive report
./scripts/cli.sh report results/ --format pdf --type comprehensive --title "Research Study"

# HTML report for web viewing
./scripts/cli.sh report results/ --format html

# Comparative analysis
./scripts/cli.sh report results/ --type comparative
```

**Windows (Development Shell):**
```powershell
# Basic report
iono report results/ --format pdf

# Comprehensive report
iono report results/ --format pdf --type comprehensive --title "Research Study"

# HTML report for web viewing
iono report results/ --format html

# Comparative analysis
iono report results/ --type comparative
```

### Report Types

1. **Standard Report**: Individual benchmark analysis
2. **Comparative Report**: Multiple run comparison
3. **Sweep Report**: Parameter sweep analysis
4. **Comprehensive Report**: Full research analysis

### Programmatic Reporting

```python
from ionosense_hpc.utils.reporting import BenchmarkReport, ReportConfig

config = ReportConfig(
    title="Performance Evaluation Report",
    author="Research Team",
    include_violin_plots=True,
    include_histograms=True,
    include_correlation=True,
    output_format="pdf"
)

report = BenchmarkReport(results, config)
report.generate("report.pdf")
```

## Best Practices

### 1. Environment Preparation

**Verify Environment:**
```bash
# Linux/WSL2
./scripts/cli.sh doctor           # Check all dependencies
./scripts/cli.sh info system      # Verify system configuration

# Windows (dev shell)
iono doctor                       # Check all dependencies
iono info system                  # Verify system configuration
```

**GPU Preparation:**
```bash
# Set GPU to base clocks (if using NVIDIA driver tools)
sudo nvidia-smi -lgc BASE_CLOCK,BASE_CLOCK

# Monitor GPU during benchmarks
./scripts/cli.sh monitor          # Linux/WSL2
imon                             # Windows (dev shell)
```

### 2. Benchmark Configuration

**Use Configuration Files:**
```yaml
# benchmark_config.yaml
name: research_benchmark
iterations: 1000
warmup_iterations: 100
confidence_level: 0.95
outlier_threshold: 3.0

engine_config:
  nfft: 1024
  channels: 2
  overlap: 0.5
  sample_rate_hz: 48000

output_settings:
  save_raw_data: true
  format: json
  generate_plots: true
```

**Run with Configuration:**
```bash
# Linux/WSL2
./scripts/cli.sh bench latency --config benchmark_config.yaml

# Windows (dev shell)
ibench latency --config benchmark_config.yaml
```

### 3. Multiple Runs for Statistical Significance

**Automated Multiple Runs:**
```bash
# Create multiple run script
for i in {1..5}; do
    ./scripts/cli.sh bench suite --output "run_$i/"
done

# Then generate comparative report
./scripts/cli.sh report . --type comparative
```

### 4. Systematic Parameter Studies

**Organized Sweep Studies:**
```bash
# Linux/WSL2
./scripts/cli.sh sweep nfft_study.yaml --output nfft_sweep/
./scripts/cli.sh sweep batch_study.yaml --output batch_sweep/
./scripts/cli.sh report nfft_sweep/ --type sweep

# Windows (dev shell)
iono sweep nfft_study.yaml --output nfft_sweep/
iono sweep batch_study.yaml --output batch_sweep/
iono report nfft_sweep/ --type sweep
```

## Interpreting Results

### Key Metrics

| Metric | Description | Good Range |
|--------|-------------|------------|
| Mean Latency | Average processing time | < 200 μs (real-time) |
| P99 Latency | 99th percentile latency | < 1.5x mean |
| Coefficient of Variation | Relative variability | < 0.1 |
| Deadline Compliance | % meeting deadline | > 99% |
| Throughput | Frames per second | > 1000 FPS |
| GPU Utilization | GPU usage | 80-95% |

### CLI Analysis Commands

**Quick Performance Check:**
```bash
# Linux/WSL2
./scripts/cli.sh bench latency | grep "Mean latency"
./scripts/cli.sh info devices    # Check GPU status

# Windows (dev shell)
ibench latency | grep "Mean latency"
iono info devices                # Check GPU status
```

### Common Performance Issues

1. **High Variability (CV > 0.2)**
   - **Diagnosis**: Run `./scripts/cli.sh monitor` during benchmark
   - **Solutions**: Increase warmup, check thermal throttling

2. **Poor Scaling**
   - **Diagnosis**: `./scripts/cli.sh bench scaling`
   - **Solutions**: Optimize memory access, check PCIe bandwidth

3. **Low GPU Utilization**
   - **Diagnosis**: `./scripts/cli.sh profile nsys benchmark --full`
   - **Solutions**: Increase channel count, optimize kernel launch

### Performance Optimization Workflow

```bash
# Linux/WSL2
./scripts/cli.sh bench scaling                    # Identify bottlenecks
./scripts/cli.sh profile nsys throughput --full   # Detailed analysis
./scripts/cli.sh sweep optimization_study.yaml    # Parameter optimization

# Windows (dev shell)
ibench scaling                                    # Identify bottlenecks
iprof nsys throughput --full                     # Detailed analysis
iono sweep optimization_study.yaml               # Parameter optimization
```

## Advanced Features

### Continuous Benchmarking

**Integrate with CI/CD:**
```yaml
# .github/workflows/benchmark.yml
name: Performance Benchmarks
on: [push, pull_request]

jobs:
  benchmark:
    runs-on: [self-hosted, gpu]
    steps:
      - uses: actions/checkout@v2
      - name: Run benchmarks
        run: ./scripts/cli.sh bench suite --output results/
      - name: Compare with baseline
        run: ./scripts/cli.sh report results/ --type comparative
```

### Custom Benchmark Integration

**Add to CLI workflow:**
```python
# In ionosense_hpc/benchmarks/custom_benchmark.py
from ionosense_hpc.benchmarks import BaseBenchmark

class CustomBenchmark(BaseBenchmark):
    def setup(self):
        # Setup code
        pass
    
    def execute_iteration(self):
        # Benchmark code
        return {"metric": value}
    
    def teardown(self):
        # Cleanup code
        pass
```

**Run via CLI:**
```bash
# Linux/WSL2
./scripts/cli.sh bench custom_benchmark

# Windows (dev shell)
ibench custom_benchmark
```

## Troubleshooting

### CLI Issues

**Command Not Found:**
```bash
# Linux/WSL2: Check script permissions
chmod +x scripts/cli.sh

# Windows: Use development shell
.\scripts\open_dev_pwsh.ps1
```

**Benchmark Failures:**
```bash
# Check environment
./scripts/cli.sh doctor         # Linux/WSL2
iono doctor                     # Windows (dev shell)

# Check GPU access
./scripts/cli.sh info devices   # Linux/WSL2
iono info devices               # Windows (dev shell)
```

### Performance Issues

**Inconsistent Results:**
```bash
# Increase warmup iterations
./scripts/cli.sh bench latency --config extended_warmup.yaml

# Check for thermal throttling
./scripts/cli.sh monitor        # Linux/WSL2
imon                           # Windows (dev shell)
```

**Low Performance:**
```bash
# Profile with Nsight
./scripts/cli.sh profile nsys latency --full    # Linux/WSL2
ipf                                             # Windows (dev shell)

# Check scaling behavior
./scripts/cli.sh bench scaling                  # Linux/WSL2
ibench scaling                                  # Windows (dev shell)
```

## References

- **CLI Help**: `./scripts/cli.sh help` / `iono help`
- **System Info**: `./scripts/cli.sh info` / `iono info`
- [NVIDIA Nsight Systems User Guide](https://docs.nvidia.com/nsight-systems/)
- [CUDA Best Practices Guide](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/)
- [IEEE Standard for Floating-Point Arithmetic](https://ieeexplore.ieee.org/document/8766229)
## Output Locations

By default, all benchmark artifacts are written under the repository `artifacts/` tree to keep the workspace clean and aligned with RSE/RE standards:

- Benchmarks: `artifacts/data/<benchmark_name>_<config>.{parquet,csv}`
- Research workflows and sweeps: `artifacts/experiments/<workflow_or_experiment_id>/`
- Reports and test outputs: `artifacts/reports/`

You can override these locations with environment variables (useful for CI or custom storage):

- `IONO_OUTPUT_ROOT`: root directory for all outputs
- `IONO_BENCH_DIR`: benchmark results root
- `IONO_EXPERIMENTS_DIR`: experiments root
- `IONO_REPORTS_DIR`: reports root

The CLI initializes these variables automatically to point to `artifacts/` so Python tools and the CLI are consistent.

