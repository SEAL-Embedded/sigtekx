# Changelog

All notable changes to the SigTekX project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-12-05

### Changed

#### BREAKING: Complete Project Rename - Ionosense-HPC → SigTekX

**Motivation**: Establish new project branding with comprehensive renaming across all documentation and tooling.

**All references updated:**
- **Package name**: `ionosense-hpc` → `sigtekx`
- **Python module**: `ionosense_hpc` → `sigtekx` (imports: `from sigtekx import Engine`)
- **CLI commands**:
  - `iono` → `sigx` (main command)
  - `ionoc` → `sigxc` (C++ benchmarking - if applicable)
  - `iprof` → `sxp` (profiling)
- **Repository URL**: `SEAL-Embedded/ionosense-hpc-lib` → `SEAL-Embedded/sigtekx`
- **Conda environment**: `ionosense-hpc` → `sigtekx`
- **Environment variables**:
  - `IONO_OUTPUT_ROOT` → `SIGX_OUTPUT_ROOT`
  - `IONO_LOG_COLOR` → `SIGX_LOG_COLOR`
- **Short aliases** (development shell):
  - `ib` → `sb` (build)
  - `it` → `st` (test)
  - `itp` → `st python`
  - `itc` → `st cpp`
  - `ifmt` → `sfmt` (format)
  - `ilint` → `slint` (lint)
  - `iprof` → `sxp` (profile)
  - `icbench` → removed (use `sigxc` or `sxp`)

**Preserved:**
- ✅ All "ionosphere" domain terminology (VLF/ULF, scintillation, etc.) remains unchanged
- ✅ Scientific references and research context preserved
- ✅ API and functionality completely unchanged - purely naming/branding update
- ✅ All tests pass with new naming

**Documentation updates:**
- `README.md`: Updated all command examples and package references
- `CONTRIBUTING.md`: Updated development workflow and CLI references
- `AGENTS.md`: Updated agent operations guide
- `CLAUDE.md`: Updated all command examples
- All inline code examples updated to reflect new naming

**Migration notes:**
- This is a **breaking change** for all users - all imports and CLI commands must be updated
- For upgrade instructions, see migration guide (coming in next release)
- Conda environment must be recreated with new name

**Impact**:
- 📋 Documentation: Updated across all root files
- 🐍 Python API: All imports change from `ionosense_hpc` to `sigtekx`
- 💻 CLI: All commands change from `iono` prefix to `sigx`
- 📦 Package: New conda environment and PyPI package name
- ✅ All 133+ tests pass with new configuration
- ✅ No functionality changes - purely naming

---

## [0.9.4] - 2025-10-23

### Changed

#### BREAKING: Complete Terminology Refactor for Industry Standards

**Motivation**: Established clear, industry-standard terminology to eliminate fundamental mental model confusion between spatial, temporal, and execution dimensions. Previous "batch" terminology caused architecture errors by conflating unrelated concepts.

**Phase 1: Spatial Dimension - `batch` → `channels`**
- `EngineConfig.batch` → `SignalConfig.channels` (C++)
- `engine.batch` → `engine.channels` (Python/YAML)
- `experiment=batch_scaling` → `experiment=channels_scaling`
- **Mental Model**: `channels` = number of independent signal streams (e.g., dual-antenna = 2)

**Phase 2: Temporal Dimension - Established `frames` terminology**
- `ResultCallback::batch_size` → `ResultCallback::num_frames` (C++)
- `RingBuffer::extract_batch(batch)` → `RingBuffer::extract_batch(num_frames)`
- `test_batch_sizes` → `test_channel_counts` (Python benchmarks)
- `validate_batch_size()` → `validate_input_size()` (Python validation)
- **Mental Model**: `frames` = number of temporal FFT windows processed

**Phase 3: C++ Architecture Clarity - Removed "engine" misnomer**
- `engine_config.hpp` → `signal_config.hpp` (no "engine" abstraction in C++)
- `engine_utils` → `signal_utils` namespace
- `EngineConfig` struct → `SignalConfig` struct
- `ExecutorConfig` now extends `SignalConfig` (was `EngineConfig`)
- **Rationale**: Only Python has an `Engine` abstraction; C++ only has executors

**Complete Mental Model (v0.9.4)**:
```
SPATIAL:   channels  → Independent signal streams (dual-antenna = 2)
TEMPORAL:  frames    → Time windows for STFT (512 FFT windows)
SPECTRAL:  nfft      → FFT window size (4096 → 2049 frequency bins)
EXECUTION: mode      → Processing strategy (batch vs streaming)
```

**Migration**:
```python
# Python API (unchanged - uses EngineConfig from schemas.py)
config = EngineConfig(nfft=4096, channels=8, overlap=0.5)
engine = Engine(config=config)
```

