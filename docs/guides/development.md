# Development Guide

This guide is for developers contributing to sigtekx. It covers the CLI-based development environment, architecture, coding standards, and contribution workflow.

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
git clone --recursive https://github.com/SEAL-Embedded/sigtekx.git
cd sigtekx

# One-command setup using CLI
./scripts/cli.sh setup

# Verify environment
./scripts/cli.sh doctor
```

#### Windows

```powershell
# Clone the repository
git clone --recursive https://github.com/SEAL-Embedded/sigtekx.git
cd sigtekx

# Start enhanced development shell
.\scripts\init_pwsh.ps1

# One-command setup using alias
sigx setup

# Verify environment
sigx doctor
```

## CLI Development Workflow

The sigtekx CLI provides a unified interface for all development tasks, with platform-specific optimizations.

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
pytest tests/ --cov=sigtekx  # Python tests with coverage report

# Modern research workflow (🌟 Recommended - Direct Tools)
python benchmarks/run_latency.py experiment=baseline           # Run single experiment
python benchmarks/run_latency.py --multirun experiment=nfft_scaling  # Run parameter sweep
snakemake --cores 4 --snakefile experiments/Snakefile         # Execute analysis pipeline
mlflow ui --backend-store-uri file://./artifacts/mlruns       # View experiment results
python custom_script.py                                       # Run any Python script
./scripts/cli.sh profile nsys latency                         # Profile with Nsight Systems
python -m sigtekx.benchmarks.accuracy                   # Numerical validation suite
./scripts/cli.sh monitor                                      # Real-time GPU monitoring
```

### Windows Development Shell

The enhanced development shell (`.\scripts\init_pwsh.ps1`) provides:

- **Automatic MSVC Setup**: Configures 64-bit Visual Studio tools
- **Conda Integration**: Activates sigtekx environment
- **Essential CLI Aliases**: Shortcuts for essential build/development tasks
- **Repository Awareness**: Commands work from any subdirectory

```powershell
# Start development shell (one-time per session)
.\scripts\init_pwsh.ps1

# Available aliases for essential CLI commands:
sigx<command>        # Main CLI alias
ib                    # Build (sigx build)
ir                    # Rebuild (sigxrebuild)

# Code quality shortcuts
ifmt                  # Format code (sigx format)
ilint                 # Lint code (sigx lint)

# Development utilities
iprof nsys latency    # Profile with Nsight
imon                  # Monitor GPU (sigxmonitor)
iinfo                 # System info (sigxinfo)
iclean                # Clean (sigx clean)
ilearn                # Learning guides (sigxlearn)

# For research workflows, use direct tools:
# python benchmarks/run_latency.py experiment=baseline
# pytest tests/ -v
# snakemake --cores 4 --snakefile experiments/Snakefile
```

### Daily Development Cycle

**Essential Development Tasks (All Platforms):**
```bash
# Start development session
cd sigtekx
sigx doctor                      # Check environment health

# Make changes to code...

# Verify changes with essential CLI tools
sigx format && sigx lint         # Format and lint code
sigx typecheck                   # Type check Python code
sigx build                       # Build with changes
pytest tests/ -v                 # Run tests

# Performance validation with direct tools
python benchmarks/run_latency.py experiment=baseline  # Performance validation
sxp nsys latency        # Detailed profiling
```

**Windows Enhanced Shell (Optional):**
```powershell
# Start development session with enhanced aliases
.\scripts\init_pwsh.ps1     # Enhanced shell with aliases
sigx doctor                     # Check environment health

# Make changes to code...

# Verify changes (using aliases)
ifmt && ilint                  # Format and lint code
sigx typecheck                 # Type check Python code
ib                             # Build with changes
pytest tests/ -v               # Run tests

# Research workflow with direct tools
python benchmarks/run_latency.py experiment=baseline  # Performance validation
iprof nsys latency            # Detailed profiling (alias)
```

## Project Structure

```
sigtekx/
├── cpp/                        # C++ backend
│   ├── include/sigtekx/          # Public C++ headers
│   ├── src/                      # C++ source and CUDA kernels
│   ├── bindings/                 # pybind11 bindings
│   └── tests/                    # C++ unit tests (Google Test)
├── src/sigtekx/                # Python package
│   ├── core/                     # Engine API and bindings
│   ├── config/                   # Pydantic configuration models
│   ├── benchmarks/               # Benchmark framework
│   └── utils/                    # Utilities (signals, device, logging)
├── tests/                      # Python tests (pytest)
├── benchmarks/                 # Benchmark entry-point scripts
├── experiments/                # Research experiments and Hydra configs
├── scripts/                    # Development tooling
│   ├── cli.ps1                   # PowerShell CLI (Windows)
│   ├── cli.sh                    # Bash CLI (Linux/macOS)
│   └── init_pwsh.ps1             # Enhanced Windows development shell
├── docs/                       # Documentation
└── environments/               # Conda environment specs
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
sigx clean
sigx build

# Debug build
sigx build -Debug

# Release build (default)
sigx build -Release

# Verbose build with all output
sigx build -Verbose

# Build without NVTX profiling
sigx build -NoNvtx
```

