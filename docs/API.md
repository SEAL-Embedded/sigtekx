# API Reference

Complete API reference for the ionosense-hpc Python package, including examples that mirror the CLI workflow.

## Getting Started

Before importing the package, make sure the C++ extension has been built with the provided CLI helpers.

**Linux / WSL2**
```bash
./scripts/cli.sh setup          # Install Python deps
./scripts/cli.sh build          # Build the CUDA extension
./scripts/cli.sh test           # Smoke test the package
```

**Windows**
```powershell
.\scripts\open_dev_pwsh.ps1    # Launch the dev shell
iono setup                     # Install Python deps
ib                             # Build the CUDA extension
it                             # Smoke test the package
```

Once the environment is ready you can import everything directly from `ionosense_hpc`.

## Core API

### `Engine`

`Engine` is the single, unified interface to the CUDA FFT pipeline.

```python
from ionosense_hpc import Engine, Presets

config = Presets.realtime()
with Engine(config) as engine:
    spectrum = engine.process(signal)
```

#### Constructor

```python
Engine(
    config: EngineConfig | str | None = None,
    *,
    validate_inputs: bool = True,
    profile_mode: bool = False,
    cuda_graphs: bool = False,
    stream_count: int | None = None,
    deterministic: bool = False,
    debug_mode: bool = False,
)
```

* `config` – pass an `EngineConfig`, a preset name ("realtime", "throughput", "validation", "profiling"), or leave `None` for the realtime preset.
* `validate_inputs` – verify shapes and dtypes in Python. Disable for maximum throughput once inputs are trusted.
* `profile_mode` – collects extended metrics that feed `Engine.detailed_metrics`.
* `cuda_graphs`, `stream_count`, `deterministic`, `debug_mode` map directly to the underlying CUDA implementation.

#### Lifecycle

`Engine` follows a simple lifecycle – constructed, used, reset or closed. Creation immediately allocates GPU resources; use the context manager to guarantee cleanup.

```python
engine = Engine("validation")
try:
    output = engine.process(frame)
finally:
    engine.close()
```

`reset()` releases GPU buffers and reinitialises the engine with the current configuration. `close()` is idempotent and may be called multiple times.

#### Processing API

* `process(data: ArrayLike) -> np.ndarray` – window, FFT and magnitude for a single frame (`nfft * batch` samples). The return value is shaped `(batch, nfft // 2 + 1)`.
* `synchronize() -> None` – flush CUDA work queues. Normally only required when integrating with other GPU libraries.
* `stats -> dict[str, Any]` – latest runtime statistics (`latency_us`, `throughput_gbps`, `frames_processed`, plus averages when profiling is enabled).
* `detailed_metrics -> dict[str, Any]` – derived metrics that include computed bandwidth and utilisation (requires `profile_mode=True`).

All validation errors are raised as `ionosense_hpc.exceptions.ValidationError`. Runtime faults in the C++ layer are surfaced as `EngineRuntimeError`.

### Convenience Functions

The module also exports helpers built on top of `Engine`:

```python
from ionosense_hpc import process_signal, benchmark_latency

spectrum = process_signal(raw_signal, "validation")
stats = benchmark_latency("realtime", iterations=50)
```

Both helpers are thin wrappers that create a short-lived `Engine` internally.

## Configuration

### `EngineConfig`

`EngineConfig` (defined in `ionosense_hpc.config.schemas`) encapsulates every configuration knob, including FFT size, batch size, overlap, stream count and profiling flags. The model is powered by Pydantic v2, so values are validated on assignment and `model_dump()` produces JSON-ready dictionaries.

Important fields:

* `nfft` – FFT size (power of two)
* `batch` – number of channels processed per call
* `overlap` – fractional overlap between consecutive frames
* `stream_count`, `pinned_buffer_count`, `warmup_iters` – pipeline parameters
* `enable_profiling`, `use_cuda_graphs` – advanced options

Computed properties (`hop_size`, `num_output_bins`, `effective_fps`, `memory_estimate_mb`) make it easy to reason about downstream behaviour.

### Presets

`ionosense_hpc.config.Presets` returns pre-tuned `EngineConfig` instances:

* `Presets.realtime()` – dual-channel, low-latency configuration
* `Presets.throughput()` – large batch, offline throughput testing
* `Presets.validation()` – small FFT for correctness checks
* `Presets.profiling()` – balanced settings for metric collection

Use `Presets.custom(**overrides)` to clone the realtime preset and adjust specific fields.

## Utilities

`ionosense_hpc.utils` hosts lightweight helpers:

* `ionosense_hpc.utils.device` – GPU discovery (`gpu_count`, `device_info`, `check_cuda_available`, `monitor_device`).
* `ionosense_hpc.utils.signals` – deterministic signal generators (`make_sine`, `make_chirp`, `make_noise`, `make_test_batch`).
* `ionosense_hpc.utils.benchmark_utils` – helpers for structured benchmark output, archiving and validation.

These utilities are pure Python and safe to import in environments without CUDA.

## Diagnostics

Two top-level helpers provide a quick health check:

```python
from ionosense_hpc import show_versions, self_test

info = show_versions()        # Print package/platform summary
ok = self_test(verbose=True)  # Create an Engine and run a validation FFT
```

`self_test` exercises the default validation preset. It returns `False` if the CUDA extension cannot be loaded or a GPU is unavailable.

## Thread Safety & Concurrency

`Engine` instances are **not** thread-safe. Create one engine per thread or process. Configuration objects are immutable and can be shared freely.

For streaming workloads prefer long-lived engines instead of recreating them for every frame – construction performs memory allocation and FFT plan creation.

## Further Reading

* `docs/DEVELOPMENT.md` – contribution workflow and debugging tips.
* `docs/INSTALL.md` – environment bootstrapping on Windows and Linux.
