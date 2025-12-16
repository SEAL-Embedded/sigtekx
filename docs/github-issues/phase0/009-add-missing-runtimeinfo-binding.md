# Add Missing RuntimeInfo Binding to Python API

## Problem

The `RuntimeInfo` struct (defined in `cpp/include/sigtekx/core/processing_stage.hpp` lines 138-142) is not exposed to Python through pybind11 bindings. This prevents Python users from querying CUDA runtime information, device capabilities, and version details that are already available in the C++ API.

**Impact:**
- Python users cannot access CUDA version information
- Device name and compute capability unavailable from Python
- Diagnostic information missing for debugging CUDA issues
- `device_info` property returns incomplete information (Issue #007)

**Current Limitation:**
```python
from sigtekx import Engine

engine = Engine(preset='default')
# Want to get runtime info:
# runtime_info = engine.get_runtime_info()  # ❌ Method exists but returns unbound type!
# print(runtime_info.cuda_version)          # ❌ AttributeError
```

## Current Implementation

**C++ Definition:**

**File:** `cpp/include/sigtekx/core/processing_stage.hpp` (lines 138-142)

```cpp
struct RuntimeInfo {
  std::string device_name;
  int cuda_version;           // e.g., 12030 for CUDA 12.3
  int cuda_runtime_version;   // Runtime API version
  int cuda_driver_version;    // Driver API version
};
```

**C++ Executor API:**

**File:** `cpp/include/sigtekx/core/pipeline_executor.hpp` (around line 132)

```cpp
class PipelineExecutor {
 public:
  virtual RuntimeInfo get_runtime_info() const = 0;
};
```

**Python Bindings Status:**

**File:** `cpp/bindings/bindings.cpp`

- `RuntimeInfo` struct: **NOT BOUND** ❌
- `get_runtime_info()` method: **Bound to executor** but returns unbound type ❌

**Evidence from engine.py (lines 764-770):**

```python
# engine.py tries to use RuntimeInfo but gets AttributeError
try:
    runtime_info = self._executor.get_runtime_info()
    info['cuda_version'] = runtime_info.cuda_version  # ❌ Fails!
except AttributeError:
    pass  # Silently ignored (Issue #007)
```

## Proposed Solution

Add complete pybind11 binding for RuntimeInfo struct with all fields.

### Implementation

**File:** `cpp/bindings/bindings.cpp` (insert before executor bindings, around line 260)

```cpp
// ✅ Bind RuntimeInfo struct
py::class_<sigtekx::RuntimeInfo>(m, "RuntimeInfo",
    "CUDA runtime and device information.\n\n"
    "Contains details about the CUDA environment and active GPU device.\n\n"
    "Attributes:\n"
    "    device_name: GPU device name (e.g., 'NVIDIA RTX 3090 Ti')\n"
    "    cuda_version: CUDA Toolkit version (e.g., 12030 for v12.3)\n"
    "    cuda_runtime_version: CUDA Runtime API version\n"
    "    cuda_driver_version: CUDA Driver API version\n\n"
    "Example:\n"
    "    >>> from sigtekx import Engine\n"
    "    >>> engine = Engine(preset='default')\n"
    "    >>> engine.initialize()\n"
    "    >>> info = engine.get_runtime_info()\n"
    "    >>> print(f'Device: {info.device_name}')\n"
    "    Device: NVIDIA RTX 3090 Ti\n"
    "    >>> print(f'CUDA: {info.cuda_version // 1000}.{(info.cuda_version % 1000) // 10}')\n"
    "    CUDA: 12.3\n")
    .def(py::init<>())

    // Read-only fields (no setters needed for runtime info)
    .def_readonly("device_name", &sigtekx::RuntimeInfo::device_name,
                  "GPU device name string")
    .def_readonly("cuda_version", &sigtekx::RuntimeInfo::cuda_version,
                  "CUDA Toolkit version (encoded as major*1000 + minor*10)")
    .def_readonly("cuda_runtime_version", &sigtekx::RuntimeInfo::cuda_runtime_version,
                  "CUDA Runtime API version")
    .def_readonly("cuda_driver_version", &sigtekx::RuntimeInfo::cuda_driver_version,
                  "CUDA Driver API version")

    // Convenience methods for version formatting
    .def_property_readonly("cuda_version_string",
                           [](const sigtekx::RuntimeInfo& info) {
                             int major = info.cuda_version / 1000;
                             int minor = (info.cuda_version % 1000) / 10;
                             return std::to_string(major) + "." + std::to_string(minor);
                           },
                           "CUDA version as formatted string (e.g., '12.3')")

    .def_property_readonly("runtime_version_string",
                           [](const sigtekx::RuntimeInfo& info) {
                             int major = info.cuda_runtime_version / 1000;
                             int minor = (info.cuda_runtime_version % 1000) / 10;
                             return std::to_string(major) + "." + std::to_string(minor);
                           },
                           "Runtime API version as formatted string")

    .def_property_readonly("driver_version_string",
                           [](const sigtekx::RuntimeInfo& info) {
                             int major = info.cuda_driver_version / 1000;
                             int minor = (info.cuda_driver_version % 1000) / 10;
                             return std::to_string(major) + "." + std::to_string(minor);
                           },
                           "Driver API version as formatted string")

    // __repr__ for debugging
    .def("__repr__", [](const sigtekx::RuntimeInfo& info) {
      std::ostringstream oss;
      int cuda_major = info.cuda_version / 1000;
      int cuda_minor = (info.cuda_version % 1000) / 10;
      oss << "<RuntimeInfo device='" << info.device_name
          << "' cuda=" << cuda_major << "." << cuda_minor << ">";
      return oss.str();
    });

// Executor bindings already have get_runtime_info() - will now return bound type! ✅
```

**Note:** The executor bindings already expose `get_runtime_info()` method (lines 285, 302 in bindings.cpp). Once `RuntimeInfo` is bound, those methods will automatically work.

## Additional Technical Insights

### CUDA Version Encoding

CUDA versions are encoded as integers:
```cpp
// CUDA 12.3.0:
cuda_version = 12030
// Decode:
major = cuda_version / 1000        // 12
minor = (cuda_version % 1000) / 10 // 3
patch = cuda_version % 10          // 0
```

**Python helper property** (provided in binding):
```python
>>> info.cuda_version
12030
>>> info.cuda_version_string
'12.3'
```

### Read-Only vs Read-Write

RuntimeInfo fields are **read-only** (`.def_readonly()`) because:
- Runtime info is queried from CUDA, not user-configurable
- Modifying these values would be meaningless
- Prevents accidental mutation

StageConfig fields are **read-write** (`.def_readwrite()`) because:
- User configures pipeline parameters
- Needs to be mutable

### Version String Formatters

The `_string` properties use lambda functions to format versions:
```cpp
.def_property_readonly("cuda_version_string",
    [](const RuntimeInfo& info) {
        int major = info.cuda_version / 1000;
        int minor = (info.cuda_version % 1000) / 10;
        return std::to_string(major) + "." + std::to_string(minor);
    })
```

This is **read-only property** (not a field), computed on access.

### Integration with device_info (Issue #007 Fix)

Once RuntimeInfo is bound, `engine.py` can use it:

```python
# engine.py (lines 764-770) - AFTER fix
if self._executor and self.is_initialized:
    try:
        runtime_info = self._executor.get_runtime_info()  # ✅ Now works!
        info['cuda_version'] = runtime_info.cuda_version_string
        info['device_name'] = runtime_info.device_name
        info['runtime_version'] = runtime_info.runtime_version_string
        info['driver_version'] = runtime_info.driver_version_string
    except Exception as e:
        logger.debug(f"Could not retrieve runtime info: {e}")
```

## Implementation Tasks

- [ ] Open `cpp/bindings/bindings.cpp`
- [ ] Locate appropriate insertion point (before executor bindings, around line 260)
- [ ] Add `py::class_<RuntimeInfo>` binding with class docstring
- [ ] Add `.def(py::init<>())` default constructor
- [ ] Add `.def_readonly("device_name", ...)` with docstring
- [ ] Add `.def_readonly("cuda_version", ...)` with docstring
- [ ] Add `.def_readonly("cuda_runtime_version", ...)` with docstring
- [ ] Add `.def_readonly("cuda_driver_version", ...)` with docstring
- [ ] Add `.def_property_readonly("cuda_version_string", ...)` lambda
- [ ] Add `.def_property_readonly("runtime_version_string", ...)` lambda
- [ ] Add `.def_property_readonly("driver_version_string", ...)` lambda
- [ ] Add `.__repr__()` method for debugging
- [ ] Build bindings: `cmake --build build`
- [ ] Test import: `from sigtekx import RuntimeInfo`
- [ ] Add unit test: `test_runtime_info_binding()`
- [ ] Add integration test: `test_engine_get_runtime_info()`
- [ ] Commit: `feat(bindings): expose RuntimeInfo struct to Python`

## Edge Cases to Handle

- **Executor not initialized:**
  ```python
  engine = Engine(preset='default')
  # engine.initialize() NOT called
  info = engine.get_runtime_info()  # May fail in C++
  ```
  - C++ executor should handle this (return empty or throw)
  - Python should catch exception (handled in Issue #007 fix)

- **Device query failure:**
  - If CUDA can't query device name, fields may be empty strings or 0
  - `__repr__` should handle gracefully

- **Multiple devices:**
  - RuntimeInfo reflects the active device (device_index in config)
  - No issue - each engine has its own RuntimeInfo

## Testing Strategy

### Unit Test (Add to `tests/test_bindings.py` or `tests/test_api.py`)

```python
import pytest
from sigtekx import Engine, RuntimeInfo

def test_runtime_info_binding():
    """Test that RuntimeInfo is accessible from Python."""
    # Create engine and initialize to populate runtime info
    with Engine(preset='default') as engine:
        info = engine.get_runtime_info()

        # Should be RuntimeInfo instance
        assert isinstance(info, RuntimeInfo)

        # All fields should be present
        assert hasattr(info, 'device_name')
        assert hasattr(info, 'cuda_version')
        assert hasattr(info, 'cuda_runtime_version')
        assert hasattr(info, 'cuda_driver_version')

        # Version string properties should exist
        assert hasattr(info, 'cuda_version_string')
        assert hasattr(info, 'runtime_version_string')
        assert hasattr(info, 'driver_version_string')

def test_runtime_info_version_formatting():
    """Test that version string formatters work correctly."""
    with Engine(preset='default') as engine:
        info = engine.get_runtime_info()

        # Version should be integer
        assert isinstance(info.cuda_version, int)
        assert info.cuda_version > 0

        # String should be formatted as "major.minor"
        assert isinstance(info.cuda_version_string, str)
        assert '.' in info.cuda_version_string

        # Decode manually and check consistency
        major = info.cuda_version // 1000
        minor = (info.cuda_version % 1000) // 10
        expected_string = f"{major}.{minor}"
        assert info.cuda_version_string == expected_string

def test_runtime_info_device_name():
    """Test that device name is populated."""
    with Engine(preset='default') as engine:
        info = engine.get_runtime_info()

        # Device name should be non-empty string
        assert isinstance(info.device_name, str)
        assert len(info.device_name) > 0
        # Should contain "NVIDIA" (assuming NVIDIA GPU)
        assert 'NVIDIA' in info.device_name or 'nvidia' in info.device_name.lower()

def test_runtime_info_repr():
    """Test RuntimeInfo __repr__ method."""
    with Engine(preset='default') as engine:
        info = engine.get_runtime_info()

        repr_str = repr(info)

        assert '<RuntimeInfo' in repr_str
        assert 'device=' in repr_str
        assert 'cuda=' in repr_str
        assert info.device_name in repr_str

def test_runtime_info_fields_readonly():
    """Test that RuntimeInfo fields are read-only."""
    with Engine(preset='default') as engine:
        info = engine.get_runtime_info()

        # Attempting to modify should raise AttributeError
        with pytest.raises(AttributeError):
            info.device_name = "Modified"

        with pytest.raises(AttributeError):
            info.cuda_version = 99999
```

### Integration Test with device_info (Requires Issue #007 fix)

```python
def test_engine_device_info_includes_runtime():
    """Test that device_info property includes RuntimeInfo fields."""
    with Engine(preset='default') as engine:
        device_info = engine.device_info

        # After Issue #007 + #009 fixes, should include runtime info
        if 'error' not in device_info:
            assert 'cuda_version' in device_info
            assert 'device_name' in device_info
            assert 'runtime_version' in device_info
            assert 'driver_version' in device_info
```

### Manual Verification (Python REPL)

```python
# Start Python interpreter
python

>>> from sigtekx import Engine
>>> engine = Engine(preset='default')
>>> engine.initialize()

>>> info = engine.get_runtime_info()
>>> print(info)
<RuntimeInfo device='NVIDIA RTX 3090 Ti' cuda=12.3>

>>> print(f"Device: {info.device_name}")
Device: NVIDIA RTX 3090 Ti

>>> print(f"CUDA Toolkit: {info.cuda_version_string}")
CUDA Toolkit: 12.3

>>> print(f"Runtime API: {info.runtime_version_string}")
Runtime API: 12.3

>>> print(f"Driver API: {info.driver_version_string}")
Driver API: 12.5

# Raw integer values
>>> print(f"CUDA version (raw): {info.cuda_version}")
CUDA version (raw): 12030

# Verify read-only
>>> info.cuda_version = 99999
AttributeError: can't set attribute

# Success! ✅
```

## Acceptance Criteria

- [ ] `RuntimeInfo` struct bound to Python
- [ ] All four fields bound as read-only: `device_name`, `cuda_version`, `cuda_runtime_version`, `cuda_driver_version`
- [ ] Version string formatters added as properties: `cuda_version_string`, `runtime_version_string`, `driver_version_string`
- [ ] `__repr__` method implemented with device and CUDA version
- [ ] Class docstring includes all attributes and usage example
- [ ] Python import works: `from sigtekx import RuntimeInfo`
- [ ] Unit test `test_runtime_info_binding` passes
- [ ] Unit test `test_runtime_info_version_formatting` passes
- [ ] Unit test `test_runtime_info_device_name` passes
- [ ] Unit test `test_runtime_info_repr` passes
- [ ] Unit test `test_runtime_info_fields_readonly` passes
- [ ] Integration test with `device_info` passes (after Issue #007 fix)
- [ ] Manual REPL test shows all fields accessible
- [ ] All existing binding tests pass (no regressions)

## Benefits

- **Complete Diagnostic Info:** Python users can query CUDA version and device details
- **Debugging Aid:** Version mismatches easily detectable from Python
- **API Completeness:** Python API now matches C++ for runtime queries
- **Issue #007 Enabler:** `device_info` property can now populate full info
- **User Experience:** Version string formatters make info human-readable
- **Production Monitoring:** Can log CUDA environment details for support

---

**Labels:** `feature`, `team-3-python`, `python`, `bindings`

**Estimated Effort:** 1-2 hours (struct binding + formatters + tests)

**Priority:** MEDIUM (nice to have, enables full diagnostic info)

**Roadmap Phase:** Phase 0 (recommended before Phase 1)

**Dependencies:** None

**Blocks:** None

**Related:** Issue #007 (device_info silent fallback fix)