**Windows Enhanced Shell (Optional Aliases):**
```powershell
# Start enhanced shell for aliases
.\scripts\init_pwsh.ps1

# Clean build using aliases
iclean
ib                    # or 'sigx build'

# Debug build
sigx build -Debug

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
pytest tests/ --cov=sigtekx --cov-report=term-missing

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
from sigtekx import Engine, Presets

@pytest.mark.gpu
class TestEngine:
    """Test Engine functionality."""

    def test_basic_processing(self):
        """Test basic signal processing."""
        config = Presets.validation()
        test_data = np.random.randn(config.nfft * config.channels).astype(np.float32)

        with Engine(config) as engine:
            output = engine.process(test_data)

            assert output.shape == (config.channels, config.num_output_bins)
            assert not np.any(np.isnan(output))
```

## Debugging

### Using CLI Debug Features

**Environment Debugging:**
```bash
# All platforms
sigx doctor                       # Comprehensive environment check
$env:SIGX_LOG_LEVEL="DEBUG"      # Enable debug logging (Windows)
export SIGX_LOG_LEVEL=DEBUG      # Enable debug logging (Linux/WSL)
```

**Build Debugging:**
```bash
# All platforms
sigx build -Debug                 # Debug build
sigx build -Verbose               # Verbose build output

# Windows enhanced shell (optional aliases)
sigx build -Debug         # Debug build
ib -Verbose              # Verbose build output
```

### CUDA Debugging

```bash
# Enable CUDA error checking
export CUDA_LAUNCH_BLOCKING=1

# Run with cuda-memcheck (Linux)
cuda-memcheck python your_script.py

# Profile with Nsight (both platforms)
sxp nsys latency                   # Essential CLI
iprof nsys latency                           # Windows alias (optional)
```

### Common Issues

1. **CLI Not Found**
   - Linux: `chmod +x scripts/cli.sh`
   - Windows: Use `.\scripts\init_pwsh.ps1` for enhanced shell

2. **Build Failures**
   - Run `sigx doctor` first
   - Check CUDA toolkit installation
   - Verify conda environment activation

3. **Import Errors**
   - Rebuild: `sigx clean` then `sigx build`
   - Check Python path in conda environment

## Contributing

### Development Workflow

1. **Setup Development Environment**
   ```bash
   # All platforms
   git clone --recursive https://github.com/SEAL-Embedded/sigtekx.git
   cd sigtekx
   sigx setup

   # Optional: Windows enhanced shell with aliases
   .\scripts\init_pwsh.ps1
   sigx setup
   ```

2. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Development Loop**
   ```bash
   # All platforms - Essential CLI
   sigx format && sigx lint        # Format and lint code
   sigx typecheck                  # Type check Python code
   sigx build                      # Build changes
   pytest tests/ -v               # Run tests

   # Windows enhanced shell (optional aliases)
   ifmt && ilint                  # Format and lint code
   sigx typecheck                 # Type check Python code
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
sigx format -Check                # Verify C++ formatting
sigx lint                         # Lint Python and C++ code
sigx typecheck                    # Type check Python code

# Windows enhanced shell (optional aliases)
ifmt -Check                      # Verify C++ formatting
ilint                            # Lint code
sigx typecheck                   # Type check
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
# Version is managed in src/sigtekx/__version__.py
pytest tests/ -v                 # Full test suite
python benchmarks/run_latency.py experiment=baseline  # Performance regression check

# Windows enhanced shell (optional aliases)
# Version is in src/sigtekx/__version__.py
pytest tests/ -v                 # Full test suite
python benchmarks/run_latency.py experiment=baseline  # Performance regression check
```

### Build and Package

```bash
# All platforms - Essential CLI
sigx clean -All                  # Clean everything
sigx build                       # Fresh release build
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

- `SIGX_OUTPUT_ROOT` – root for all artifacts (defaults to `artifacts/`)
- `SIGX_BENCH_DIR`, `SIGX_EXPERIMENTS_DIR`, `SIGX_REPORTS_DIR` – per-area overrides

Override them in CI or custom setups if you need different paths.

## Resources

### Essential CLI Commands
- **CLI Help**: `sigx help`
- **Environment Check**: `sigx doctor`
- **C++ Benchmarking**: `sigxc help`
- **Python Profiling**: `sxp --help`

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
