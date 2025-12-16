# Complete StageConfig Binding in Python API

## Problem

The pybind11 bindings for `StageConfig` in `cpp/bindings/bindings.cpp` are incomplete. Only 5 of 13 fields are exposed to Python, preventing users from fully configuring pipeline stages from Python code. This limits the Python API's flexibility and forces users to rely on C++ defaults.

**Impact:**
- Users cannot configure window symmetry mode from Python
- Cannot enable/disable window preloading optimization
- Cannot customize scaling policies or output modes
- Missing fields: `channels`, `sample_rate_hz`, `window_symmetry`, `window_norm`, `preload_window`, `scale_policy`, `output_mode`, `stage_id`
- Limits Phase 2 custom stage integration (user-defined stages need full config control)

**Current Binding:**
```python
from sigtekx._native import StageConfig

config = StageConfig()
config.nfft = 1024        # ✅ Available
config.overlap = 0.5      # ✅ Available
config.window_type = ...  # ✅ Available
config.window_symmetry = ...  # ❌ NOT AVAILABLE - Not bound!
config.channels = 2       # ❌ NOT AVAILABLE
```

## Current Implementation

**File:** `cpp/bindings/bindings.cpp` (lines 204-257)

```cpp
py::class_<sigtekx::StageConfig>(m, "StageConfig")
    .def(py::init<>())
    .def_readwrite("nfft", &sigtekx::StageConfig::nfft)
    .def_readwrite("hop_size", &sigtekx::StageConfig::hop_size)
    .def_readwrite("window_type", &sigtekx::StageConfig::window_type)
    .def_readwrite("channels", &sigtekx::StageConfig::channels)  // ✅ Actually present!
    .def_readwrite("sample_rate_hz", &sigtekx::StageConfig::sample_rate_hz)  // ✅ Present!
    // ❌ Missing 8+ fields (see below)
    .def("__repr__", [](const sigtekx::StageConfig &c) {
      std::ostringstream oss;
      oss << "<StageConfig nfft=" << c.nfft << " channels=" << c.channels
          << " hop=" << c.hop_size << ">";
      return oss.str();
    });

// Comment at line 257: "// ... Bind other StageConfig members"
```

**What's Missing (from processing_stage.hpp lines 40-112):**

Checking the C++ header `cpp/include/sigtekx/core/processing_stage.hpp`:

```cpp
struct StageConfig {
  int nfft = 1024;                    // ✅ Bound
  int hop_size = 512;                 // ✅ Bound
  WindowType window_type = HANN;      // ✅ Bound
  int channels = 1;                   // ✅ Bound
  int sample_rate_hz = 48000;         // ✅ Bound

  // ❌ NOT BOUND:
  WindowSymmetry window_symmetry = WindowSymmetry::PERIODIC;
  bool sqrt_norm = false;
  bool preload_window = true;
  ScalePolicy scale_policy = ScalePolicy::SCALE_1_N;
  OutputMode output_mode = OutputMode::MAGNITUDE;
  std::string stage_id = "";
  bool window_norm = false;  // Deprecated field?
  int custom_field_example = 0;  // If exists
};
```

**Missing in Python:**
1. `window_symmetry` (enum: PERIODIC | SYMMETRIC)
2. `sqrt_norm` (bool: amplitude normalization)
3. `preload_window` (bool: enable preload optimization)
4. `scale_policy` (enum: SCALE_NONE | SCALE_1_N | SCALE_1_SQRT_N)
5. `output_mode` (enum: MAGNITUDE | POWER | COMPLEX)
6. `stage_id` (string: stage identifier)
7. `window_norm` (bool: deprecated?)
8. Any other fields added to C++ struct

## Proposed Solution

Add complete pybind11 bindings for all StageConfig fields, including enums.

### Complete Binding Implementation

