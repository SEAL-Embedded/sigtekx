# SigTekX

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![CUDA 13.0+](https://img.shields.io/badge/CUDA-13.0+-green.svg)](https://developer.nvidia.com/cuda-toolkit)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

CUDA-accelerated STFT pipeline and research-grade benchmarking suite for real-time signal processing — from sub-millisecond streaming to reproducible experiment workflows.

## Overview

SigTekX provides a Python interface to a high-performance CUDA-based STFT engine, optimized for real-time spectral analysis with sub-millisecond latency. The project includes a comprehensive research infrastructure following Research Software Engineering (RSE) best practices: Hydra configuration, Snakemake workflows, MLflow tracking, DVC versioning, and an interactive Streamlit dashboard. It is designed for production streaming workloads and reproducible ionospheric physics research.

## Measured Performance

All numbers measured on **RTX 3090 Ti** (SM 8.6, 24 GB) / AMD Ryzen 9 5950X, Windows 11. GPU clocks locked for stability; see [Stability Improvements](docs/performance/stability-improvements.md) for methodology.

| Metric | Value | Configuration |
|--------|-------|---------------|
| Mean latency | **160 μs** | Streaming, NFFT=4096, 2-ch, 100kHz |
| P99 latency | **205 μs** | Same |
| Real-time compliance | **100%** | 0 deadline misses, 45,430 frames |
| Benchmark CV | **12.2%** | After 4-phase stability work |
| Spectral accuracy | **131 dB SNR** | vs NumPy/SciPy reference |

## Key Features

- **High-Performance GPU Computing**: CUDA-accelerated STFT pipeline with asynchronous multi-stream execution
- **Clean Python API**: Type-safe interface with Pydantic configuration and context managers
- **Research Infrastructure**: Hydra configuration, Snakemake workflows, MLflow tracking, DVC versioning
- **Professional Benchmarking**: Statistical analysis with latency, throughput, accuracy, and real-time metrics
- **Domain-Specific Presets**: Ready-to-use configurations for ionospheric scintillation research (VLF/ULF)
- **NVTX Profiling**: Built-in support for NVIDIA Nsight Systems and Compute
- **Interactive Dashboard**: Streamlit dashboard for real-time experiment exploration (`sigx dashboard`)
- **Developer-Friendly CLI**: Comprehensive tooling with convenient shell aliases

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Researcher / User                                       │
│  ↓                                                       │
│  Hydra Configuration (YAML-based experiments)           │
│  ↓                                                       │
│  Python API (sigtekx.Engine)                            │
│  ├── Pydantic Config Models                             │
│  ├── Benchmark Framework (Latency/Throughput/Accuracy)  │
│  └── Utilities (Signals, Device, Profiling)             │
│  ↓                                                       │
│  C++ Backend (BatchExecutor/StreamingExecutor pybind11) │
│  ├── Direct Executor Interface (no facade layer)        │
│  ├── Async Processing Pipeline (multi-stream)           │
│  └── Optimized CUDA Kernels (STFT pipeline)             │
│  ↓                                                       │
│  GPU (cuFFT + Custom Window/Magnitude Kernels)          │
└─────────────────────────────────────────────────────────┘
```

See [Architecture Overview](docs/architecture/overview.md) and [Executor Architecture](docs/architecture/executors.md) for details.

## Requirements

| Category | Requirement |
|----------|-------------|
| OS | Windows 11 (primary), Linux (experimental) |
| GPU | NVIDIA, compute capability 6.0+ (Pascal or newer) |
| RAM | 8 GB+ (16 GB recommended for large experiments) |
| Python | 3.11+ |
| CUDA Toolkit | 13.0+ |
| Visual Studio | 2022 with C++ build tools (Windows) |
| CMake | 3.26+ |
| PowerShell | 7.0+ (Windows) |
| Conda | Miniconda or Anaconda |

## Quick Start

```powershell
# 1. Clone repository
git clone --recursive https://github.com/SEAL-Embedded/sigtekx.git
cd sigtekx

# 2. Start development shell (sets up MSVC, conda, aliases)
.\scripts\init_pwsh.ps1 -Interactive

# 3. Setup environment and build
sigx setup          # Creates conda env, installs dependencies
sigx build          # Builds C++ backend

# 4. Verify installation
sigx doctor         # Check environment health
sigx test           # Run test suite

# 5. Run a quick benchmark
python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency
```

For platform-specific instructions and troubleshooting, see [Installation Guide](docs/getting-started/install.md).

## Python API

### Basic Usage

```python
from sigtekx import Engine
import numpy as np

with Engine(preset='iono') as engine:
    signal = np.random.randn(engine.config.nfft * engine.config.channels).astype(np.float32)
    spectrum = engine.process(signal)
    print(f"Output: {spectrum.shape}  Latency: {engine.stats['latency_us']:.1f} μs")
```

### Custom Configuration

```python
from sigtekx import Engine, EngineConfig

config = EngineConfig(
    nfft=4096,
    channels=2,
    overlap=0.75,
    window_type='blackman',   # window function
    scale_policy='1/N',       # normalization
    output_mode='magnitude',  # output format
    mode='streaming'          # execution mode
)
engine = Engine(config=config)
```

### Logging

Imports are silent by default; a `NullHandler` is attached to the `sigtekx` logger so user code controls logging.

```python
import logging
from sigtekx.utils.logging import setup_logging

logging.basicConfig(level="INFO")
setup_logging(level="DEBUG")   # optional: rich console formatter for sigtekx*
```

Environment knobs: `IONO_LOG_LEVEL=DEBUG` and `IONO_LOG_COLOR=0/1` configure logging without code changes.

## Configuration Presets

| Preset | NFFT | Overlap | Use Case |
|--------|------|---------|----------|
| `default` | 1024 | 0.5 | General-purpose baseline |
| `iono` | 4096 | 0.75 | Ionospheric scintillation (standard) |
| `ionox` | 8192 | 0.9 | Ionospheric scintillation (high-resolution) |

```python
engine = Engine(preset='iono')                          # Standard ionosphere
engine = Engine(preset='iono', nfft=8192, mode='streaming')  # Override parameters
config = EngineConfig.from_preset('iono', overlap=0.875)
```

## Development Commands

```powershell
# Environment
sigx setup          # Create conda environment and install package
sigx doctor         # Check environment health

# Build
sigx build          # Release build
sigx build --clean  # Clean rebuild
sigx build --debug  # Debug build

# Test
sigx test           # All tests (Python + C++)
sigx test python    # Python only
sigx test cpp       # C++ only
sigx test --coverage

# Code quality
sigx format         # Format C++ code (clang-format)
sigx lint           # Lint Python code (ruff)
sigx lint --fix     # Auto-fix lint issues

# Utilities
sigx clean          # Remove build artifacts
sigx dashboard      # Launch Streamlit dashboard
sigx help           # Full CLI reference
```

### GPU Profiling

```powershell
# Nsight Systems (timeline analysis)
sxp nsys latency
sxp nsys throughput

# Nsight Compute (kernel analysis)
sxp ncu latency

# C++ direct benchmarking
sigxc bench                          # Quick validation (~10s)
sigxc bench --preset latency --full  # Production-equivalent run
```

### Running Experiments

```powershell
# Single experiment
python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency

# Parameter sweep
python benchmarks/run_latency.py --multirun engine.nfft=1024,2048,4096,8192 +benchmark=latency

# Full pipeline (all experiments + dashboard data)
snakemake --cores 4 --snakefile experiments/Snakefile
sigx dashboard
```

See [Experiment Guide](docs/benchmarking/experiment-guide.md) for the full list of 26 experiment configurations.

## Documentation

| Topic | Document |
|-------|----------|
| Installation | [docs/getting-started/install.md](docs/getting-started/install.md) |
| Workflow | [docs/getting-started/workflow-guide.md](docs/getting-started/workflow-guide.md) |
| API Reference | [docs/reference/api-reference.md](docs/reference/api-reference.md) |
| Configuration | [docs/reference/configuration.md](docs/reference/configuration.md) |
| Architecture Overview | [docs/architecture/overview.md](docs/architecture/overview.md) |
| Executor Architecture | [docs/architecture/executors.md](docs/architecture/executors.md) |
| Benchmarking | [docs/benchmarking/README.md](docs/benchmarking/README.md) |
| Experiment Guide | [docs/benchmarking/experiment-guide.md](docs/benchmarking/experiment-guide.md) |
| Performance | [docs/performance/stability-improvements.md](docs/performance/stability-improvements.md) |
| Thread Safety | [docs/architecture/thread-safety.md](docs/architecture/thread-safety.md) |
| IEEE 754 Compliance | [docs/technical-notes/ieee754-compliance.md](docs/technical-notes/ieee754-compliance.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Project Structure

```
sigtekx/
├── cpp/                   # C++ backend (CUDA kernels, executors)
│   ├── include/           # Public headers
│   ├── src/               # Implementation
│   └── tests/             # Google Test suite
├── src/sigtekx/           # Python package
│   ├── core/              # Engine, builder, native bindings
│   ├── config/            # EngineConfig, presets, enums
│   ├── benchmarks/        # Benchmark framework
│   └── utils/             # Device, signals, archiving
├── benchmarks/            # Experiment runner scripts
├── experiments/           # Hydra configs, Snakemake pipeline, Streamlit dashboard
├── tests/                 # Python test suite (pytest)
├── scripts/               # CLI (cli.ps1), dev shell (init_pwsh.ps1)
├── docs/                  # Documentation
├── baselines/             # Persistent performance baselines
├── artifacts/             # Generated results (gitignored)
└── environments/          # Conda environment specs
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style guidelines, testing requirements, and the pull request process.

```powershell
# Fork, clone, then:
.\scripts\init_pwsh.ps1 -Interactive
sigx setup
git checkout -b feat/my-feature
# ... make changes ...
sigx build && sigx test
git commit -m "feat(scope): description"
```

## License & Citation

Released under the [MIT License](LICENSE).

If you use SigTekX in your research, please cite:

```bibtex
@software{sigtekx2025,
  title  = {SigTekX: CUDA-Accelerated STFT Engine for Real-Time Signal Processing},
  author = {Rahsaz, Kevin},
  year   = {2025},
  url    = {https://github.com/SEAL-Embedded/sigtekx},
  note   = {Version 0.9.5}
}
```

---

Issues and discussions: [github.com/SEAL-Embedded/sigtekx](https://github.com/SEAL-Embedded/sigtekx)
