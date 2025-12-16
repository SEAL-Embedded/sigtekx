# GitHub Issues - Ready for Kanban

This directory contains pre-formatted GitHub issues ready to be copied into the SigTekX project board.

## Files

### Phase 0: Pre-Phase 1 Audit Fixes (Foundation)

| File | Issue | Priority | Severity | Effort |
|------|-------|----------|----------|--------|
| `phase0/001-fix-streaming-executor-cv-wait.md` | Fix Broken Condition Variable Wait | **CRITICAL** | High | 1-2 hours |
| `phase0/002-fix-python-bindings-dangling-pointer.md` | Fix Dangling Pointer in Python Bindings | **CRITICAL** | High | 30 mins |
| `phase0/003-document-streaming-executor-thread-safety.md` | Document Thread-Safety Contract | HIGH | Medium | 2-3 hours |
| `phase0/004-optimize-streaming-executor-sync.md` | Optimize Redundant Synchronization | MEDIUM | Low | 3-4 hours |
| `phase0/005-fix-benchmark-latency-resource-leak.md` | Fix Resource Leak in benchmark_latency() | MEDIUM-HIGH | Medium | 30 mins |
| `phase0/006-fix-unsafe-config-override.md` | Fix Unsafe Configuration Override | MEDIUM-HIGH | Medium | 1 hour |
| `phase0/007-fix-silent-fallback-in-device-info.md` | Fix Silent Fallback in device_info | MEDIUM | Low | 1-2 hours |
| `phase0/008-complete-stageconfig-binding.md` | Complete StageConfig Binding | MEDIUM | Low | 2-3 hours |
| `phase0/009-add-missing-runtimeinfo-binding.md` | Add Missing RuntimeInfo Binding | MEDIUM | Low | 1-2 hours |
| `phase0/010-fix-csv-append-race-condition.md` | Fix CSV Append Race Condition | HIGH | High | 1-2 hours |
| `phase0/011-add-warmup-to-throughput-accuracy-benchmarks.md` | Add Warmup to Benchmarks | MEDIUM-HIGH | Medium | 1-2 hours |
| `phase0/012-add-error-logging-in-mlflow.md` | Add Error Logging in MLflow | MEDIUM | Low | 2-3 hours |

**Total Phase 0 Effort:** ~17-24 hours (5 critical/high issues: ~6 hours)

### Phase 1-4: Methods Paper Roadmap Issues

| File | Issue | Priority | Phase | Effort |
|------|-------|----------|-------|--------|
| `001-fix-dataarchiver-race-condition.md` | Fix DataArchiver Race Condition | Medium | Phase 0/1 | 1-2 hours |
| `002-refactor-stage-registry.md` | Refactor Stage Registry | Medium-High | Phase 0 | 3-4 hours |
| `003-zero-copy-ring-buffer.md` | Zero-Copy Ring Buffer Extraction | High | Phase 1 | 4-6 hours |
| `004-per-stage-timing.md` | Add Per-Stage Timing Infrastructure | High | Phase 1 | 4-6 hours |
| `005-custom-stage-cpp-class.md` | Add CustomStage C++ Class | High | Phase 2 | 6-8 hours |
| `006-numba-integration.md` | Add Numba Integration | Critical | Phase 2 | 8-10 hours |
| `007-pytorch-integration.md` | Integrate PyTorch Models | High | Phase 2 | 6-8 hours |
| `008-persistent-state-support.md` | Enable Persistent State Buffers | Medium | Phase 2 | 4-6 hours |
| `009-snapshot-buffer.md` | Add Snapshot Buffer | High | Phase 3 | 6-8 hours |
| `010-event-queue.md` | Add MPSC Event Queue | High | Phase 3 | 8-10 hours |
| `011-callback-stage.md` | Implement CallbackStage | Medium | Phase 3 | 6-8 hours |
| `012-custom-stage-overhead-benchmark.md` | Validate Custom Stage Overhead | High | Phase 4 | 4-6 hours |
| `013-rtf-validation.md` | Run RTF Validation Experiments | High | Phase 4 | 3-4 hours |
| `014-stress-test.md` | Add 1-Hour Stress Test | Medium | Phase 4 | 4-6 hours |
| `015-cupy-comparison.md` | Benchmark SigTekX vs CuPy | High | Phase 4 | 6-8 hours |
| `016-pytorch-validation.md` | Validate PyTorch Denoiser | Medium | Phase 4 | 6-8 hours |
| `017-scaling-analysis.md` | Generate Scaling Analysis Heatmap | High | Phase 4 | 4-6 hours |

## How to Use