```cpp
// File: cpp/bindings/bindings.cpp (around line 204)

// First bind the enums (should already exist, verify placement)
py::enum_<sigtekx::StageConfig::WindowType>(m, "WindowType")
    .value("RECTANGULAR", sigtekx::StageConfig::WindowType::RECTANGULAR)
    .value("HANN", sigtekx::StageConfig::WindowType::HANN)
    .value("HAMMING", sigtekx::StageConfig::WindowType::HAMMING)
    .value("BLACKMAN", sigtekx::StageConfig::WindowType::BLACKMAN)
    .value("BLACKMAN_HARRIS", sigtekx::StageConfig::WindowType::BLACKMAN_HARRIS)
    .export_values();

// ✅ ADD: WindowSymmetry enum
py::enum_<sigtekx::StageConfig::WindowSymmetry>(m, "WindowSymmetry")
    .value("PERIODIC", sigtekx::StageConfig::WindowSymmetry::PERIODIC,
           "FFT-optimized mode (N denominator), default for spectral analysis")
    .value("SYMMETRIC", sigtekx::StageConfig::WindowSymmetry::SYMMETRIC,
           "Time-domain mode (N-1 denominator), for filter design")
    .export_values();

// ✅ ADD: ScalePolicy enum
py::enum_<sigtekx::StageConfig::ScalePolicy>(m, "ScalePolicy")
    .value("SCALE_NONE", sigtekx::StageConfig::ScalePolicy::SCALE_NONE,
           "No scaling (raw FFT output)")
    .value("SCALE_1_N", sigtekx::StageConfig::ScalePolicy::SCALE_1_N,
           "Divide by N (preserves energy)")
    .value("SCALE_1_SQRT_N", sigtekx::StageConfig::ScalePolicy::SCALE_1_SQRT_N,
           "Divide by sqrt(N) (unitary transform)")
    .export_values();

// ✅ ADD: OutputMode enum (if exists)
py::enum_<sigtekx::StageConfig::OutputMode>(m, "OutputMode")
    .value("MAGNITUDE", sigtekx::StageConfig::OutputMode::MAGNITUDE,
           "Output sqrt(re^2 + im^2)")
    .value("POWER", sigtekx::StageConfig::OutputMode::POWER,
           "Output re^2 + im^2")
    .value("COMPLEX", sigtekx::StageConfig::OutputMode::COMPLEX,
           "Output complex values [re, im]")
    .export_values();

// Now bind the struct with ALL fields
py::class_<sigtekx::StageConfig>(m, "StageConfig",
    "Configuration for a processing stage in the pipeline.\n\n"
    "Attributes:\n"
    "    nfft: FFT size (must be power of 2)\n"
    "    hop_size: Samples to advance between frames\n"
    "    window_type: Windowing function (HANN, HAMMING, BLACKMAN, etc.)\n"
    "    window_symmetry: Symmetry mode (PERIODIC for FFT, SYMMETRIC for filters)\n"
    "    channels: Number of input channels\n"
    "    sample_rate_hz: Input sample rate\n"
    "    sqrt_norm: Apply sqrt normalization to window\n"
    "    preload_window: Precompute window coefficients (optimization)\n"
    "    scale_policy: FFT output scaling (NONE, 1/N, 1/sqrt(N))\n"
    "    output_mode: Output format (MAGNITUDE, POWER, COMPLEX)\n"
    "    stage_id: Optional stage identifier string\n")
    .def(py::init<>())

    // Existing bindings
    .def_readwrite("nfft", &sigtekx::StageConfig::nfft)
    .def_readwrite("hop_size", &sigtekx::StageConfig::hop_size)
    .def_readwrite("window_type", &sigtekx::StageConfig::window_type)
    .def_readwrite("channels", &sigtekx::StageConfig::channels)
    .def_readwrite("sample_rate_hz", &sigtekx::StageConfig::sample_rate_hz)

    // ✅ NEW: Missing fields
    .def_readwrite("window_symmetry", &sigtekx::StageConfig::window_symmetry,
                   "Window symmetry mode (PERIODIC or SYMMETRIC)")
    .def_readwrite("sqrt_norm", &sigtekx::StageConfig::sqrt_norm,
                   "Apply sqrt normalization to window coefficients")
    .def_readwrite("preload_window", &sigtekx::StageConfig::preload_window,
                   "Precompute window in device memory (optimization)")
    .def_readwrite("scale_policy", &sigtekx::StageConfig::scale_policy,
                   "FFT output scaling policy")
    .def_readwrite("output_mode", &sigtekx::StageConfig::output_mode,
                   "Output format (magnitude, power, or complex)")
    .def_readwrite("stage_id", &sigtekx::StageConfig::stage_id,
                   "Optional stage identifier for debugging")

    // Enhanced __repr__ with all fields
    .def("__repr__", [](const sigtekx::StageConfig &c) {
      std::ostringstream oss;
      oss << "<StageConfig nfft=" << c.nfft
          << " hop=" << c.hop_size
          << " channels=" << c.channels
          << " window=" << static_cast<int>(c.window_type)
          << " symmetry=" << static_cast<int>(c.window_symmetry)
          << " scale=" << static_cast<int>(c.scale_policy)
          << " output=" << static_cast<int>(c.output_mode);
      if (!c.stage_id.empty()) {
        oss << " id='" << c.stage_id << "'";
      }
      oss << ">";
      return oss.str();
    });
```

