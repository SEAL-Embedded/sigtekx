# Contributing to SigTekX

Thank you for your interest in contributing to sigtekx! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Team Structure](#team-structure)
- [How to Contribute](#how-to-contribute)
- [Development Process](#development-process)
- [Style Guidelines](#style-guidelines)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)

## Getting Started

### Prerequisites

Before contributing, ensure you have the development environment set up properly.

#### Required Software

- **Python 3.11+** (via Conda/Miniconda)
- **CUDA Toolkit 13.0+** 
- **Visual Studio 2022** with C++ build tools (Windows)
- **PowerShell 7.0+** (for Windows development)
- **NVIDIA GPU** with compute capability 6.0+

#### Initial Setup

```powershell
# Clone the repository with submodules
git clone --recursive https://github.com/your-org/sigtekx.git
cd sigtekx

# Start development shell (handles MSVC, conda activation, etc.)
.\scripts\init_pwsh.ps1 -Interactive

# Setup environment (creates conda env, installs dependencies)
sigx setup

# Verify environment
sigx doctor
```

### Development Shell

The project uses an enhanced PowerShell development shell (`init_pwsh.ps1`) that:
- Automatically activates Visual Studio build tools (MSVC)
- Sets up conda environment
- Provides convenient command aliases (`iono`, `ib`, `it`, etc.)
- Ensures correct 64-bit environment for CUDA

**Always start your development session with:**
```powershell
.\scripts\init_pwsh.ps1 -Interactive
```

### Verify Your Setup

```powershell
sigx doctor                     # Comprehensive environment check
sigx build                      # Verify build works
sigx test                       # Verify tests pass
```

## Development Workflow

### CLI Commands

The `sigx` CLI provides essential development commands:

```powershell
# Environment management
sigx setup                      # Create conda environment and install package
sigx doctor                     # Check development environment health

# Build
sigx build                      # Build with default preset (windows-rel)
sigx build --debug              # Build debug configuration
sigx build --clean              # Clean rebuild
sigx build --verbose            # Verbose build output

# Testing
sigx test                       # Run all tests (Python + C++)
sigx test python                # Python tests only
sigx test cpp                   # C++ tests only
sigx test --coverage            # With coverage report
sigx test --verbose             # Verbose test output

# Code Quality
sigx format                     # Format C++ code with clang-format
sigx format --check             # Check formatting without changes
sigx lint                       # Lint Python code with ruff
sigx lint --fix                 # Auto-fix lint issues

# Utilities
sigx clean                      # Remove build artifacts
sigx clean --all                # Remove build + artifacts directories
sigx ui                         # Launch MLflow UI
sxp nsys latency                # Profile with Nsight Systems
sxp ncu throughput              # Profile with Nsight Compute
sigx run <script.py>            # Run Python script with proper environment
```

### Convenient Aliases

The development shell provides short aliases for common commands:

```powershell
ib                              # iono build
it                              # iono test
itp                             # iono test python
itc                             # iono test cpp
ifmt                            # iono format
ilint                           # iono lint
iclean                          # iono clean
iprof                           # iono profile
ihelp                           # iono help
ireload                         # Reload shell functions
```

## Team Structure

The project is organized into **two primary development boards**:

### Board 1: Platform & Core Systems
**Teams:** Core Systems (Team 1) + MLOps (Team 2)

- **Team 1**: C++/CUDA backend, processing pipeline, performance optimization
- **Team 2**: Build systems, CI/CD, development tooling, environment management

**Focus:** Infrastructure that enables research

### Board 2: User Interface & Research
**Teams:** Python Ecosystem (Team 3) + Research & Data Science (Team 4)

- **Team 3**: Python API, configuration, benchmarks, testing
- **Team 4**: Research experiments, analysis pipelines, data science

**Focus:** User-facing capabilities and scientific workflows

See the [Project Boards](https://github.com/your-org/ionosense-hpc/projects) for active work items.

## How to Contribute

### Types of Contributions

#### 1. Bug Reports (All Teams)
- Use the GitHub issue tracker
- Check if the issue already exists
- Run diagnostics: `iono doctor`
- Provide minimal reproducible example
- Include full error output

#### 2. Bug Fixes (All Teams)
- Reference the issue number in your PR
- Include tests that verify the fix
- Update documentation if needed
- Ensure all existing tests still pass

#### 3. New Features

**Team 1 (C++/CUDA):**
- Discuss major architecture changes first
- Follow RAII patterns for resource management
- Include performance benchmarks
- Update Python bindings if needed

**Team 2 (Infrastructure):**
- Test on clean environment
- Update documentation for new workflows
- Consider cross-platform implications
- Verify CI/CD integration

**Team 3 (Python API):**
- Include comprehensive tests
- Add type hints for all public APIs
- Update documentation and examples
- Follow Pydantic patterns for configuration

**Team 4 (Research):**
- Document experiment configurations
- Include analysis scripts
- Ensure reproducibility (seeds, versioning)
- Share results in MLflow

#### 4. Performance Improvements (Teams 1, 3)
- Profile before and after changes
- Use `iono profile` for GPU profiling
- Document optimization techniques
- Ensure no accuracy regressions

#### 5. Documentation (All Teams)
- Keep code examples up to date
- Test all command-line examples
- Update architecture diagrams if needed
- Add Jupyter notebook examples for complex workflows

## Development Process

### 1. Fork and Clone

```powershell
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/sigtekx.git
cd sigtekx
git remote add upstream https://github.com/original/sigtekx.git

# Setup development environment
.\scripts\init_pwsh.ps1 -Interactive
sigx setup
```

### 2. Create Feature Branch

```powershell
# Update your fork
git checkout main
git fetch upstream
git merge upstream/main

# Create feature branch following conventions:
git checkout -b feat/team-X/your-feature-name      # For features
git checkout -b fix/team-X/issue-number-description  # For bugs
git checkout -b docs/team-X/documentation-update    # For docs

# Team prefixes: team-1 (C++), team-2 (infra), team-3 (python), team-4 (research)
```

### 3. Development Loop

```powershell
# Make your changes...

# Build and test frequently
sb                              # Quick build
st                              # Run all tests

# For C++ work (Team 1):
sigx build --debug              # Debug build for development
st cpp                          # C++ tests only
sxp nsys latency                # Profile performance

# For Python work (Team 3):
st python                       # Python tests only
slint --fix                     # Fix lint issues
sigx test --coverage            # Check coverage

# For Research work (Team 4):
python benchmarks/run_latency.py experiment=baseline +benchmark=latency
sigx ui                         # View results in MLflow
```

### 4. Code Quality Checks

Before committing, ensure code quality:

```powershell
# Format C++ code
sigx format

# Lint Python code
sigx lint --fix

# Run all tests
sigx test

# Verify build is clean
sigx build --clean
```

### 5. Commit Your Changes

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructuring
- `perf`: Performance improvement
- `test`: Tests
- `build`: Build system
- `ci`: CI/CD
- `chore`: Maintenance

**Scopes:** `team-1`, `team-2`, `team-3`, `team-4`, `core`, `api`, `benchmarks`, `cli`, `docs`

**Example:**
```bash
git commit -m "feat(team-3): add real-time latency benchmark

- Implements sub-millisecond latency measurement
- Adds deadline miss tracking
- Integrates with MLflow for tracking

Closes #123"
```

### 6. Push and Create PR

```powershell
git push origin feat/team-X/your-feature-name
```

Then create a Pull Request on GitHub.

## Style Guidelines

### Python Style (Teams 3, 4)

- **PEP 8** with 100-character line limit
- **Type hints** required for all public APIs
- **Docstrings** (Google style) for all public functions/classes
- **Formatting**: Enforced by `ruff` (run `iono lint --fix`)

```python
def process_signal(
    data: np.ndarray,
    config: EngineConfig | None = None,
    validate: bool = True,
) -> np.ndarray:
    """Process a signal using the FFT engine.
    
    Args:
        data: Input signal array (shape: [batch, nfft])
        config: Optional engine configuration
        validate: Whether to validate input dimensions
        
    Returns:
        Magnitude spectrum array (shape: [batch, nfft//2+1])
        
    Raises:
        ValidationError: If input validation fails
        EngineStateError: If engine is not initialized
    """
    # Implementation
```

### C++ Style (Team 1)

- **Google C++ Style Guide**
- **Formatting**: Enforced by `clang-format` (run `iono format`)
- **Naming**: `snake_case` for functions/variables, `CamelCase` for classes
- **RAII**: Use smart pointers, avoid manual memory management
- **Move semantics**: Delete copy, default move for resource-owning classes

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
    
    void process(const float* input, float* output, size_t num_samples);
    
private:
    class Impl;
    std::unique_ptr<Impl> pImpl_;  // Pimpl pattern
};
```

### Configuration Style (Team 4)

Use Hydra YAML for experiment configurations:

```yaml
# experiments/conf/experiment/my_experiment.yaml
# @package _global_

defaults:
  - /engine: throughput
  - /benchmark: throughput

experiment:
  name: my_experiment
  description: "Description of what this experiment does"
  
engine:
  nfft: 2048
  batch: 8
  overlap: 0.5

benchmark:
  iterations: 1000
  warmup_iterations: 100
```

## Testing Requirements

### Running Tests

```powershell
iono test                       # All tests
iono test python                # Python only
iono test cpp                   # C++ only
iono test --coverage            # With coverage report
iono test --verbose             # Verbose output
iono test -Pattern "test_name"  # Specific test pattern
```

### Test Structure (Teams 3, 4)

```python
import pytest
import numpy as np
from sigtekx import Engine
from sigtekx.config import Presets

class TestEngine:
    """Test the Engine class."""
    
    @pytest.fixture
    def engine(self):
        """Create a test engine instance."""
        return Engine(Presets.validation())
    
    def test_basic_processing(self, engine):
        """Test basic signal processing."""
        # Arrange
        input_data = np.random.randn(1024).astype(np.float32)
        
        # Act
        output = engine.process(input_data)
        
        # Assert
        assert output.shape == (1, 513)  # nfft//2+1
        assert output.dtype == np.float32
        assert np.all(output >= 0)  # Magnitude is non-negative
        assert not np.any(np.isnan(output))
    
    @pytest.mark.parametrize("nfft", [256, 512, 1024, 2048])
    def test_different_sizes(self, nfft):
        """Test processing with different FFT sizes."""
        config = Presets.validation()
        config.nfft = nfft
        engine = Engine(config)
        
        input_data = np.zeros(nfft, dtype=np.float32)
        output = engine.process(input_data)
        
        assert output.shape == (1, nfft // 2 + 1)
```

### Performance Tests (Teams 1, 3)

```python
def test_latency_requirement():
    """Ensure real-time latency requirement is met."""
    engine = Engine(Presets.realtime())
    data = np.random.randn(2048).astype(np.float32)
    
    # Warmup
    for _ in range(100):
        engine.process(data)
    
    # Measure
    import time
    latencies = []
    for _ in range(1000):
        start = time.perf_counter()
        engine.process(data)
        latencies.append((time.perf_counter() - start) * 1e6)
    
    p99_latency = np.percentile(latencies, 99)
    assert p99_latency < 200, f"P99 latency {p99_latency:.1f}μs exceeds 200μs"
```

### C++ Tests (Team 1)

Use Google Test framework. Tests are run automatically with `iono test cpp`.

## Pull Request Process

### Before Submitting

1. **Ensure Code Quality**
   ```powershell
   sigx format              # Format C++ code
   sigx lint --fix          # Fix lint issues
   ```

2. **Run All Tests**
   ```powershell
   sigx test                # All tests must pass
   sigx build --clean       # Must build cleanly
   ```

3. **Update Documentation**
   - Add/update docstrings
   - Update README.md if needed
   - Add entry to CHANGELOG.md (Unreleased section)
   - Update architecture diagrams if applicable

4. **Verify on Clean Environment** (Team 2)
   ```powershell
   sigx clean --all
   sigx setup
   sigx build
   sigx test
   ```

### PR Template

```markdown
## Description
[Brief description of changes]

## Type of Change
- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change
- [ ] Documentation update
- [ ] Performance improvement
- [ ] Infrastructure/tooling

## Team
- [ ] Team 1 (C++/CUDA)
- [ ] Team 2 (MLOps/Infrastructure)
- [ ] Team 3 (Python API)
- [ ] Team 4 (Research/Data Science)

## Validation
- [ ] `sigx format` applied
- [ ] `sigx lint` passes
- [ ] `sigx test` passes
- [ ] `sigx build --clean` succeeds
- [ ] Tested on GPU: [model name]

## Testing
- [ ] All existing tests pass
- [ ] Added new tests for changes
- [ ] Manual testing completed

## Documentation
- [ ] Code includes docstrings/comments
- [ ] Updated relevant documentation
- [ ] Updated CHANGELOG.md

## Related Issues
Closes #[issue number]

## Performance Impact
[If applicable, include before/after benchmarks]

## Breaking Changes
[If applicable, describe migration path]
```

### Review Process

1. **Automated Checks**
   - CI/CD runs tests and builds
   - Code coverage analysis
   - Style checking

2. **Peer Review**
   - At least one maintainer approval required
   - Team lead review for team-specific changes
   - Address all review feedback

3. **Merge Criteria**
   - All tests passing
   - Approved by maintainer
   - No merge conflicts
   - Documentation updated
   - CHANGELOG.md updated

## Reporting Issues

For detailed guidance on creating high-quality issues, see **[Creating Issues Guide](docs/CREATING_ISSUES.md)**.

### Quick Issue Guidelines

**Title Format:** `[Action Verb] [Specific Problem] in [Component]`

**Required Labels:**
- **Type**: `bug`, `feature`, or `task`
- **Team**: `team-1-cpp`, `team-2-mlops`, `team-3-python`, `team-4-research`
- **Categories**: `python`, `c++`, `cuda`, `performance`, `documentation`, etc.

### Bug Reports

```markdown
## Bug Description
[Clear description of the bug]

## To Reproduce
Steps to reproduce (include exact commands):
1. `iono setup`
2. `iono build`
3. Run: `python script.py`
4. See error

## Expected Behavior
[What should happen]

## Actual Behavior
[What actually happens]

## Environment
```powershell
# Run these commands and paste output:
sigx doctor
```

## System Information
- OS: [Windows 10/11]
- Python: [version from `python --version`]
- CUDA: [version from `nvcc --version`]
- GPU: [model from `nvidia-smi`]

## Error Output
```
[Paste full error message and stack trace]
```

## Additional Context
[Any other relevant information]
```

### Feature Requests

For detailed guidance on proposing features, see **[Creating Issues Guide](docs/CREATING_ISSUES.md)**.

```markdown
## Feature Description
[Clear description of the proposed feature]

## Motivation
Why is this feature needed? What problem does it solve?

## Proposed Implementation
[High-level description of how it could be implemented]

## Team Assignment
Which team(s) would this affect?
- [ ] Team 1 (C++/CUDA Core)
- [ ] Team 2 (Infrastructure)
- [ ] Team 3 (Python API)
- [ ] Team 4 (Research)

## Alternatives Considered
[Other approaches you've considered]

## Additional Context
[Any other relevant information, examples, or mockups]
```

## Research Contributions (Team 4)

### Experiment Contributions

1. **Create Experiment Configuration**
   ```yaml
   # experiments/conf/experiment/my_study.yaml
   # @package _global_
   
   defaults:
     - /engine: throughput
     - /benchmark: throughput
   
   experiment:
     name: my_study
     description: "Study description"
   
   engine:
     nfft: 4096
     batch: 16
   ```

2. **Run Experiment**
   ```powershell
   python benchmarks/run_throughput.py experiment=my_study +benchmark=throughput
   ```

3. **Document Results**
   - Save outputs to `artifacts/`
   - Track in MLflow (`iono ui`)
   - Create analysis notebook in `experiments/notebooks/`
   - Add figures to `artifacts/figures/`

4. **Share Findings**
   - Open PR with configuration and analysis
   - Include visualizations
   - Document methodology in notebook
   - Reference related papers/research

## Community

### Getting Help

- **CLI Help**: `sigx help`
- **Environment Check**: `sigx doctor`
- **Documentation**: Check `docs/` directory
- **Issues**: Search [existing issues](https://github.com/sigtekx/issues)
- **Discussions**: Join [GitHub Discussions](https://github.com/sigtekx/discussions)

### Communication

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: Questions and design discussions
- **Pull Requests**: Code contributions
- **Project Boards**: Track active work

### Code of Conduct

- Be respectful and inclusive
- Use clear, professional language
- Focus on constructive feedback
- Help newcomers learn the codebase
- Follow the project's technical standards

## Quick Reference

### Essential Commands

```powershell
# Setup and environment
.\scripts\init_pwsh.ps1 -Interactive    # Start dev shell
sigx setup                              # Setup environment
sigx doctor                             # Check health

# Development cycle
sb                                      # Build (sigx build)
st                                      # Test (sigx test)
sfmt                                    # Format (sigx format)
slint                                   # Lint (sigx lint)

# Specialized tasks
sxp nsys latency                        # GPU profiling
sigx ui                                 # MLflow UI
python benchmarks/run_*.py              # Run benchmarks
```

### Team-Specific Workflows

**Team 1 (C++/CUDA):**
```powershell
sigx build --debug
st cpp
sxp ncu throughput
```

**Team 2 (Infrastructure):**
```powershell
sigx clean --all
sigx setup
sigx build --clean
sigx test
```

**Team 3 (Python):**
```powershell
st python
slint --fix
sigx test --coverage
```

**Team 4 (Research):**
```powershell
python benchmarks/run_latency.py experiment=my_exp +benchmark=latency
sigx ui
jupyter lab experiments/notebooks/
```

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

If you have questions:
1. Check `iono help` for CLI documentation
2. Run `iono doctor` for environment issues
3. Search existing issues and discussions
4. Open a discussion for general questions
5. Contact maintainers for specific concerns

Thank you for contributing to sigtekx!
