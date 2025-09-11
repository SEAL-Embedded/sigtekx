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
./scripts/cli.sh test        # Linux/WSL2
.\scripts\cli.ps1 test       # Windows
```

## CLI Interface

Ionosense-HPC includes a comprehensive CLI for all development and research workflows:

### Linux/WSL2
```bash
# Environment management
./scripts/cli.sh setup                    # Create conda environment
./scripts/cli.sh info                     # Show system information
./scripts/cli.sh doctor                   # Verify environment

# Build and development
./scripts/cli.sh build                    # Build project
./scripts/cli.sh test                     # Run all tests
./scripts/cli.sh clean                    # Clean build artifacts

# Code quality
./scripts/cli.sh format                   # Format C++ code
./scripts/cli.sh lint                     # Lint Python and C++
./scripts/cli.sh check                    # Run all checks

# Benchmarking and profiling
./scripts/cli.sh bench suite              # Run benchmark suite
./scripts/cli.sh profile nsys latency     # Profile with Nsight
./scripts/cli.sh sweep experiment.yaml    # Parameter sweep
```

### Windows
```powershell
# Environment management
.\scripts\cli.ps1 setup                   # Create conda environment
.\scripts\cli.ps1 info                    # Show system information
.\scripts\cli.ps1 doctor                  # Verify environment

# Build and development
.\scripts\cli.ps1 build                   # Build project
.\scripts\cli.ps1 test                    # Run all tests
.\scripts\cli.ps1 clean                   # Clean build artifacts

# Code quality
.\scripts\cli.ps1 format                  # Format C++ code
.\scripts\cli.ps1 lint                    # Lint Python and C++
.\scripts\cli.ps1 check                   # Run all checks

# Benchmarking and profiling
.\scripts\cli.ps1 bench suite             # Run benchmark suite
.\scripts\cli.ps1 profile nsys latency    # Profile with Nsight
.\scripts\cli.ps1 sweep experiment.yaml   # Parameter sweep
```

## Quick Usage Examples

### Basic Processing

```python
from ionosense_hpc import Processor, Presets
import numpy as np

# Create processor with real-time preset
with Processor(Presets.realtime()) as proc:
    # Generate test signal
    signal = np.random.randn(2048).astype(np.float32)
    
    # Process signal
    spectrum = proc.process(signal)
    
    print(f"Output shape: {spectrum.shape}")
    print(f"Processing latency: {proc.get_stats()['latency_us']:.1f} μs")
```

### CLI Workflow Examples

**Linux/WSL2:**
```bash
# Complete development workflow
./scripts/cli.sh setup                    # One-time setup
./scripts/cli.sh build                    # Build project
./scripts/cli.sh test                     # Verify functionality

# Research workflows
./scripts/cli.sh bench suite              # Run benchmark suite
./scripts/cli.sh profile nsys latency     # Profile performance
./scripts/cli.sh sweep config.yaml        # Parameter sweep experiment
./scripts/cli.sh report results/          # Generate research report
```

**Windows (Enhanced Development Shell):**
```powershell
# Start development shell with all tools configured
.\scripts\open_dev_pwsh.ps1

# Now use convenient aliases
iono setup                                # One-time setup
ib                                        # Build project (iono build)
it                                        # Test all (iono test)

# Research workflows with shortcuts
ibench suite                              # Run benchmark suite
iprof nsys latency                        # Profile performance
iono sweep config.yaml                    # Parameter sweep experiment
iono report results/                      # Generate research report
```