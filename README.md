# Ionosense-HPC

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![CUDA 13.0+](https://img.shields.io/badge/CUDA-13.0+-green.svg)](https://developer.nvidia.com/cuda-toolkit)

High-performance CUDA FFT engine and benchmarking suite for real-time signal processing.

## Overview

Ionosense-HPC provides a Python interface to a high-performance CUDA-based signal processing engine, optimized for real-time signal analysis. It includes a professional, research-grade benchmarking infrastructure for reproducible performance evaluation following RSE (Research Software Engineering) and IEEE standards.

### Key Features

- **High-Performance FFT Processing**: CUDA-accelerated FFT engine with sub-200μs latency
- **Research CLI Platform**: Comprehensive CLI for builds, benchmarks, and analysis
- **Flexible Configuration**: Pre-configured presets for real-time, throughput, and validation scenarios
- **Comprehensive Benchmarking**: Research-grade benchmark suite with statistical analysis
- **NVTX Profiling**: Built-in support for NVIDIA Nsight profiling
- **Batch Processing**: Efficient multi-channel parallel processing
- **Python Interface**: Clean, Pythonic API with context managers and type hints

## Requirements

- Python 3.11 or higher
- CUDA Toolkit 13.0 or higher
- NVIDIA GPU with compute capability 6.0+
- C++17 compatible compiler
- CMake 3.25+

## Installation

See [INSTALL.md](INSTALL.md) for detailed platform-specific installation instructions.

### Quick Start

```bash
# Clone repository
git clone https://github.com/your-org/ionosense-hpc.git
cd ionosense-hpc

# Setup environment and build (Linux/WSL2)
./scripts/cli.sh setup
./scripts/cli.sh build

# Setup environment and build (Windows)
.\scripts\cli.ps1 setup
.\scripts\cli.ps1 build

# Verify installation
pytest tests/ -v            # Direct testing
.\scripts\cli.ps1 doctor    # Windows environment check
```

## CLI Interface

Ionosense-HPC includes a focused CLI for essential setup and build tasks. For research workflows, we recommend using the underlying tools directly for maximum flexibility and control.

### Essential CLI Commands (All Platforms)
```bash
# Environment setup and build (Essential CLI usage)
.\scripts\cli.ps1 setup                   # Create conda environment & install
.\scripts\cli.ps1 build                   # Build project with CMake
.\scripts\cli.ps1 clean                   # Clean build artifacts
.\scripts\cli.ps1 doctor                  # Verify environment health

# Code quality and development
.\scripts\cli.ps1 format                  # Format C++ code with clang-format
.\scripts\cli.ps1 lint                    # Lint Python (ruff) and C++ code
.\scripts\cli.ps1 typecheck               # Run mypy type checking
.\scripts\cli.ps1 check                   # Combined format/lint/typecheck

# System information and profiling
.\scripts\cli.ps1 info                    # Show system/benchmark/config info
.\scripts\cli.ps1 status                  # Research environment status
.\scripts\cli.ps1 profile nsys latency    # Profile with NVIDIA Nsight
.\scripts\cli.ps1 monitor                 # Real-time GPU monitoring

# Learning and help
.\scripts\cli.ps1 learn                   # Interactive learning guides
.\scripts\cli.ps1 help                    # CLI help
```

### Direct Research Tools (Recommended for daily use)
```bash
# Single experiments via Hydra
python benchmarks/run_latency.py experiment=baseline
python benchmarks/run_latency.py engine.nfft=8192 benchmark.iterations=100

# Parameter sweeps via Hydra multirun
python benchmarks/run_latency.py --multirun engine.nfft=1024,2048,4096,8192
python benchmarks/run_latency.py --multirun experiment=nfft_scaling

# Analysis workflows via Snakemake
snakemake --cores 4 --snakefile experiments/Snakefile
snakemake --cores 4 generate_figures --snakefile experiments/Snakefile

# Experiment tracking via MLflow
mlflow ui --backend-store-uri file://./artifacts/mlruns
mlflow experiments list --tracking-uri file://./artifacts/mlruns

# Data versioning via DVC
dvc status
dvc repro
dvc push

# Testing via pytest
pytest tests/ -v
pytest tests/ --cov=ionosense_hpc
```

## Modern Research Toolchain

Ionosense-HPC uses a modern, reproducible research stack:

- **🔧 Hydra**: Configuration management and parameter sweeps
- **🐍 Snakemake**: Workflow orchestration for analysis pipelines
- **📊 DVC**: Data version control for reproducible experiments
- **📈 MLflow**: Experiment tracking with metrics, parameters, and artifacts
- **🚀 NVIDIA Nsight**: Performance profiling and optimization

### Available Experiment Configurations

```bash
# Single experiments with Hydra
python benchmarks/run_latency.py experiment=baseline           # Baseline performance characterization
python benchmarks/run_latency.py experiment=baseline engine.nfft=2048  # With parameter overrides

# Parameter sweeps with Hydra multirun
python benchmarks/run_latency.py --multirun experiment=nfft_scaling      # Sweep over different NFFT sizes
python benchmarks/run_latency.py --multirun experiment=batch_scaling     # Sweep over batch sizes
python benchmarks/run_latency.py --multirun experiment=full_grid         # Comprehensive parameter grid
python benchmarks/run_latency.py --multirun experiment=stress_test       # Stress testing configuration

# Available benchmarks: latency, throughput, accuracy, realtime
python benchmarks/run_throughput.py experiment=baseline
python benchmarks/run_accuracy.py --multirun experiment=nfft_scaling
```

### Modern Workflow Integration

```bash
# Complete reproducible workflow using direct tools
python benchmarks/run_latency.py experiment=baseline                      # Run experiments
python benchmarks/run_latency.py --multirun experiment=nfft_scaling       # Parameter exploration
snakemake --cores 4 --snakefile experiments/Snakefile                     # Generate analysis and reports
mlflow ui --backend-store-uri file://./artifacts/mlruns                   # View results in MLflow UI
dvc status                                                                 # Check data versioning with DVC
```

## Quick Usage Examples

### Basic Processing

```python
from ionosense_hpc import Engine, Presets
import numpy as np

# Create processor with real-time preset
with Engine(Presets.realtime()) as engine:
    # Generate test signal
    signal = np.random.randn(2048).astype(np.float32)
    
    # Process signal
    spectrum = engine.process(signal)
    
    print(f"Output shape: {spectrum.shape}")
    print(f"Processing latency: {proc.get_stats()['latency_us']:.1f} μs")
```

### Workflow Examples

**Essential Setup (All Platforms):**
```bash
# Complete development workflow
.\scripts\cli.ps1 setup                   # One-time environment setup
.\scripts\cli.ps1 build                   # Build project
pytest tests/ -v                          # Verify functionality

# Code quality checks
.\scripts\cli.ps1 format                  # Format code
.\scripts\cli.ps1 lint                    # Lint code
.\scripts\cli.ps1 check                   # Combined checks
```

**Modern Research Workflows (Direct Tools):**
```bash
# Single experiments with Hydra
python benchmarks/run_latency.py experiment=baseline           # Run single experiment
python benchmarks/run_latency.py experiment=baseline engine.nfft=2048  # Override parameters

# Parameter sweeps with Hydra multirun
python benchmarks/run_latency.py --multirun experiment=nfft_scaling    # Run parameter sweep
python benchmarks/run_throughput.py --multirun experiment=baseline     # Different benchmark type

# Analysis workflows with Snakemake
snakemake --cores 4 --snakefile experiments/Snakefile         # Execute full analysis pipeline
snakemake --cores 4 generate_figures --snakefile experiments/Snakefile  # Generate specific outputs

# Experiment tracking with MLflow
mlflow ui --backend-store-uri file://./artifacts/mlruns       # View results in MLflow UI
mlflow experiments list --tracking-uri file://./artifacts/mlruns  # List experiments

# Profiling with Nsight
.\scripts\cli.ps1 profile nsys latency                        # Profile with Nsight Systems

# Custom scripts
python custom_script.py                                       # Run any custom script
```