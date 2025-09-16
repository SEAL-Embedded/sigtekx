# Project Structure

Complete layout of the ionosense-hpc-lib codebase with documentation links tailored to the current repository state.

## Directory Tree

```
ionosense-hpc-lib/
|-- .github/                # CI workflows, composite actions, issue templates
|-- .guide/                 # Reference PDFs and legacy CUDA samples for context
|-- .ionosense/             # Tooling state (ruff reports, session logs)
|-- build/                  # Generated artefacts (benchmarks, reports, build presets)
|-- cpp/                    # C++17/CUDA sources, bindings, and tests
|   |-- bindings/           # pybind11 bridge exposing the research engine
|   |-- include/ionosense/  # Public headers and CUDA resource wrappers
|   |-- src/                # Engine implementation, CUDA kernels, helpers
|   `-- tests/              # C++ test suite (gtest/CTest presets)
|-- docs/                   # Project documentation (API, development, benchmarking)
|-- environments/           # Conda environment definitions per workflow
|-- python/                 # Python package and tests
|   |-- src/ionosense_hpc/  # User facing package (benchmarks, config, core, utils)
|   `-- tests/              # Pytest suite (unit, integration, gpu markers)
|-- research/               # Reproducible experiments, notebooks, data management
|-- scripts/                # Cross platform CLI wrappers and profiling helpers
|-- AGENTS.md               # Agent operations guide
|-- accuracy_debug_plan.md  # Investigation notes for current performance work
|-- CMakeLists.txt          # Top level CMake configuration
|-- CMakePresets.json       # Preset builds for host toolchains
|-- CONTRIBUTING.md         # Contribution workflow and review expectations
|-- Dockerfile              # Container recipe for CI/local parity
|-- PROJECT_STRUCTURE.md    # This document
|-- README.md               # High level introduction and quick start
|-- pyproject.toml          # Python packaging, lint, and test configuration
```

### C++ Library (cpp/)
```
cpp/
|-- bindings/
|   |-- bindings.cpp        # pybind11 module entrypoint
|   `-- README.md           # Binding layer documentation
|-- include/ionosense/
|   |-- cuda_wrappers.hpp   # RAII wrappers for CUDA/cuFFT handles
|   |-- processing_stage.hpp# Abstract interfaces for processing stages
|   |-- research_engine.hpp # Public API surface for ResearchEngine
|   `-- README.md           # Header level design notes
|-- src/
|   |-- ops_fft.cu          # CUDA kernels for FFT and spectral ops
|   |-- processing_stage.cpp# Stage implementations
|   |-- research_engine.cpp # Core engine logic
|   `-- README.md           # Implementation details and module map
|`-- tests/                 # C++ tests executed via CTest presets
```

### Python Package (python/src/ionosense_hpc)
```
python/src/ionosense_hpc/
|-- __init__.py             # Package exports
|-- __version__.py          # Semantic version string (synced with CMake/Python)
|-- exceptions.py           # Domain specific exception hierarchy
|-- benchmarks/             # Benchmark orchestration and CLI entrypoints
|-- config/                 # Presets, schema validation, config loaders
|-- core/                   # High level engine wrappers around the C++ module
|-- stages/                 # Stage registry and dynamic composition helpers
|-- testing/                # Fixtures, validators, GPU markers for pytest
|-- utils/                  # Device management, logging, profiling, reporting helpers
|-- .libs/                  # Platform dependent shared libraries shipped with wheels
`-- py.typed                # Marks package as PEP 561 typed
```

### Research Assets (research/)
```
research/
|-- configs/                # Experiment YAML configurations
|-- data/
|   |-- raw/                # Immutable source datasets
|   `-- processed/          # Derived data products committed to experiments
|-- dsp_course/             # Reference material and courseware experiments
|-- experiments/            # Reproducible scripts coordinating CLI + notebooks
|-- notebooks/              # Exploratory analysis (Jupyter)
`-- results/                # Generated figures, tables, and reports
```

### Build Outputs
```
build/
|-- benchmark_results/      # Summary CSV/JSON from CLI benchmark runs
|-- experiments/            # Research experiment artefacts staged by CLI
|-- nsight_reports/         # Nsight Systems/Compute traces
|-- reports/                # Lint, coverage, and QA summaries
`-- windows-rel/            # Latest Windows release build (CTest + binaries)
```

### Python Module Artefacts
Shared objects produced by builds land in `python/src/ionosense_hpc/core/`. Expect `_engine.pyd` on Windows and `_engine.so` on Linux/WSL.

## Development Workflow

### 1. Environment Setup
```bash
# Linux / WSL2
./scripts/cli.sh setup
conda activate ionosense-hpc

# Windows (PowerShell)
./scripts/cli.ps1 setup
conda activate ionosense-hpc

# Windows with enhanced shell
./scripts/open_dev_pwsh.ps1
iono setup
```