```cpp
// C++ API (struct names changed)
SignalConfig config;  // Was EngineConfig
config.channels = 8;  // Was config.batch
```

**Impact**:
- ⚠️ **Zero backwards compatibility** - breaking changes across all dimensions
- 🔴 **C++ breaking**: `EngineConfig` → `SignalConfig`, `engine_utils::` → `signal_utils::`
- 🟡 **C++ API change**: `ResultCallback` signature (`batch_size` → `num_frames`)
- 🟡 **Python minor**: `validate_batch_size()` → `validate_input_size()` (internal)
- ✅ **All 133 C++ tests passing**
- ✅ **Documentation updated** with dimension reference in README
- 📁 **Files changed**: 21 files (93 Phase 1 + architecture fixes)

**Fixes**: This refactor resolves fundamental architecture errors caused by terminology confusion that led to incorrect mental models and implementation issues.

## [0.9.3] - 2025-10-15

### Added

#### New Unified API System
- **Three initialization patterns** for `Engine` class:
  - Pattern 1: Preset-based - `Engine(preset='iono', **overrides)`
  - Pattern 2: Config-based - `Engine(config=custom_config)`
  - Pattern 3: Pipeline-based - `Engine(pipeline=custom_pipeline)`
- **New preset functions** replacing static `Presets` class:
  - `get_preset(name, **overrides)` - Get preset configuration with optional overrides
  - `list_presets()` - List all available presets
  - `describe_preset(name)` - Get detailed preset information
  - `compare_presets(names)` - Compare multiple presets side-by-side
- **Domain-specific presets** for ionosphere research:
  - `'default'` (1024 FFT, 0.5 overlap, Hann window) - General-purpose
  - `'iono'` (4096 FFT, 0.75 overlap, Blackman window) - Ionosphere scintillation
  - `'ionox'` (8192 FFT, 0.9 overlap, Blackman window) - Extreme ionosphere (ULF/VLF, missile detection)
- **`PipelineBuilder` class** with fluent interface for custom pipeline construction:
  - `add_window()` - Configure window stage
  - `add_fft()` - Configure FFT stage
  - `add_magnitude()` - Add magnitude computation
  - `configure()` - Set signal/execution parameters
  - `build()` - Build immutable pipeline

#### Configuration Enhancements
- **Unified `EngineConfig`** consolidating all engine parameters:
  - Signal parameters: `nfft`, `batch`, `overlap`, `sample_rate_hz`
  - Pipeline parameters: `window`, `window_symmetry`, `window_norm`, `scale`, `output`
  - Execution parameters: `mode`, `stream_count`, `pinned_buffer_count`, `device_id`
  - Performance parameters: `warmup_iters`, `timeout_ms`, `enable_profiling`
- **`EngineConfig.from_preset()` factory method** for preset-based configuration with overrides
- **New enumerations** exposed to Python:
  - `WindowSymmetry` - PERIODIC (FFT), SYMMETRIC (time-domain)
  - `WindowNorm` - UNITY, SQRT
  - `OutputMode` - MAGNITUDE, COMPLEX
  - `ExecutionMode` - BATCH, STREAMING
- **Computed properties** on `EngineConfig`:
  - `hop_size` - Samples between frame starts
  - `num_output_bins` - Frequency bins in output
  - `frame_duration_ms` - Frame duration
  - `hop_duration_ms` - Time between frames
  - `effective_fps` - Frames per second
  - `memory_estimate_mb` - Estimated GPU memory usage

#### Testing & Validation
- **Comprehensive test suite** with 50+ integration tests in `tests/test_unified_api.py`:
  - 8 preset tests
  - 11 EngineConfig tests
  - 9 PipelineBuilder tests
  - 8 Engine initialization tests
  - 6 enum tests
  - 4 end-to-end integration tests
  - 3 backward compatibility tests (deprecated patterns)
- All tests passing with clean ruff lint and mypy type checks

#### Documentation
- **Complete API reference** rewrite in `docs/guides/api-reference.md`:
  - Three initialization patterns with examples
  - Full enum documentation
  - PipelineBuilder usage guide
  - Preset functions reference
- **Migration guide** in `docs/migration/v0.9.3-api-migration.md`:
  - Breaking changes summary
  - Migration examples for all common patterns
  - Configuration parameter mapping
  - Common migration issues and solutions
- **Updated README** with new quick usage examples
- **Updated workflow guide** with API version notes

### Changed

#### API Breaking Changes
- **`Engine` constructor** changed from positional to keyword arguments:
  - OLD: `Engine(config)` (single positional)
  - NEW: `Engine(preset=..., config=..., pipeline=..., **overrides)` (keyword args)
- **Preset initialization** now uses keyword argument:
  - OLD: `Engine(Presets.realtime())`
  - NEW: `Engine(preset='default', mode='streaming')`
