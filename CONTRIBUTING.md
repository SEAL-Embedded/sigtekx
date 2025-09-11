# Contributing to Ionosense-HPC

Thank you for your interest in contributing to ionosense-hpc! This document provides guidelines and instructions for contributing to the project using our integrated CLI platform.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [CLI-Based Development Workflow](#cli-based-development-workflow)
- [How to Contribute](#how-to-contribute)
- [Development Process](#development-process)
- [Style Guidelines](#style-guidelines)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)
- [Community](#community)

## Getting Started

### Prerequisites

Before contributing, ensure you have the development environment set up using our CLI platform.

#### Linux/WSL2 Setup

```bash
# Clone the repository with submodules
git clone --recursive https://github.com/your-org/ionosense-hpc.git
cd ionosense-hpc

# One-command setup using CLI
./scripts/cli.sh setup

# Verify environment
./scripts/cli.sh doctor
```

#### Windows Setup

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

### Development Environment Verification

**Linux/WSL2:**
```bash
./scripts/cli.sh doctor         # Comprehensive environment check
./scripts/cli.sh info system    # System information
./scripts/cli.sh build          # Verify build works
./scripts/cli.sh test           # Verify tests pass
```

**Windows (Enhanced Development Shell):**
```powershell
iono doctor                     # Comprehensive environment check
iono info system                # System information
ib                             # Verify build works (iono build)
it                             # Verify tests pass (iono test)
```

## CLI-Based Development Workflow

Ionosense-HPC uses a unified CLI platform that streamlines all development tasks. Familiarize yourself with these commands for efficient contribution.

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

# Code quality (essential for contributions)
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

# Research validation
./scripts/cli.sh validate       # Numerical validation suite
./scripts/cli.sh bench latency  # Performance validation
```

### Windows Development Shell Commands

The enhanced development shell provides convenient aliases and automatic environment setup:

```powershell
# Start development shell (required for Windows development)
.\scripts\open_dev_pwsh.ps1

# Available aliases for common tasks:
iono <command>                  # Main CLI alias
ib                             # Build (iono build)
ir                             # Rebuild (iono rebuild)
it                             # Test all (iono test)
itp                            # Test Python only (iono test py)
itc                            # Test C++ only (iono test cpp)

# Code quality shortcuts (essential for contributions)
ifmt                           # Format code (iono format)
ifmt --check                   # Check formatting (iono format --check)
ilint                          # Lint code (iono lint)
iono typecheck                 # Type checking
iono check                     # All quality checks

# Research validation shortcuts
ival                           # Validate (iono validate)
ibench latency                 # Performance validation
```

## How to Contribute

### Types of Contributions

#### 1. Bug Reports
- Use the GitHub issue tracker
- Check if the issue already exists
- Run diagnostics: `./scripts/cli.sh doctor` / `iono doctor`
- Provide minimal reproducible example
- Include system information from `./scripts/cli.sh info system` / `iono info system`

#### 2. Bug Fixes
- Reference the issue number in your PR
- Include tests: `./scripts/cli.sh test` / `it`
- Verify fix with: `./scripts/cli.sh validate` / `ival`
- Update documentation if needed

#### 3. New Features
- Discuss major features in an issue first
- Implement with tests and documentation
- Follow existing architecture patterns
- Verify with: `./scripts/cli.sh check` / `iono check`
- Consider performance impact: `./scripts/cli.sh bench` / `ibench`

#### 4. Performance Improvements
- Include benchmark results: `./scripts/cli.sh bench suite` / `ibench suite`
- Profile changes: `./scripts/cli.sh profile nsys` / `iprof nsys`
- Ensure no regression in other areas
- Document the optimization approach

#### 5. Documentation
- Verify examples work: `./scripts/cli.sh test` / `it`
- Check formatting: `./scripts/cli.sh format --check` / `ifmt --check`
- Test CLI commands referenced in docs

#### 6. Tests
- Run existing tests: `./scripts/cli.sh test` / `it`
- Add missing test coverage
- Verify performance: `./scripts/cli.sh validate` / `ival`
- Test on both platforms if possible

## Development Process

### 1. Fork and Create Branch

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/ionosense-hpc.git
cd ionosense-hpc
git remote add upstream https://github.com/original/ionosense-hpc.git

# Setup development environment
./scripts/cli.sh setup        # Linux/WSL2
# OR (Windows)
.\scripts\open_dev_pwsh.ps1
iono setup
```

### 2. Create Feature Branch

```bash
# Update your fork
git checkout main
git fetch upstream
git merge upstream/main

# Create feature branch
git checkout -b feature/your-feature-name
# Or for bugs
git checkout -b fix/issue-number-description
```

### 3. Development Loop with CLI

**Linux/WSL2:**
```bash
# Make your changes...

# Verify code quality (runs format check, lint, typecheck, quick tests)
./scripts/cli.sh check

# Build with changes
./scripts/cli.sh build

# Run full test suite
./scripts/cli.sh test

# Validate performance (for performance-critical changes)
./scripts/cli.sh validate
./scripts/cli.sh bench latency
```

**Windows (in development shell):**
```powershell
# Make your changes...

# Verify code quality using aliases
iono check                     # format, lint, typecheck, quick tests

# Build with changes
ib                            # iono build

# Run full test suite
it                            # iono test

# Validate performance (for performance-critical changes)
ival                          # iono validate
ibench latency                # iono bench latency
```

### 4. Pre-commit Validation

Before committing, always run the complete validation suite:

```bash
# Linux/WSL2
./scripts/cli.sh check --staged    # Check only staged files
./scripts/cli.sh build             # Ensure builds cleanly
./scripts/cli.sh test              # Full test suite

# Windows (dev shell)
iono check --staged               # Check only staged files
ib                               # Ensure builds cleanly
it                               # Full test suite
```

### 5. Commit Your Changes

```bash
# Stage your changes
git add .

# Verify staged changes
./scripts/cli.sh format --staged   # Linux/WSL2
ifmt --staged                      # Windows (dev shell)

# Commit with descriptive message
git commit -m "feat(module): add new capability

- Detailed description of what changed
- Why the change was needed
- Any breaking changes or side effects

Closes #123"
```

#### Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Test additions or corrections
- `build`: Build system changes
- `ci`: CI/CD changes
- `chore`: Maintenance tasks

### 6. Push Changes

```bash
git push origin feature/your-feature-name
```

## Style Guidelines

### Code Formatting and Linting

Ionosense-HPC enforces code quality through the CLI platform. Always use these commands before committing:

**Linux/WSL2:**
```bash
./scripts/cli.sh format         # Format C++ code
./scripts/cli.sh lint           # Lint Python and C++
./scripts/cli.sh typecheck      # Type checking
./scripts/cli.sh check          # All quality checks
```

**Windows (development shell):**
```powershell
ifmt                           # Format C++ code (iono format)
ilint                          # Lint Python and C++ (iono lint)
iono typecheck                 # Type checking
iono check                     # All quality checks
```

### Python Style

- **Style Guide**: PEP 8 with 100-character line limit
- **Type Hints**: Required for all public APIs
- **Docstrings**: Google style for all public functions/classes
- **Formatting**: Enforced by `./scripts/cli.sh format` / `ifmt`
- **Linting**: Enforced by `./scripts/cli.sh lint` / `ilint`

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

### C++ Style

- **Style Guide**: Google C++ Style Guide
- **Formatting**: Enforced by `./scripts/cli.sh format` / `ifmt` (clang-format)
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

## Testing Requirements

### Test Coverage

All contributions must include appropriate tests and pass the existing test suite.

**Running Tests with CLI:**
```bash
# Linux/WSL2
./scripts/cli.sh test           # All tests
./scripts/cli.sh test py        # Python tests only
./scripts/cli.sh test cpp       # C++ tests only
./scripts/cli.sh test --coverage  # With coverage report

# Windows (dev shell)
it                             # All tests (iono test)
itp                            # Python tests (iono test py)
itc                            # C++ tests (iono test cpp)
iono test --coverage           # With coverage report
```

### Performance Validation

For performance-critical changes, validate with benchmarks:

```bash
# Linux/WSL2
./scripts/cli.sh validate      # Numerical validation
./scripts/cli.sh bench latency # Performance validation
./scripts/cli.sh bench suite   # Comprehensive benchmarks

# Windows (dev shell)
ival                          # Numerical validation (iono validate)
ibench latency                # Performance validation
ibench suite                  # Comprehensive benchmarks
```

### Test Structure

```python
import pytest
import numpy as np
from ionosense_hpc import Processor, EngineConfig

class TestProcessor:
    """Test the Processor class."""
    
    @pytest.fixture
    def processor(self):
        """Create a test processor."""
        config = EngineConfig(nfft=256, batch=1)
        return Processor(config)
    
    def test_basic_processing(self, processor):
        """Test basic signal processing."""
        # Arrange
        input_data = np.random.randn(256).astype(np.float32)
        
        # Act
        output = processor.process(input_data)
        
        # Assert
        assert output.shape == (1, 129)
        assert output.dtype == np.float32
        assert not np.any(np.isnan(output))
    
    @pytest.mark.parametrize("nfft", [256, 512, 1024])
    def test_different_sizes(self, nfft):
        """Test processing with different FFT sizes."""
        config = EngineConfig(nfft=nfft)
        processor = Processor(config)
        
        input_data = np.zeros(nfft, dtype=np.float32)
        output = processor.process(input_data)
        
        assert output.shape == (1, nfft // 2 + 1)
```

### Performance Tests

```python
def test_latency_requirement():
    """Ensure real-time latency requirement is met."""
    config = Presets.realtime()
    processor = Processor(config)
    
    # Warm up
    data = np.random.randn(2048).astype(np.float32)
    for _ in range(100):
        processor.process(data)
    
    # Measure
    latencies = []
    for _ in range(1000):
        start = time.perf_counter()
        processor.process(data)
        latencies.append((time.perf_counter() - start) * 1e6)
    
    p99_latency = np.percentile(latencies, 99)
    assert p99_latency < 200, f"P99 latency {p99_latency:.1f}μs exceeds 200μs requirement"
```

## Pull Request Process

### Before Submitting

1. **Run Complete Validation**
   ```bash
   # Linux/WSL2
   ./scripts/cli.sh check       # Format, lint, typecheck, quick tests
   ./scripts/cli.sh build       # Build cleanly
   ./scripts/cli.sh test        # Full test suite
   
   # Windows (dev shell)
   iono check                   # Format, lint, typecheck, quick tests
   ib                          # Build cleanly
   it                          # Full test suite
   ```

2. **Update Documentation**
   - Add/update docstrings
   - Update README if needed
   - Add to CHANGELOG.md (unreleased section)
   - Verify CLI commands in docs work

3. **Performance Validation** (if relevant)
   ```bash
   # Linux/WSL2
   ./scripts/cli.sh validate    # Numerical validation
   ./scripts/cli.sh bench latency  # Performance check
   
   # Windows (dev shell)
   ival                        # Numerical validation
   ibench latency              # Performance check
   ```

4. **Rebase if Needed**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

### PR Template

When creating your pull request, use this template:

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Performance improvement

## CLI Validation
- [ ] `./scripts/cli.sh check` passes (Linux) OR `iono check` passes (Windows)
- [ ] `./scripts/cli.sh test` passes (Linux) OR `it` passes (Windows)
- [ ] `./scripts/cli.sh validate` passes (Linux) OR `ival` passes (Windows) (if performance-related)

## Testing
- [ ] All tests pass locally
- [ ] Added new tests for changes
- [ ] Tested on GPU (specify model): _______________

## Checklist
- [ ] Code follows project style guidelines (enforced by CLI)
- [ ] Self-reviewed code
- [ ] Added/updated documentation
- [ ] Updated CHANGELOG.md
- [ ] No new warnings generated

## Related Issues
Closes #(issue number)

## Performance Impact
[If applicable, include benchmark results from `./scripts/cli.sh bench` / `ibench`]

## Screenshots
[If applicable, include screenshots]
```

### Review Process

1. **Automated Checks**
   - CI/CD pipeline runs tests
   - Code coverage analysis
   - Style checking (same as CLI commands)

2. **Peer Review**
   - At least one maintainer review
   - Address all feedback
   - Discuss design decisions

3. **Merge Criteria**
   - All tests passing
   - Approved by maintainer
   - No merge conflicts
   - Documentation updated
   - CLI validation completed

## Reporting Issues

### Environment Information

Always include environment information when reporting issues:

```bash
# Linux/WSL2
./scripts/cli.sh doctor --verbose > environment_info.txt
./scripts/cli.sh info system >> environment_info.txt

# Windows (dev shell)
iono doctor --verbose > environment_info.txt
iono info system >> environment_info.txt
```

### Bug Report Template

```markdown
## Description
Clear description of the bug

## To Reproduce
Steps to reproduce (include CLI commands used):
1. `./scripts/cli.sh setup` (or `iono setup`)
2. `./scripts/cli.sh build` (or `ib`)
3. See error

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Environment
Attach output from:
- Linux/WSL2: `./scripts/cli.sh doctor --verbose`
- Windows: `iono doctor --verbose`

## CLI Commands Used
List the specific CLI commands that led to the issue

## Additional Context
Any other relevant information

## Possible Solution
[Optional] Suggest a fix
```

### Feature Request Template

```markdown
## Feature Description
Clear description of the feature

## Motivation
Why is this feature needed?

## Proposed CLI Integration
How should this feature integrate with the CLI?
- New commands?
- Modified existing commands?
- Configuration changes?

## Proposed Solution
How could this be implemented?

## Alternatives Considered
Other approaches considered

## Additional Context
Any other relevant information
```

## Community

### Getting Help

- **CLI Help**: `./scripts/cli.sh help` / `iono help`
- **Environment Check**: `./scripts/cli.sh doctor` / `iono doctor`
- **Documentation**: Read the [docs](docs/)
- **Issues**: Search [existing issues](https://github.com/ionosense-hpc/issues)
- **Discussions**: Join [GitHub Discussions](https://github.com/ionosense-hpc/discussions)
- **Email**: contact@ionosense.com

### Communication Channels

- **GitHub Issues**: Bug reports and feature requests
- **GitHub Discussions**: General questions and discussions
- **Pull Requests**: Code contributions
- **Email List**: Major announcements

### Development Community Standards

1. **Use CLI for Consistency**: Always use the CLI commands for builds, tests, and validation
2. **Cross-Platform Awareness**: Test on both Linux and Windows if possible
3. **Performance Consciousness**: Validate performance impact of changes
4. **Documentation First**: Update docs along with code changes
5. **Research Standards**: Follow RSE/RE practices for reproducible research

### Recognition

Contributors are recognized in:
- [CONTRIBUTORS.md](CONTRIBUTORS.md) file
- GitHub contributors page
- Release notes for significant contributions
- Annual contributor spotlight (blog post)

## CLI Quick Reference for Contributors

### Essential Commands

**Linux/WSL2:**
```bash
./scripts/cli.sh setup          # One-time setup
./scripts/cli.sh check          # Pre-commit validation
./scripts/cli.sh build          # Build project
./scripts/cli.sh test           # Run all tests
./scripts/cli.sh doctor         # Environment check
./scripts/cli.sh validate       # Performance validation
```

**Windows (Enhanced Development Shell):**
```powershell
.\scripts\open_dev_pwsh.ps1     # Start dev shell
iono setup                      # One-time setup
iono check                      # Pre-commit validation
ib                             # Build project (iono build)
it                             # Run all tests (iono test)
iono doctor                     # Environment check
ival                           # Performance validation (iono validate)
```

### Code Quality Commands

```bash
# Format and lint (Linux/WSL2)
./scripts/cli.sh format --check
./scripts/cli.sh format --staged
./scripts/cli.sh lint
./scripts/cli.sh typecheck

# Format and lint (Windows dev shell)
ifmt --check                   # iono format --check
ifmt --staged                  # iono format --staged
ilint                         # iono lint
iono typecheck
```

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

If you have questions about contributing:
1. Check this guide and other documentation
2. Use CLI help: `./scripts/cli.sh help` / `iono help`
3. Search existing issues and discussions
4. Open a discussion for general questions
5. Contact maintainers for specific concerns

Thank you for contributing to ionosense-hpc! 🚀