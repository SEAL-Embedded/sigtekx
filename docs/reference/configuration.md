# Configuration Guide

**Status:** Phase 0 (v0.9.4+)
**Last Updated:** 2026-01-01

## Overview

SigTekX provides two configuration classes for different use cases:

| Config Class | Level | Primary Use Case | Import From |
|--------------|-------|------------------|-------------|
| **EngineConfig** | High-level | Experiments, benchmarks, production | `from sigtekx import EngineConfig` |
| **StageConfig** | Low-level | Custom pipeline stages (Phase 1/2) | `from sigtekx.core import _native` |

**Rule of thumb:** Use `EngineConfig` for 99% of use cases. Only use `StageConfig` when building custom multi-stage pipelines.

---

## Quick Start

### For Experiments and Benchmarks (Recommended)

```python
from sigtekx import (
    EngineConfig,
    WindowType,
    WindowSymmetry,
    WindowNorm,
    ScalePolicy,
    OutputMode,
    ExecutionMode,
)

# Create configuration with all available toggles
config = EngineConfig(
    # Signal parameters
    nfft=8192,
    channels=8,
    overlap=0.75,
    sample_rate_hz=100000,

    # Pipeline parameters (all toggles available!)
    window_type=WindowType.BLACKMAN,
    window_symmetry=WindowSymmetry.PERIODIC,
    window_norm=WindowNorm.UNITY,
    scale_policy=ScalePolicy.ONE_OVER_N,
    output_mode=OutputMode.MAGNITUDE,

    # Execution control
    mode=ExecutionMode.STREAMING,
    stream_count=3,
    device_id=0,

    # Performance tuning
    warmup_iters=10,
    use_cuda_graphs=False,
    enable_profiling=True,
)

# Use with Engine
from sigtekx import Engine
engine = Engine(config=config)
```

### For Custom Pipeline Stages (Advanced)

```python
from sigtekx.core import _native

# Low-level per-stage configuration
config = _native.StageConfig()

# Signal parameters
config.nfft = 4096
config.channels = 2
config.overlap = 0.75
config.sample_rate_hz = 48000

# Pipeline parameters
config.window_type = _native.WindowType.HANN
config.window_symmetry = _native.WindowSymmetry.PERIODIC
config.window_norm = _native.WindowNorm.UNITY
config.scale_policy = _native.ScalePolicy.ONE_OVER_N
config.output_mode = _native.OutputMode.MAGNITUDE

# Optimization toggles (StageConfig only!)
config.preload_window = True  # Precompute window coefficients
config.inplace = True          # Enable in-place operations

# Computed properties
hop = config.hop_size  # Returns nfft * (1 - overlap)

# Use for custom stage construction (Phase 1/2)
# stage = custom_stage_factory.create(config)
```

---

## Field-by-Field Comparison

### Signal Processing Parameters

| Field | EngineConfig | StageConfig | Description |
|-------|--------------|-------------|-------------|
| FFT size | `nfft` ✅ | `nfft` ✅ | FFT size (must be power of 2) |
| Channels | `channels` ✅ | `channels` ✅ | Number of independent signal channels |
| Overlap | `overlap` ✅ | `overlap` ✅ | Frame overlap factor [0.0, 1.0) |
| Sample rate | `sample_rate_hz` ✅ | `sample_rate_hz` ✅ | Input sample rate in Hz |

**Notes:**
- All signal parameters have identical names and behavior
- Both configs validate that nfft is a power of 2

### Pipeline Parameters

| Feature | EngineConfig | StageConfig | Description |
|---------|--------------|-------------|-------------|
| Window function | `window_type` ✅ | `window_type` ✅ | Window function (RECTANGULAR, HANN, BLACKMAN) |
| Window symmetry | `window_symmetry` ✅ | `window_symmetry` ✅ | PERIODIC (FFT) vs SYMMETRIC (time-domain) |
| Window normalization | `window_norm` ✅ | `window_norm` ✅ | UNITY or SQRT normalization |
| FFT scaling | `scale_policy` ✅ | `scale_policy` ✅ | NONE, ONE_OVER_N, ONE_OVER_SQRT_N |
| Output format | `output_mode` ✅ | `output_mode` ✅ | MAGNITUDE or COMPLEX |
| Warmup iterations | `warmup_iters` ✅ | `warmup_iters` ✅ | Warmup iterations for stable performance |