1. Open the markdown file for the issue you want to create
2. Copy the entire contents (Ctrl+A, Ctrl+C)
3. Go to [GitHub Issues](https://github.com/SEAL-Embedded/sigtekx/issues/new)
4. Paste the contents into the issue description
5. Extract the title from the first heading
6. Add the labels listed at the bottom of the file
7. Submit the issue

## Roadmap Alignment

These issues are aligned with the [Methods Paper Roadmap](../development/methods-paper-roadmap.md) and the [Phase 1 Readiness Audit](../development/phase1-readiness-audit.md):

### Phase 0: Foundation Audit Fixes (NEW - December 2025)

**Critical Issues (Must Fix Before Phase 1):**
- **phase0/001**: Fix broken CV wait in StreamingExecutor (async mode non-functional)
- **phase0/002**: Fix dangling pointer in Python bindings (segfault risk)
- **phase0/010**: Fix CSV race condition (data corruption in multirun)

**High Priority (Strongly Recommended):**
- **phase0/003**: Document thread-safety contract (prevents misuse)
- **phase0/005**: Fix resource leak in `benchmark_latency()` (memory safety)
- **phase0/006**: Fix unsafe config override (validation bypass)
- **phase0/011**: Add warmup to benchmarks (measurement bias)

**Medium Priority (Nice to Have):**
- **phase0/004**: Optimize streaming sync (performance)
- **phase0/007**: Fix silent device_info fallback (diagnostics)
- **phase0/008**: Complete StageConfig binding (API completeness)
- **phase0/009**: Add RuntimeInfo binding (diagnostics)
- **phase0/012**: Add error logging in MLflow (monitoring)

**Verdict:** CONDITIONAL GO - Fix 5 critical/high issues (~6 hours) before Phase 1

### Phase 0: Infrastructure Preparation (Original Roadmap)
- **Issue #1**: DataArchiver race condition fix (needed for parallel experiments)
- **Issue #2**: Stage Registry refactoring (Python-only preparation)

### Phase 1 (Memory Architecture - v0.9.6)
- **Issue #3**: Zero-copy ring buffer (Task 1.1 - 7% latency improvement)
- **Issue #4**: Per-stage timing (Task 1.2 - enables Phase 2 validation)

### Phase 2 (Custom Stage Integration - THE CORE NOVELTY - v0.9.7)
- **Issue #5**: CustomStage C++ class (Task 2.1 - foundation for custom kernels)
- **Issue #6**: Numba integration (Task 2.2 - Python → C++ bridge, CRITICAL)
- **Issue #7**: PyTorch model integration (Task 2.3 - hybrid compute)
- **Issue #8**: Persistent state support (Task 2.4 - stateful algorithms)

### Phase 3 (Control Plane Decoupling - v0.9.8)
- **Issue #9**: Snapshot buffer (Task 3.1 - async data access for GUI)
- **Issue #10**: Event queue (Task 3.2 - lock-free async events)
- **Issue #11**: Callback stage (Task 3.3 - async I/O operations)

### Phase 4 (Scientific Validation - v1.0)
- **Issue #12**: Custom stage overhead benchmark (Task 4.1 - <10µs validation)
- **Issue #13**: RTF validation (Task 4.2 - RTF <0.3 across parameter space)
- **Issue #14**: Long-duration stress test (Task 4.3 - 1hr+ stability)
- **Issue #15**: CuPy comparison (Task 4.4 - competitive positioning)
- **Issue #16**: PyTorch validation (Task 4.5 - ML integration demo)
- **Issue #17**: Scaling analysis (Task 4.6 - NFFT × channels heatmap)

## Labels Reference

Each issue includes labels in the following categories:

### Type (choose one)
- `bug` - Something is broken or incorrect
- `feature` - New capability or enhancement
- `task` - Code quality, refactoring, or maintenance

### Team (choose one or more)
- `team-1-cpp` - C++/CUDA core systems
- `team-2-mlops` - Infrastructure, build, CI/CD
- `team-3-python` - Python API, config, utilities
- `team-4-research` - Experiments, analysis, benchmarks

### Categories (choose relevant)
- `python`, `c++`, `cuda`
- `architecture`, `performance`, `reliability`
- `good first issue`

## Issue Format

Each issue follows the project's standard format from `docs/guides/creating-issues.md`:

1. **Problem** - Clear description with context and impact
2. **Current Implementation** - Code showing the problematic pattern
3. **Proposed Solution** - Concrete code showing the fix
4. **Additional Technical Insights** - Design considerations
5. **Implementation Tasks** - Specific, actionable checklist
6. **Edge Cases to Handle** - Special scenarios
7. **Testing Strategy** - Validation approach
8. **Acceptance Criteria** - Definition of done
9. **Benefits** - Why this matters
10. **Labels, Priority, Effort** - Metadata for project management

## Notes

- All issues have been validated against the current codebase
- Code examples reference actual file paths and line numbers
- Each issue is self-contained and ready to implement
- Dependencies and blocking relationships are documented

## Questions?

See [Creating Issues Guide](../guides/creating-issues.md) for detailed formatting guidelines.
