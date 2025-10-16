# Development Guide

This guide is for developers contributing to ionosense-hpc. It covers the CLI-based development environment, architecture, coding standards, and contribution workflow.

## Table of Contents

- [Development Environment](#development-environment)
- [CLI Development Workflow](#cli-development-workflow)
- [Project Structure](#project-structure)
- [Architecture Overview](#architecture-overview)
- [Building from Source](#building-from-source)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Debugging](#debugging)
- [Contributing](#contributing)
- [Release Process](#release-process)

## Development Environment

### Prerequisites

- **Operating System**: Windows 11 or Ubuntu 24.04 LTS (WSL2 supported)
- **Python**: 3.11 or higher
- **CUDA Toolkit**: 13.0 or higher
- **Compiler**: GCC 14.x (Linux), MSVC 2022 (Windows)
- **CMake**: 3.26 or higher
- **Git**: 2.25 or higher

### Setting Up Development Environment

#### Linux/WSL2

```bash
# Clone the repository with submodules
git clone --recursive https://github.com/your-org/ionosense-hpc.git
cd ionosense-hpc

# One-command setup using CLI
./scripts/cli.sh setup

# Verify environment
./scripts/cli.sh doctor
```

#### Windows

```powershell
# Clone the repository
git clone --recursive https://github.com/your-org/ionosense-hpc.git
cd ionosense-hpc

# Start enhanced development shell
.\scripts\open_dev_pwsh.ps1

# One-command setup using alias
iono setup

# Verify environment
iono doctor
```

## CLI Development Workflow

The ionosense-hpc CLI provides a unified interface for all development tasks, with platform-specific optimizations.

### Linux/WSL2 Commands

```bash
# Environment management
./scripts/cli.sh setup          # Create conda environment and install deps
./scripts/cli.sh doctor         # Comprehensive environment check
./scripts/cli.sh info           # Show system/project information

# Build and development
./scripts/cli.sh build          # Configure and build (release)
./scripts/cli.sh build linux-debug  # Debug build
./scripts/cli.sh rebuild        # Clean rebuild
./scripts/cli.sh clean          # Clean build artifacts

# Code quality
./scripts/cli.sh format         # Format C++ code with clang-format
./scripts/cli.sh format --check # Check formatting without changes
./scripts/cli.sh lint           # Lint Python (ruff) and C++ (format check)
./scripts/cli.sh typecheck      # Run mypy type checking
./scripts/cli.sh check          # Run format, lint, typecheck, and quick tests

# Testing (Direct Tools)
pytest tests/ -v               # Run all Python tests
ctest --preset windows-tests   # Run C++ tests (adjust preset for platform)
pytest tests/ --cov=ionosense_hpc  # Python tests with coverage report

# Modern research workflow (🌟 Recommended - Direct Tools)
python benchmarks/run_latency.py experiment=baseline           # Run single experiment
python benchmarks/run_latency.py --multirun experiment=nfft_scaling  # Run parameter sweep
snakemake --cores 4 --snakefile experiments/Snakefile         # Execute analysis pipeline
mlflow ui --backend-store-uri file://./artifacts/mlruns       # View experiment results
python custom_script.py                                       # Run any Python script
./scripts/cli.sh profile nsys latency                         # Profile with Nsight Systems
python -m ionosense_hpc.benchmarks.accuracy                   # Numerical validation suite
./scripts/cli.sh monitor                                      # Real-time GPU monitoring
```

### Windows Development Shell

The enhanced development shell (`.\scripts\open_dev_pwsh.ps1`) provides:

- **Automatic MSVC Setup**: Configures 64-bit Visual Studio tools
- **Conda Integration**: Activates ionosense-hpc environment
- **Essential CLI Aliases**: Shortcuts for essential build/development tasks
- **Repository Awareness**: Commands work from any subdirectory

```powershell
# Start development shell (one-time per session)
.\scripts\open_dev_pwsh.ps1

# Available aliases for essential CLI commands:
iono <command>        # Main CLI alias
ib                    # Build (iono build)
ir                    # Rebuild (iono rebuild)

# Code quality shortcuts
ifmt                  # Format code (iono format)
ilint                 # Lint code (iono lint)

# Development utilities
iprof nsys latency    # Profile with Nsight
imon                  # Monitor GPU (iono monitor)
iinfo                 # System info (iono info)
iclean                # Clean (iono clean)
ilearn                # Learning guides (iono learn)

# For research workflows, use direct tools:
# python benchmarks/run_latency.py experiment=baseline
# pytest tests/ -v
# snakemake --cores 4 --snakefile experiments/Snakefile
```

### Daily Development Cycle

**Essential Development Tasks (All Platforms):**
```bash
# Start development session
cd ionosense-hpc
.\scripts\cli.ps1 doctor         # Check environment health

# Make changes to code...

# Verify changes with essential CLI tools
.\scripts\cli.ps1 check          # Format, lint, typecheck
.\scripts\cli.ps1 build          # Build with changes
pytest tests/ -v                 # Run tests

# Performance validation with direct tools
python benchmarks/run_latency.py experiment=baseline  # Performance validation
.\scripts\cli.ps1 profile nsys latency               # Detailed profiling
```

**Windows Enhanced Shell (Optional):**
```powershell
# Start development session with enhanced aliases
.\scripts\open_dev_pwsh.ps1     # Enhanced shell with aliases
iono doctor                     # Check environment health

# Make changes to code...

# Verify changes (using aliases)
iono check                      # Format, lint, typecheck
ib                             # Build with changes
pytest tests/ -v               # Run tests

# Research workflow with direct tools
python benchmarks/run_latency.py experiment=baseline  # Performance validation
iprof nsys latency            # Detailed profiling (alias)
```

## Project Structure

```
ionosense-hpc-lib/
├── bindings/                   # C++/Python binding configurations
│   └── bindings.cpp              # pybind11 entrypoint
├── include/                    # C++ public headers
│   └── ionosense/                # Main library header directory
│       ├── cuda_wrappers.hpp     # RAII wrappers for CUDA/cuFFT resources
│       ├── processing_stage.hpp  # Abstract interface for processing stages
│       └── research_engine.hpp   # Public C++ API for the research engine
├── src/                        # C++ source code implementations
│   ├── ops_fft.cu                # CUDA kernels for windowing and magnitude calculations
│   ├── processing_stage.cpp      # Implementations for concrete processing stages
│   └── research_engine.cpp       # ResearchEngine implementation details
├── tests/                      # C++ unit tests
├── python/                     # Python package source and tests
│   ├── src/                    # Source code for the Python package
│   │   └── ionosense_hpc/        # The main Python package
│   │       ├── benchmarks/       # Performance benchmarking tools
│   │       ├── config/           # Configuration management
│   │       ├── core/             # Core Python logic wrapping the C++ library
│   │       ├── stages/           # Python representations of processing stages
│   │       ├── testing/          # Utilities for testing the Python code
│   │       └── utils/            # Utility functions
│   └── tests/                  # Python unit and integration tests
├── scripts/                    # Command-line interface and utility scripts
│   ├── cli.ps1                   # PowerShell CLI script for Windows
│   ├── cli.sh                    # Bash CLI script for Linux/macOS
│   └── open_dev_pwsh.ps1         # Enhanced Windows development shell
└── docs/                       # Project documentation
```

## Architecture Overview

### Runtime Architecture

```
┌──────────────────────────────┐
│        Python API Layer       │  <- Engine class
└──────────────┬───────────────┘
               │ FFI bridge
┌──────────────▼───────────────┐
│     C++ ResearchEngine        │  <- CUDA orchestration
└──────────────┬───────────────┘
               │ CUDA kernels
┌──────────────▼───────────────┐
│         NVIDIA GPU            │
└──────────────────────────────┘
```

### Key Components

1. **Engine** – unified Python interface, lifecycle management, validation
2. **ResearchEngine** – C++ implementation that schedules CUDA work
3. **Config** – Pydantic models describing FFT, batching, and profiling options
4. **Benchmarks** – reusable benchmarking infrastructure built on top of `Engine`
5. **Utilities** – signal generators, device helpers, reporting helpers

## Building from Source

### Using CLI (Essential Commands)

**All Platforms:**
```bash
# Clean build
.\scripts\cli.ps1 clean
.\scripts\cli.ps1 build

# Debug build
.\scripts\cli.ps1 build -Debug

# Release build (default)
.\scripts\cli.ps1 build -Release

# Verbose build with all output
.\scripts\cli.ps1 build -Verbose

# Build without NVTX profiling
.\scripts\cli.ps1 build -NoNvtx
```

**Windows Enhanced Shell (Optional Aliases):**
```powershell
# Start enhanced shell for aliases
.\scripts\open_dev_pwsh.ps1

# Clean build using aliases
iclean
ib                    # or 'iono build'

# Debug build
iono build -Debug

# Verbose build
ib -Verbose
```

> Note: `clean` removes only build outputs, while `clean -All` additionally clears generated artifacts such as `artifacts/`, caches, and reports but intentionally leaves the version-controlled `experiments/` workflow tree intact.


### Manual Build (Advanced)

If you need to customize the build beyond CLI options:

```bash
# Configure manually
cd cpp
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)

# Install Python package in development mode
cd ../../python
pip install -e .
```

## Coding Standards

### Python Code Style

- **Style Guide**: PEP 8 with 100-character line limit
- **Type Hints**: Required for all public APIs
- **Docstrings**: Google style for all public functions/classes
- **Formatting**: Enforced by `cli.sh format` / `ifmt`
- **Linting**: Enforced by `cli.sh lint` / `ilint`

```python
def process_signal(
    data: np.ndarray,
    config: EngineConfig | None = None,
    validate: bool = True
) -> np.ndarray:
    """Process a signal using the FFT engine.
    
    Args:
        data: Input signal array
        config: Optional engine configuration
        validate: Whether to validate input
        
    Returns:
        Magnitude spectrum array
        
    Raises:
        ValidationError: If input validation fails
    """
```

### C++ Code Style

- **Style Guide**: Google C++ Style Guide
- **Formatting**: Enforced by `cli.sh format` / `ifmt` (clang-format)
- **Naming**: snake_case for functions, CamelCase for classes
- **Headers**: Include guards and forward declarations
- **Memory**: RAII and smart pointers

```cpp
class ResearchEngine {
public:
    explicit ResearchEngine(const EngineConfig& config);
    ~ResearchEngine();
    
    // Delete copy operations
    ResearchEngine(const ResearchEngine&) = delete;
    ResearchEngine& operator=(const ResearchEngine&) = delete;
    
    // Move operations
    ResearchEngine(ResearchEngine&&) noexcept = default;
    ResearchEngine& operator=(ResearchEngine&&) noexcept = default;
    
    void process(const float* input, float* output);
    
private:
    class Impl;
    std::unique_ptr<Impl> pImpl;
};
```

### Git Commit Messages

Follow the Conventional Commits specification:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Example:
```
feat(benchmarks): add parameter sweep functionality

- Implement grid and random search strategies
- Add Latin Hypercube sampling support
- Include results aggregation and analysis

Closes #123
```

## Testing

### Running Tests with Direct Tools

**Python Tests (pytest):**
```bash
# Run all Python tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=ionosense_hpc --cov-report=term-missing

# Run specific test patterns
pytest tests/ -k "test_engine" -v

# Run only GPU tests
pytest tests/ -m gpu -v

# Run only non-GPU tests (for CI/testing without hardware)
pytest tests/ -m "not gpu" -v
```

**C++ Tests (ctest):**
```bash
# Run all C++ tests (adjust preset for your platform)
ctest --preset windows-tests --output-on-failure

# Run C++ tests with specific pattern
ctest --preset windows-tests -R "test_engine"

# Verbose C++ test output
ctest --preset windows-tests --output-on-failure --verbose
```

**Combined Testing:**
```bash
# Run both Python and C++ tests
pytest tests/ -v && ctest --preset windows-tests --output-on-failure
```

### Test Categories

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **Benchmark Tests**: Validate benchmark infrastructure
- **GPU Tests**: Tests requiring CUDA hardware (marked with `@pytest.mark.gpu`)

### Writing Tests

```python
import pytest
import numpy as np
from ionosense_hpc import Engine, Presets

@pytest.mark.gpu
class TestEngine:
    """Test Engine functionality."""

    def test_basic_processing(self):
        """Test basic signal processing."""
        config = Presets.validation()
        test_data = np.random.randn(config.nfft * config.batch).astype(np.float32)

        with Engine(config) as engine:
            output = engine.process(test_data)

            assert output.shape == (config.batch, config.num_output_bins)
            assert not np.any(np.isnan(output))
```

## Debugging

### Using CLI Debug Features

**Environment Debugging:**
```bash
# All platforms
.\scripts\cli.ps1 doctor          # Comprehensive environment check
.\scripts\cli.ps1 info system     # System information
$env:IONO_LOG_LEVEL="DEBUG"      # Enable debug logging (Windows)
export IONO_LOG_LEVEL=DEBUG      # Enable debug logging (Linux/WSL)
```

**Build Debugging:**
```bash
# All platforms
.\scripts\cli.ps1 build -Debug     # Debug build
.\scripts\cli.ps1 build -Verbose   # Verbose build output

# Windows enhanced shell (optional aliases)
iono build -Debug         # Debug build
ib -Verbose              # Verbose build output
```

### CUDA Debugging

```bash
# Enable CUDA error checking
export CUDA_LAUNCH_BLOCKING=1

# Run with cuda-memcheck (Linux)
cuda-memcheck python your_script.py

# Profile with Nsight (both platforms)
.\scripts\cli.ps1 profile nsys latency       # Essential CLI
iprof nsys latency                           # Windows alias (optional)
```

### Common Issues

1. **CLI Not Found**
   - Linux: `chmod +x scripts/cli.sh`
   - Windows: Use `.\scripts\open_dev_pwsh.ps1` for enhanced shell

2. **Build Failures**
   - Run `.\scripts\cli.ps1 doctor` first
   - Check CUDA toolkit installation
   - Verify conda environment activation

3. **Import Errors**
   - Rebuild: `.\scripts\cli.ps1 clean` then `.\scripts\cli.ps1 build`
   - Check Python path in conda environment

## Contributing

### Development Workflow

1. **Setup Development Environment**
   ```bash
   # All platforms
   git clone --recursive https://github.com/your-org/ionosense-hpc.git
   cd ionosense-hpc
   .\scripts\cli.ps1 setup

   # Optional: Windows enhanced shell with aliases
   .\scripts\open_dev_pwsh.ps1
   iono setup
   ```

2. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Development Loop**
   ```bash
   # All platforms - Essential CLI
   .\scripts\cli.ps1 check         # Format, lint, typecheck
   .\scripts\cli.ps1 build         # Build changes
   pytest tests/ -v               # Run tests

   # Windows enhanced shell (optional aliases)
   iono check                     # Format, lint, typecheck
   ib                            # Build changes
   pytest tests/ -v              # Run tests
   ```

4. **Commit and Push**
   ```bash
   git add .
   git commit -m "feat(component): description"
   git push origin feature/your-feature-name
   ```

5. **Create Pull Request** on GitHub

### Pre-commit Checks

The CLI provides aggregated checks for code quality:

```bash
# All platforms - Essential CLI
.\scripts\cli.ps1 check           # Format, lint, typecheck
.\scripts\cli.ps1 check -Staged   # Only check staged files

# Windows enhanced shell (optional aliases)
iono check                       # Format, lint, typecheck
iono check -Staged               # Only check staged files
```

This runs:
- `format -Check`: Verify C++ formatting
- `lint`: Python (ruff) and C++ linting
- `typecheck`: mypy type checking

For tests, run `pytest tests/ -v` separately to have full control over test execution.

## Release Process

### Version Management

```bash
# All platforms
.\scripts\cli.ps1 info            # Check current version
pytest tests/ -v                 # Full test suite
python benchmarks/run_latency.py experiment=baseline  # Performance regression check

# Windows enhanced shell (optional aliases)
iono info                        # Check current version
pytest tests/ -v                 # Full test suite
python benchmarks/run_latency.py experiment=baseline  # Performance regression check
```

### Build and Package

```bash
# All platforms - Essential CLI
.\scripts\cli.ps1 clean -All     # Clean everything
.\scripts\cli.ps1 build          # Fresh release build
pytest tests/ -v                 # Verify build

# Windows enhanced shell (optional aliases)
iclean -All                      # Clean everything
ib                              # Fresh release build
pytest tests/ -v                # Verify build
```

## Outputs & Artifacts

To keep the repo clean and follow RSE/RE practices, all generated artifacts default to the top-level `artifacts/` tree:

- `artifacts/data/` – derived benchmark outputs (parquet/csv) generated by Hydra runners
- `artifacts/experiments/` – research workflows and parameter sweeps
- `artifacts/profiling/` – Nsight Systems/Compute traces grouped by tool
- `artifacts/reports/` – coverage, lint/test summaries, validation logs
- `artifacts/logs/` – JSONL research logs emitted by the CLI

The CLI initializes environment variables so Python code writes to these locations:

- `IONO_OUTPUT_ROOT` – root for all artifacts (defaults to `artifacts/`)
- `IONO_BENCH_DIR`, `IONO_EXPERIMENTS_DIR`, `IONO_REPORTS_DIR` – per-area overrides

Override them in CI or custom setups if you need different paths.

## Resources

### Essential CLI Commands
- **CLI Help**: `.\scripts\cli.ps1 help`
- **Environment Check**: `.\scripts\cli.ps1 doctor`
- **System Info**: `.\scripts\cli.ps1 info`
- **Learning Guides**: `.\scripts\cli.ps1 learn`

### Direct Tools Documentation
- [Hydra Configuration](https://hydra.cc/) - Experiment configuration management
- [Snakemake Workflows](https://snakemake.readthedocs.io/) - Workflow orchestration
- [MLflow Tracking](https://mlflow.org/) - Experiment tracking and management
- [DVC Data Versioning](https://dvc.org/) - Data version control
- [Pytest Testing](https://docs.pytest.org/) - Python testing framework

### Development Resources
- [CUDA Programming Guide](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)
- [cuFFT Documentation](https://docs.nvidia.com/cuda/cufft/)
- [Python Packaging Guide](https://packaging.python.org/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
