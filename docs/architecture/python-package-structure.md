# Code Review Reading Guide

### Acceptance Criteria
Deliver an ordered walkthrough that links to concrete files, explains why each stop matters, and flags any unfamiliar concepts to dig into.

---

## 1. Orientation Docs
- [README.md](README.md), [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md), [pyproject.toml](../pyproject.toml)  
  Skim these first to anchor terminology, CLI workflows, and dependency expectations before diving into modules.

---

## 2. Package Entry Point
- [src/sigtekx/__init__.py](src/sigtekx/__init__.py)  
  This file sets the foundation for the whole package:
  - **DLL bootstrapping**: Ensures required Windows DLLs and CUDA toolkit libraries are discoverable before the C++ extension loads.
  - **Engine handling**: Wraps the import of the C++ extension (`_native`) in a resilient way—falling back to a proxy class with clear error messages if the build or DLLs are missing.
  - **Public API exposure**: Defines what’s accessible at the top level (`Engine`, `process_signal`, `benchmark_latency`, `gpu_count`, etc.).
  - **Diagnostics**: Includes `show_versions()` for environment reporting (Python, NumPy, CUDA, pynvml versions) and `self_test()` to verify installation, GPU availability, and numerical stability.

These helpers provide crucial early checks and context—make sure to run them when validating a new install.

---

## 3. Error Surface
- [src/sigtekx/exceptions.py](src/sigtekx/exceptions.py)  
  Establishes a rich hierarchy of domain-specific exceptions that surface errors consistently across the stack:
  - **Base class**: `IonosenseError` unifies all error types with optional `hint` and structured context.
  - **Configuration & validation**: `ConfigError`, `ValidationError` guide misconfigurations or schema mismatches.
  - **Hardware & runtime**: `DeviceNotFoundError`, `DllLoadError`, `EngineStateError`, `EngineRuntimeError` cover GPU, DLL, and CUDA execution failures.
  - **Research-oriented**: `BenchmarkError`, `BenchmarkTimeoutError`, `ExperimentError`, `ReproducibilityError` map to benchmarking and reproducibility standards.
  - **Analysis & workflow**: Exceptions for reporting (`ReportGenerationError`), insufficient data, workflow orchestration, and system resource exhaustion.

Reading this taxonomy early helps you quickly interpret validation failures, runtime crashes, and benchmarking issues, since almost every higher-level component raises these.

---

## 4. Configuration Backbone
- [src/sigtekx/config/schemas.py](src/sigtekx/config/schemas.py)  
  **What it defines:** The canonical `EngineConfig` (Pydantic v2) with strict types, assignment-time validation, and computed properties used throughout the stack.  
  **Key validators & props:** power-of-two `nfft`; model-level memory guard; computed `hop_size`, `num_output_bins`, `frame_duration_ms`, `hop_duration_ms`, `effective_fps`, `memory_estimate_mb`; and research metadata (`experiment_id`, `tags`, `notes`).

- [src/sigtekx/config/validation.py](src/sigtekx/config/validation.py)  
  **What it enforces:** NumPy-first checks to catch config/data issues before CUDA does.  
  **Read in this order & why:** (1) `validate_config_device_compatibility` (headroom/compute-capability), (2) `estimate_memory_usage_mb` (buffer/workspace model), (3) `validate_input_array` (dtype/shape/contiguity/NaN-Inf), (4) `validate_input_size` (input == `channels*nfft`).

- [src/sigtekx/config/presets.py](src/sigtekx/config/presets.py)  
  **Why it matters:** Shared mental model for benchmark modes.  
  **Presets:** `realtime()` (tight deadlines, profiling off), `throughput()` (big `nfft`/`batch`), `validation()` (deterministic, profiling on), `profiling()` (balanced to expose compute/memory).  
  **Tip:** `Presets.custom(**overrides)` for PR-specific experiments without drifting defaults.

- [src/sigtekx/config/__init__.py](src/sigtekx/config/__init__.py)  
  Collects the public surface (`EngineConfig`, `Presets`, validation helpers) so callers don’t import deep internals.

**Reviewer checklist**  
- Do validators reflect new constraints introduced by the PR?  
- Do presets still match their intent (realtime/throughput/profiling)?  
- Will memory/headroom warnings trigger appropriately for new default sizes?  
- Are array validations strict enough to catch the class of bugs fixed by the PR?

---

## 5. Utility Layer
**Why this matters:** these helpers are the glue—paths, logging, device detection, profiling, signals, benchmark/report utilities. If they’re misunderstood, reviewers waste cycles on boilerplate rather than core changes.