- **Configuration parameter structure**:
  - All parameters now in single unified `EngineConfig`
  - Removed separate `ExecutorConfig` and `StageConfig` classes
  - Parameters automatically mapped to appropriate C++ components

#### Internal Refactoring
- **Benchmark scripts** updated to use new preset functions:
  - `latency.py`, `throughput.py`, `realtime.py`, `accuracy.py` all migrated
  - Replaced old preset methods with `get_preset('default')`
  - Added mode overrides where appropriate (e.g., `mode='streaming'`)
- **Test fixtures** updated in `src/ionosense_hpc/testing/fixtures.py`:
  - `validation_config` fixture uses `get_preset('default', batch=1)`
  - Streaming-mode fixtures use `mode='streaming'` override
  - All fixtures compatible with new API
- **Main exports** updated in `src/ionosense_hpc/__init__.py`:
  - Removed `Presets` class export
  - Added preset function exports
  - Added `PipelineBuilder` and `Pipeline` exports
  - Added new enum exports

#### C++ Bindings
- **Exposed additional enums** in `cpp/bindings/bindings.cpp`:
  - `WindowSymmetry` enum (PERIODIC, SYMMETRIC)
  - `WindowNorm` enum (UNITY, SQRT)
  - `OutputMode` enum (MAGNITUDE, COMPLEX_PASSTHROUGH)
- All enums now accessible from Python with string auto-conversion

### Removed

#### Deprecated Components
- **`Presets` static class** (`src/ionosense_hpc/config/presets.py` old implementation):
  - Removed old preset methods → Use `Engine(preset='default', mode='streaming')` or similar
  - Removed `Presets.throughput()` → Use `Engine(preset='default')` or `Engine(preset='iono')`
  - Removed `Presets.validation()` → Use `Engine(preset='default', batch=1)`
  - Removed `Presets.profiling()` → Use `Engine(preset='default', enable_profiling=True)`
  - Removed `Presets.custom(**kwargs)` → Use `get_preset('default', **kwargs)`
- **Old preset naming**:
  - No longer using generic names (validation, profiling, etc.)
  - Replaced with domain-specific names (default, iono, ionox)
- **Multiple configuration classes**:
  - Consolidated into single `EngineConfig`
  - Removed separate `ExecutorConfig` and `StageConfig` from Python API

### Migration

See detailed migration guide: `docs/migration/v0.9.3-api-migration.md`

**Quick Migration Summary:**

```python
# OLD (v0.9.2)
from ionosense_hpc import Engine
from ionosense_hpc.config import Presets

config = Presets.realtime()
engine = Engine(config)

# NEW (v0.9.3)
from ionosense_hpc import Engine

# Option 1: Direct preset (simplest)
engine = Engine(preset='default', mode='streaming')

# Option 2: Using get_preset
from ionosense_hpc.config import get_preset
config = get_preset('default', mode='streaming')
engine = Engine(config=config)

# Option 3: Using from_preset factory
from ionosense_hpc import EngineConfig
config = EngineConfig.from_preset('default', mode='streaming')
engine = Engine(config=config)
```

**No backward compatibility:** The v0.9.3 API is a clean break from v0.9.2. All code must be migrated to the new patterns.

### Technical Details

#### Architecture
- **C++ Backend (arch/cpp-abs branch)**: v0.9.3 cpp-abs
  - `IPipelineExecutor` interface with `BatchExecutor` and `StreamingExecutor`
  - `IProcessingStage` interface with `WindowStage`, `FFTStage`, `MagnitudeStage`
  - `PipelineBuilder` for composing stages
  - `EngineConfig` and `ExecutorConfig` separation at C++ level

#### Configuration System
- **Pydantic v2** validation with field validators
- **Automatic enum conversion** from strings to enum values
- **Resource estimation** with memory usage warnings
- **Mode-specific overrides** in `from_preset()` factory method

#### Testing Coverage
- **50/50 tests passing** in unified API test suite
- **Clean linting**: ruff check passing
- **Clean type checking**: mypy passing
- **Integration tests**: End-to-end workflow validation

### Notes

- This release focuses exclusively on API design and does not include performance changes
- All previous performance characteristics are maintained
- Experiment configurations (Hydra YAML) remain fully compatible
- C++ backend changes are internal; Python API is the primary interface

---

## [0.9.2] - 2025-09-30

### Added
- Snakemake-based research workflow orchestration (clean/setup/build/test) with Hydra override support.
- Automated analysis and figure generation commands plus a demo data generator for dashboard workflows.
- Restored experiment and analysis CLI commands with artifact-aware defaults and colorized console output.

