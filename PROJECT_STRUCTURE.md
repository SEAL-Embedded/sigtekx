# Project Structure

Complete layout of the ionosense-hpc-lib codebase with documentation links.

## Directory Tree

```
ionosense-hpc-lib/
│
├── .guide/                    # C++/CUDA code examples and documentation
├── bindings/                  # C++ to Python bindings (pybind11)
├── include/                   # C++ header files for the core library
├── src/                       # C++/CUDA source code implementation
├── tests/                     # C++ unit tests (GTest)
│
├── python/
│    ├── src/
│    │   └── ionosense_hpc/
│    │       ├── __init__.py
│    │       │
│    │       ├── benchmarks/
│    │       │   ├── __init__.py
│    │       │   ├── accuracy.py
│    │       │   ├── base.py
│    │       │   ├── latency.py
│    │       │   └── throughput.py
│    │       │
│    │       ├── core/
│    │       │   ├── __init__.py
│    │       │   ├── config.py
│    │       │   ├── exceptions.py
│    │       │   ├── fft_processor.py
│    │       │   ├── pipelines.py
│    │       │   └── profiling.py
│    │       │
│    │       └── utils/
│    │           ├── __init__.py
│    │           ├── console.py
│    │           ├── data_export.py
│    │           ├── device.py
│    │           ├── signals.py
│    │           └── validation.py
│    │
│    └── tests/
│        ├── conftest.py
│        ├── test_config.py
│        ├── test_fft_processor.py
│        ├── test_integration.py
│        └── test_pipelines.py
│
├── research/                  # Experiments, analysis, and reports
│   ├── notebooks/             # Exploratory notebooks and visualizations
│   ├── data/                  # Datasets for experiments
│   │   ├── raw/               # Original, immutable data sources
│   │   └── processed/         # Cleaned, transformed, or feature-engineered data
│   │
│   ├── experiments/           # Reproducible experiment scripts
│   ├── results/               # Output from experiments (plots, tables, models)
│   │   ├── figures/           # Generated plots and visualizations
│   │   ├── tables/            # Tabular data and summary statistics
│   │   └── models/            # Saved, trained model artifacts
│   │
│   ├── reports/               # Project reports, papers, and presentations
│   └── configs/               # Configuration files for experiments & benchmarks
│
├── scripts/                   # Helper scripts for development and environment setup
│
├── .gitignore                 # Specifies intentionally untracked files to ignore
├── CMakeLists.txt             # Top-level build script for CMake
├── CMakePresets.json          # Default build configurations for CMake
├── environment.linux.yml      # Conda environment for Linux
├── environment.win.yml        # Conda environment for Windows
└── README.md                  # Main project documentation
```

## Component Map

<p align="center">
  <img src="./docs/.components-map.svg" alt="Component Map" height="2000" width="2000"/>
</p>

### another diagram, just the code structure

<p align="center">
  <img src="./docs/.software-architecture.svg" alt="Component Map" height="1000" width="800"/>
</p>

### and now c++/cuda source architecture

<p align="center">
  <img src="./docs/.cuda-structure.svg" alt="Component Map" height="2000" width="2000"/>
</p>


## Key Files

### Configuration Files

| File | Purpose |
|------|---------|
| `CMakeLists.txt` | Main build configuration |
| `CMakePresets.json` | Platform-specific build presets |
| `environment.linux.yml` | Linux Conda environment |
| `environment.win.yml` | Windows Conda environment |
| `pyproject.toml` | Python package metadata |

### Core Implementation

| File | Lines | Purpose |
|------|-------|---------|
| `src/fft_engine.cpp` | ~400 | Stream management, memory, graphs |
| `src/ops_fft.cu` | ~100 | CUDA kernel implementations |
| `bindings/bindings.cpp` | ~120 | Python bindings |
| `include/ionosense/fft_engine.hpp` | ~80 | Public C++ API |

### Scripts

| Script | Command Examples |
|--------|------------------|
| `cli.sh` | `./scripts/cli.sh build`<br/>`./scripts/cli.sh test`<br/>`./scripts/cli.sh bench raw_throughput` |
| `cli.ps1` | `.\scripts\cli.ps1 setup`<br/>`.\scripts\cli.ps1 profile nsys realtime` |

## Build Outputs

### Linux Build (`build/linux-rel/`)
```
build/linux-rel/
├── compile_commands.json    # For IDE integration
├── test_engine             # C++ test executable
└── CMakeCache.txt          # CMake configuration cache
```

### Windows Build (`build/windows-rel/`)
```
build/windows-rel/
├── test_engine.exe         # C++ test executable
├── Release/
└── CMakeCache.txt
```

### Python Module Location
```
python/ionosense_hpc/core/
├── _engine.so              # Linux
└── _engine.pyd             # Windows
```

## Development Workflow

### 1. Environment Setup
```bash
# Linux
./scripts/cli.sh setup
conda activate ionosense-hpc

# Windows
.\scripts\cli.ps1 setup
conda activate ionosense-hpc
```

### 2. Build
```bash
# Full build
./scripts/cli.sh build

# Debug build
./scripts/cli.sh build linux-debug

# Clean rebuild
./scripts/cli.sh rebuild
```

### 3. Test
```bash
# All tests
./scripts/cli.sh test

# C++ only
ctest --preset linux-tests

# Python only
pytest python/tests -v
```

### 4. Benchmark
```bash
# List benchmarks
./scripts/cli.sh list benchmarks

# Run benchmark
./scripts/cli.sh bench raw_throughput -n 4096

# Profile
./scripts/cli.sh profile nsys raw_throughput
```

## Documentation Index

| Document | Audience | Purpose |
|----------|----------|---------|
| [README.md](README.md) | Everyone | Project overview, quick start |
| [src/README.md](src/README.md) | C++ Developers | Source code architecture |
| [bindings/README.md](bindings/README.md) | Binding Developers | Python interface details |
| [python/README.md](python/README.md) | Python Users | API usage guide |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Contributors | Development guide |
| [docs/BENCHMARKS.md](docs/BENCHMARKS.md) | Researchers | Performance methodology |

## Git Workflow

### Branch Structure
```
main            # Stable releases
├── develop     # Integration branch
├── feature/*   # New features
├── fix/*       # Bug fixes
└── perf/*      # Performance improvements
```

### Commit Convention
```
type(scope): description

- feat: New feature
- fix: Bug fix
- perf: Performance improvement
- docs: Documentation
- test: Testing
- build: Build system
```

## Dependencies

### Build Dependencies
- CMake ≥3.26
- CUDA Toolkit ≥12.0
- C++17 compiler (GCC 11+, MSVC 2022)
- Python 3.11

### Runtime Dependencies
- CUDA driver ≥525
- cuFFT library
- NumPy ≥1.24

### Python Dependencies
```
numpy           # Array operations
pybind11        # C++ bindings
pytest          # Testing
tqdm            # Progress bars
```

## Performance Targets

| Metric | Target | Current |
|--------|--------|---------|
| Latency (dual FFT) | <110 μs | ~180 μs |
| Throughput (4K FFT) | >1M/s | 1.2M/s |
| Memory Transfer | <40% time | 38% |
| RMS Error | <1e-5 | 8.3e-6 |
