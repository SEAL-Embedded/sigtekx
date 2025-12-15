# Add Numba Integration for Custom CUDA Kernels in Python (Phase 2 Task 2.2)

## Problem

Python users **cannot inject custom CUDA kernels into pipelines**. There is no bridge between `@cuda.jit` decorated functions (Numba) and the C++ `CustomStage` class. This blocks the **core value proposition** of SigTekX: "Python flexibility without sacrificing real-time performance."

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 2 Task 2.2):
- **THE CORE NOVELTY**: Enable Python users to add custom DSP algorithms without C++ knowledge
- Target overhead: <10µs for custom Numba stages
- Critical for v1.0 methods paper: demonstrate Python ease-of-use with real-time guarantees
- Competitive moat: No other Python GPU DSP library offers this

**Impact:**
- Scientists must write C++ code to add custom algorithms (defeats purpose)
- Cannot demonstrate core innovation in paper
- No advantage over CuPy/NumPy (Python-only, but no pipeline extensibility)
- Cannot claim "Python ease without sacrificing real-time"

## Current Implementation

**File:** `src/sigtekx/core/builder.py` (lines 45-75)

```python
class PipelineBuilder:
    def __init__(self):
        self._stages = []

    def add_window(self, window_type: str) -> Self:
        self._stages.append({'type': 'window', 'window_type': window_type})
        return self

    def add_fft(self) -> Self:
        self._stages.append({'type': 'fft'})
        return self

    def add_magnitude(self) -> Self:
        self._stages.append({'type': 'magnitude'})
        return self

    # NO add_custom() method - hardcoded stages only!
```

