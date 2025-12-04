# SigTekX Rename - Executive Summary

**SigTekX** = **Sig**nal **Tek**ton e**X**celeration
- Building GPU-accelerated signal processing pipelines
- Tekton (Greek): "builder" - reflecting the pipeline builder architecture

**Date**: 2025-12-03
**Prepared by**: Claude Code (Automated Audit)

---

## Quick Answer to Your Questions

### How big is the rename task?

**MODERATE to LARGE** - Affects **100+ files** across Python, C++, CMake, configs, docs, and tests.

**Estimated effort**: 12-18 hours of focused work + testing

### Should the repo name be changed?

**YES** - Recommended: `sigtekx` (exact match with PyPI package name)

**Alternatives**: `sigtekx-hpc` or `sigtekx-lib` (but exact match is cleaner)

### Same as Python package name?

**YES** - Best practice is to match exactly:
- **PyPI package**: `sigtekx`
- **Repository**: `sigtekx` (or `SigTekX`)
- **Import name**: `import sigtekx`

---

## Scope Breakdown

| Area | Files Affected | Complexity | Time |
|------|----------------|------------|------|
| **Python package** (`ionosense_hpc` → `sigtekx`) | 20 files | High | 2-3h |
| **C++ namespace** (`ionosense` → `sigtekx`) | 25+ files | High | 3-4h |
| **CMake build system** | 5 files | Medium | 1-2h |
| **Configuration YAMLs** | 10-15 files | Medium | 2-3h |
| **Documentation** | 10+ files | Medium | 2-3h |
| **Scripts & CLI** | 10 files | Medium | 1-2h |
| **Tests** | 15 files | Low | 1-2h |
| **TOTAL** | **~100 files** | **MODERATE** | **12-18h** |

---

## What About "Ionosphere"?

**GOOD NEWS**: The ~40 files with "ionosphere" references are **domain-specific examples** and should be **KEPT**!

- `experiments/conf/engine/ionosphere_*.yaml` ✅ Keep (domain configs)
- `experiments/conf/experiment/ionosphere_*.yaml` ✅ Keep (research examples)
- Documentation mentioning ionosphere research ✅ Keep (application domain)

**You're only renaming the project identity, not removing the ionosphere use case!**

---

## Deliverables Provided

### 1. Comprehensive Rename Guide
**Location**: `docs/RENAME-TO-SIGTEKX-GUIDE.md`

**Contents**:
- Detailed step-by-step checklist for all 100+ files
- File-by-file breakdown by category
- Search-replace patterns
- Testing & validation procedures
- Git commit strategy
- Repository rename instructions

**When to use**: When you're ready to execute the full rename (plan 1-2 days)

### 2. PyPI Placeholder Package
**Location**: `pypi-placeholder/`

**Contents**:
- `pyproject.toml` - Minimal config for v0.0.0
- `src/sigtekx/__init__.py` - Placeholder module with nice message
- `README.md` - Placeholder description
- `LICENSE` - MIT license
- `PUBLISH.md` - Step-by-step publishing guide

**When to use**: TODAY - Claim the "sigtekx" name on PyPI

### 3. Backup of Current Config
**Location**: `pyproject.toml.backup-2025-12-03`

**Contents**: Your current working `pyproject.toml` (v0.9.4)

**When to use**: Reference when creating the full renamed package

---

## Immediate Action Plan (Today)

### Step 1: Claim PyPI Name (30 minutes)

```bash
# 1. Navigate to placeholder
cd pypi-placeholder

# 2. Install publishing tools (if needed)
pip install --upgrade build twine

# 3. Build placeholder package
python -m build

# 4. Test on TestPyPI first (optional but recommended)
python -m twine upload --repository testpypi dist/*
# Username: __token__
# Password: <your TestPyPI token>

# 5. Verify test install
pip install --index-url https://test.pypi.org/simple/ sigtekx

# 6. If test works, publish to real PyPI
python -m twine upload dist/*
# Username: __token__
# Password: <your PyPI token>

# 7. Verify
pip install sigtekx
python -c "import sigtekx"  # Should show nice placeholder message
```

**See** `pypi-placeholder/PUBLISH.md` for detailed instructions.

### Step 2: Verify Success

- Visit https://pypi.org/project/sigtekx/
- Confirm package is visible and owned by you
- Name is now claimed! ✅

---

## Future Action Plan (When Ready)

### Phase 1: Planning (1 day before)

- [ ] Read `docs/RENAME-TO-SIGTEKX-GUIDE.md` thoroughly
- [ ] Create feature branch: `git checkout -b rename-to-sigtekx`
- [ ] Create backup tag: `git tag backup-pre-sigtekx-rename`
- [ ] Schedule 1-2 dedicated days for rename work

### Phase 2: Execution (1-2 days)