- [src/sigtekx/utils/paths.py](src/sigtekx/utils/paths.py)  
  *Manages output directories and file naming.* Defaults land under `build/` but can be overridden by env vars. Ensures reproducible run layouts, avoids cluttering repo root.

- [src/sigtekx/utils/device.py](src/sigtekx/utils/device.py)  
  *CUDA/NVML info and fallbacks.* Wraps `pynvml` and CUDA APIs to query device count, memory, and capabilities. Falls back gracefully on CPU-only machines so tests and docs don’t crash.

- [src/sigtekx/utils/profiling.py](src/sigtekx/utils/profiling.py)  
  *NVTX decorators and ranges.* Annotates hot paths for Nsight Systems/Compute. Exports safe no-op fallbacks when NVTX isn’t available, so code runs in any env.

- [src/sigtekx/utils/reproducibility.py](src/sigtekx/utils/reproducibility.py)  
  *Deterministic RNG management.* Provides `DeterministicGenerator` for reproducible multi-stream seeds across fixtures and benchmarks.

- [src/sigtekx/utils/archiving.py](src/sigtekx/utils/archiving.py)  
  *Result archiving.* Handles JSON snapshots, manifests, and standardized `benchmark_results/<name>/<timestamp>` paths via `DataArchiver`.

- [src/sigtekx/utils/validation.py](src/sigtekx/utils/validation.py)  
  *Statistical validation.* Exposes `ValidationHelper` for measurement QA, distribution checks, and tolerance enforcement.


- [src/sigtekx/utils/signals.py](src/sigtekx/utils/signals.py)  
  *Synthetic signal generators.* Provides sine, noise, and composite test vectors with seeded RNG. Used across fixtures, validation, and benchmarks.

- [src/sigtekx/utils/__init__.py](src/sigtekx/utils/__init__.py)  
  *Namespace management.* Re-exports key helpers and implements lazy import wrappers to reduce startup overhead.

**Reviewer checklist**  
- Are new outputs written under the controlled `build/` tree (or via env override) and not scattered?  
- Do contributions use the provided `logger` rather than raw `print`?  
- Are NVTX spans consistent with the domain/color scheme, and do they no-op safely if NVTX is missing?  
- Are new benchmarks/tests using seeded generators or archiving results when claiming reproducibility?  
- Are synthetic signals or benchmark helpers reused instead of re‑implementing data pipelines?  
- Do reporting changes guard optional dependencies and emit into the correct reports subdir?  
- Are utils imported through the stable `sigtekx.utils` namespace rather than deep paths?

------

## 6. Core Engine Wrapper
- [src/sigtekx/core/engine.py](src/sigtekx/core/engine.py)  
  **Purpose:** A thin, explicit Python wrapper around the C++ `ResearchEngine` with NumPy-friendly I/O and a strict lifecycle (Created → Initialized → Closed).

**Key concepts to review**  
- **Config intake & presets**: accepts `EngineConfig`, a preset string (`"realtime"|"throughput"|"validation"|"profiling"`), or `None` (defaults to `realtime`). Presets are resolved via a map and deep-copied for isolation. Invalid names raise `ValueError`.  
- **Device sanity checks**: `_validate_device_requirements()` pulls GPU info from `utils.device.device_info()` and calls `validate_config_device_compatibility(...)` to fail fast on headroom/capability issues.  
- **Initialization path**: `_import_cpp_engine()` loads the C++ extension and normalizes DLL errors into `DllLoadError`. `_initialize()` instantiates `ResearchEngine`, translates the Pydantic config into a C++ `EngineConfig` struct, and calls `.initialize(...)`.  
- **Supported dtypes**: `_SUPPORTED_DTYPES = (np.float32,)`; complex input is rejected early with a `ValidationError`.  
- **Processing contract**: `process(data)` coerces to contiguous `float32`, enforces `(nfft*batch,)`, returns `(batch, num_output_bins)` magnitude array; size mismatches raise `ValidationError`; CUDA faults → `EngineRuntimeError`.  
- **Stats/profiling**: `process()` accumulates per-frame latency when profiling; `stats` returns last-frame metrics and `avg_latency_us` if enabled; `detailed_metrics` derives bytes/frame and bandwidth.  
- **Lifecycle ops**: `reset()` reinitializes; `close()` releases resources (idempotent); `synchronize()` fences GPU work and wraps errors as `EngineRuntimeError`. Context manager auto-syncs and closes on exit.  
- **Advanced toggles**: ctor flags (`profile_mode`, `cuda_graphs`, `stream_count`, `deterministic`, `debug_mode`); `enable_experimental_feature()` guards switches like `unsafe_mode`, `cuda_graphs`, `multi_stream`.  
- **Class helpers**: `get_available_devices()` / `select_best_device()` proxy C++ queries and degrade gracefully.  
- **One-shot APIs**: `process_signal(data, config)`; `benchmark_latency(config, iterations, data_size)` for quick sanity checks.

