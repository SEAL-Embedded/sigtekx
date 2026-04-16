# Project Structure

Complete layout of the sigtekx codebase with documentation links tailored to the current repository state.

## Directory Tree

```
sigtekx/
|-- .github/                # CI workflows, composite actions, issue templates
|-- datasets/               # Persistent named benchmark result sets (local, cloud, C++)
|-- benchmarks/             # Standalone benchmarking utilities and scenarios
|-- build/                  # Generated artefacts (benchmarks, reports, build presets)
|-- cpp/                    # C++17/CUDA sources, bindings, and tests
|   |-- benchmarks/         # C++ standalone benchmark harness
|   |-- bindings/           # pybind11 bridge exposing the research engine
|   |-- include/sigtekx/   # Public headers and CUDA resource wrappers
|   |-- src/                # Engine implementation, CUDA kernels, helpers
|   `-- tests/              # C++ test suite (gtest/CTest presets)
|-- docs/                   # Project documentation (API, development, benchmarking)
|-- environments/           # Conda environment definitions per workflow
|-- experiments/            # Snakemake rules, analysis scripts, Streamlit dashboard
|-- scripts/                # PowerShell helpers, profiling utilities, GPU management
|-- src/                    # Python package source tree
|   `-- sigtekx/            # User facing package (benchmarks, config, core, utils)
|-- tests/                  # Pytest suite (unit, integration, GPU markers)
|-- AGENTS.md               # Agent operations guide
|-- CHANGELOG.md            # Version history and release notes
|-- CMakeLists.txt          # Top level CMake configuration
|-- CMakePresets.json       # Preset builds for host toolchains
|-- CONTRIBUTING.md         # Contribution workflow and review expectations
|-- Dockerfile              # Container recipe for CI/local parity
|-- LICENSE                 # Project license
|-- README.md               # High level introduction and quick start
|-- dvc.yaml                # DVC pipeline definition
|-- pyproject.toml          # Python packaging, lint, and test configuration
```

### C++ Library (cpp/) - v0.9.5 Architecture
```
cpp/
|-- benchmarks/             # C++ standalone benchmark harness
|   |-- core/              # Config, results, persistence, baseline CLI
|   |-- formatters/        # Output formatters
|   |-- runners/           # Benchmark runners (latency, throughput, realtime, accuracy)
|   |-- utils/             # Signal generator, reference compute
|   |-- baseline_cli.cpp   # Baseline management CLI
|   `-- main.cpp           # Entry point
|-- bindings/
|   `-- bindings.cpp        # pybind11 BatchExecutor/StreamingExecutor bindings
|-- include/sigtekx/
|   |-- core/              # Core abstractions and CUDA resource wrappers
|   |   |-- cuda_wrappers.hpp
|   |   |-- executor_config.hpp
|   |   |-- pipeline_builder.hpp
|   |   |-- pipeline_executor.hpp
|   |   |-- processing_stage.hpp
|   |   |-- ring_buffer.hpp
|   |   |-- signal_config.hpp
|   |   `-- window_functions.hpp
|   |-- executors/         # Executor implementations
|   |   |-- batch_executor.hpp
|   |   `-- streaming_executor.hpp
|   `-- profiling/         # NVTX profiling utilities
|       `-- nvtx.hpp
|-- src/                   # Implementation files
|   |-- core/              # Pipeline, stages, window functions, ring buffer
|   |-- executors/         # Batch & streaming executors
|   |-- kernels/           # STFT pipeline kernels (windowing, FFT wrapper, magnitude)
|   `-- profiling/         # NVTX profiling
`-- tests/                 # C++ tests (organized by component)
    |-- core/              # Pipeline and stage tests
    |-- executors/         # Executor tests
    |-- integration/       # Integration tests
    |-- kernels/           # Kernel unit tests
    `-- profiling/         # Profiling tests
```

### Python Package (src/sigtekx)
```
src/sigtekx/
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
|   |-- experiment/         # Experiment definitions (ionosphere_*, baseline_*)
|   `-- benchmark/          # Benchmark parameter grids
|-- analysis/               # Shared analysis modules (loaded by Streamlit and Quarto)
|-- scripts/                # Analysis, figure generation, report assembly
|-- streamlit/              # Interactive Streamlit dashboard (sigx dashboard)
|   |-- app.py              # Dashboard entry point
|   |-- components/         # Reusable UI components
|   `-- pages/              # Dashboard pages (general, ionosphere, config explorer)
|-- quarto/                 # Static publication-quality report templates
`-- validation/             # Experiment validation utilities
```

Snakemake coordinates benchmark execution, analysis, and report generation using these assets.
The Streamlit dashboard (`sigx dashboard`) provides interactive exploration of results.

### Artifacts (artifacts/)

```
artifacts/
|-- benchmark_results/      # Python standalone benchmark API outputs (fallback location)
|-- cpp/                    # C++ benchmark outputs (ephemeral, gitignored)
|-- data/                   # Hydra Python experiment outputs (CSV) - PRIMARY for analysis
|-- experiments/            # Hydra run directories for single runs and multirun sweeps
|-- mlruns/                 # MLflow tracking store (local file backend)
|-- profiling/
|   |-- ncu_reports/        # Nsight Compute traces (.ncu-rep)
|   `-- nsys_reports/       # Nsight Systems traces (.nsys-rep)
`-- reports/                # Generated analysis reports and summaries
```

### Persistent Datasets (datasets/)

