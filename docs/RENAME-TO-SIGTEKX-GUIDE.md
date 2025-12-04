# SigTekX Rename Guide

**Date**: 2025-12-03
**Current Name**: ionosense-hpc
**Target Name**: sigtekx
**Name Meaning**: **Sig**nal **Tek**ton e**X**celeration (tekton = Greek for "builder")
**Purpose**: Rebrand the library to SigTekX - a GPU-accelerated signal processing pipeline builder, moving ionosphere-specific functionality to be domain examples rather than the primary identity

---

## Executive Summary

This document outlines the complete process for renaming the `ionosense-hpc` project to `sigtekx`. The rename is **moderate to large in scope**, affecting approximately **100+ files** across Python, C++, configuration, documentation, and build systems.

### Scope Assessment

| Category | Impact Level | File Count | Effort Estimate |
|----------|-------------|------------|-----------------|
| **Python Package Structure** | High | 15-20 files | 2-3 hours |
| **C++ Namespace & Headers** | High | 20+ files | 3-4 hours |
| **Build System (CMake)** | High | 5 files | 1-2 hours |
| **Configuration Files (Hydra/YAML)** | Medium | 40+ files | 2-3 hours |
| **Documentation** | Medium | 10+ files | 2-3 hours |
| **Scripts & CLI** | Medium | 10 files | 1-2 hours |
| **Tests** | Medium | 15+ files | 1-2 hours |
| **Git History** | Low | N/A | No change needed |
| **TOTAL** | **MODERATE-HIGH** | **100+ files** | **12-18 hours** |

### Key Observations

1. **"ionosense" references**: ~20 files (core identity)
2. **"ionosphere" references**: ~40+ files (domain examples - KEEP THESE)
3. **C++ namespace**: `namespace ionosense` used throughout
4. **Python package**: `ionosense_hpc` → `sigtekx`
5. **CLI prefix**: `iono` → `sigx` or `stx`
6. **Repository**: Should be renamed to match

---

## Part 1: Repository Name Decision

### Option 1: Exact Match (Recommended)
- **PyPI package**: `sigtekx`
- **Repository**: `sigtekx` (or `SigTekX`)
- **Rationale**: Maximum clarity, easy to find, consistent branding

### Option 2: Descriptive Suffix
- **PyPI package**: `sigtekx`
- **Repository**: `sigtekx-hpc` or `sigtekx-lib`
- **Rationale**: More descriptive, follows current pattern

### Recommendation

**Use Option 1** (`sigtekx` for both). Reasons:
- Clean, modern branding
- Easy to remember and type
- Package name matches repo name exactly
- The "signal processing HPC library" aspect is clear from the description

---

## Part 2: Detailed Rename Checklist

### Phase 1: Planning & Backup (30 min)

- [ ] **Create feature branch**: `git checkout -b rename-to-sigtekx`
- [ ] **Backup current state**: `git tag backup-pre-sigtekx-rename`
- [ ] **Document current install**: Test that current version works
- [ ] **Save this guide**: Keep this document for reference

### Phase 2: Python Package Structure (2-3 hours)

#### 2.1 Directory Rename
```bash
# Rename main package directory
git mv src/ionosense_hpc src/sigtekx
```

#### 2.2 Update Python Files (15-20 files)

**Files requiring `ionosense_hpc` → `sigtekx` changes:**

Core package files:
- [ ] `src/sigtekx/__init__.py` (1. module docstring, 2. import paths, 3. print messages)
- [ ] `src/sigtekx/__version__.py`
- [ ] `src/sigtekx/exceptions.py` (rename `IonosenseError` → `SigTekXError`)
- [ ] `src/sigtekx/core/__init__.py`
- [ ] `src/sigtekx/core/engine.py`
- [ ] `src/sigtekx/core/builder.py`
- [ ] `src/sigtekx/config/__init__.py`
- [ ] `src/sigtekx/stages/__init__.py`
- [ ] `src/sigtekx/utils/__init__.py`
- [ ] `src/sigtekx/utils/profiling.py`
- [ ] `src/sigtekx/utils/logging.py`
- [ ] `src/sigtekx/benchmarks/__init__.py`
- [ ] `src/sigtekx/testing/__init__.py`

