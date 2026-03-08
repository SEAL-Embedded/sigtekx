# API Reference

Complete API reference for the sigtekx Python package unified API (v0.9.3+).

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
 sigx setup                     # Install Python deps
 ib                             # Build the CUDA extension
it                             # Smoke test the package
```

Once the environment is ready you can import everything directly from `sigtekx`.

## Core API

### `Engine`

`Engine` is the single, unified interface to the CUDA FFT pipeline. It supports three initialization patterns for maximum flexibility.

#### Initialization Patterns

**Pattern 1: Preset-based (Recommended for common use cases)**

```python
from sigtekx import Engine

# Use default configuration (1024 FFT, 0.5 overlap)
engine = Engine(preset='default')

# Use ionosphere configuration (16384 FFT batch / 4096 streaming, 0.75 overlap, Blackman window)
engine = Engine(preset='iono')

# Use extreme ionosphere configuration (32768 FFT batch / 8192 streaming, 0.9375 overlap)
engine = Engine(preset='ionox')

# Override specific parameters
engine = Engine(preset='iono', nfft=8192, mode='streaming')

# Context manager for automatic cleanup
with Engine(preset='iono') as engine:
    spectrum = engine.process(signal)
```

**Pattern 2: Config-based (Full control)**

```python
from sigtekx import Engine, EngineConfig

# Create custom configuration
config = EngineConfig(
    nfft=4096,
    channels=8,
    overlap=0.75,
    window='blackman',
    window_symmetry='periodic',
    window_norm='unity',
    scale='1/N',
    output='magnitude',
    mode='channels'
)
engine = Engine(config=config)

# Or use the factory method from preset
config = EngineConfig.from_preset('iono', nfft=8192, overlap=0.875)
engine = Engine(config=config)
```

**Pattern 3: Pipeline-based (Advanced custom pipelines)**

```python
from sigtekx import Engine, PipelineBuilder

# Build custom pipeline with fluent interface
pipeline = (
    PipelineBuilder()
    .add_window('blackman', symmetry='periodic', norm='unity')
    .add_fft(scale='1/N')
    .add_magnitude()
    .configure(nfft=4096, channels=8, overlap=0.75)
    .build()
)
engine = Engine(pipeline=pipeline)
```

#### Constructor

```python
Engine(
    preset: str | None = None,
    config: EngineConfig | None = None,
    pipeline: Pipeline | None = None,
    **overrides
)
```

**Parameters:**
* `preset` - Preset name: `'default'`, `'iono'`, or `'ionox'`
* `config` - Custom `EngineConfig` instance for full control
* `pipeline` - Custom `Pipeline` from `PipelineBuilder` for advanced use cases
* `**overrides` - Quick parameter overrides (e.g., `nfft=8192, mode='streaming'`)

**Priority:** `pipeline` > `config` > `preset` (with `'default'` as fallback)

#### Available Presets

Presets adapt their parameters based on execution mode for optimal performance:

**Batch Mode (default)** - Optimized for high throughput:

| Preset | NFFT | Batch | Overlap | Window | Description |
|--------|------|-------|---------|--------|-------------|
| `default` | 1024 | 2 | 0.5 | Hann | General-purpose signal processing |
| `iono` | 16384 | 32 | 0.75 | Blackman | Ionosphere scintillation research (high resolution) |
| `ionox` | 32768 | 32 | 0.9375 | Blackman | Extreme ionosphere (ULF/VLF, missile detection) |

**Streaming Mode** - Optimized for low latency:

| Preset | NFFT | Batch | Overlap | Window | Description |
|--------|------|-------|---------|--------|-------------|
| `default` | 1024 | 2 | 0.5 | Hann | General-purpose signal processing |
| `iono` | 4096 | 2 | 0.75 | Blackman | Ionosphere scintillation research (low latency) |
| `ionox` | 8192 | 2 | 0.9 | Blackman | Extreme ionosphere (balanced quality/latency) |

Use preset functions for more control:

```python
from sigtekx.config import get_preset, list_presets, describe_preset, compare_presets

# Get preset configuration (defaults to batch executor variant)
config = get_preset('iono')  # 16384 NFFT, 32 batch (high throughput)

