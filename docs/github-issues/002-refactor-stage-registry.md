# Refactor Stage Registry to Unify Core and Custom Stage Architecture

## Problem

The project currently has a **split architecture** for processing stages that prevents the core engine from leveraging an extensible registry pattern. This creates inconsistency and blocks Phase 2's core novelty (custom stage integration via Numba/PyTorch).

**Current split:**
1. **Static metadata** in `src/sigtekx/stages/definitions.py`:
   - `STAGE_METADATA` dict with hardcoded stage info
   - `StageType` enum (WINDOW, FFT, MAGNITUDE, PHASE, FILTER, RESAMPLE)
   - No connection to actual C++ stage classes

2. **Dynamic registry** in `src/sigtekx/stages/registry.py`:
   - `StageRegistry` class with registration, lookup, metadata
   - Global singleton `_global_registry`
   - `@register_stage` decorator
   - **Currently unused** (not exposed in `__init__.py`, no custom stages registered)

3. **Cosmetic builder** in `src/sigtekx/core/builder.py`:
   - `PipelineBuilder` creates Python stage specifications
   - `Pipeline` object stores stage dicts
   - **C++ ignores these** - always creates Window→FFT→Magnitude regardless of Python spec
   - Cannot control C++ pipeline from Python (per roadmap line 122)