**Notes:**
- **Standardized naming** (as of v0.9.4): All fields use descriptive names (`window_type`, `scale_policy`, `output_mode`)
- Enums are identical between Python and C++ (same values)

### Optimization Parameters (StageConfig Only)

| Field | StageConfig | Description |
|-------|-------------|-------------|
| `preload_window` | ✅ | Precompute window coefficients in device memory (optimization) |
| `inplace` | ✅ | Enable in-place operations hint (optimization) |

**Notes:**
- These are low-level optimization toggles for custom stage development
- Not exposed in EngineConfig (defaults are already optimal)

### Execution Control (EngineConfig Only)

| Field | EngineConfig | Description |
|-------|--------------|-------------|
| `mode` | ✅ | ExecutionMode.BATCH or ExecutionMode.STREAMING |
| `stream_count` | ✅ | Number of CUDA streams for pipelining (1-32) |
| `pinned_buffer_count` | ✅ | Number of pinned memory buffers (min 2) |
| `device_id` | ✅ | CUDA device ID (-1 for auto-select) |

**Notes:**
- Controls how the engine executes the pipeline
- Not relevant for individual stages (StageConfig)

### Performance Tuning (EngineConfig Only)

| Field | EngineConfig | Description |
|-------|--------------|-------------|
| `timeout_ms` | ✅ | Timeout for operations in milliseconds |
| `use_cuda_graphs` | ✅ | Enable CUDA graphs for optimized execution |
| `enable_profiling` | ✅ | Enable internal profiling and metrics collection |
| `validation_mode` | ✅ | Input validation strictness (STRICT, BASIC, DISABLED) |

**Notes:**
- Advanced performance tuning and debugging features
- Only available at engine level

---

## Computed Properties

Both configs provide computed properties for convenience:

### EngineConfig Properties

```python
config = EngineConfig(nfft=2048, overlap=0.75, sample_rate_hz=48000)

config.hop_size                # 512 (nfft * (1 - overlap))
config.num_output_bins         # 1025 (nfft // 2 + 1)
config.frame_duration_ms       # 42.67 ms
config.hop_duration_ms         # 10.67 ms
config.effective_fps           # 93.75 frames/sec
config.memory_estimate_mb      # Estimated memory usage
```

### StageConfig Methods

```python
config = _native.StageConfig()
config.nfft = 2048
config.overlap = 0.75

config.hop_size()  # 512 (nfft * (1 - overlap))
```

---

## When to Use Each Config

### Use EngineConfig When:

✅ **Running experiments** (benchmark scripts with Hydra configs)
✅ **Production signal processing** (standard pipelines)
✅ **Prototyping new configurations** (Pydantic validation catches errors)
✅ **Need execution control** (batch vs streaming, device selection)
✅ **Want high-level API** (ergonomic, well-documented)

**Example use cases:**
- Ionosphere VLF/ULF detection experiments
- Real-time streaming spectrograms
- Batch processing of signal archives
- Performance benchmarking

### Use StageConfig When:

✅ **Building custom pipeline stages** (Phase 1/2 multi-speed integration)
✅ **Need per-stage configuration** (different settings for each stage)
✅ **Require optimization toggles** (preload_window, inplace)
✅ **Working at C++ level** (direct binding access)

**Example use cases:**
- Custom demodulation stages with different FFT sizes
- Multi-scale analysis with per-stage window functions
- Optimization ablation studies (toggling preload_window)
- Low-level pipeline research

---

## Common Patterns

### Pattern 1: Quick Configuration Override

```python
from sigtekx import EngineConfig, WindowType

# Start with defaults, override specific fields
config = EngineConfig()
config.nfft = 8192
config.window_type = WindowType.BLACKMAN
config.overlap = 0.875
```

### Pattern 2: Full Custom Configuration

```python
from sigtekx import EngineConfig, WindowType, WindowSymmetry, ScalePolicy

config = EngineConfig(
    nfft=4096,
    channels=8,
    overlap=0.75,
    sample_rate_hz=100000,
    window_type=WindowType.BLACKMAN,
    window_symmetry=WindowSymmetry.PERIODIC,
    scale_policy=ScalePolicy.ONE_OVER_N,
    mode=ExecutionMode.STREAMING,
)
```

### Pattern 3: Using Presets

```python
from sigtekx import get_preset

# Start from preset, then customize
config = get_preset('iono')  # Returns EngineConfig
config.channels = 8           # Override specific field
config.overlap = 0.9          # Adjust for your use case
```

