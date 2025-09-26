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

- **Operating System**: Linux (Ubuntu 20.04+), Windows 10/11 with WSL2, or Windows native
- **Python**: 3.8 or higher
- **CUDA Toolkit**: 11.0 or higher
- **Compiler**: GCC 9+ (Linux), MSVC 2019+ (Windows)
- **CMake**: 3.18 or higher
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

# Testing
./scripts/cli.sh test           # Run all tests
./scripts/cli.sh test py        # Python tests only
./scripts/cli.sh test cpp       # C++ tests only
./scripts/cli.sh test --coverage  # With coverage report

# Research and benchmarking
./scripts/cli.sh bench latency  # Run specific benchmark
./scripts/cli.sh bench suite    # Run complete benchmark suite
./scripts/cli.sh profile nsys latency  # Profile with Nsight Systems
./scripts/cli.sh sweep experiment.yaml  # Parameter sweep
./scripts/cli.sh validate       # Numerical validation suite
./scripts/cli.sh monitor        # Real-time GPU monitoring
```

### Windows Development Shell

The enhanced development shell (`.\scripts\open_dev_pwsh.ps1`) provides:

- **Automatic MSVC Setup**: Configures 64-bit Visual Studio tools
- **Conda Integration**: Activates ionosense-hpc environment  
- **Smart Aliases**: Convenient shortcuts with tab completion
- **Repository Awareness**: Commands work from any subdirectory

```powershell
# Start development shell (one-time per session)
.\scripts\open_dev_pwsh.ps1

# Available aliases and shortcuts:
iono <command>        # Main CLI alias
ib                    # Build (iono build)
ir                    # Rebuild (iono rebuild)
it                    # Test all (iono test)
itp                   # Test Python only (iono test py)
itc                   # Test C++ only (iono test cpp)

# Code quality shortcuts
ifmt                  # Format code (iono format)
ilint                 # Lint code (iono lint)

# Benchmarking shortcuts
ibench latency        # Run latency benchmark
iprof nsys latency    # Profile with Nsight
ipq                   # Quick Nsight profile
ipf                   # Full Nsight profile

# Utilities
ival                  # Validate (iono validate)
imon                  # Monitor GPU (iono monitor)
iinfo                 # System info (iono info)
iclean                # Clean (iono clean)

# Tab completion works for all commands and arguments
iono <TAB>           # Shows available commands
ibench <TAB>         # Shows available benchmarks
iprof <TAB>          # Shows profiling options
```

### Daily Development Cycle

**Linux/WSL2:**
```bash
# Start development session
cd ionosense-hpc
./scripts/cli.sh doctor         # Check environment health

# Make changes to code...

# Verify changes
./scripts/cli.sh check          # Format, lint, typecheck, quick tests
./scripts/cli.sh build          # Build with changes
./scripts/cli.sh test           # Full test suite

# Research workflow
./scripts/cli.sh bench latency  # Performance validation
./scripts/cli.sh profile nsys latency  # Detailed profiling
```

**Windows:**
```powershell
# Start development session
.\scripts\open_dev_pwsh.ps1     # Enhanced shell with all tools
iono doctor                     # Check environment health

# Make changes to code...

# Verify changes (using aliases)
iono check                      # Format, lint, typecheck, quick tests
ib                             # Build with changes  
it                             # Full test suite

# Research workflow
ibench latency                 # Performance validation
iprof nsys latency            # Detailed profiling
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

### Using CLI (Recommended)

**Linux/WSL2:**
```bash
# Clean build
./scripts/cli.sh clean
./scripts/cli.sh build

# Debug build
./scripts/cli.sh build linux-debug

# Verbose build with all output
./scripts/cli.sh build --verbose

# Build without NVTX profiling
./scripts/cli.sh build --no-nvtx
```

**Windows (Development Shell):**
```powershell
# Start enhanced shell
.\scripts\open_dev_pwsh.ps1

# Clean build using aliases
iclean
ib                    # or 'iono build'

# Debug build
iono build windows-debug

# Verbose build
ib --verbose

# Build without NVTX profiling  
ib --no-nvtx
```

> Note: `iclean` removes only build outputs, while `iclean --all` additionally clears generated artifacts such as `artifacts/`, caches, and reports but intentionally leaves the version-controlled `experiments/` workflow tree intact.


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

### Running Tests with CLI

**Linux/WSL2:**
```bash
# Run all tests
./scripts/cli.sh test

# Run specific test suites
./scripts/cli.sh test py         # Python only
./scripts/cli.sh test cpp        # C++ only

# Run with coverage
./scripts/cli.sh test --coverage

# Run specific patterns
./scripts/cli.sh test --pattern "test_engine"

# Verbose output
./scripts/cli.sh test --verbose
```