**Impact:**
- Blocks Phase 2 Task 2.2: Numba integration requires registering custom kernels at runtime
- Cannot add custom stages (no bridge between Python spec and C++ execution)
- PipelineBuilder is misleading (users think it controls pipeline, but it doesn't)
- Metadata is disconnected from execution (two sources of truth)

**Roadmap Context** (`docs/development/methods-paper-roadmap.md`):
- Phase 2 (v0.9.7): Custom Stage Integration (THE CORE NOVELTY)
- Task 2.1: Create C++ `CustomStage` class accepting `CUfunction` pointer
- Task 2.2: Expose to Python via pybind11, create `NumbaStageAdapter`
- Task 2.3: Enhance `PipelineBuilder.add_custom(kernel_func, workspace_mb=0)`

**This issue is a prerequisite** - cannot implement custom stages without a unified registry that bridges Python ↔ C++.

## Current Implementation

**File:** `src/sigtekx/stages/definitions.py` (lines 8-68)

```python
class StageType(str, Enum):
    """Enumeration of processing stage types."""
    WINDOW = "window"
    FFT = "fft"
    MAGNITUDE = "magnitude"
    PHASE = "phase"  # Future
    FILTER = "filter"  # Future
    RESAMPLE = "resample"  # Future

# Static metadata dictionary - disconnected from C++ implementation
STAGE_METADATA: dict[StageType, dict[str, Any]] = {
    StageType.WINDOW: {
        "description": "Apply window function to reduce spectral leakage.",
        "implemented": True,
        "parameters": ["window_type", "window_norm"],
    },
    StageType.FFT: {
        "description": "Fast Fourier Transform using cuFFT.",
        "implemented": True,
        "parameters": ["nfft", "batch"],
    },
    # ... more static entries
}
```

**File:** `src/sigtekx/stages/registry.py` (lines 10-95)

```python
class StageRegistry:
    """Registry for processing stages (currently unused)."""

    def __init__(self):
        self._stages: dict[str, Callable] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(self, name: str, func: Callable, metadata: dict | None = None):
        """Register a stage (no C++ connection)."""
        self._stages[name] = func
        if metadata:
            self._metadata[name] = metadata

    # ... more methods

_global_registry = StageRegistry()  # Unused singleton
```

**File:** `src/sigtekx/core/builder.py` (lines 20-180)

```python
class PipelineBuilder:
    """Fluent interface for pipeline construction (cosmetic - doesn't control C++)."""

    def __init__(self):
        self._stages: list[dict[str, Any]] = []
        self._config: EngineConfig | None = None

    def add_window(self, type: str = 'hann', ...) -> Self:
        """Add window stage (creates dict, not actual stage instance)."""
        self._stages.append({
            'type': 'window',
            'params': {'window_type': type, ...}
        })
        return self

    def build(self) -> Pipeline:
        """Build pipeline (returns immutable Python object, C++ ignores it)."""
        return Pipeline(stages=self._stages, config=self._config)
```

**C++ Side** (`cpp/src/core/stage_factory.cpp`):

```cpp
// Enum-based factory - NOT a registry, NOT extensible
std::unique_ptr<ProcessingStage> StageFactory::create(StageType type) {
    switch(type) {
        case StageType::WINDOW: return std::make_unique<WindowStage>();
        case StageType::FFT: return std::make_unique<FFTStage>();
        case StageType::MAGNITUDE: return std::make_unique<MagnitudeStage>();
        default: throw std::runtime_error("Unknown stage type");
    }
    // No way to register custom stages at runtime
}
```

**The disconnect:**
- Python `StageRegistry` exists but has no C++ counterpart
- Python `PipelineBuilder` creates specs that C++ never reads
- C++ `StageFactory` is hardcoded enum switch, not extensible
- No mechanism to pass `CUfunction` pointers from Python to C++

## Proposed Solution

**Phase 0 Preparation** (this issue - infrastructure only):

Create a **unified registry pattern** that prepares for Phase 2 custom stages, but doesn't implement them yet. Focus on making the architecture extensible.

**Step 1: Make Python registry aware of core stages**

```python
# src/sigtekx/stages/registry.py (enhanced)

from typing import Protocol, TypedDict

class StageMetadata(TypedDict):
    """Standardized metadata for all stages."""
    description: str
    implemented: bool
    parameters: list[str]
    stage_type: Literal["core", "custom", "experimental"]
    version_added: str

class IStageFactory(Protocol):
    """Protocol for stage factory functions."""
    def __call__(self, config: dict) -> Any: ...

class StageRegistry:
    """Unified registry for core + custom stages."""

    def __init__(self):
        self._stages: dict[str, IStageFactory] = {}
        self._metadata: dict[str, StageMetadata] = {}
        self._core_stages_registered = False

    def ensure_core_stages(self) -> None:
        """Lazy-load core stage metadata from definitions.py."""
        if not self._core_stages_registered:
            from sigtekx.stages.definitions import STAGE_METADATA, StageType

            for stage_type, metadata in STAGE_METADATA.items():
                if metadata.get("implemented", False):
                    self.register_core_stage(
                        name=stage_type.value,
                        metadata={
                            "description": metadata["description"],
                            "implemented": True,
                            "parameters": metadata["parameters"],
                            "stage_type": "core",
                            "version_added": "0.9.6"
                        }
                    )
            self._core_stages_registered = True

    def register_core_stage(self, name: str, metadata: StageMetadata) -> None:
        """Register a core stage (no factory yet - Phase 2)."""
        self._metadata[name] = metadata
        # Note: Factory registration deferred to Phase 2

    def get_core_pipeline(self) -> list[str]:
        """Get default core pipeline order."""
        self.ensure_core_stages()
        return ["window", "fft", "magnitude"]

    def validate_stage_exists(self, name: str) -> bool:
        """Check if stage is registered."""
        self.ensure_core_stages()
        return name in self._metadata

    def get_metadata(self, name: str) -> StageMetadata:
        """Get stage metadata."""
        self.ensure_core_stages()
        if name not in self._metadata:
            raise ValueError(f"Stage '{name}' not registered")
        return self._metadata[name]
```

**Step 2: Make PipelineBuilder validate against registry**

```python
# src/sigtekx/core/builder.py (enhanced)

from sigtekx.stages.registry import get_global_registry

class PipelineBuilder:
    """Fluent interface for pipeline construction (now validated)."""

    def __init__(self):
        self._stages: list[dict[str, Any]] = []
        self._config: EngineConfig | None = None
        self._registry = get_global_registry()

    def add_window(self, type: str = 'hann', ...) -> Self:
        """Add window stage (validated against registry)."""
        # NEW: Validate stage exists
        if not self._registry.validate_stage_exists("window"):
            raise ValueError("Window stage not available")

        # NEW: Validate parameters against metadata
        metadata = self._registry.get_metadata("window")
        expected_params = set(metadata["parameters"])
        provided_params = {'window_type', 'window_norm', 'window_symmetry'}
        if not provided_params.issubset(expected_params | {'window_type'}):
            raise ValueError(f"Invalid parameters for window stage")

        self._stages.append({
            'type': 'window',
            'params': {'window_type': type, ...}
        })
        return self

    def add_custom(self, name: str, factory: Callable, **params) -> Self:
        """Add custom stage (placeholder for Phase 2)."""
        # Phase 2 will implement this
        raise NotImplementedError(
            "Custom stages require Phase 2 implementation. "
            "See roadmap Task 2.2: Numba Integration"
        )

    def build(self) -> Pipeline:
        """Build pipeline (validates all stages exist)."""
        # NEW: Validate entire pipeline before building
        for stage_spec in self._stages:
            stage_type = stage_spec['type']
            if not self._registry.validate_stage_exists(stage_type):
                raise ValueError(f"Stage '{stage_type}' not registered")

        return Pipeline(stages=self._stages, config=self._config)
```

**Step 3: Deprecate static STAGE_METADATA access**

```python
# src/sigtekx/stages/definitions.py (add compatibility layer)

import warnings
from sigtekx.stages.registry import get_global_registry

def get_stage_metadata_legacy() -> dict[StageType, dict[str, Any]]:
    """Legacy compatibility for STAGE_METADATA access.

    DEPRECATED: Use StageRegistry.get_metadata() instead.
    """
    warnings.warn(
        "Direct STAGE_METADATA access is deprecated. "
        "Use get_global_registry().get_metadata(name) instead.",
        DeprecationWarning,
        stacklevel=2
    )

    registry = get_global_registry()
    registry.ensure_core_stages()

    # Convert registry data to legacy format
    legacy_metadata = {}
    for stage_type in StageType:
        try:
            metadata = registry.get_metadata(stage_type.value)
            legacy_metadata[stage_type] = dict(metadata)
        except ValueError:
            pass  # Stage not registered

    return legacy_metadata
```

**What this DOES NOT do (deferred to Phase 2):**

- ❌ Does NOT create C++ `CustomStage` class
- ❌ Does NOT implement Numba integration
- ❌ Does NOT connect Python PipelineBuilder to C++ execution
- ❌ Does NOT add factory functions (just metadata registration)

**What this DOES do (Phase 0 preparation):**

- ✅ Creates unified metadata source (registry replaces static dict)
- ✅ Adds validation to PipelineBuilder (catches errors early)
- ✅ Establishes extension points for Phase 2 (`add_custom` placeholder)
- ✅ Maintains backward compatibility (deprecation warnings, not breakage)
- ✅ Documents the split architecture gap (clear TODO for Phase 2)

## Additional Technical Insights

- **Lazy Registration**: Core stages registered on first access to avoid import-time side effects (prevents circular imports)

- **Protocol-Based Design**: `IStageFactory` protocol enables duck-typing for custom stage factories in Phase 2

- **Metadata Schema**: `StageMetadata` TypedDict provides type safety for stage information

- **Validation Benefits**: Early validation catches configuration errors before GPU resources are allocated

- **Phase 2 Bridge**: The registry structure is designed to accept `CUfunction` pointer registration in Phase 2:
  ```python
  # Future Phase 2 implementation
  def register_custom_stage(self, name: str, cu_function: CUfunction, metadata: StageMetadata):
      self._stages[name] = lambda config: CustomStage(cu_function, config)
      self._metadata[name] = metadata
  ```

- **No C++ Changes Yet**: This issue is Python-only, making it safe to implement before Phase 1 memory optimizations

## Implementation Tasks

**Part 1: Enhance StageRegistry (Python)**

- [ ] Open `src/sigtekx/stages/registry.py`
- [ ] Add `StageMetadata` TypedDict at top of file (lines 5-12)
- [ ] Add `IStageFactory` Protocol definition
- [ ] Add `_core_stages_registered: bool = False` to `__init__`
- [ ] Implement `ensure_core_stages()` method (loads from definitions.py)
- [ ] Implement `register_core_stage(name, metadata)` method
- [ ] Implement `get_core_pipeline()` method (returns ["window", "fft", "magnitude"])
- [ ] Implement `validate_stage_exists(name)` method
- [ ] Enhance `get_metadata(name)` to call `ensure_core_stages()` first
- [ ] Add docstring explaining Phase 2 extension plan

**Part 2: Enhance PipelineBuilder (Python)**

- [ ] Open `src/sigtekx/core/builder.py`
- [ ] Import `get_global_registry` at top
- [ ] Add `self._registry = get_global_registry()` to `__init__`
- [ ] Update `add_window()` to validate stage exists
- [ ] Update `add_fft()` to validate stage exists
- [ ] Update `add_magnitude()` to validate stage exists
- [ ] Add `add_custom()` method that raises NotImplementedError with Phase 2 reference
- [ ] Update `build()` to validate all stages in pipeline
- [ ] Add docstring note about current C++ limitations

**Part 3: Add Deprecation Layer (Python)**

- [ ] Open `src/sigtekx/stages/definitions.py`
- [ ] Add `get_stage_metadata_legacy()` function at bottom of file
- [ ] Import `warnings` module
- [ ] Implement conversion from registry to legacy dict format
- [ ] Add DeprecationWarning with migration instructions

**Part 4: Update Tests**

- [ ] Open `tests/test_stages.py`
- [ ] Add test: `test_core_stages_registered()` - verify window/fft/magnitude in registry
- [ ] Add test: `test_registry_metadata_matches_definitions()` - ensure consistency
- [ ] Add test: `test_pipeline_builder_validates_stages()` - verify early validation
- [ ] Add test: `test_add_custom_raises_not_implemented()` - verify Phase 2 placeholder
- [ ] Add test: `test_legacy_metadata_access_deprecated()` - verify warning raised
- [ ] Run tests: `pytest tests/test_stages.py -v`

**Part 5: Documentation**

- [ ] Update `src/sigtekx/stages/__init__.py` docstring to explain registry pattern
- [ ] Add comment in `registry.py` explaining C++ bridge requirements (Phase 2)
- [ ] Update `docs/architecture/` with registry design (optional, can defer)
- [ ] Add inline comments explaining validation logic in `builder.py`

## Edge Cases to Handle

- **Circular Imports**: Lazy registration in `ensure_core_stages()` prevents import-time dependency cycles

- **Missing Metadata**: If a stage is in the enum but not in `STAGE_METADATA`, registry should skip it (future stages)

- **Duplicate Registration**: If `ensure_core_stages()` called twice, `_core_stages_registered` flag prevents re-registration

- **Invalid Stage Names**: Validation should provide clear error messages with available stage names

- **Legacy Code**: Existing code using `STAGE_METADATA` should get deprecation warnings but continue working

## Testing Strategy

**Unit tests** (`tests/test_stages.py`):

```python
def test_core_stages_auto_registered():
    """Verify core stages (window, fft, magnitude) are automatically registered."""
    from sigtekx.stages.registry import get_global_registry

    registry = get_global_registry()
    assert registry.validate_stage_exists("window")
    assert registry.validate_stage_exists("fft")
    assert registry.validate_stage_exists("magnitude")

def test_pipeline_builder_validates_unknown_stages():
    """Verify PipelineBuilder rejects unregistered stages."""
    from sigtekx.core.builder import PipelineBuilder

    builder = PipelineBuilder()
    builder.add_window()
    builder.add_fft()

    # Manually inject invalid stage
    builder._stages.append({'type': 'invalid_stage', 'params': {}})

    with pytest.raises(ValueError, match="Stage 'invalid_stage' not registered"):
        builder.build()

def test_registry_metadata_consistency():
    """Verify registry metadata matches definitions.py."""
    from sigtekx.stages.registry import get_global_registry
    from sigtekx.stages.definitions import STAGE_METADATA, StageType

    registry = get_global_registry()

    for stage_type, static_metadata in STAGE_METADATA.items():
        if not static_metadata.get("implemented", False):
            continue

        registry_metadata = registry.get_metadata(stage_type.value)
        assert registry_metadata["description"] == static_metadata["description"]
        assert set(registry_metadata["parameters"]) == set(static_metadata["parameters"])

def test_add_custom_placeholder_phase2():
    """Verify add_custom() raises NotImplementedError with Phase 2 reference."""
    from sigtekx.core.builder import PipelineBuilder

    builder = PipelineBuilder()

    with pytest.raises(NotImplementedError, match="Phase 2 implementation"):
        builder.add_custom("my_stage", lambda cfg: None)
```

**Integration test** (manual verification):

```python
# Create pipeline with validation
from sigtekx import PipelineBuilder

pipeline = (PipelineBuilder()
    .add_window('hann')
    .add_fft()
    .add_magnitude()
    .build())

print(f"Pipeline stages: {len(pipeline.stages)}")
print(f"Stage types: {[s['type'] for s in pipeline.stages]}")

# Expected output:
# Pipeline stages: 3
# Stage types: ['window', 'fft', 'magnitude']
```

## Acceptance Criteria

- [ ] `StageMetadata` TypedDict defined with all required fields
- [ ] `StageRegistry.ensure_core_stages()` loads window/fft/magnitude metadata
- [ ] `PipelineBuilder.add_window/fft/magnitude()` validate against registry
- [ ] `PipelineBuilder.build()` validates entire pipeline
- [ ] `PipelineBuilder.add_custom()` raises NotImplementedError with Phase 2 reference
- [ ] Legacy `STAGE_METADATA` access raises DeprecationWarning
- [ ] All tests pass
- [ ] No C++ changes required
- [ ] Docstrings explain Phase 2 extension plan

## Benefits

- **Phase 2 Readiness**: Registry infrastructure ready for custom stage registration
- **Early Validation**: Catches configuration errors before GPU allocation
- **Extensibility**: Clear path for Numba/PyTorch integration
- **Type Safety**: `StageMetadata` TypedDict enables static analysis
- **Backward Compatibility**: Existing code works with deprecation warnings
- **No Performance Impact**: Lazy registration, metadata-only (no execution changes)
- **Documentation**: Makes the "cosmetic builder" limitation explicit

## Limitations (Phase 2 Work)

This issue intentionally does NOT:
- Implement C++ `CustomStage` class
- Connect PipelineBuilder to C++ execution
- Add Numba kernel extraction
- Implement factory functions

**Reason:** Keep Phase 0 Python-only to avoid coupling with Phase 1 C++ memory optimizations. Phase 2 will add C++ integration after memory architecture is stable.

---

**Labels:** `task`, `team-3-python`, `python`, `architecture`, `refactoring`

**Estimated Effort:** 3-4 hours (Python-only refactoring)

**Priority:** Medium-High (prerequisite for Phase 2, but not urgent)

**Roadmap Phase:** Phase 0 (preparation for Phase 2)

**Dependencies:** None (Python-only, no C++ changes)

**Blocks:** Phase 2 Task 2.2 (Numba Integration), Task 2.3 (PyTorch Integration)