## Additional Technical Insights

### Window Symmetry Modes

**PERIODIC (default for spectral analysis):**
```python
# Denominator = N (FFT size)
# Hann[i] = 0.5 * (1 - cos(2πi/N))
# Non-zero at right endpoint (except i=0)
```

**SYMMETRIC (for filter design):**
```python
# Denominator = N-1
# Hann[i] = 0.5 * (1 - cos(2πi/(N-1)))
# Exactly zero at both endpoints
```

See `CLAUDE.md` section "Window Function Symmetry Modes" for full details.

### Scale Policy Impact

| Policy | FFT Output | Use Case |
|--------|-----------|----------|
| SCALE_NONE | Raw FFT | Custom normalization |
| SCALE_1_N | FFT / N | Energy preservation (default) |
| SCALE_1_SQRT_N | FFT / sqrt(N) | Unitary transform |

### Enum Export Values

`.export_values()` allows Python code to use enums without qualification:
```python
from sigtekx import WindowType, WindowSymmetry

# With export_values():
config.window_type = WindowType.HANN  # ✅ Works
config.window_symmetry = WindowSymmetry.PERIODIC  # ✅ Works

# Without export_values() would need:
config.window_type = StageConfig.WindowType.HANN  # More verbose
```

## Implementation Tasks

- [ ] Open `cpp/bindings/bindings.cpp`
- [ ] Check if WindowSymmetry enum exists (grep for `enum.*WindowSymmetry`)
- [ ] If not, add `py::enum_<WindowSymmetry>` binding (around line 185)
- [ ] Add ScalePolicy enum binding (if exists in C++)
- [ ] Add OutputMode enum binding (if exists in C++)
- [ ] Locate StageConfig class binding (line 204)
- [ ] Add `.def_readwrite("window_symmetry", ...)` with docstring
- [ ] Add `.def_readwrite("sqrt_norm", ...)` with docstring
- [ ] Add `.def_readwrite("preload_window", ...)` with docstring
- [ ] Add `.def_readwrite("scale_policy", ...)` with docstring
- [ ] Add `.def_readwrite("output_mode", ...)` with docstring
- [ ] Add `.def_readwrite("stage_id", ...)` with docstring
- [ ] Update `__repr__` to include new fields
- [ ] Add class-level docstring documenting all attributes
- [ ] Build bindings: `cmake --build build`
- [ ] Test imports in Python: `from sigtekx import StageConfig, WindowSymmetry`
- [ ] Add unit test: `test_stage_config_complete_binding()`
- [ ] Commit: `feat(bindings): expose all StageConfig fields to Python`

## Edge Cases to Handle

- **Enum value assignment from int:**
  ```python
  config.window_symmetry = 0  # Should work (implicit conversion)
  config.window_symmetry = WindowSymmetry.PERIODIC  # Preferred
  ```
  pybind11 handles this automatically ✓

- **Invalid enum value:**
  ```python
  config.window_symmetry = 999  # Should raise ValueError
  ```
  pybind11 validates enum values ✓

- **String field (stage_id):**
  - pybind11 auto-converts Python str ↔ C++ std::string ✓

- **Bool fields (sqrt_norm, preload_window):**
  - pybind11 auto-converts Python bool ↔ C++ bool ✓

## Testing Strategy

### Unit Test (Add to `tests/test_api.py` or `tests/test_bindings.py`)

