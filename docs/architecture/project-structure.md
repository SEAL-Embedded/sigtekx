# Project Structure

Complete layout of the ionosense-hpc-lib codebase with documentation links tailored to the current repository state.

## Directory Tree

```
ionosense-hpc-lib/
|-- .github/                # CI workflows, composite actions, issue templates
|-- .guide/                 # Reference PDFs and legacy CUDA samples for context
|-- .ionosense/             # Tooling state (ruff reports, session logs)
|-- benchmarks/             # Standalone benchmarking utilities and scenarios
|-- build/                  # Generated artefacts (benchmarks, reports, build presets)
|-- cpp/                    # C++17/CUDA sources, bindings, and tests
|   |-- bindings/           # pybind11 bridge exposing the research engine
|   |-- include/ionosense/  # Public headers and CUDA resource wrappers
|   |-- src/                # Engine implementation, CUDA kernels, helpers
|   `-- tests/              # C++ test suite (gtest/CTest presets)
|-- docs/                   # Project documentation (API, development, benchmarking)
|-- environments/           # Conda environment definitions per workflow
|-- experiments/            # Snakemake rules and analysis scripts
|-- notebooks/              # Exploratory analysis (Jupyter)
|-- scripts/                # PowerShell helpers, profiling utilities, GPU management
|-- src/                    # Python package source tree
|   `-- ionosense_hpc/      # User facing package (benchmarks, config, core, utils)
|-- tests/                  # Pytest suite (unit, integration, GPU markers)
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

### C++ Library (cpp/) - v0.9.3 Architecture
```
cpp/
|-- benchmarks/             # C++ standalone benchmarks
|   |-- core/              # Config, results, persistence
|   |-- formatters/        # Output formatters
|   |-- runners/           # Benchmark runners (latency, throughput, etc.)
|   |-- utils/             # Signal generator, reference compute
|   `-- main.cpp           # Entry point
|-- bindings/
|   `-- bindings.cpp        # pybind11 BatchExecutor/StreamingExecutor bindings
|-- include/ionosense/
|   |-- core/              # Core abstractions
|   |   |-- executor_config.hpp
|   |   |-- pipeline_executor.hpp
|   |   |-- pipeline_builder.hpp
|   |   `-- processing_stage.hpp
|   |-- executors/         # Executor implementations
|   |   |-- batch_executor.hpp
|   |   `-- streaming_executor.hpp
|   |-- kernels/           # CUDA kernel headers
|   `-- profiling/         # NVTX profiling utilities
|       `-- nvtx.hpp
|-- src/                   # Implementation files
|   |-- core/              # Pipeline, stages, utils
|   |-- executors/         # Batch & streaming executors
|   |-- kernels/           # STFT pipeline kernels (windowing, FFT wrapper, magnitude)
|   `-- profiling/         # NVTX profiling
|`-- tests/                # C++ tests (organized by component)
    |-- core/              # Pipeline and stage tests
    |-- executors/         # Executor tests
    |-- integration/       # Integration tests
    `-- profiling/         # Profiling tests
```

### Python Package (src/ionosense_hpc)
```
src/ionosense_hpc/
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

### Benchmarks (benchmarks/)
```
benchmarks/
|-- run_accuracy.py         # Hydra entry point for accuracy sweeps
|-- run_latency.py          # Latency benchmarking harness
|-- run_realtime.py         # Real-time pipeline evaluation
`-- run_throughput.py       # Throughput benchmarking harness
```

Each script is a Hydra-driven application used directly or orchestrated through Snakemake.

### Experiments & Analysis (experiments/)
```
experiments/
|-- Snakefile               # Snakemake workflow for end-to-end studies
|-- conf/
|   |-- config.yaml         # Global Hydra configuration
|   |-- engine/             # Engine presets
|   |-- experiment/         # Experiment definitions (ionosphere_*)
|   `-- benchmark/          # Benchmark parameter grids
`-- scripts/                # Analysis, figure generation, report assembly
```

Snakemake coordinates benchmark execution, analysis, and report generation using these assets.

### Artifacts (artifacts/)