### Pattern 4: Hydra Integration (Experiments)

```yaml
# experiments/conf/experiment/my_experiment.yaml
defaults:
  - override /engine: ionosphere_hires

engine:
  nfft: 8192
  channels: 8
  overlap: 0.75
  window_type: BLACKMAN
  window_symmetry: PERIODIC
  scale_policy: ONE_OVER_N
  mode: STREAMING
```

```python
# benchmarks/run_my_experiment.py
@hydra.main(config_path="../experiments/conf", config_name="config")
def main(cfg: DictConfig):
    engine_cfg = EngineConfig(**cfg.engine)
    # ... run experiment
```

---

## Field Name History (Breaking Changes)

### v0.9.4+ (Current)

**Standardized to descriptive names:**
- ✅ `window_type` (was `window` in v0.9.3)
- ✅ `scale_policy` (was `scale` in v0.9.3)
- ✅ `output_mode` (was `output` in v0.9.3)

**Rationale:**
- Consistency with C++ API (StageConfig)
- Clearer intent (avoids ambiguity)
- No users yet, so breaking changes acceptable

**Migration from v0.9.3:**
```python
# OLD (v0.9.3)
config.window = WindowType.HANN
config.scale = ScalePolicy.ONE_OVER_N
config.output = OutputMode.MAGNITUDE

# NEW (v0.9.4+)
config.window_type = WindowType.HANN
config.scale_policy = ScalePolicy.ONE_OVER_N
config.output_mode = OutputMode.MAGNITUDE
```

---

## Enum Reference

All enums are available from both Python and C++:

### WindowType

```python
from sigtekx import WindowType

WindowType.RECTANGULAR  # No taper (rectangular window)
WindowType.HANN         # Hann window (raised cosine)
WindowType.BLACKMAN     # Blackman window (higher sidelobe suppression)
```

**Use case:** Choose based on frequency resolution vs sidelobe suppression tradeoff.

### WindowSymmetry

```python
from sigtekx import WindowSymmetry

WindowSymmetry.PERIODIC   # FFT-optimized (denominator N), default for spectral analysis
WindowSymmetry.SYMMETRIC  # Time-domain (denominator N-1), for FIR filter design
```

**Use case:** Use PERIODIC (default) for FFT/STFT. Use SYMMETRIC for filter coefficient windowing.

**See also:** CLAUDE.md section "Window Function Symmetry Modes" for mathematical formulas.

### WindowNorm

```python
from sigtekx import WindowNorm

WindowNorm.UNITY  # Normalize to unity power/energy gain (default)
WindowNorm.SQRT   # Apply square root normalization
```

**Use case:** Controls how window coefficients are normalized.

### ScalePolicy

```python
from sigtekx import ScalePolicy

ScalePolicy.NONE           # No scaling (raw FFT output)
ScalePolicy.ONE_OVER_N     # Divide by N (preserves energy, default)
ScalePolicy.ONE_OVER_SQRT_N # Divide by sqrt(N) (unitary transform)
```

**Use case:**
- Use `ONE_OVER_N` (default) for energy-preserving spectral analysis
- Use `ONE_OVER_SQRT_N` for unitary transforms
- Use `NONE` for custom normalization

### OutputMode

```python
from sigtekx import OutputMode

OutputMode.MAGNITUDE  # Output sqrt(re^2 + im^2) (default)
OutputMode.COMPLEX    # Output complex FFT [re, im]
```

**Use case:**
- Use `MAGNITUDE` for spectrograms and amplitude spectra
- Use `COMPLEX` when you need phase information

### ExecutionMode (EngineConfig only)

```python
from sigtekx import ExecutionMode

ExecutionMode.BATCH      # Process complete batches with maximum throughput
ExecutionMode.STREAMING  # Continuous processing with low latency (v0.9.4+)
```

**Use case:**
- Use `BATCH` for offline processing of complete datasets
- Use `STREAMING` for real-time signal analysis

---

## Validation and Error Handling

### EngineConfig Validation

EngineConfig uses Pydantic validation to catch errors early:

```python
# ✅ Valid configuration
config = EngineConfig(nfft=2048, overlap=0.5)

# ❌ Invalid: nfft not a power of 2
config = EngineConfig(nfft=2000)  # ValueError: nfft must be a power of 2

# ❌ Invalid: overlap out of range
config = EngineConfig(overlap=1.5)  # ValidationError: overlap must be [0.0, 1.0)

# ❌ Invalid: typo in field name
config = EngineConfig(nfft=2048, overlapp=0.5)  # ValidationError: extra fields not permitted
```