- [src/sigtekx/core/__init__.py](src/sigtekx/core/__init__.py) — re-exports `Engine` for stable imports.

**Reviewer checklist**  
- Do preset defaults still match their intent when routed through `_process_config`?  
- Would the PR’s memory/stream changes trip `_validate_device_requirements()` on common GPUs?  
- Are new failure modes mapped to the existing exception taxonomy (not raw `RuntimeError`)?  
- If profiling is involved, does the code increment `frames_processed` and compute `avg_latency_us` correctly?  
- Are context-manager semantics preserved (sync + close) and are resources released on error paths?

---

## 7. Pipeline Metadata
- **Stage definitions:** [src/sigtekx/stages/definitions.py](src/sigtekx/stages/definitions.py)  
- **Stage registry:** [src/sigtekx/stages/registry.py](src/sigtekx/stages/registry.py)  
- **Public surface:** [src/sigtekx/stages/__init__.py](src/sigtekx/stages/__init__.py)

**Reviewer checklist**  
- If a PR adds a new stage, is it named in `StageType` and documented in `STAGE_METADATA`?  
- Are docs/CLI pulling stage lists from `list_implemented_stages()` instead of hard-coding?  
- Do custom extensions use the decorator (`@register_stage`) with metadata?  
- Any risk of silent overwrite (same stage name)? Ensure warnings are tested in CI.

---

## 8. Benchmarking Stack
**What this section gives you:** a unified, RSE/RE-friendly way to run reliable, repeatable benchmarks with NVTX traces, context capture, and standardized stats.

**Core primitives —** [benchmarks/base.py](src/sigtekx/benchmarks/base.py)  
- `BenchmarkContext` captures full environment (platform, CUDA devices, git state, package versions) and computes a deterministic `environment_hash` for traceability.  
- `BenchmarkConfig` centralizes iterations/warmups, confidence/outlier controls, determinism (`seed`, `deterministic`), GPU requirements, and output toggles.  
- `BaseBenchmark` lifecycle: `setup()` → repeated `execute_iteration()` → `teardown()` with `_setup_reproducibility()` (env vars like `CUBLAS_WORKSPACE_CONFIG`) and NVTX helpers (`setup_range`, `benchmark_range`, etc.).

**Latency —** [benchmarks/latency.py](src/sigtekx/benchmarks/latency.py)  
- End-to-end latency (µs) with pre/post GPU sync; CPU-timed fallback until GPU events are exposed.  
- Tracks jitter and deadline compliance (`deadline_us`); placeholders for component timing.  
- Deterministic test data via `make_test_batch`; engine from `Presets.realtime()`.

**Realtime —** [benchmarks/realtime.py](src/sigtekx/benchmarks/realtime.py)  
- Simulates streaming with strict frame deadlines (defaults to `hop_duration_ms`), busy-wait or sleep timing, and drop-frame protection (`drop_frame_threshold`).  
- Emits processed/dropped frames, deadline misses, mean/max latency, jitter, and compliance rate.

**Throughput & scaling —** [benchmarks/throughput.py](src/sigtekx/benchmarks/throughput.py)  
- Sustained processing by **duration** or target **data size (GB)**; pre-generates deterministic noise batches.  
- Reports frames/s, samples/s, GB/s; optional memory and PCIe bandwidth estimates; periodic GPU resource sampling (utilization, temp, power).

**Accuracy —** [benchmarks/accuracy.py](src/sigtekx/benchmarks/accuracy.py)  
- Validates GPU output vs reference (SciPy/Numpy) and checks fundamentals (Parseval, linearity, window accuracy) with configurable tolerances and SNR thresholds.  
- Produces pass/fail summary plus mean/max error and SNR stats.

**Parameter sweeps —** [benchmarks/sweep.py](src/sigtekx/benchmarks/sweep.py)  
- `ParameterSpec` supports explicit `values` or generated ranges (int/float, lin/log spacing); optional Latin Hypercube via SciPy with graceful fallback.  
- Nested param paths (e.g., `engine_config.nfft`) let you mutate deep configs; saves full experiment config + context to disk under a centralized experiments root.