```
datasets/
|-- <name>/                 # Python benchmark snapshot (sigx dataset save)
|   |-- manifest.json       # source, git sha, hardware, summary metrics
|   |-- data/               # copied from artifacts/data/
|   `-- mlruns/             # optional (scope=standard|full)
|-- aws-<timestamp>/        # Cloud run pulled by scripts/aws/download_results.sh
`-- cpp/                    # C++ benchmark snapshots (sigxc dataset save)
    |-- latency_full/       # Example: latency preset full run
    `-- <name>/             # metadata.json + results.json + results.csv
```

**Benchmark Output Locations:**

| System | Directory | Purpose | Created By |
|--------|-----------|---------|------------|
| **Hydra Experiments (live)** | `artifacts/data/` | Ephemeral scratchpad — every local run writes here | `run_latency.py`, `run_throughput.py`, etc. |
| **Python Standalone API** | `artifacts/benchmark_results/` | Fallback for direct benchmark class usage | Benchmark classes when `output_dir=None` |
| **Python Persistent Datasets** | `datasets/<name>/` | Named snapshots that survive `sigx clean` | `sigx dataset save <name>` |
| **AWS Cloud Datasets** | `datasets/aws-<timestamp>/` | EC2 runs pulled from S3 | `scripts/aws/download_results.sh` |
| **C++ Persistent Datasets** | `datasets/cpp/<name>/` | C++ benchmark snapshots (decoupled from Python) | `sigxc dataset save <name>` |

The `datasets/` root is the single persistent storage concept. The `datasets/cpp/` subtree is fully decoupled from the Python pipeline so the raw C++ benchmark path can be exercised and archived even when Python is broken.


### Build Outputs (build/)

```
build/
|-- windows-rel/            # Latest Windows release build (CTest + binaries)
`-- <preset>/               # Any additional CMake presets generated locally
```


### Python Module Artefacts
Shared objects produced by builds land in `src/sigtekx/core/`. Expect `_engine.pyd` on Windows and `_engine.so` on Linux/WSL.


## Documentation Index

| Document | Audience | Purpose |
|----------|----------|---------|
| [README.md](README.md) | Everyone | High-level overview, supported platforms, quick links |
| [docs/README.md](docs/README.md) | Everyone | Documentation entry point and navigation |
| [docs/getting-started/install.md](docs/getting-started/install.md) | Contributors | Environment provisioning on Windows and Ubuntu |
| [docs/getting-started/workflow-guide.md](docs/getting-started/workflow-guide.md) | Researchers | Snakemake-driven experiment workflow |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contributors | Day-to-day development practices and checklists |
| [docs/benchmarking/README.md](docs/benchmarking/README.md) | Researchers | Benchmark methodology, datasets, and KPIs |
| [docs/reference/api-reference.md](docs/reference/api-reference.md) | Integrators | Python package surface and binding details |
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

## Measured Performance (v0.9.5, RTX 3090 Ti)

| Metric | Measured | Configuration |
|--------|----------|---------------|
| StreamingExecutor latency (mean) | 160.1 µs | nfft=4096, 2ch, overlap=0.5, 100 kHz |
| StreamingExecutor latency (P95) | 191.5 µs | same |
| StreamingExecutor throughput | 4,549 FPS | same |
| Real-time compliance | 100% | 48 kHz ionosphere streaming |
| SNR | >123 dB | vs double-precision reference |

## Output Artefacts
- Generated content persists under `artifacts/` (configurable via `SIGX_OUTPUT_ROOT`).
- Benchmark outputs:
  - Hydra experiments (live scratchpad): `artifacts/data/`
  - Python standalone: `artifacts/benchmark_results/`
  - Persistent datasets (Python + AWS + C++): `datasets/`
- Experiment dumps: `artifacts/experiments/`
- QA reports (lint, coverage, validation): `artifacts/reports/`
- Profiling traces: `artifacts/profiling/nsys_reports/` & `artifacts/profiling/ncu_reports/`
- CLI research logs: `artifacts/logs/`

## Tooling Notes
- Run `cmake --list-presets` and `ctest --list-presets` to discover configured build and test targets.
- Confirm the active Conda environment with `conda info --envs`; all developer tooling resolves from `sigtekx`.
- Execute GPU-specific tests on demand via `python -m pytest -m gpu --maxfail=1`.
- Clear analysis caches manually when stale by deleting `.mypy_cache/`, `.ruff_cache/`, and `.pytest_cache/`.
- Nsight CLI tools (`nsys`, `ncu`) store reports under `artifacts/profiling/`; set `SIGX_OUTPUT_ROOT` to redirect outputs per experiment.

## Related Standards & Practices
- Research Software Engineering (RSE) guidelines govern documentation, testing, and reproducibility.
- Requirements Engineering principles applied via issue templates and CONTRIBUTING checklist.
- IEEE 1074 guides lifecycle activities (planning, verification, maintenance) enforced in docs and CI gates.
- IEEE 754 considerations documented in benchmarking + validation routines; avoid precision regressions without review.

## Update History
- 2026-04-15: Unified persistent benchmark storage under `datasets/` (replacing `baselines/`); `sigx dataset`/`sigxc dataset` verbs replace `baseline`. C++ snapshots move to `datasets/cpp/`, AWS cloud runs land in `datasets/aws-<timestamp>/`.
- 2026-03-07: Aligned with v0.9.5: updated cpp/ headers, experiments/ layout, dataset location, performance table uses real measured numbers (RTX 3090 Ti).
- 2025-10-15: Removed deprecated CLI wrapper references, refreshed documentation index, and aligned directory descriptions with current tooling.
- 2025-09-15: Synchronized structure with `cpp/`, refreshed dependency constraints, and aligned workflow commands with CLI scripts.