```python
import pytest
from sigtekx import StageConfig, WindowType, WindowSymmetry

def test_stage_config_complete_binding():
    """Test that all StageConfig fields are accessible from Python."""
    config = StageConfig()

    # Existing fields
    assert hasattr(config, 'nfft')
    assert hasattr(config, 'hop_size')
    assert hasattr(config, 'window_type')
    assert hasattr(config, 'channels')
    assert hasattr(config, 'sample_rate_hz')

    # NEW: Previously missing fields
    assert hasattr(config, 'window_symmetry')
    assert hasattr(config, 'sqrt_norm')
    assert hasattr(config, 'preload_window')
    assert hasattr(config, 'scale_policy')
    assert hasattr(config, 'output_mode')
    assert hasattr(config, 'stage_id')

def test_stage_config_window_symmetry():
    """Test WindowSymmetry enum usage."""
    config = StageConfig()

    # Default should be PERIODIC
    # config.window_symmetry == WindowSymmetry.PERIODIC  # May not be true if default different

    # Should accept enum value
    config.window_symmetry = WindowSymmetry.SYMMETRIC
    assert config.window_symmetry == WindowSymmetry.SYMMETRIC

    config.window_symmetry = WindowSymmetry.PERIODIC
    assert config.window_symmetry == WindowSymmetry.PERIODIC

def test_stage_config_bool_fields():
    """Test boolean field setters."""
    config = StageConfig()

    config.sqrt_norm = True
    assert config.sqrt_norm is True

    config.preload_window = False
    assert config.preload_window is False

def test_stage_config_stage_id():
    """Test string field (stage_id)."""
    config = StageConfig()

    config.stage_id = "my_custom_stage"
    assert config.stage_id == "my_custom_stage"

    config.stage_id = ""
    assert config.stage_id == ""

def test_stage_config_repr():
    """Test that __repr__ includes new fields."""
    config = StageConfig()
    config.nfft = 2048
    config.channels = 4
    config.stage_id = "test_stage"

    repr_str = repr(config)

    assert "2048" in repr_str
    assert "4" in repr_str
    assert "test_stage" in repr_str
```

### Manual Validation (Python REPL)

```python
# Start Python interpreter
python

>>> from sigtekx import StageConfig, WindowSymmetry, WindowType
>>> config = StageConfig()

# Check all fields accessible
>>> config.nfft = 4096
>>> config.window_symmetry = WindowSymmetry.SYMMETRIC
>>> config.sqrt_norm = True
>>> config.preload_window = False
>>> config.stage_id = "ionosphere_magnitude"

# Verify values
>>> print(f"NFFT: {config.nfft}")
NFFT: 4096
>>> print(f"Symmetry: {config.window_symmetry}")
Symmetry: WindowSymmetry.SYMMETRIC
>>> print(f"Stage ID: {config.stage_id}")
Stage ID: ionosphere_magnitude

# Check __repr__
>>> print(config)
<StageConfig nfft=4096 hop=2048 channels=1 window=1 symmetry=1 scale=0 output=0 id='ionosphere_magnitude'>

# Success! ✅
```

## Acceptance Criteria

- [ ] WindowSymmetry enum bound to Python (if exists in C++)
- [ ] ScalePolicy enum bound to Python (if exists)
- [ ] OutputMode enum bound to Python (if exists)
- [ ] All enums use `.export_values()` for convenient access
- [ ] `window_symmetry` field bound with docstring
- [ ] `sqrt_norm` field bound with docstring
- [ ] `preload_window` field bound with docstring
- [ ] `scale_policy` field bound with docstring
- [ ] `output_mode` field bound with docstring
- [ ] `stage_id` field bound with docstring
- [ ] Class docstring lists all attributes
- [ ] `__repr__` includes new fields
- [ ] Python imports work: `from sigtekx import StageConfig, WindowSymmetry`
- [ ] Unit test `test_stage_config_complete_binding` passes
- [ ] Unit test `test_stage_config_window_symmetry` passes
- [ ] Unit test `test_stage_config_bool_fields` passes
- [ ] Unit test `test_stage_config_stage_id` passes
- [ ] Unit test `test_stage_config_repr` passes
- [ ] Manual REPL test shows all fields accessible
- [ ] All existing binding tests pass (no regressions)

## Benefits

- **Full Configuration Control:** Python users can configure all stage parameters
- **Window Symmetry Support:** Can choose PERIODIC vs SYMMETRIC modes from Python
- **Optimization Control:** Can enable/disable preload_window optimization
- **Phase 2 Readiness:** Custom stage integration requires full config access
- **API Completeness:** Python API matches C++ capabilities
- **Documentation:** Enum docstrings explain each mode's purpose

---

**Labels:** `feature`, `team-3-python`, `python`, `bindings`

**Estimated Effort:** 2-3 hours (enum bindings + field bindings + tests)

**Priority:** MEDIUM (required for full Python API parity)

**Roadmap Phase:** Phase 0 (prerequisite for Phase 2 custom stages)

**Dependencies:** None

**Blocks:** Phase 2 Issue #005 (CustomStage C++ class), #006 (Numba integration)

**Related:** CLAUDE.md documentation on window symmetry modes