**Why Numba integration doesn't exist:**
- No mechanism to extract `CUfunction` pointer from Numba
- No Python → C++ bridge for kernel binding
- `PipelineBuilder` is cosmetic (doesn't control actual C++ pipeline construction)

## Proposed Solution

**Create Numba → C++ bridge with `NumbaStageAdapter`:**

```python
# src/sigtekx/stages/custom.py (NEW FILE)
"""Custom stage integration for Numba CUDA kernels."""

from typing import Callable, Optional
import numpy as np

try:
    from numba import cuda
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False


class NumbaStageAdapter:
    """Adapter to extract CUfunction pointer from Numba @cuda.jit kernels."""

    def __init__(self, kernel_func: Callable, workspace_mb: float = 0):
        """
        Initialize adapter for Numba CUDA kernel.

        Args:
            kernel_func: Numba @cuda.jit decorated function
            workspace_mb: Persistent state buffer size in MB (default: 0)

        Raises:
            ImportError: If Numba is not installed
            TypeError: If kernel_func is not a Numba CUDA kernel
        """
        if not NUMBA_AVAILABLE:
            raise ImportError(
                "Numba is not installed. Install with: pip install numba>=0.58"
            )

        # Validate kernel is Numba CUDA function
        if not hasattr(kernel_func, 'driver_function'):
            raise TypeError(
                f"{kernel_func.__name__} is not a Numba CUDA kernel. "
                "Decorate with @cuda.jit"
            )

        # Extract CUfunction pointer from Numba internals
        # kernel_func.driver_function.handle.value is a CUfunction (void*)
        self.cu_function = kernel_func.driver_function.handle.value

        # Convert workspace from MB to bytes
        self.workspace_bytes = int(workspace_mb * 1024 * 1024)

        # Store kernel for inspection
        self._kernel = kernel_func

    def __repr__(self) -> str:
        return (
            f"NumbaStageAdapter(kernel={self._kernel.__name__}, "
            f"cu_function=0x{self.cu_function:x}, "
            f"workspace={self.workspace_bytes} bytes)"
        )
```

```python
# src/sigtekx/core/builder.py (ENHANCED)
from sigtekx.stages.custom import NumbaStageAdapter

class PipelineBuilder:
    # ... existing methods ...

    def add_custom(self,
                   kernel_func: Callable,
                   grid: tuple[int, int, int] = (1, 1, 1),
                   block: tuple[int, int, int] = (256, 1, 1),
                   workspace_mb: float = 0) -> Self:
        """
        Add custom CUDA kernel stage to pipeline.

        Args:
            kernel_func: Numba @cuda.jit decorated function
            grid: Grid dimensions (x, y, z)
            block: Block dimensions (x, y, z)
            workspace_mb: Persistent state buffer size in MB

        Returns:
            Self for method chaining

        Example:
            >>> from numba import cuda
            >>> @cuda.jit
            >>> def my_filter(input, output, n):
            >>>     i = cuda.grid(1)
            >>>     if i < n:
            >>>         output[i] = input[i] * 0.9  # Simple gain
            >>>
            >>> pipeline = (PipelineBuilder()
            >>>     .add_window('hann')
            >>>     .add_fft()
            >>>     .add_custom(my_filter, grid=(128, 1, 1), block=(256, 1, 1))
            >>>     .add_magnitude()
            >>>     .build())
        """
        # Extract CUfunction pointer via adapter
        adapter = NumbaStageAdapter(kernel_func, workspace_mb)

        # Add to stage list for C++ binding
        self._stages.append({
            'type': 'custom',
            'kernel_ptr': adapter.cu_function,  # Pass to C++ as CUfunction
            'grid': grid,
            'block': block,
            'workspace_bytes': adapter.workspace_bytes
        })

        return self
```

```cpp
// cpp/bindings/bindings.cpp (ENHANCED)
#include <pybind11/pybind11.h>
#include "sigtekx/core/custom_stage.hpp"

namespace py = pybind11;

PYBIND11_MODULE(_sigtekx, m) {
    // ... existing bindings ...

    // Expose CustomStage to Python
    py::class_<CustomStage, ProcessingStage, std::shared_ptr<CustomStage>>(m, "CustomStage")
        .def(py::init<CUfunction, dim3, dim3, size_t>(),
             py::arg("kernel_func"),
             py::arg("grid"),
             py::arg("block"),
             py::arg("workspace_bytes") = 0)
        .def("get_state_ptr", &CustomStage::get_state_ptr);

    // Helper to create CustomStage from Python dict
    m.def("create_custom_stage", [](py::dict stage_info) {
        // Extract CUfunction pointer (passed as uintptr_t from Python)
        auto kernel_ptr = stage_info["kernel_ptr"].cast<uintptr_t>();
        CUfunction kernel_func = reinterpret_cast<CUfunction>(kernel_ptr);

        // Extract grid/block dimensions
        auto grid_tuple = stage_info["grid"].cast<py::tuple>();
        dim3 grid(grid_tuple[0].cast<int>(),
                  grid_tuple[1].cast<int>(),
                  grid_tuple[2].cast<int>());

        auto block_tuple = stage_info["block"].cast<py::tuple>();
        dim3 block(block_tuple[0].cast<int>(),
                   block_tuple[1].cast<int>(),
                   block_tuple[2].cast<int>());

        size_t workspace_bytes = stage_info["workspace_bytes"].cast<size_t>();

        return std::make_shared<CustomStage>(kernel_func, grid, block, workspace_bytes);
    });
}
```

## Additional Technical Insights

- **Numba Internals**: `kernel.driver_function.handle.value` exposes the `CUfunction` pointer (CUDA Driver API). This is undocumented but stable since Numba 0.58+.

- **Version Pinning Required**: Pin Numba >=0.58 in `pyproject.toml`. Earlier versions had unstable internals.

- **Fallback to CuPy**: If Numba unavailable, could support CuPy's `RawKernel` (also exposes `CUfunction`). Recommend Numba first (better JIT performance).

- **Grid/Block Auto-Sizing**: Could add helper to auto-calculate grid dimensions from data size. For v1.0, user-specified is sufficient.

- **Kernel Signature Convention**: User must match signature: `kernel(input, output, n, state)`. Document in user guide.

- **Performance Validation**: After integration, measure overhead via Issue #012 (custom stage overhead benchmark). Target: <10µs.

- **Error Diagnostics**: If kernel launch fails, provide clear error with kernel name and signature mismatch hints.

## Implementation Tasks

- [ ] Create `src/sigtekx/stages/__init__.py` (make stages module)
- [ ] Create `src/sigtekx/stages/custom.py` with `NumbaStageAdapter` class
- [ ] Implement `__init__()` to extract `cu_function` from Numba kernel
- [ ] Add validation: check `hasattr(kernel_func, 'driver_function')`
- [ ] Add `ImportError` if Numba not installed (clear message)
- [ ] Add `__repr__()` for debugging
- [ ] Open `src/sigtekx/core/builder.py`
- [ ] Add `add_custom()` method to `PipelineBuilder` class
- [ ] Import `NumbaStageAdapter` at top of file
- [ ] Add docstring with example usage
- [ ] Open `cpp/bindings/bindings.cpp`
- [ ] Expose `CustomStage` class to pybind11
- [ ] Add `create_custom_stage()` helper function (dict → CustomStage)
- [ ] Update `pyproject.toml`: add `numba>=0.58` to dependencies
- [ ] Create integration test: `tests/test_custom_numba.py`
  - Test: Simple gain kernel (multiply by scalar)
  - Test: Kernel with workspace (IIR filter)
  - Test: Invalid kernel (not @cuda.jit) raises TypeError
  - Test: Numba not installed raises ImportError (mock)
- [ ] Measure overhead: `python benchmarks/custom_stage_overhead.py` (after Issue #012)
- [ ] Update documentation: `docs/api/custom-stages.md` with user example
- [ ] Build: `./scripts/cli.ps1 build`
- [ ] Test: `./scripts/cli.ps1 test python`
- [ ] Commit: `feat(python): add Numba integration for custom CUDA kernels`

## Edge Cases to Handle

- **Numba Not Installed**: ImportError with installation instructions
  - Mitigation: Clear error message: "Install Numba: pip install numba>=0.58"

- **Invalid Kernel (Not @cuda.jit)**: TypeError if not Numba kernel
  - Mitigation: Check `hasattr(kernel_func, 'driver_function')`, raise with example

- **Kernel Signature Mismatch**: Runtime error if kernel expects different args
  - Mitigation: Document signature convention, provide diagnostic on launch failure

- **Numba Version Incompatibility**: Older Numba versions have different internals
  - Mitigation: Pin Numba >=0.58, check version in `NumbaStageAdapter.__init__()`

- **CUfunction Pointer Invalid**: If Numba returns null pointer
  - Mitigation: Validate `cu_function != 0` before passing to C++

## Testing Strategy

**Integration Test (Python):**

```python
# tests/test_custom_numba.py
import pytest
import numpy as np
from numba import cuda
from sigtekx import PipelineBuilder

@cuda.jit
def gain_kernel(input, output, n, state):
    """Simple gain: output = input * 0.5"""
    i = cuda.grid(1)
    if i < n:
        output[i] = input[i] * 0.5

def test_custom_numba_stage():
    """Test Numba kernel integration."""
    # Build pipeline with custom stage
    pipeline = (PipelineBuilder()
        .add_window('hann')
        .add_fft()
        .add_custom(gain_kernel, grid=(128, 1, 1), block=(256, 1, 1))
        .add_magnitude()
        .build())

    # Process test signal
    signal = np.random.randn(4096).astype(np.float32)
    result = pipeline.process(signal)

    # Verify custom stage executed (output affected by 0.5 gain)
    assert result.shape == (2049,)  # RFFT output size
    # Further validation: compare with/without custom stage

def test_invalid_kernel_raises_error():
    """Test error handling for non-Numba kernel."""
    def not_a_kernel(x):
        return x * 2

    with pytest.raises(TypeError, match="not a Numba CUDA kernel"):
        PipelineBuilder().add_custom(not_a_kernel)

def test_numba_not_installed(monkeypatch):
    """Test error when Numba unavailable."""
    monkeypatch.setattr('sigtekx.stages.custom.NUMBA_AVAILABLE', False)

    with pytest.raises(ImportError, match="Numba is not installed"):
        from sigtekx.stages.custom import NumbaStageAdapter
        NumbaStageAdapter(lambda: None)
```

**Performance Benchmark:**

```bash
# After Issue #012 (custom stage overhead benchmark)
python benchmarks/custom_stage_overhead.py
# Expected: Overhead <10µs for Numba custom magnitude vs built-in
```

## Acceptance Criteria

- [ ] `NumbaStageAdapter` class implemented
- [ ] Extracts `CUfunction` pointer from Numba kernel
- [ ] `PipelineBuilder.add_custom()` method works
- [ ] Integration test passes: custom gain kernel
- [ ] Error handling works: invalid kernel raises TypeError
- [ ] Error handling works: Numba not installed raises ImportError
- [ ] Overhead < 10µs (measured via Issue #012)
- [ ] Documentation includes user example
- [ ] Works with Numba >= 0.58
- [ ] All Python tests pass

## Benefits

- **Core Novelty Demonstrated**: Python users can inject custom CUDA kernels without C++
- **Real-Time Performance**: <10µs overhead maintains RTF < 0.3 target
- **Competitive Moat**: No other Python GPU DSP library offers this flexibility
- **Scientific Productivity**: Iterate on algorithms in seconds (Python JIT) vs hours (C++ recompile)
- **Methods Paper Ready**: Key innovation for v1.0 publication
- **Foundation for PyTorch**: Same pattern applies to ML model integration (Issue #007)

---

**Labels:** `feature`, `team-1-cpp`, `team-3-python`, `c++`, `python`, `cuda`, `architecture`

**Estimated Effort:** 8-10 hours (Python/C++ bridge, Numba internals, requires thorough testing)

**Priority:** Critical (Core Novelty - Phase 2 Task 2.2)

**Roadmap Phase:** Phase 2 (v0.9.7)

**Dependencies:** Issue #005 (CustomStage C++ class must exist first)

**Blocks:** Issue #012 (custom stage overhead benchmark)