```
artifacts/
|-- cpp/                    # C++ benchmark outputs (baselines for regression detection)
|   `-- baselines/          # JSON baselines: <preset>_<variant>_<mode>.json
|-- benchmark_results/      # Python standalone benchmark API outputs (fallback location)
|-- data/                   # Hydra Python experiment outputs (CSV/Parquet) - PRIMARY for analysis
|-- experiments/            # Hydra run directories for single runs and multirun sweeps
|-- logs/                   # Research CLI JSONL logs for traceability
|-- mlruns/                 # MLflow tracking store (local file backend)
|-- profiling/
|   |-- ncu_reports/        # Nsight Compute traces (.ncu-rep)
|   `-- nsys_reports/       # Nsight Systems traces (.nsys-rep)
`-- reports/                # Generated analysis reports and summaries
```

**Benchmark Output Locations (Three Separate Systems):**

| System | Directory | Purpose | Created By |
|--------|-----------|---------|------------|
| **Hydra Experiments** | `artifacts/data/` | Primary experiment outputs for analysis pipeline | `run_latency.py`, `run_throughput.py`, etc. |
| **Python Standalone API** | `artifacts/benchmark_results/` | Fallback for direct benchmark class usage | Benchmark classes when `output_dir=None` |
| **C++ Baseline Storage** | `artifacts/cpp/baselines/` | Performance regression detection for C++ dev | `ionoc bench --save-baseline` |

These are intentionally separate to keep C++ development workflows independent from Python experiment orchestration.


### Build Outputs (build/)

```
build/
|-- windows-rel/            # Latest Windows release build (CTest + binaries)
`-- <preset>/               # Any additional CMake presets generated locally
```


### Python Module Artefacts
Shared objects produced by builds land in `src/ionosense_hpc/core/`. Expect `_engine.pyd` on Windows and `_engine.so` on Linux/WSL.


## Documentation Index

| Document | Audience | Purpose |
|----------|----------|---------|
| [README.md](README.md) | Everyone | High-level overview, supported platforms, quick links |
| [docs/README.md](docs/README.md) | Everyone | Documentation entry point and navigation |
| [docs/getting-started/install.md](docs/getting-started/install.md) | Contributors | Environment provisioning on Windows and Ubuntu |
| [docs/getting-started/workflow-guide.md](docs/getting-started/workflow-guide.md) | Researchers | Snakemake-driven experiment workflow |
| [docs/guides/development.md](docs/guides/development.md) | Contributors | Day-to-day development practices and checklists |
| [docs/guides/benchmarking.md](docs/guides/benchmarking.md) | Researchers | Benchmark methodology, datasets, and KPIs |
| [docs/guides/api-reference.md](docs/guides/api-reference.md) | Integrators | Python package surface and binding details |
| [docs/guides/creating-issues.md](docs/guides/creating-issues.md) | Maintainers | Requirements capture templates and review cues |
| [docs/architecture/overview.md](docs/architecture/overview.md) | Contributors | System architecture diagrams and rationale |
| [docs/performance/gpu-clock-locking.md](docs/performance/gpu-clock-locking.md) | Performance engineers | GPU clock management for reproducible runs |
| [docs/technical-notes/ieee754-compliance.md](docs/technical-notes/ieee754-compliance.md) | Numerics team | IEEE 754 compliance expectations |


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
- Generated content persists under `artifacts/` (configurable via `IONO_OUTPUT_ROOT`).
- Benchmark outputs: See three separate systems documented in Artifacts section above
  - Hydra experiments: `artifacts/data/` (primary)
  - Python standalone: `artifacts/benchmark_results/`
  - C++ baselines: `artifacts/cpp/baselines/`
- Experiment dumps: `artifacts/experiments/`
- QA reports (lint, coverage, validation): `artifacts/reports/`
- Profiling traces: `artifacts/profiling/nsys_reports/` & `artifacts/profiling/ncu_reports/`
- CLI research logs: `artifacts/logs/`

## Tooling Notes
- Run `cmake --list-presets` and `ctest --list-presets` to discover configured build and test targets.
- Confirm the active Conda environment with `conda info --envs`; all developer tooling resolves from `ionosense-hpc`.
- Execute GPU-specific tests on demand via `python -m pytest -m gpu --maxfail=1`.
- Clear analysis caches manually when stale by deleting `.mypy_cache/`, `.ruff_cache/`, and `.pytest_cache/`.
- Nsight CLI tools (`nsys`, `ncu`) store reports under `artifacts/profiling/`; set `IONO_OUTPUT_ROOT` to redirect outputs per experiment.

## Related Standards & Practices
- Research Software Engineering (RSE) guidelines govern documentation, testing, and reproducibility.
- Requirements Engineering principles applied via issue templates and CONTRIBUTING checklist.
- IEEE 1074 guides lifecycle activities (planning, verification, maintenance) enforced in docs and CI gates.
- IEEE 754 considerations documented in benchmarking + validation routines; avoid precision regressions without review.

## Update History
- 2025-10-15: Removed deprecated CLI wrapper references, refreshed documentation index, and aligned directory descriptions with current tooling.
- 2025-09-15: Synchronized structure with `cpp/`, refreshed dependency constraints, and aligned workflow commands with CLI scripts.