Test files:
- [ ] `tests/test_*.py` (all import statements: `from ionosense_hpc` → `from sigtekx`)

Benchmark/experiment files:
- [ ] `benchmarks/*.py` (all import statements)
- [ ] `experiments/streamlit/**/*.py` (all import statements)
- [ ] `experiments/analysis/**/*.py` (all import statements)

#### 2.3 Key Search-Replace Patterns

```python
# Pattern 1: Package imports
"from ionosense_hpc" → "from sigtekx"
"import ionosense_hpc" → "import sigtekx"

# Pattern 2: Exception class name (ionosense_hpc/exceptions.py)
"class IonosenseError" → "class SigTekXError"
"IonosenseError" → "SigTekXError" (in docstrings, inheritance)

# Pattern 3: Module docstrings
"Ionosense-HPC" → "SigTekX"
"ionosense-hpc" → "sigtekx"

# Pattern 4: Print/log messages
"ionosense" → "sigtekx" (in user-facing strings)
"Ionosense" → "SigTekX" (in titles/headers)
```

### Phase 3: C++ Codebase (3-4 hours)

#### 3.1 C++ Namespace Rename (20+ files)

**Strategy**: `namespace ionosense` → `namespace sigtekx`

**Files affected** (all `.hpp`, `.cpp`, `.cu` files):
- [ ] `cpp/include/ionosense/**/*.hpp` → `cpp/include/sigtekx/**/*.hpp` (directory rename)
- [ ] `cpp/src/**/*.cpp` (namespace declarations)
- [ ] `cpp/src/**/*.cu` (namespace declarations)
- [ ] `cpp/bindings/bindings.cpp` (pybind11 module name)
- [ ] `cpp/tests/**/*.cpp` (namespace usage, includes)
- [ ] `cpp/benchmarks/**/*.cpp` (namespace usage, includes)

**Directory rename**:
```bash
git mv cpp/include/ionosense cpp/include/sigtekx
```

**Files to update** (contains `namespace ionosense`):
Based on earlier grep, these 20+ files:
- `cpp/include/sigtekx/core/*.hpp`
- `cpp/include/sigtekx/executors/*.hpp`
- `cpp/include/sigtekx/profiling/*.hpp`
- `cpp/src/core/*.cpp`
- `cpp/src/executors/*.cpp`
- `cpp/src/profiling/*.cu`
- `cpp/tests/**/*.cpp`
- `cpp/benchmarks/**/*.cpp` and `.hpp`

**Search-replace pattern**:
```cpp
// Pattern 1: Namespace declaration
namespace ionosense { → namespace sigtekx {

// Pattern 2: Namespace usage
ionosense:: → sigtekx::

// Pattern 3: Include guards (in .hpp files)
#ifndef IONOSENSE_ → #ifndef SIGTEKX_
#define IONOSENSE_ → #define SIGTEKX_

// Pattern 4: Include paths
#include "ionosense/ → #include "sigtekx/
#include <ionosense/ → #include <sigtekx/

// Pattern 5: Comments/docs
"ionosense" → "sigtekx"
"Ionosense" → "SigTekX"
```

#### 3.2 Pybind11 Module Name

**File**: `cpp/bindings/bindings.cpp`

```cpp
// OLD:
PYBIND11_MODULE(_engine, m) {
    m.doc() = "Ionosense HPC C++ Engine";
    // ...
}

// NEW:
PYBIND11_MODULE(_engine, m) {
    m.doc() = "SigTekX HPC C++ Engine";
    // Note: Keep module name as "_engine" (internal detail)
    // or rename to "_core" or similar
}
```