**Benefits:**
- Errors caught immediately (not during execution)
- Clear error messages
- Type checking and IDE autocomplete

### StageConfig Validation

StageConfig is a C++ binding with minimal validation:

```python
config = _native.StageConfig()

# ⚠️ No validation - accepts any integer
config.nfft = 2000  # Not a power of 2, but no error until execution

# ⚠️ No validation - accepts out-of-range values
config.overlap = 1.5  # Invalid, but no error until execution
```

**Trade-off:**
- Faster (no Python overhead)
- More flexible (for advanced use)
- Less safe (errors caught later)

---

## Integration with Hydra

EngineConfig is designed to work seamlessly with Hydra configs:

### YAML Configuration

```yaml
# experiments/conf/engine/my_config.yaml
nfft: 4096
channels: 8
overlap: 0.75
sample_rate_hz: 100000
window_type: BLACKMAN
window_symmetry: PERIODIC
window_norm: UNITY
scale_policy: ONE_OVER_N
output_mode: MAGNITUDE
mode: STREAMING
stream_count: 3
device_id: 0
warmup_iters: 10
```

### Python Script

```python
import hydra
from omegaconf import DictConfig
from sigtekx import EngineConfig, Engine

@hydra.main(config_path="../experiments/conf", config_name="config")
def main(cfg: DictConfig):
    # Convert Hydra config to EngineConfig
    engine_cfg = EngineConfig(**cfg.engine)

    # Use with Engine
    engine = Engine(config=engine_cfg)
    # ... run experiment

if __name__ == "__main__":
    main()
```

### Parameter Sweeps

```yaml
# experiments/conf/experiment/resolution_sweep.yaml
defaults:
  - override /engine: ionosphere_base

# Hydra multirun sweep
engine.nfft: 1024, 2048, 4096, 8192
engine.overlap: 0.5, 0.75, 0.875
```

```bash
python benchmarks/run_latency.py --multirun \
  experiment=resolution_sweep \
  +benchmark=latency
```

---

## FAQ

### Q: Which config should I use for my ionosphere experiments?

**A:** Use `EngineConfig`. It has all the toggles you need (window_symmetry, scale_policy, output_mode, etc.) and integrates with Hydra configs.

### Q: Can I convert between EngineConfig and StageConfig?

**A:** Not directly. The Engine internally converts EngineConfig to C++ ExecutorConfig/SignalConfig, which then creates StageConfigs for each pipeline stage. This is handled automatically.

### Q: Why do some fields have different names?

**A:** As of v0.9.4, all common fields use the same names. Previously (v0.9.3), EngineConfig used short names (`window`, `scale`, `output`) while StageConfig used descriptive names. This was standardized for consistency.

### Q: Do I need to worry about StageConfig for my research?

**A:** Not for Phase 0. Use `EngineConfig` for all experiments and benchmarks. StageConfig is only needed when building custom pipeline stages (Phase 1/2).

### Q: Can I toggle optimization flags like preload_window in experiments?

**A:** Not directly via EngineConfig (those fields aren't exposed). For optimization ablation studies, you'll need to modify the C++ code or wait for Phase 1/2 custom stage support.

### Q: How do I know if my configuration is valid?

**A:** With `EngineConfig`, Pydantic validates immediately:
```python
try:
    config = EngineConfig(nfft=2000)  # Invalid
except ValueError as e:
    print(f"Config error: {e}")
```

With `StageConfig`, validation happens at execution time (less safe).

---

## See Also

- **CLAUDE.md** - Development workflow and CLI usage
- **docs/reference/api-reference.md** - Complete API documentation
- **docs/benchmarking/** - Running experiments with Hydra
- **experiments/conf/** - Example Hydra configuration files
- **Window Symmetry Modes** - CLAUDE.md section for mathematical details

---

## Changelog

### v0.9.4 (2026-01-01)
- ✅ Standardized field names across EngineConfig and StageConfig
- ✅ Renamed `window` → `window_type`, `scale` → `scale_policy`, `output` → `output_mode`
- ✅ Added complete StageConfig Python bindings (12 fields)
- ✅ Created comprehensive configuration guide

### v0.9.3
- Initial EngineConfig with short field names
- StageConfig C++ bindings (partial)
