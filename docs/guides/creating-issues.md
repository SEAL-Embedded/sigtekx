# Creating Issues for Ionosense-HPC

This guide helps you create high-quality, actionable GitHub issues for the sigtekx project. Whether you're reporting bugs, requesting features, or proposing improvements, following these guidelines ensures your issue is clear, implementable, and properly categorized.

## Quick Reference

### Issue Types
- **`bug`** - Reliability issues, race conditions, incorrect behavior
- **`feature`** - New capabilities, enhancements, additions  
- **`task`** - Refactoring, code quality improvements, maintenance

### Team Labels
- **`team-1-cpp`** - C++/CUDA core systems work
- **`team-2-mlops`** - Infrastructure, build systems, CI/CD
- **`team-3-python`** - Python API, configuration, utilities
- **`team-4-research`** - Research experiments, analysis, benchmarks

### Category Labels
`python`, `c++`, `cuda`, `architecture`, `config`, `documentation`, `enhancement`, `maintenance`, `performance`, `refactoring`, `reliability`, `research`, `good first issue`

## Project Context

**Ionosense-HPC** is a high-performance CUDA FFT signal processing library with:
- C++17/CUDA backend (`cpp/`)
- Python interface (`python/src/sigtekx/`)
- Research-grade benchmarking infrastructure
- Focus on reproducible engineering and RSE standards

## Issue Title Format

**Pattern:** `[Action Verb] [Specific Problem] in [Component]`

**Good Examples:**
- `Fix Redundant Output in CLI Test Commands`
- `Add Real-time Latency Benchmark with Deadline Tracking`
- `Refactor Pipeline Composition from Execution Strategy`
- `Improve Error Handling in DeviceBuffer Allocation`

**Bad Examples:**
- `Bug in tests` (too vague)
- `Make things faster` (not specific)
- `Update code` (no context)

## Required Sections

### 1. Problem Section

Clearly describe what's wrong and why it matters.

```markdown
## Problem

[Clear description of the issue, including context and impact]

## Current Implementation

```language
[Actual code from the codebase showing the problematic pattern]
```

[Explanation of what's wrong with the current approach]
```

**Example:**
```markdown
## Problem

The CLI test runner produces redundant output when running language-specific test commands (`itp` for Python, `itc` for C++). Each specific command first prints a generic "Running tests..." message, then prints a language-specific message, creating unnecessary duplication.

## Current Implementation

File: `scripts/cli.ps1` (lines 109-167)

```powershell
function Invoke-Test {
    Write-Status "Running tests..."  # ← Always prints
    
    switch ($Suite.ToLower()) {
        { $_ -in @("python", "py", "p") } {
            Write-Status "Running Python tests..."  # ← Redundant
        }
    }
}
```

The issue is that line 117 executes unconditionally for all test suite types, then each switch case prints its own more descriptive message.
```

### 2. Proposed Solution

Provide concrete, working code showing how to fix the issue.

```markdown
## Proposed Solution

```language
[Concrete code showing the fix]
```

[Explanation of the approach and why it's better]
```

**Example:**
```markdown
## Proposed Solution

Remove the unconditional status message and let each test suite case handle its own output:

```powershell
function Invoke-Test {
    # ← Remove: Write-Status "Running tests..."
    
    switch ($Suite.ToLower()) {
        { $_ -in @("python", "py", "p") } {
            Write-Status "Running Python tests..."  # ✅ Only this prints
            & python -m pytest tests/ @args
        }
    }
}
```

This eliminates redundancy while maintaining clear user feedback for each command.
```

### 3. Additional Technical Insights (Optional but Recommended)

Add when you're confident about implementation details.

```markdown
## Additional Technical Insights

- **[Category]**: [Specific technical detail]
- **[Performance/Security/Integration]**: [Benefit or consideration]
- **[Design Pattern]**: [How this fits with architecture]
```

**Example:**
```markdown
## Additional Technical Insights

- **User Experience**: Each command now has exactly one status message that accurately describes what's happening, reducing console noise.

- **CLI Design Pattern**: This follows the principle that specific commands should provide specific feedback. Users running `itp` know they want Python tests.

- **Maintainability**: Changes to test execution logic only require updating the switch cases, not the wrapper function.
```

### 4. Implementation Tasks

Break down the work into specific, actionable tasks.

```markdown
## Implementation Tasks

- [ ] [Specific task with file/function reference]
- [ ] [Another specific task]
- [ ] [Testing task]
- [ ] [Documentation task]
```

**Example:**
```markdown
## Implementation Tasks

- [ ] Open `scripts/cli.ps1` and locate `Invoke-Test` function (~line 109)
- [ ] Remove line 117: `Write-Status "Running tests..."`
- [ ] Test `iono test python` - should show ONLY "Running Python tests..."
- [ ] Test `iono test cpp` - should show ONLY "Running C++ tests..."
- [ ] Test `iono test` - should show ONLY "Running all tests..."
- [ ] Verify success/error messages still appear correctly
- [ ] Commit with message: `fix(cli): remove redundant test output message`
```

### 5. Optional Sections

Add these when relevant:

#### Benefits
```markdown
## Benefits

- [Specific improvement]
- [Another benefit]
```

#### Edge Cases to Handle
```markdown
## Edge Cases to Handle

- **Case 1**: [Description and how to handle]
- **Case 2**: [Description and how to handle]
```

#### Testing Strategy
```markdown
## Testing Strategy

Manual testing checklist:
```powershell
# Test command 1
PS> command1  # Expected output

# Test command 2
PS> command2  # Expected output
```
```

#### Acceptance Criteria
```markdown
## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] All tests pass
- [ ] Documentation updated
```

## Label Assignment

### Primary Type (Choose One)
- **`bug`** - Something is broken, incorrect, or unreliable
- **`feature`** - New capability or enhancement
- **`task`** - Code quality, refactoring, or maintenance work

### Team Assignment (Choose One or More)
- **`team-1-cpp`** - C++/CUDA core, processing stages, CUDA kernels
- **`team-2-mlops`** - Build system, CI/CD, CLI, profiling tools
- **`team-3-python`** - Python API, config, benchmarks, tests
- **`team-4-research`** - Experiments, analysis pipelines, ML integration

### Category Tags (Choose Relevant)
- **`python`** - Python code changes
- **`c++`** - C++ code changes
- **`cuda`** - CUDA kernel changes
- **`architecture`** - Design decisions, major refactoring
- **`config`** - Configuration management
- **`documentation`** - Docs, examples, guides
- **`performance`** - Optimization, profiling
- **`reliability`** - Error handling, stability
- **`research`** - Scientific workflow, experiments
- **`good first issue`** - Well-defined, straightforward task

### Label Examples

**Example 1: CLI Bug**
```
Type: bug
Team: team-2-mlops
Categories: maintenance, good first issue
```

**Example 2: New Benchmark Feature**
```
Type: feature
Teams: team-3-python, team-4-research
Categories: python, research, performance
```

**Example 3: CUDA Optimization**
```
Type: task
Team: team-1-cpp
Categories: cuda, performance, architecture
```

**Example 4: Architecture Refactor**
```
Type: task
Teams: team-1-cpp, team-3-python
Categories: c++, python, architecture, refactoring
```

## Team-Specific Guidance

### Team 1 (C++/CUDA Core)

**Focus Areas:**
- ResearchEngine implementation
- Processing stages (Window, FFT, Magnitude)
- CUDA kernels and memory management
- Performance optimization

**Issue Requirements:**
- Include profiling data for performance issues
- Reference CUDA best practices
- Consider memory bandwidth implications
- Test on multiple GPU architectures if possible

**Example Issue:**
```markdown
# Optimize Magnitude Kernel for Ampere GPUs

## Problem
The current magnitude kernel uses a simple 1D grid/block configuration...

## Current Implementation
```cuda
// From cpp/src/ops_fft.cu
__global__ void magnitude_kernel(...) {
    // Implementation
}
```

## Proposed Solution
```cuda
// Optimized for Ampere with cooperative groups
__global__ void magnitude_kernel_v2(...) {
    // Improved implementation
}
```

---
**Labels:** `task`, `team-1-cpp`, `cuda`, `performance`
```

### Team 2 (MLOps/Infrastructure)

**Focus Areas:**
- CMake build system
- CI/CD pipelines
- Development CLI (`cli.ps1`)
- Environment management

**Issue Requirements:**
- Test on clean environment
- Consider cross-platform implications
- Update documentation for workflow changes
- Include before/after examples

**Example Issue:**
```markdown
# Add Automated Dependency Validation to CI Pipeline

## Problem
Dependencies can become outdated without detection...

## Proposed Solution
Add a GitHub Actions workflow that checks...

---
**Labels:** `task`, `team-2-mlops`, `enhancement`
```

### Team 3 (Python API)

**Focus Areas:**
- Engine Python interface
- Configuration models (Pydantic)
- Benchmark framework
- Testing infrastructure

**Issue Requirements:**
- Include type hints in all code examples
- Add tests with examples
- Update docstrings
- Consider backward compatibility

**Example Issue:**
```markdown
# Add Type-Safe Result Validation to Benchmarks

## Problem
Benchmark results are currently stored as plain dicts...

## Current Implementation
```python
# From benchmarks/base.py
def run(self):
    results = {}  # No type safety
```

## Proposed Solution
```python
# Use TypedDict for type safety
from typing import TypedDict

class BenchmarkResult(TypedDict):
    latency_us: float
    throughput_gbps: float
```

---
**Labels:** `task`, `team-3-python`, `python`, `refactoring`
```

### Team 4 (Research/Data Science)

**Focus Areas:**
- Experiment configurations (Hydra)
- Analysis pipelines (Snakemake)
- Visualization scripts
- MLflow integration

**Issue Requirements:**
- Include reproducibility considerations
- Document experiment setup
- Provide example configurations
- Reference scientific methodology

**Example Issue:**
```markdown
# Add Automated Statistical Significance Testing to Analysis Pipeline

## Problem
Currently requires manual analysis to determine statistical significance...

## Proposed Solution
Add Snakemake rule that runs statistical tests...

---
**Labels:** `feature`, `team-4-research`, `research`, `enhancement`
```