**Decision**: Keep `_engine` as module name (it's internal) OR rename to `_core`/`_backend`.

### Phase 4: Build System (1-2 hours)

#### 4.1 CMakeLists.txt (5 files)

**Main CMakeLists.txt**:
```cmake
# Line 2: Project name
project(ionosense_hpc LANGUAGES CXX)
→ project(sigtekx LANGUAGES CXX)

# Options (lines 19-24)
option(IONO_WITH_TESTS ...) → option(SIGTEKX_WITH_TESTS ...)
option(IONO_WITH_GRAPHS ...) → option(SIGTEKX_WITH_GRAPHS ...)
option(IONO_WITH_PYTHON ...) → option(SIGTEKX_WITH_PYTHON ...)
option(IONO_WITH_CUDA ...) → option(SIGTEKX_WITH_CUDA ...)
option(IONO_WITH_NVTX ...) → option(SIGTEKX_WITH_NVTX ...)
option(IONO_ENABLE_COVERAGE ...) → option(SIGTEKX_ENABLE_COVERAGE ...)

# All IONO_ variable references throughout file
IONO_WITH_CUDA → SIGTEKX_WITH_CUDA (etc.)

# Include paths (line 82, 168-170)
cpp/include/ionosense/ → cpp/include/sigtekx/

# Install paths (lines 203, 209-215, 219)
/ionosense_hpc/core → /sigtekx/core
/ionosense_hpc/.libs → /sigtekx/.libs

# Import validation (line 272)
"import ionosense_hpc" → "import sigtekx"

# Status messages (lines 55, 68, 251, 261, 272)
"[ionosense]" → "[sigtekx]"

# Compile definitions (lines 176, 196, 332)
IONOSENSE_ENABLE_PROFILING → SIGTEKX_ENABLE_PROFILING
```

**Files to update**:
- [ ] `CMakeLists.txt` (root)
- [ ] Any other CMake files in `cpp/` or `build/` (if committed)

#### 4.2 CMakePresets.json

Check for any "ionosense" or "IONO_" references:
- [ ] Update preset names if they contain "iono"
- [ ] Update any cmake variables starting with `IONO_`

### Phase 5: Python Build Configuration (30 min)

#### 5.1 pyproject.toml

**Already backed up** (see Phase 6 deliverable)

```toml
# [project]
name = "ionosense-hpc" → "sigtekx"
description = "High-performance CUDA FFT..."
  → "SigTekX: High-performance CUDA signal processing library..."

# [project.optional-dependencies]
research = ["ionosense-hpc[...]"] → ["sigtekx[...]"]
export = ["ionosense-hpc[...]"] → ["sigtekx[...]"]
full = ["ionosense-hpc[...]"] → ["sigtekx[...]"]

# [project.urls]
Homepage = "...ionosense-hpc-lib" → "...sigtekx" (or new repo name)
Documentation = "...ionosense-hpc-lib..." → "...sigtekx..."
"Bug Tracker" = "...ionosense-hpc-lib..." → "...sigtekx..."

# [tool.scikit-build.wheel]
packages = ["src/ionosense_hpc"] → ["src/sigtekx"]

# [tool.ruff.lint]
isort.known-first-party = ["ionosense_hpc"] → ["sigtekx"]

# [tool.pytest.ini_options]
addopts = ["--cov=ionosense_hpc"] → ["--cov=sigtekx"]

# [tool.coverage.run]
source = ["ionosense_hpc"] → ["sigtekx"]
```

- [ ] Update `pyproject.toml`

#### 5.2 setup.py / setup.cfg

- [ ] Check if these exist (probably not with scikit-build-core)
- [ ] Update if present

### Phase 6: Scripts & CLI (1-2 hours)

#### 6.1 PowerShell Scripts

**Files to update**:
- [ ] `scripts/cli.ps1` (main CLI)
- [ ] `scripts/cli-cpp.ps1` (C++ CLI)
- [ ] `scripts/init_pwsh.ps1` (shell initialization)
- [ ] `scripts/gpu-manager.ps1`
- [ ] Other `scripts/*.ps1`

**Changes**:
```powershell
# Function aliases
function iono { ... } → function sigx { ... }  # or stx
function ionoc { ... } → function sigxc { ... }
function iprof { ... } → function sigxprof { ... }  # or keep as sxprof

# Import paths
"import ionosense_hpc" → "import sigtekx"

# Status messages
"[ionosense]" → "[sigtekx]"
```

**CLI Command Naming Options**:
| Old | Option 1 | Option 2 | Recommendation |
|-----|----------|----------|----------------|
| `iono` | `sigx` | `stx` | `sigx` (clearer) |
| `ionoc` | `sigxc` | `stxc` | `sigxc` |
| `iprof` | `sigxprof` | `sxprof` | `sxprof` (shorter) |
| `icbench` | `sxbench` | `stxb` | `sxbench` |

#### 6.2 Python Scripts

**Files**:
- [ ] `scripts/prof_helper.py`

**Changes**:
- Import statements: `ionosense_hpc` → `sigtekx`
- CLI references

### Phase 7: Configuration Files (2-3 hours)

#### 7.1 Hydra Configuration (experiments/conf/)

**Important**: Keep "ionosphere" references in experiment names!

**Files requiring changes** (focus on `ionosense`, NOT `ionosphere`):
- [ ] `experiments/conf/config.yaml`
- [ ] Any YAML with `ionosense_hpc` import paths or references

**Search for**:
```bash
grep -r "ionosense_hpc" experiments/conf/
grep -r "ionosense" experiments/conf/  # Be careful - don't change "ionosphere"!
```

**Changes**:
- Only update Python import paths if they exist
- Update any MLflow experiment names if they say "ionosense"
- **DO NOT** change "ionosphere_*" config names (those are domain-specific)

#### 7.2 DVC Configuration

- [ ] `dvc.yaml` - check for any ionosense references
- [ ] `.dvc/config` - check for experiment names

### Phase 8: Documentation (2-3 hours)

#### 8.1 Core Documentation Files

**Files requiring updates**:
- [ ] `README.md` (comprehensive rewrite)
- [ ] `CLAUDE.md` (CLI commands, package names)
- [ ] `docs/INSTALL.md`
- [ ] `docs/architecture/*.md`
- [ ] `docs/guides/*.md`
- [ ] `docs/performance/*.md`
- [ ] Any other `docs/**/*.md`

**Search-replace patterns**:
```markdown
# Package/project name
ionosense-hpc → sigtekx
Ionosense-HPC → SigTekX
ionosense_hpc → sigtekx

# CLI commands
iono → sigx
ionoc → sigxc
iprof → sxprof

# Code examples
```python
from ionosense_hpc import Engine
→ from sigtekx import Engine

# URLs (if repo is renamed)
ionosense-hpc-lib → sigtekx (or new repo name)

# Keep "ionosphere" in domain context
"ionosphere research" ✓ (keep)
"ionospheric physics" ✓ (keep)
```

#### 8.2 Diagrams

**Diagram source files** (`docs/diagrams/src/*.d2`):
- [ ] Update any references to "ionosense" in labels/titles
- [ ] Regenerate SVG outputs
- [ ] Keep "ionosphere" in domain-specific contexts

**Files from grep**:
- `docs/diagrams/src/common/styles.d2`
- `docs/diagrams/src/*.d2` (all diagram sources)

### Phase 9: Tests (1-2 hours)

**Files**:
- [ ] `tests/test_*.py` (all ~15 files)

**Changes**:
```python
# Imports
from ionosense_hpc import ... → from sigtekx import ...
import ionosense_hpc → import sigtekx

# Exception assertions
with pytest.raises(IonosenseError): → with pytest.raises(SigTekXError):
```

### Phase 10: Miscellaneous Files (30 min)

#### 10.1 Git Configuration
- [ ] `.gitignore` - check for "ionosense" patterns (probably none)
- [ ] `.github/workflows/*.yml` - if any CI/CD exists

#### 10.2 License & Attribution
- [ ] `LICENSE` - no changes needed (already correct author)
- [ ] `CITATION.cff` - if exists, update project name

#### 10.3 Package Metadata
- [ ] `MANIFEST.in` - if exists
- [ ] `requirements*.txt` - if any reference package name

---

## Part 3: Testing & Validation

### Build & Test Checklist

After completing renames:

1. **Clean build**:
   ```powershell
   Remove-Item -Recurse -Force build/, src/sigtekx/core/_engine.*
   ```

2. **Update CMake cache**:
   ```powershell
   cmake --preset windows-rel  # or your preset
   ```

3. **Build**:
   ```powershell
   sigx build  # (new command name!)
   ```

4. **Run tests**:
   ```powershell
   sigx test
   ```

5. **Test imports**:
   ```python
   python -c "import sigtekx; print(sigtekx.__version__)"
   python -c "from sigtekx import Engine; print('OK')"
   ```

6. **Run benchmark**:
   ```powershell
   python benchmarks/run_latency.py +benchmark=latency
   ```

7. **Check CLI**:
   ```powershell
   sigx doctor
   sigx help
   ```

### Validation Checklist

- [ ] All tests pass (`sigx test`)
- [ ] Python imports work (`import sigtekx`)
- [ ] C++ compilation succeeds
- [ ] CLI commands work with new names
- [ ] Documentation renders correctly
- [ ] No "ionosense_hpc" references remain (except git history)
- [ ] Benchmarks run successfully
- [ ] Streamlit dashboard works

---

## Part 4: Git & Repository

### Git Commit Strategy

**Option A: Single Atomic Commit** (Recommended for clean history)
```bash
git add -A
git commit -m "refactor: rename project from ionosense-hpc to sigtekx

BREAKING CHANGE: Complete project rename
- Python package: ionosense_hpc → sigtekx
- C++ namespace: ionosense → sigtekx
- CLI commands: iono → sigx, ionoc → sigxc, iprof → sxprof
- Repository: ionosense-hpc-lib → sigtekx
- Exception class: IonosenseError → SigTekXError

Note: 'ionosphere' references preserved as domain-specific examples

See docs/RENAME-TO-SIGTEKX-GUIDE.md for complete details"
```

**Option B: Phased Commits** (If you want to track each phase)
```bash
# Phase 1
git add src/
git commit -m "refactor(python): rename package ionosense_hpc → sigtekx"

# Phase 2
git add cpp/
git commit -m "refactor(cpp): rename namespace ionosense → sigtekx"

# etc...
```

### Repository Rename (GitHub)

**After testing is complete**:

1. **GitHub Settings** → Repository name → Rename to `sigtekx`
2. **Update local remote**:
   ```bash
   git remote set-url origin https://github.com/SEAL-Embedded/sigtekx.git
   ```
3. **Update clone instructions** in docs

**URL Migration**:
- Old: `https://github.com/SEAL-Embedded/ionosense-hpc-lib`
- New: `https://github.com/SEAL-Embedded/sigtekx`

---

## Part 5: Immediate PyPI Placeholder

See separate deliverable: `pyproject.toml.backup` and placeholder package.

---

## Appendix: File Counts by Category

### Python Files (~15-20)
- `src/sigtekx/**/*.py`: 12 files
- `tests/*.py`: 8 files
- `benchmarks/*.py`: 5 files
- `experiments/**/*.py`: 15+ files

### C++ Files (~25)
- `cpp/include/sigtekx/**/*.hpp`: 11 files
- `cpp/src/**/*.{cpp,cu}`: 8 files
- `cpp/tests/**/*.cpp`: 10+ files
- `cpp/benchmarks/**/*.{cpp,hpp}`: 5 files

### Configuration Files (~10)
- `CMakeLists.txt`, `CMakePresets.json`
- `pyproject.toml`
- `experiments/conf/**/*.yaml`: Select files only

### Documentation (~10)
- `README.md`, `CLAUDE.md`, `docs/**/*.md`

### Scripts (~7)
- `scripts/*.ps1`: 7 files
- `scripts/*.py`: 1 file

---

## Summary

**Scope**: This is a **moderate to large** rename affecting 100+ files across the entire codebase.

**Time Estimate**: 12-18 hours of focused work + testing

**Risk Level**: Medium - requires careful testing of build system and Python packaging

**Reversibility**: High - all changes are text-based, can be reverted via git

**Recommendation**:
1. Complete placeholder PyPI publish TODAY (see Part 5)
2. Schedule dedicated time for full rename (1-2 days)
3. Do rename on feature branch with thorough testing
4. Keep "ionosphere" references as valuable domain examples

---

## Questions for Consideration

1. **CLI command prefix**: `sigx`, `stx`, or something else?
2. **Pybind11 module name**: Keep `_engine` or rename to `_core`/`_backend`?
3. **Repository name**: `sigtekx` exactly, or `sigtekx-hpc`/`sigtekx-lib`?
4. **Exception class**: `SigTekXError` or `SigTekError` or `STXError`?

**Recommended Answers**:
1. `sigx` (clear, pronounceable)
2. Keep `_engine` (internal detail, less churn)
3. `sigtekx` (exact match with package)
4. `SigTekXError` (matches brand)

---

**Document Version**: 1.0
**Last Updated**: 2025-12-03
**Author**: Claude Code (via audit)