### Changed
- Standardized benchmark and experiment artifacts under `artifacts/` and Snakemake-managed paths.
- Streamlined CLI surface by removing legacy experiment runners and routing to the new workflow stack.
- Tightened PowerShell bootstrap scripts to hook conda/mamba consistently and improve version detection.

### Fixed
- Normalized FFT scaling and accuracy thresholds to resolve cross-platform drift.
- Corrected latency benchmark chirp parameter regression and hardened Hydra override handling.
- Hardened device discovery and GPU detection to fail fast instead of masking driver issues.

### Removed
- Deprecated experiment runners, bespoke CLI paths, and redundant configs in favor of Snakemake-managed workflows.

### Documentation
- Updated benchmarking and development guides to describe the Snakemake workflow and refreshed artifact layout.

---

## [0.9.1] - 2025-09-16

### Added
- NVTX instrumentation across C++ kernels, Python pipelines, and Google Tests with matching NVTX unit coverage.
- GPU monitor helper plus CLI shortcuts (`iono check`, `iono typecheck`, staged lint/format, targeted `--pattern` tests) for rapid feedback.

### Changed
- Unified the Python API layers (`processor`, `engine`, `rawengine`) into a single `engine` surface with shared fixtures.
- Centralized benchmark outputs under `build/` and normalized naming across analysis and validation paths.
- Reworked CLI maintenance commands (`clean`, `doctor`) to respect caches and provide verbose reporting options.
- Migrated C++/CUDA sources into the top-level `cpp/` directory and aligned CMake presets across platforms.

### Fixed
- Resolved dozens of mypy and ruff issues uncovered during the automation rollout.
- Addressed documentation pointers and fixture mismatches introduced by the API consolidation.

### Documentation
- Updated API, benchmarking, development, and install guides to reflect the unified engine API and new automation flows.

---

## [0.9.0] - 2025-08-30

### Added
- Benchmarking and profiling commands in the repo CLI, including GPU doctor diagnostics.
- Python signals core, configuration framework, and the initial pipeline wrapper bridging to the CUDA engine.
- Cross-platform CMake presets and environment bootstrap scripts for Windows and Linux developers.

### Changed
- Reorganized the CUDA engine into `fft_engine.cpp`, `ops_fft.cu`, and stage objects aligned with modern C++17 patterns.
- Overhauled CLI scripts to detect mamba/conda automatically, trim redundant logic, and accelerate workflows.
- Restructured packaging to ship the Python extension cleanly (shared `ion_engine` object and wheel-friendly layout).

### Fixed
- Achieved reproducible builds across platforms (PIC/shared `cudart`, ignored compiled artifacts).
- Reduced build times via Ninja + ccache and better dependency caching.

### Documentation
- Added project structure and architecture documentation along with expanded root README setup guidance.

---

## [0.8.0] - 2025-07-04

### Added
- Pybind11 bindings replacing the legacy ctypes bridge, enabling direct Python access to the CUDA engine.
- GPU-resident de-interleaving, windowing, magnitude, and batched benchmark updates with simplified APIs.
- Expanded unit tests for the FFT engine covering lifecycle, accuracy versus NumPy, and buffer handling.

### Changed
- Build system migrated to CMake (with `.bat` fallback) alongside reorganized CUDA source layout and documentation refresh.
- CUDA engine refactored to object-oriented design with auto-detected GPU architectures, streams, graphs, and pinned buffers.
- Profiling and benchmarking pipelines updated with GPU warm-up routines and cleaner summaries.

### Documentation
- Added inline documentation across engine modules plus refreshed architectural notes for the new kernels.

Note: Backfilled from internal development log (June-July 2025).

---

## [0.5.0] - 2025-06-24

### Added
- Real-time CUDA engine capabilities with CUDA Graphs, multi-stream execution, and pinned host buffers.
- GPU-side windowing and de-interleaving kernels integrated into the FFT pipeline.
- Profiling hooks and benchmarks covering real-time scenarios plus improved pytest coverage.

### Changed
- Build pipeline upgraded to auto-detect GPU architectures and support the evolving CMake orchestration.
- API streamlined for real-time use cases, reducing overhead and simplifying configuration.

### Documentation
- Expanded module documentation and build notes for the real-time stack.

Note: Backfilled from internal development log (June 2025).

---

## [0.1.0] - 2025-05-18

### Added
- Initial CUDA-accelerated FFT prototype using cuFFT integrated into the research test harness.
- Python CUDA interface refactored to object-oriented design, enabling clean engine lifecycle management.
- Performance optimizations (R2C FFT path, reduced overhead) delivering roughly 1.5-2x speedups versus earlier builds.

### Notes
- Captured early deployment learnings, including field laptop toolchain setup and real-time testing progress.
- Benchmarked against NumPy and cuFFT baselines while planning the custom kernel follow-up.

Note: Backfilled from internal development log (March-May 2025).