Follow the checklist in `docs/RENAME-TO-SIGTEKX-GUIDE.md`:

1. **Python package** (2-3h): Rename dirs, update imports, fix exception class
2. **C++ codebase** (3-4h): Rename namespace, update includes, fix CMake refs
3. **Build system** (1-2h): Update CMakeLists.txt, pyproject.toml
4. **Configuration** (2-3h): Update YAML files (carefully - keep "ionosphere")
5. **Documentation** (2-3h): Update all .md files, regenerate diagrams
6. **Scripts** (1-2h): Update CLI commands, aliases
7. **Tests** (1-2h): Update imports and assertions

### Phase 3: Testing (0.5 day)

- [ ] Clean rebuild: `Remove-Item -Recurse build/; sigx build`
- [ ] Run all tests: `sigx test`
- [ ] Test imports: `python -c "import sigtekx"`
- [ ] Run benchmark: `python benchmarks/run_latency.py +benchmark=latency`
- [ ] Test CLI: `sigx doctor`
- [ ] Manual smoke tests

### Phase 4: Finalization (1-2 hours)

- [ ] Git commit (atomic or phased)
- [ ] Rename GitHub repository to `sigtekx`
- [ ] Update remote: `git remote set-url origin ...`
- [ ] Publish v0.1.0 or v1.0.0 to PyPI
- [ ] Update placeholder package description on PyPI

---

## Recommended Naming Conventions

### Package & Repository
- **PyPI package name**: `sigtekx`
- **Repository name**: `sigtekx`
- **Import statement**: `from sigtekx import Engine`

### CLI Commands
- **Main CLI**: `iono` → `sigx`
- **C++ CLI**: `ionoc` → `sigxc`
- **Profiling**: `iprof` → `sxprof`
- **Benchmarks**: `icbench` → `sxbench`

### Code Entities
- **Python package**: `ionosense_hpc` → `sigtekx`
- **C++ namespace**: `namespace ionosense` → `namespace sigtekx`
- **CMake project**: `project(ionosense_hpc)` → `project(sigtekx)`
- **CMake options**: `IONO_*` → `SIGTEKX_*`
- **Exception class**: `IonosenseError` → `SigTekXError`

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Build breaks | Medium | High | Test incrementally, use feature branch |
| Import errors | Medium | High | Comprehensive testing, update all files |
| Missing renames | Medium | Medium | Use grep to verify, follow checklist |
| Git history issues | Low | Low | Use atomic commit, test before push |
| PyPI conflicts | Low | High | Claim name today (done!), test on TestPyPI |

**Overall risk**: MEDIUM (manageable with careful execution)

---

## Key Decisions Needed

Before starting the full rename, decide on:

1. **CLI command prefix**: `sigx` (recommended) vs `stx` vs other?
2. **Exception class name**: `SigTekXError` (recommended) vs `SigTekError` vs `STXError`?
3. **Pybind11 module**: Keep `_engine` (recommended) or rename to `_core`?
4. **Commit strategy**: Single atomic commit (recommended) vs phased commits?

**My recommendations** (already reflected in guide):
1. `sigx` - pronounceable and clear
2. `SigTekXError` - matches brand identity
3. Keep `_engine` - internal detail, less churn
4. Atomic commit - cleaner history

---

## Support Files Reference

| File | Purpose |
|------|---------|
| `docs/RENAME-TO-SIGTEKX-GUIDE.md` | Complete step-by-step guide |
| `pypi-placeholder/` | Package to claim PyPI name |
| `pypi-placeholder/PUBLISH.md` | Publishing instructions |
| `pyproject.toml.backup-2025-12-03` | Backup of current config |
| `SIGTEKX-RENAME-SUMMARY.md` | This file (executive summary) |

---

## Questions?

If you need clarification on any part of the rename process:

1. Check the detailed guide: `docs/RENAME-TO-SIGTEKX-GUIDE.md`
2. Search for specific patterns in the guide
3. Test changes incrementally on a feature branch
4. Keep the backup tag for safety: `git tag backup-pre-sigtekx-rename`

---

## Timeline Summary

| Phase | Duration | When |
|-------|----------|------|
| **Claim PyPI name** | 30 min | TODAY ✅ |
| **Read & plan** | 2-3 hours | Before rename |
| **Execute rename** | 12-18 hours | When ready (1-2 days) |
| **Testing** | 2-4 hours | After rename |
| **Finalization** | 1-2 hours | Final step |
| **TOTAL** | 15-25 hours | Over 2-3 days |

---

**Good luck with the rename! The name "SigTekX" is a great choice for a signal processing library.** 🚀

---

**Document prepared**: 2025-12-03
**Audit tool**: Claude Code
**Codebase analyzed**: ionosense-hpc-lib (100+ files)