### 2. Build
```bash
# Default release build
./scripts/cli.sh build

# Debug preset
./scripts/cli.sh build linux-debug

# Clean rebuild
./scripts/cli.sh rebuild
```

### 3. Test
```bash
# Full suite (Python + C++)
./scripts/cli.sh test

# Python only
./scripts/cli.sh test py

# C++ only (CTest preset)
./scripts/cli.sh test cpp
```

### 4. Quality Gates
```bash
# Format C++ code (clang-format)
./scripts/cli.sh format

# Lint Python + C++
./scripts/cli.sh lint

# Type-check Python (mypy)
./scripts/cli.sh typecheck

# Aggregate quality checks
./scripts/cli.sh check
```

### 5. Benchmark & Profile
```bash
# Run benchmark suite
./scripts/cli.sh bench suite

# Launch Nsight Systems profile (example target)
./scripts/cli.sh profile nsys latency

# Parameter sweep experiment
./scripts/cli.sh sweep research/configs/sweep_experiment.yaml
```

## Documentation Index

| Document | Audience | Purpose |
|----------|----------|---------|
| [README.md](README.md) | Everyone | Overview, requirements, quick start |
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | Contributors | Repository map (this file) |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Contributors | Detailed development workflow |
| [docs/BENCHMARKING.md](docs/BENCHMARKING.md) | Researchers | Benchmark methodology and KPIs |
| [docs/API.md](docs/API.md) | Integrators | Python API reference |
| [cpp/include/ionosense/README.md](cpp/include/ionosense/README.md) | C++ Developers | Public API design |
| [cpp/src/README.md](cpp/src/README.md) | C++ Developers | Implementation notes |
| [cpp/bindings/README.md](cpp/bindings/README.md) | Binding Engineers | Python bridge specifics |
| [python/README.md](python/README.md) | Python Users | Package usage and tips |

## Git Workflow

### Branch Structure
```
main            # Stable releases
`-- feature/*   # Feature, fix, perf, and docs branches (named with purpose)
```

### Commit Convention
```
type(scope): description

Accepted types: feat, fix, perf, docs, test, build, ci, chore
```

Reference issues or research tickets in commit messages when applicable to maintain traceability.

## Dependencies

### Build-Time
- CMake >= 3.26
- CUDA Toolkit >= 13.0 (matching driver support)
- C++17 compiler (GCC 11+, Clang 15+, MSVC 2022)
- Python 3.11
- Conda/mamba for environment management (via CLI)

### Runtime
- NVIDIA GPU with compute capability 6.0+
- CUDA driver >= 550
- cuFFT 13.x runtime libraries
- NumPy 1.26.x

### Python Package Core Dependencies
- numpy==1.26.4
- scipy==1.13.0
- pydantic>=2.0
- pynvml>=11.5

### Python Dev Extras
- pytest>=8.0, pytest-xdist, pytest-timeout, pytest-cov
- ruff>=0.4
- mypy>=1.10

## Performance Targets (Current)

| Metric | Target | Notes |
|--------|--------|-------|
| Dual FFT latency | < 110 us | Measured with research preset on RTX 6000 Ada |
| 4K FFT throughput | > 1.0 M FFT/s | Bench suite `throughput` scenario |
| Memory transfer ratio | < 40% total time | Maintain overlap with compute |
| RMS error | < 1e-5 | Compared against double precision reference |

## Output Artefacts
- Generated content remains under `build/` (configurable via `IONO_OUTPUT_ROOT`).
- Benchmark CSVs/plots: `build/benchmark_results/`
- Experiment dumps: `build/experiments/`
- QA reports (lint, coverage): `build/reports/`
- Profiling traces: `build/nsight_reports/`

## Tooling Notes
- Use `./scripts/cli.sh doctor` or `iono doctor` to validate environments.
- GPU heavy pytest marked with `gpu`; enable via `./scripts/cli.sh test py -- --gpu`.
- Clear caches with CLI helpers: `./scripts/cli.sh clean --caches`.
- CTest presets defined in `CMakePresets.json` (`linux-debug`, `linux-rel`, `windows-rel`).

## Related Standards & Practices
- Research Software Engineering (RSE) guidelines govern documentation, testing, and reproducibility.
- Requirements Engineering principles applied via issue templates and CONTRIBUTING checklist.
- IEEE 1074 guides lifecycle activities (planning, verification, maintenance) enforced in docs and CI gates.
- IEEE 754 considerations documented in benchmarking + validation routines; avoid precision regressions without review.

## Update History
- 2025-09-15: Synchronized structure with `cpp/`, refreshed dependency constraints, and aligned workflow commands with CLI scripts.