**Windows (Development Shell):**
```powershell
# Run all tests
it                              # or 'iono test'

# Run specific test suites  
itp                             # Python only (iono test py)
itc                             # C++ only (iono test cpp)

# Run with coverage
iono test --coverage

# Run specific patterns
iono test --pattern "test_engine"

# Verbose output
it --verbose
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
# Linux/WSL2
./scripts/cli.sh doctor          # Comprehensive environment check
./scripts/cli.sh info system     # System information
export IONO_LOG_LEVEL=DEBUG     # Enable debug logging

# Windows (in dev shell)
iono doctor                      # Comprehensive environment check
iono info system                 # System information
$env:IONO_LOG_LEVEL="DEBUG"     # Enable debug logging
```

**Build Debugging:**
```bash
# Linux/WSL2
./scripts/cli.sh build linux-debug  # Debug build
./scripts/cli.sh build --verbose    # Verbose build output

# Windows (in dev shell)
iono build windows-debug         # Debug build
ib --verbose                     # Verbose build output
```

### CUDA Debugging

```bash
# Enable CUDA error checking
export CUDA_LAUNCH_BLOCKING=1

# Run with cuda-memcheck (Linux)
cuda-memcheck python your_script.py

# Profile with Nsight (both platforms)
./scripts/cli.sh profile nsys benchmark_name  # Linux
iprof nsys benchmark_name                     # Windows
```

### Common Issues

1. **CLI Not Found**
   - Linux: `chmod +x scripts/cli.sh`
   - Windows: Use `.\scripts\open_dev_pwsh.ps1` for enhanced shell

2. **Build Failures**
   - Run `./scripts/cli.sh doctor` / `iono doctor` first
   - Check CUDA toolkit installation
   - Verify conda environment activation

3. **Import Errors**
   - Rebuild: `./scripts/cli.sh rebuild` / `ir`
   - Check Python path in conda environment

## Contributing

### Development Workflow

1. **Setup Development Environment**
   ```bash
   # Linux/WSL2
   git clone --recursive https://github.com/your-org/ionosense-hpc.git
   cd ionosense-hpc
   ./scripts/cli.sh setup
   
   # Windows
   git clone --recursive https://github.com/your-org/ionosense-hpc.git
   cd ionosense-hpc
   .\scripts\open_dev_pwsh.ps1
   iono setup
   ```

2. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Development Loop**
   ```bash
   # Linux/WSL2
   ./scripts/cli.sh check         # Format, lint, typecheck, quick tests
   ./scripts/cli.sh build         # Build changes
   ./scripts/cli.sh test          # Full test suite
   
   # Windows (in dev shell)
   iono check                     # Format, lint, typecheck, quick tests
   ib                            # Build changes
   it                            # Full test suite
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
# Linux/WSL2
./scripts/cli.sh check           # Format, lint, typecheck, quick tests
./scripts/cli.sh check --staged  # Only check staged files

# Windows (in dev shell)
iono check                       # Format, lint, typecheck, quick tests
iono check --staged              # Only check staged files
```

This runs:
- `format --check`: Verify C++ formatting
- `lint`: Python (ruff) and C++ linting
- `typecheck`: mypy type checking
- Quick Python tests (excluding slow/GPU tests)

## Release Process

### Version Management

```bash
# Linux/WSL2
./scripts/cli.sh info            # Check current version
./scripts/cli.sh test            # Full test suite
./scripts/cli.sh bench suite     # Performance regression check

# Windows (in dev shell)
iono info                        # Check current version
it                              # Full test suite
ibench suite                    # Performance regression check
```

### Build and Package

```bash
# Linux/WSL2
./scripts/cli.sh clean --all     # Clean everything
./scripts/cli.sh build          # Fresh release build
./scripts/cli.sh test            # Verify build

# Windows (in dev shell)
iclean --all                    # Clean everything
ib                             # Fresh release build
it                             # Verify build
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

- **CLI Help**: `./scripts/cli.sh help` / `iono help`
- **Environment Check**: `./scripts/cli.sh doctor` / `iono doctor`
- **System Info**: `./scripts/cli.sh info` / `iono info`
- [CUDA Programming Guide](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)
- [cuFFT Documentation](https://docs.nvidia.com/cuda/cufft/)
- [Python Packaging Guide](https://packaging.python.org/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Pytest Documentation](https://docs.pytest.org/)