## Quality Checklist

Before submitting your issue, ensure:

- [ ] **Title** is specific and action-oriented
- [ ] **Problem** section clearly explains the issue
- [ ] **Current Implementation** shows actual code (when applicable)
- [ ] **Proposed Solution** provides concrete code or approach
- [ ] **Implementation Tasks** are specific and actionable
- [ ] **Labels** are correctly assigned (type + team + categories)
- [ ] **Code examples** use proper syntax highlighting
- [ ] **File paths** are referenced when specific files are involved
- [ ] **Technical depth** is appropriate for the issue complexity

## Using AI to Generate Issues

You can provide this guide to AI assistants (like Claude) to help generate well-formatted issues:

**Prompt Template:**
```
I need a GitHub issue for sigtekx. Here's what I want to accomplish:

[Describe what you want to fix/add/improve]

Please create an issue following the format in docs/CREATING_ISSUES.md:
- Include Problem and Current Implementation sections
- Provide a concrete Proposed Solution with code
- Add Implementation Tasks
- Suggest appropriate labels (type, team, categories)
- Format in raw markdown
```

**Example Prompt:**
```
I need a GitHub issue for sigtekx. The Python test runner in cli.ps1 
prints duplicate status messages - it prints "Running tests..." then 
"Running Python tests..." when you run just the Python tests.

Please create an issue following docs/CREATING_ISSUES.md with:
- The problem and current code
- A fix that removes the duplicate message
- Implementation tasks
- Appropriate labels
```

## Where to Put This File

This file should be located at: **`docs/CREATING_ISSUES.md`**

Referenced from:
- `CONTRIBUTING.md` - "See [Creating Issues Guide](docs/CREATING_ISSUES.md)"
- `README.md` - Link in "Contributing" section
- `.github/ISSUE_TEMPLATE/config.yml` - Add link to guidelines

## Examples from the Project

### Good Issue Example 1: Bug Fix
```markdown
# Fix Redundant Test Output in CLI

## Problem
The CLI test commands produce redundant output...

## Current Implementation
```powershell
# From scripts/cli.ps1
function Invoke-Test {
    Write-Status "Running tests..."
    # ...
}
```

## Proposed Solution
[Complete proposed fix]

## Implementation Tasks
- [ ] Remove line 117 from cli.ps1
- [ ] Test all three variants (it, itp, itc)
- [ ] Update tests if needed

---
**Labels:** `bug`, `team-2-mlops`, `maintenance`, `good first issue`
```

### Good Issue Example 2: Feature
```markdown
# Add Pipeline/Executor Architecture Refactoring

## Problem
The ResearchEngine tightly couples pipeline composition with execution strategy...

## Current Implementation
```cpp
// From cpp/src/research_engine.cpp
void ResearchEngine::Impl::process(...) {
    // Monolithic implementation
}
```

## Proposed Solution
```cpp
// New architecture
class PipelineExecutor { ... };
class BatchExecutor : public PipelineExecutor { ... };
class StreamingExecutor : public PipelineExecutor { ... };
```

## Implementation Tasks
- [ ] Define PipelineExecutor interface
- [ ] Implement BatchExecutor
- [ ] Refactor ResearchEngine to use executor
- [ ] Update tests

---
**Labels:** `task`, `team-1-cpp`, `c++`, `architecture`, `refactoring`
```

## Common Mistakes to Avoid

### ❌ Bad: Vague Title
```
# Bug in tests
```

### ✅ Good: Specific Title
```
# Fix Redundant Output in CLI Test Commands
```

---

### ❌ Bad: No Code Examples
```
## Problem
The tests print too many messages.

## Solution
Fix the printing.
```

### ✅ Good: Concrete Code
```
## Problem
The CLI test runner prints duplicate messages...

## Current Implementation
```powershell
function Invoke-Test {
    Write-Status "Running tests..."  # Line 117
    Write-Status "Running Python tests..."  # Line 129
}
```

## Solution
Remove line 117...
```

---

### ❌ Bad: Vague Tasks
```
- [ ] Fix the code
- [ ] Test it
```

### ✅ Good: Specific Tasks
```
- [ ] Open scripts/cli.ps1, locate Invoke-Test function
- [ ] Remove line 117: Write-Status "Running tests..."
- [ ] Test with: iono test python
- [ ] Verify output shows only "Running Python tests..."
```

## Getting Help

If you're unsure about:
- **Which team** to assign: Look at which files are affected
- **Which labels** to use: Start with type + team, add categories as relevant
- **Technical depth**: Provide as much detail as you can; reviewers will ask questions
- **Code examples**: Reference existing code even if you're not sure about the fix

Don't let uncertainty stop you from creating an issue. We'd rather have a well-intentioned issue that needs refinement than miss out on improvements!

## Questions?

- Check [CONTRIBUTING.md](../CONTRIBUTING.md) for general contribution guidelines
- Ask in [GitHub Discussions](https://github.com/SEAL-Embedded/sigtekx/discussions)
- Tag `@maintainers` in your issue for help with formatting