# Get streaming variant for low latency
config = get_preset('iono', executor='streaming')  # 4096 NFFT, 2 batch (low latency)

# List all available presets
presets = list_presets()  # Returns ['default', 'iono', 'ionox']

# Get detailed preset information (shows both variants)
info = describe_preset('iono')

# Compare multiple presets
comparison = compare_presets(['default', 'iono', 'ionox'])
```

#### Lifecycle

`Engine` follows a simple lifecycle: constructed, used, reset or closed. Creation immediately allocates GPU resources; use the context manager to guarantee cleanup.

```python
# Context manager (recommended)
with Engine(preset='iono') as engine:
    output = engine.process(frame)

# Manual lifecycle
engine = Engine(preset='iono')
try:
    output = engine.process(frame)
finally:
    engine.close()
```

* `reset()` - Releases GPU buffers and reinitializes with current configuration
* `close()` - Idempotent cleanup, may be called multiple times

#### Processing API

* **`process(data: ArrayLike) -> np.ndarray`** - Window, FFT, and magnitude for a single frame (`nfft * batch` samples). Returns shape `(batch, nfft // 2 + 1)`.
* **`synchronize() -> None`** - Flush CUDA work queues (normally only needed when integrating with other GPU libraries).
* **`stats -> dict[str, Any]`** - Latest runtime statistics (`latency_us`, `throughput_gbps`, `frames_processed`).

**Example:**
```python
import numpy as np
from sigtekx import Engine

with Engine(preset='iono') as engine:
    signal = np.random.randn(engine.config.nfft * engine.config.channels).astype(np.float32)
    spectrum = engine.process(signal)

    print(f"Input shape: {signal.shape}")
    print(f"Output shape: {spectrum.shape}")
    print(f"Latency: {engine.stats['latency_us']:.1f} μs")
```

#### Error Handling

All exceptions inherit from `SigTekXError` and include stable error codes for programmatic handling, logging, and documentation lookup.

```python
from sigtekx import Engine
from sigtekx.exceptions import ValidationError, EngineRuntimeError

try:
    engine = Engine(preset='iono', nfft=1000)  # Not a power of 2
except ValidationError as e:
    print(f"Configuration error: {e}")
    print(f"Error code: {e.error_code}")  # E1020
    print(f"Machine repr: {repr(e)}")     # Includes error code for logging
```

**Error Codes**

Each exception has a stable `error_code` class attribute (format: `E{category}{sequence}`):

| Code | Exception | Description |
|------|-----------|-------------|
| **E000** | `SigTekXError` | Base exception for all errors |
| **E1010** | `ConfigError` | Configuration validation error |
| **E1020** | `ValidationError` | Input data validation error |
| **E2010** | `DeviceNotFoundError` | No CUDA devices found |
| **E2020** | `DllLoadError` | DLL/library loading failed |
| **E3010** | `EngineStateError` | Invalid engine state |
| **E3020** | `EngineRuntimeError` | Runtime processing error |
| **E4000** | `BenchmarkError` | Base benchmark error |
| **E4010** | `ExperimentError` | Base experiment error |
| **E4100** | `BenchmarkTimeoutError` | Iteration timeout |
| **E4110** | `BenchmarkValidationError` | Validation failed |
| **E4200** | `ReproducibilityError` | Reproducibility metadata error |
| **E4210** | `EnvironmentMismatchError` | Environment mismatch |
| **E4220** | `DataIntegrityError` | Data corruption |
| **E5000** | `AnalysisError` | Base analysis error |
| **E5010** | `InsufficientDataError` | Insufficient data |
| **E5020** | `ReportGenerationError` | Report generation failed |
| **E6000** | `WorkflowError` | Base workflow error |
| **E6010** | `DependencyError` | Missing dependencies |
| **E6020** | `ResourceExhaustedError` | Resource exhausted |

Error codes appear in `repr()` (for logging) but not `str()` (backward compatible). All exceptions include contextual hints and additional attributes documented in their docstrings.

## Configuration

### `EngineConfig`

`EngineConfig` (defined in `sigtekx.config.schemas`) is the unified configuration class that consolidates all engine parameters. Powered by Pydantic v2 with automatic validation.

#### Signal Parameters

* `nfft: int` - FFT size (must be power of 2, default: 1024)
* `batch: int` - Number of parallel signals to process (default: 2)
* `overlap: float` - Frame overlap factor [0.0, 1.0) (default: 0.5)
* `sample_rate_hz: int` - Input signal sample rate in Hz (default: 48000)

#### Pipeline Parameters

* `window: WindowType` - Window function type (default: `WindowType.HANN`)
  - Options: `RECTANGULAR`, `HANN`, `BLACKMAN`
* `window_symmetry: WindowSymmetry` - Window symmetry mode (default: `WindowSymmetry.PERIODIC`)
  - `PERIODIC` - For FFT processing (denominator N)
  - `SYMMETRIC` - For time-domain analysis (denominator N-1)
* `window_norm: WindowNorm` - Window normalization scheme (default: `WindowNorm.UNITY`)
  - `UNITY` - Normalize to unity power/energy gain
  - `SQRT` - Apply square root normalization
* `scale: ScalePolicy` - FFT output scaling policy (default: `ScalePolicy.ONE_OVER_N`)
  - Options: `NONE`, `ONE_OVER_N`, `ONE_OVER_SQRT_N`
* `output: OutputMode` - Pipeline output format (default: `OutputMode.MAGNITUDE`)
  - Options: `MAGNITUDE`, `COMPLEX`

#### Execution Parameters

* `mode: ExecutionMode` - Execution strategy (default: `ExecutionMode.BATCH`)
  - `BATCH` - Maximum throughput batch processing
  - `STREAMING` - Low-latency streaming with ring buffer
* `stream_count: int` - Number of CUDA streams for pipelining (default: 3, range: 1-32)
* `pinned_buffer_count: int` - Number of pinned memory buffers (default: 2, range: 2-8)
* `device_id: int` - CUDA device ID (-1 for auto-select, default: -1)

#### Performance Parameters

* `warmup_iters: int` - Number of warmup iterations (default: 1)
* `timeout_ms: int` - Timeout for operations in milliseconds (default: 1000)
* `enable_profiling: bool` - Enable internal profiling (default: False)

#### Computed Properties

```python
config = EngineConfig(nfft=4096, overlap=0.75, sample_rate_hz=48000)

print(config.hop_size)              # 1024 samples
print(config.num_output_bins)       # 2049 bins
print(config.frame_duration_ms)     # 85.33 ms
print(config.hop_duration_ms)       # 21.33 ms
print(config.effective_fps)         # 46.88 FPS
print(config.memory_estimate_mb)    # Estimated GPU memory usage
```

#### Factory Method

```python
# Create from preset with overrides (gets batch variant by default)
config = EngineConfig.from_preset('iono', nfft=32768, overlap=0.875)

# Apply execution mode override (automatically selects streaming variant)
config = EngineConfig.from_preset('iono', mode='streaming')  # 4096 NFFT, 2 batch

# Combine mode override with parameter overrides
config = EngineConfig.from_preset('iono', mode='streaming', channels=4)

# Note: Mode parameter selects preset variant (batch vs streaming),
# then applies mode-specific optimizations
```

#### Serialization

```python
# Export to dictionary
config_dict = config.to_dict()

# Load from dictionary
config = EngineConfig(**config_dict)

# Pydantic model operations
config_json = config.model_dump_json()
config_copy = config.model_copy(update={'nfft': 8192})
```

### `PipelineBuilder`

`PipelineBuilder` provides a fluent interface for constructing custom processing pipelines.

#### Basic Usage

```python
from sigtekx import PipelineBuilder

pipeline = (
    PipelineBuilder()
    .add_window('blackman', symmetry='periodic', norm='unity')
    .add_fft(scale='1/N')
    .add_magnitude()
    .configure(nfft=4096, channels=8, overlap=0.75)
    .build()
)
```

#### Methods

* **`add_window(type='hann', symmetry='periodic', norm='unity')`** - Add window stage
* **`add_fft(scale='1/N')`** - Add FFT stage
* **`add_magnitude()`** - Add magnitude computation stage
* **`configure(config=None, **kwargs)`** - Set signal/execution parameters
* **`build() -> Pipeline`** - Build immutable pipeline

#### Advanced Example

```python
# Custom pipeline for complex output
pipeline = (
    PipelineBuilder()
    .add_window('hann', symmetry='symmetric', norm='sqrt')
    .add_fft(scale='1/sqrt(N)')
    .configure(
        nfft=2048,
        channels=4,
        overlap=0.625,
        mode='streaming',
        stream_count=4
    )
    .build()
)

from sigtekx import Engine
engine = Engine(pipeline=pipeline)
```

## Enumerations

All enums are available from `sigtekx`:

```python
from sigtekx import (
    WindowType, WindowSymmetry, WindowNorm,
    ScalePolicy, OutputMode, ExecutionMode
)

# Use in configuration
config = EngineConfig(
    window=WindowType.BLACKMAN,
    window_symmetry=WindowSymmetry.PERIODIC,
    window_norm=WindowNorm.UNITY,
    scale=ScalePolicy.ONE_OVER_N,
    output=OutputMode.MAGNITUDE,
    mode=ExecutionMode.BATCH
)

# Or use string values (automatically converted)
config = EngineConfig(
    window='blackman',
    window_symmetry='periodic',
    window_norm='unity',
    scale='1/N',
    output='magnitude',
    mode='channels'
)
```

## Utilities

`sigtekx.utils` hosts lightweight helpers:

* **`sigtekx.utils.device`** - GPU discovery
  - `gpu_count()` - Get number of available GPUs
  - `device_info(device_id)` - Query GPU properties
  - `check_cuda_available()` - Check CUDA availability
  - `monitor_device(device_id)` - Real-time GPU monitoring

* **`sigtekx.utils.signals`** - Deterministic signal generators
  - `make_sine(sample_rate, n_samples, frequency, ...)` - Sine wave
  - `make_chirp(sample_rate, n_samples, f_start, f_end, ...)` - Chirp signal
  - `make_multitone(sample_rate, n_samples, frequencies, ...)` - Multi-tone signal
  - `make_noise(n_samples, ...)` - Noise generators (white, pink, brown)
  - `make_test_batch(signal_type, config, ...)` - Test data batch

* **`sigtekx.utils.archiving`** - Benchmark result storage
  - `DataArchiver` - Structured result archiving

* **`sigtekx.utils.validation`** - Statistical validation
  - `ValidationHelper` - Accuracy validation utilities

* **`sigtekx.utils.reproducibility`** - Deterministic RNG
  - `DeterministicGenerator` - Reproducible random streams

* **`sigtekx.utils.paths`** - Output path management
  - `get_benchmarks_root()` - Benchmark results directory
  - `get_benchmark_result_path(name)` - Result file paths

These utilities are pure Python and safe to import in environments without CUDA.

## Diagnostics

Two top-level helpers provide a quick health check:

```python
from sigtekx import show_versions, self_test

# Print package/platform summary
info = show_versions()

# Create an Engine and run a validation FFT
ok = self_test(verbose=True)
```

`self_test` exercises the default preset. It returns `False` if the CUDA extension cannot be loaded or a GPU is unavailable.

## Thread Safety & Concurrency

`Engine` instances are **not** thread-safe. Create one engine per thread or process. Configuration objects are immutable and can be shared freely.

For streaming workloads prefer long-lived engines instead of recreating them for every frame - construction performs memory allocation and FFT plan creation.

## Migration from v0.9.2

The v0.9.3 unified API replaces the old `Presets` class. See `docs/migration/v0.9.3-api-migration.md` for detailed migration guide.

**Quick migration:**

```python
# OLD (v0.9.2)
from sigtekx import Engine
from sigtekx.config import Presets

config = Presets.realtime()
engine = Engine(config)

# NEW (v0.9.3+)
from sigtekx import Engine

engine = Engine(preset='default', mode='streaming')
# or
from sigtekx.config import get_preset
config = get_preset('default')
config.mode = 'streaming'
engine = Engine(config=config)
```

## Further Reading

* `docs/migration/v0.9.3-api-migration.md` - Detailed migration guide from v0.9.2
* `docs/getting-started/workflow-guide.md` - Research experiment workflows
* `CONTRIBUTING.md` - Contribution workflow and debugging tips
* `docs/getting-started/install.md` - Environment setup