**Suite orchestration —** [benchmarks/suite.py](src/sigtekx/benchmarks/suite.py)  
- `SuiteConfig` selects/excludes benchmarks, sets global iterations/warmup, and configures output/reporting.  
- `BenchmarkSuite.run()` wires NVTX spans, resolves presets per benchmark type, saves suite config + environment, and streams results to an output directory under the benchmarks root.  
- Registry includes: `latency`, `latency_streaming`, `throughput`, `scaling`, `realtime`, `accuracy`.

**Research workflows —** [benchmarks/research_workflow.py](src/sigtekx/benchmarks/research_workflow.py)  
- Chains setups, individual benchmarks, sweeps, analyses, and report generation under a single `workflow_id`, with robust config and environment capture for reproducibility.

**Public API —** [benchmarks/__init__.py](src/sigtekx/benchmarks/__init__.py)

**Reviewer checklist**  
- Are NVTX ranges present around setup/compute/teardown hot paths?  
- Do configs set `seed` and `deterministic=True` when claiming reproducibility?  
- If deadlines are asserted (latency/realtime), are violations analyzed (%>deadline, worst margin, p99)?  
- For throughput claims, do metrics include frames/s **and** GB/s (with context where possible)?  
- For accuracy claims, are tolerances + reference impl documented, and do results report mean/max error + SNR?  
- Are suite/sweep outputs saving configs + environment snapshots under the proper root dirs?

---

## 9. Testing Support
**Why it matters:** pytest fixtures + numerical validators underpin confidence in reproducibility, GPU correctness, and scientific validity.

**Fixtures —** [testing/fixtures.py](src/sigtekx/testing/fixtures.py)  
- **Dirs**: `temp_data_dir`, `temp_benchmark_dir` for ephemeral data/results/reports.  
- **Configs**: `validation_config`, `realtime_config`, `benchmark_base_config`, `benchmark_config`.  
- **Contexts/results**: `benchmark_context`, `sample_benchmark_result` for deterministic metadata & fake results.  
- **YAML I/O**: `yaml_benchmark_config`, `yaml_sweep_config` to generate small config files for parsing tests.  
- **Engine lifecycles**: `test_engine` yields a real `Engine` (with cleanup); `mock_engine` monkeypatches a fake one for CPU-only runs.  
- **Signal/data**: `seeded_rng`, `test_sine_data`, `test_batch_data`, `test_noise_data`, `test_signal_suite`.  
- **Mock hardware**: `mock_device_info`, `gpu_available`, `skip_without_gpu`, `require_nsight` for hardware-dependent gating.  
- **Benchmark runs**: `benchmark_runner`, `parameter_sweep_runner` for end-to-end dummies.  
- **Reference/validation**: `reference_fft_output`, `validation_helper`, `data_archiver`.  
- **Research metadata**: `research_metadata`, `experiment_config` embed RSE/RE/IEEE fields.  
- **Parametrized**: `test_signal_type`, `test_nfft_size`, `test_batch_size`, `sweep_type` expand coverage.

**Validators —** [testing/validators.py](src/sigtekx/testing/validators.py)  
- **Numerical closeness**: `assert_allclose` wraps NumPy with tuned rtol/atol.  
- **Spectral checks**: `assert_spectral_peak` (peak freq), `assert_parseval` (energy), `validate_fft_symmetry` (Hermitian).  
- **Signal quality**: `assert_snr` (SNR thresholds), `calculate_thd` (harmonic distortion).  
- **Comparisons**: `compare_with_reference` (rmse/mae/max/correlation) with sane dtype-aware thresholds.  
- **Range & stability**: `validate_output_range`, `check_numerical_stability` (per-element variance across runs).

**Init —** [testing/__init__.py](src/sigtekx/testing/__init__.py)  
- Empty `__all__` keeps imports explicit and avoids pytest plugin side-effects.

**Reviewer checklist**  
- Do new tests pull configs/fixtures instead of hard-coding arrays/paths?  
- For GPU-dependent tests, are `skip_without_gpu` / `require_nsight` used to avoid CI hangs?  
- Are accuracy tests leveraging `assert_parseval`, `assert_snr`, or `compare_with_reference` with documented tolerances?  
- Do PRs add parametrized fixtures to expand coverage rather than duplicating loops?  
- If new benchmarks/tests claim reproducibility, are RNGs seeded (`seeded_rng`) and metadata archived (`data_archiver`)?

---

## 10. Usage Examples
- Explore [tests/](tests/) and referenced notebooks in [~/docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md)  
  These provide idiomatic usage, parameter combinations, and expected behaviours once the library is understood.

