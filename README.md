# Ionosense-HPC

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![CUDA 13.0+](https://img.shields.io/badge/CUDA-13.0+-green.svg)](https://developer.nvidia.com/cuda-toolkit)

High-performance CUDA FFT engine and research-grade benchmarking suite for real-time signal processing and ionospheric physics research.

## Overview

Ionosense-HPC provides a Python interface to a high-performance CUDA-based signal processing engine, optimized for real-time FFT analysis with sub-200μs latency. The project includes a comprehensive research infrastructure following Research Software Engineering (RSE) best practices for reproducible computational experiments.

### Key Features

- **🚀 High-Performance GPU Computing**: CUDA-accelerated FFT pipeline with asynchronous multi-stream execution
- **🐍 Clean Python API**: Type-safe interface with Pydantic configuration and context managers
- **🔬 Research Infrastructure**: Hydra configuration, Snakemake workflows, MLflow tracking, DVC versioning
- **📊 Professional Benchmarking**: Statistical analysis with latency, throughput, accuracy, and real-time metrics
- **⚡ Sub-200μs Latency**: Optimized for real-time signal processing applications
- **🎯 Domain-Specific**: Ready-to-use configurations for ionospheric scintillation research
- **📈 NVTX Profiling**: Built-in support for NVIDIA Nsight Systems and Compute
- **🔧 Developer-Friendly**: Comprehensive CLI with convenient aliases

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Researcher                                             │
│  ↓                                                       │
│  Hydra Configuration (YAML-based experiments)           │
│  ↓                                                       │
│  Python API (ionosense_hpc.Engine)                      │
│  ├── Pydantic Config Models                             │
│  ├── Benchmark Framework (Latency/Throughput/Accuracy)  │
│  └── Utilities (Signals, Device, Profiling)             │
│  ↓                                                       │
│  C++ Backend (BatchExecutor/StreamingExecutor pybind11) │
│  ├── Direct Executor Interface (no facade layer)        │
│  ├── Async Processing Pipeline (multi-stream)           │
│  └── Optimized CUDA Kernels (STFT pipeline)             │
│  ↓                                                       │
│  GPU (CUDA FFT + Custom Kernels)                        │
│  ↓                                                       │
│  MLflow (Tracking) + DVC (Versioning)                   │
│  ↓                                                       │
│  Snakemake (Analysis Pipeline)                          │
└─────────────────────────────────────────────────────────┘
```

## Requirements

### System Requirements
- **OS**: Windows 11 (primary), Linux (experimental)
- **GPU**: NVIDIA GPU with compute capability 6.0+ (Pascal or newer)
- **RAM**: 8GB+ (16GB recommended for large experiments)

### Software Requirements
- **Python**: 3.11 or higher
- **CUDA Toolkit**: 13.0 or higher
- **Visual Studio 2022**: with C++ build tools
- **CMake**: 3.26+
- **PowerShell**: 7.0+ (Windows)
- **Conda/Miniconda**: For environment management

## Installation

### Quick Start

```powershell
# 1. Clone repository
git clone --recursive https://github.com/your-org/ionosense-hpc.git
cd ionosense-hpc

# 2. Start development shell (sets up MSVC, conda, aliases)
.\scripts\init_pwsh.ps1 -Interactive

# 3. Setup environment and build
iono setup          # Creates conda env, installs dependencies
iono build          # Builds C++ backend

# 4. Verify installation
iono doctor         # Check environment health
iono test           # Run test suite
```

### Detailed Installation

See [INSTALL.md](docs/INSTALL.md) for platform-specific instructions, troubleshooting, and advanced configuration.

## Quick Usage

### Python API

```python
from ionosense_hpc import Engine
import numpy as np

# Create engine with default preset (1024 FFT, sub-200μs latency)
with Engine(preset='default') as engine:
    # Generate or load signal data
    signal = np.random.randn(engine.config.nfft * engine.config.channels).astype(np.float32)

    # Process signal (GPU-accelerated FFT)
    spectrum = engine.process(signal)

    # Access performance metrics
    stats = engine.stats
    print(f"Latency: {stats['latency_us']:.1f} μs")
    print(f"Throughput: {stats['throughput_gbps']:.2f} GB/s")
    print(f"Output shape: {spectrum.shape}")
```

### Key Terminology

Ionosense-HPC uses industry-standard terminology for signal processing dimensions (v0.9.5+):

```
┌──────────────────────────────────────────────────────┐
│  Signal Processing Dimensions                        │
├──────────────────────────────────────────────────────┤
│  SPATIAL:  channels  (independent signal streams)    │
│             Example: 2 channels = dual-antenna setup │
│                                                       │
│  TEMPORAL: frames    (time windows for STFT)         │
│             Example: 512 frames = 512 FFT windows    │
│                                                       │
│  SPECTRAL: nfft      (FFT window size)               │
│             Example: nfft=4096 → 2049 frequency bins │
└──────────────────────────────────────────────────────┘
```

**Important parameters:**
- `channels`: Number of independent signal streams (e.g., dual-antenna = 2)
- `nfft`: FFT window size (must be power of 2)
- `overlap`: Overlap between consecutive frames (0.0-1.0)
- `hop_size`: Samples between frame starts = `nfft * (1 - overlap)`

**Note:** In v0.9.4, `batch` was renamed to `channels` for clarity and industry alignment.

### Configuration Presets

```python
from ionosense_hpc import Engine

# Available presets for different use cases
engine_default = Engine(preset='default')  # General-purpose (1024 FFT)
engine_iono = Engine(preset='iono')        # Ionosphere research (4096 FFT, 0.75 overlap)
engine_ionox = Engine(preset='ionox')      # Extreme ionosphere (8192 FFT, 0.9 overlap)

# Override preset parameters
engine = Engine(preset='iono', nfft=8192, mode='streaming')
```

### Custom Configuration

```python
from ionosense_hpc import Engine, EngineConfig

# Full custom configuration
config = EngineConfig(
    nfft=4096,                 # FFT size
    channels=8,                # Number of signal channels
    overlap=0.75,              # Window overlap
    sample_rate_hz=48000,      # Sampling rate
    window='blackman',         # Window function
    mode='batch',              # Execution mode
    enable_profiling=True      # NVTX markers
)

engine = Engine(config=config)

# Or use factory method from preset
config = EngineConfig.from_preset('iono', nfft=8192, overlap=0.875)
engine = Engine(config=config)
```

## Development Commands

### Essential CLI Commands

The development shell provides the `iono` command for all development tasks:

```powershell
# Environment Setup
iono setup                      # Create conda environment & install package
iono doctor                     # Check environment health

# Building
iono build                      # Build release configuration
iono build --debug              # Build debug configuration
iono build --clean              # Clean rebuild
iono build --verbose            # Verbose build output

# Testing
iono test                       # Run all tests (Python + C++)
iono test python                # Python tests only
iono test cpp                   # C++ tests only
iono test --coverage            # With coverage report
iono test --verbose             # Verbose output

# Code Quality
iono format                     # Format C++ code (clang-format)
iono format --check             # Check formatting without changes
iono lint                       # Lint Python code (ruff)
iono lint --fix                 # Auto-fix lint issues

# Utilities
iono clean                      # Remove build artifacts
iono clean --all                # Remove build + artifacts
iono ui                         # Launch MLflow UI
iono run <script.py>            # Run Python script
iono help                       # Show CLI help
```

### Convenient Aliases

The development shell provides short aliases for common commands:

```powershell
ib          # iono build
ir          # iono rebuild (clean build)
it          # iono test (all tests)
itp         # iono test python
itc         # iono test cpp
ifmt        # iono format
ilint       # iono lint
iclean      # iono clean
iprof       # iono profile
ihelp       # iono help
ireload     # Reload shell functions
```

### GPU Profiling

```powershell
# Profile with Nsight Systems (timeline analysis)
iono profile nsys latency
iono profile nsys throughput

# Profile with Nsight Compute (kernel analysis)
iono profile ncu latency --mode full
iono profile ncu throughput --kernel magnitude_kernel

# Interactive mode (guided profiling)
iono profile
```

## Research Workflow

### Experiment Configuration with Hydra

Create modular experiment configurations:

```yaml
# experiments/conf/experiment/my_study.yaml
# @package _global_

defaults:
  - /engine: throughput
  - /benchmark: throughput

experiment:
  name: frequency_resolution_study
  description: "Impact of FFT size on spectral resolution"

engine:
  nfft: 4096
  channels: 16
  overlap: 0.5
  sample_rate_hz: 48000
```

### Run Single Experiments

```powershell
# Run with specific configuration
python benchmarks/run_latency.py experiment=baseline +benchmark=latency

# Override parameters on command line
python benchmarks/run_latency.py experiment=baseline engine.nfft=2048
```

### Run Parameter Sweeps

```powershell
# Sweep over NFFT sizes
python benchmarks/run_latency.py --multirun experiment=nfft_scaling +benchmark=latency

# Sweep over channel counts
python benchmarks/run_throughput.py --multirun experiment=channels_scaling +benchmark=throughput

# Custom parameter sweep
python benchmarks/run_latency.py --multirun engine.nfft=1024,2048,4096,8192 +benchmark=latency
```

### Ionosphere Research Configurations

Ready-to-use configurations for ionospheric scintillation studies:

```powershell
# Multi-scale resolution study (4K-32K FFT)
python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput

# Temporal analysis with overlap optimization
python benchmarks/run_throughput.py --multirun experiment=ionosphere_temporal +benchmark=throughput

# Comprehensive multi-scale parameter sweep
python benchmarks/run_latency.py experiment=ionosphere_multiscale +benchmark=latency
```

### Analysis Pipeline with Snakemake

```powershell
# Run complete analysis pipeline
snakemake --cores 4 --snakefile experiments/Snakefile

# Generate specific outputs
snakemake --cores 4 generate_figures --snakefile experiments/Snakefile
snakemake --cores 4 generate_report --snakefile experiments/Snakefile

# Dry run to see what will be executed
snakemake --cores 4 --snakefile experiments/Snakefile --dry-run
```

### Experiment Tracking with MLflow

```powershell
# Launch MLflow UI
iono ui
# Opens at http://localhost:5000

# Or use MLflow directly
mlflow ui --backend-store-uri artifacts/mlruns --port 5000

# Query experiments from command line
mlflow experiments list --tracking-uri file://./artifacts/mlruns
mlflow runs list --experiment-id 0
```

### Data Versioning with DVC

```powershell
# Check data pipeline status
dvc status

# Reproduce entire pipeline
dvc repro

# Pull data from remote storage
dvc pull

# Push artifacts to remote storage
dvc push
```

## Example Workflows

### Development Workflow

```powershell
# 1. Start development shell
.\scripts\init_pwsh.ps1 -Interactive

# 2. Make changes to code...

# 3. Build and test
ib                          # Build (iono build)
it                          # Test (iono test)

# 4. Check code quality
ifmt                        # Format C++ code
ilint --fix                 # Fix Python lint issues

# 5. Commit changes
git add .
git commit -m "feat(core): add new feature"
```

### Research Workflow

```powershell
# 1. Configure experiment
# Edit experiments/conf/experiment/my_study.yaml

# 2. Run experiment
python benchmarks/run_throughput.py experiment=my_study +benchmark=throughput

# 3. View results
iono ui                     # Open MLflow UI

# 4. Run analysis pipeline
snakemake --cores 4 --snakefile experiments/Snakefile

# 5. Version control data
dvc add artifacts/data/my_study_results.csv
dvc push
git add artifacts/data/my_study_results.csv.dvc
git commit -m "data: add my_study results"
```

### Performance Optimization Workflow

```powershell
# 1. Baseline measurement
python benchmarks/run_latency.py experiment=baseline +benchmark=latency

# 2. Profile with Nsight Systems
iono profile nsys latency

# 3. Make optimization changes...

# 4. Rebuild and profile again
ib
iono profile nsys latency

# 5. Compare results in MLflow
iono ui
```

## Project Structure

```
ionosense-hpc/
├── cpp/                        # C++ backend source
│   ├── include/                # Public headers
│   ├── src/                    # Implementation
│   └── tests/                  # C++ tests (Google Test)
├── python/                     # Python package
│   └── src/ionosense_hpc/      # Package source
│       ├── core/               # Engine API
│       ├── config/             # Configuration models
│       ├── benchmarks/         # Benchmark framework
│       └── utils/              # Utilities
├── tests/                      # Python tests (pytest)
├── benchmarks/                 # Benchmark scripts
│   ├── run_latency.py
│   ├── run_throughput.py
│   ├── run_accuracy.py
│   └── run_realtime.py
├── experiments/                # Research experiments
│   ├── conf/                   # Hydra configurations
│   ├── notebooks/              # Jupyter notebooks
│   └── Snakefile               # Analysis pipeline
├── scripts/                    # Development tools
│   ├── cli.ps1                 # Main CLI
│   ├── init_pwsh.ps1           # Dev shell setup
│   └── prof_helper.py          # Profiling helper
├── artifacts/                  # Generated artifacts
│   ├── data/                   # Benchmark results
│   ├── figures/                # Generated plots
│   ├── reports/                # Analysis reports
│   └── mlruns/                 # MLflow tracking
├── docs/                       # Documentation
│   ├── INSTALL.md              # Installation guide
│   ├── ARCHITECTURE.md         # System architecture
│   ├── API.md                  # Python API reference
│   └── diagrams/               # PlantUML diagrams
├── environments/               # Conda environments
├── CMakeLists.txt              # C++ build configuration
├── pyproject.toml              # Python package configuration
├── CONTRIBUTING.md             # Contribution guidelines
└── README.md                   # This file
```

## Documentation

- **[Installation Guide](docs/INSTALL.md)** - Platform-specific setup instructions
- **[Architecture Guide](docs/ARCHITECTURE.md)** - System design and implementation details
- **[API Reference](docs/API.md)** - Python API documentation
- **[Benchmarking Guide](docs/BENCHMARKING.md)** - Performance testing and analysis
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute
- **[Experiment Guide](experiments/README.md)** - Research workflow documentation

### Quick Help

```powershell
iono help                       # CLI command reference
iono doctor                     # Environment diagnostics
```

## Performance Targets

### Latency Benchmarks
- **Real-time Processing**: < 200μs (99th percentile)
- **Standard Processing**: < 500μs (99th percentile)
- **Throughput Mode**: < 1ms (99th percentile)

### Throughput Benchmarks
- **Memory Bandwidth**: > 100 GB/s (sustained)
- **PCIe Bandwidth**: > 20 GB/s (H2D + D2H combined)
- **Processing Rate**: > 10 million samples/second

### Accuracy Requirements
- **Spectral Accuracy**: < 1e-6 relative error vs. NumPy/SciPy
- **Parseval's Theorem**: < 1e-5 energy conservation error
- **Phase Accuracy**: < 1e-4 radians (when applicable)

## Hardware Tested

### NVIDIA GPUs
- **RTX 40-series**: RTX 4090, RTX 4080
- **RTX 30-series**: RTX 3090, RTX 3080, RTX 3070
- **RTX 20-series**: RTX 2080 Ti, RTX 2070
- **Tesla**: T4, V100, A100

### Compute Capabilities
- **Primary**: SM 8.x (Ampere) and SM 9.x (Ada Lovelace)
- **Supported**: SM 6.0+ (Pascal and newer)

## Troubleshooting

### Environment Issues

```powershell
# Check environment health
iono doctor

# Common issues:
# 1. Conda environment not found
iono setup                      # Recreate environment

# 2. CUDA not found
# Install CUDA Toolkit 13.0+ from NVIDIA

# 3. Visual Studio tools not found
# Install VS 2022 with C++ build tools

# 4. Build failures
iono build --clean --verbose    # Clean rebuild with output
```

### Performance Issues

```powershell
# Check GPU utilization
nvidia-smi

# Profile to find bottlenecks
iono profile nsys latency

# Verify CUDA driver version
nvidia-smi
```

### Test Failures

```powershell
# Run tests with verbose output
iono test --verbose

# Run specific test
iono test -Pattern "test_name"

# Check Python tests only
itp

# Check C++ tests only
itc
```

For more troubleshooting, see [INSTALL.md](docs/INSTALL.md).

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup
- Team structure (4 teams across 2 boards)
- Code style guidelines
- Testing requirements
- Pull request process

### Quick Contribution Guide

```powershell
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/ionosense-hpc.git
cd ionosense-hpc

# 2. Setup environment
.\scripts\init_pwsh.ps1 -Interactive
iono setup

# 3. Create branch
git checkout -b feat/team-X/my-feature

# 4. Make changes and test
ib && it

# 5. Ensure code quality
ifmt && ilint

# 6. Commit and push
git commit -m "feat(scope): description"
git push origin feat/team-X/my-feature

# 7. Create Pull Request on GitHub
```

## Team Structure

The project is organized into two development boards:

### Board 1: Platform & Core Systems
- **Team 1**: C++/CUDA backend and performance
- **Team 2**: Build systems, CI/CD, infrastructure

### Board 2: User Interface & Research
- **Team 3**: Python API and testing
- **Team 4**: Research experiments and analysis

See [Project Boards](https://github.com/your-org/ionosense-hpc/projects) for active work.

## Citations

If you use Ionosense-HPC in your research, please cite:

```bibtex
@software{ionosense_hpc,
  title = {Ionosense-HPC: High-Performance CUDA FFT Engine for Signal Processing},
  author = {Your Organization},
  year = {2025},
  url = {https://github.com/your-org/ionosense-hpc}
}
```

## Acknowledgments

- Built with NVIDIA CUDA and cuFFT
- Uses pybind11 for Python bindings
- Hydra for configuration management
- MLflow for experiment tracking
- DVC for data versioning
- Snakemake for workflow orchestration

## Contact

- **Issues**: [GitHub Issues](https://github.com/SEAL-Embedded/ionosense-hpc-lib/issues)
- **Discussions**: [GitHub Discussions](https://github.com/SEAL-Embedded/ionosense-hpc-lib/discussions)

## Status

**Active Development** - This project is under active development. APIs may change between minor versions. We follow semantic versioning for releases.
