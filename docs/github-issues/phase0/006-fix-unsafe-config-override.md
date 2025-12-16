# Fix Unsafe Configuration Override Bypassing Validation

## Problem

The Engine's configuration override mechanism in `__init__()` uses direct `setattr()` to apply parameter overrides, bypassing Pydantic's validation. This allows invalid configuration values to slip through undetected, potentially causing runtime errors or incorrect behavior.

**Impact:**
- Invalid config values (e.g., `nfft="invalid"`, `overlap=1.5`) not caught at initialization
- Runtime errors occur deep in C++ code instead of early validation
- Violates Pydantic's validation guarantees
- Inconsistent with Pydantic best practices

**Affected Code:**
```python
# User provides invalid override
engine = Engine(preset='default', nfft="not_a_number")  # ❌ No validation!
# Later, in C++ bindings:
# TypeError: expected int, got str
```

**Example Failure Scenarios:**

**Scenario 1: Type mismatch**
```python
engine = Engine(preset='default', nfft="4096")  # String instead of int
# setattr accepts it without validation
# Later crashes in C++ with confusing error
```

**Scenario 2: Out-of-range value**
```python
engine = Engine(preset='default', overlap=1.5)  # Invalid: overlap must be < 1.0
# setattr accepts it
# Later causes undefined behavior in overlap calculation
```

**Scenario 3: Invalid enum value**
```python
engine = Engine(preset='default', mode="invalid_mode")
# setattr accepts arbitrary string
# Crashes when trying to convert to ExecutionMode enum
```

## Current Implementation

**File:** `src/sigtekx/core/engine.py` (lines 164-169)

```python
# Apply parameter overrides
if overrides:
    for key, value in overrides.items():
        if hasattr(self._config, key):
            # ❌ UNSAFE: Bypasses Pydantic validation
            setattr(self._config, key, value)
        else:
            raise ValueError(
                f"Unknown configuration parameter: {key}",
                hint=f"Valid parameters: {', '.join(EngineConfig.model_fields.keys())}",
            )
```

**What's Wrong:**

1. **Direct setattr() bypasses validation:**
   - Pydantic models use `__setattr__` hook for validation
   - But when model created with `model_validate_python()`, `model_config['validate_assignment'] = False` by default
   - Need to use `model_copy(update={...})` which triggers full validation

2. **Only checks attribute existence:**
   - `hasattr()` check ensures field exists
   - But doesn't validate type, range, or constraints

3. **Deferred validation failures:**
   - Invalid values accepted at init
   - Fail later during `executor_->initialize()` in C++
   - Error messages less helpful (C++ exception vs Python validation error)

## Proposed Solution

Replace `setattr()` with Pydantic's `model_copy(update={...})` method, which creates a new validated config instance.

### Fixed Implementation

```python
# Apply parameter overrides
if overrides:
    # ✅ SAFE: Use Pydantic's model_copy with validation
    try:
        self._config = self._config.model_copy(update=overrides)
    except ValueError as e:
        # Catch Pydantic validation errors and re-raise with context
        raise SigtekxConfigError(
            f"Invalid configuration override: {e}",
            hint="Check parameter types and ranges in EngineConfig schema",
            context={"invalid_overrides": overrides}
        ) from e
```

**How This Works:**

1. **`model_copy(update=overrides)`:**
   - Creates NEW config instance with updated values
   - Runs full Pydantic validation on all fields
   - Raises `ValueError` if any field invalid

2. **Early validation:**
   - Catches errors at Engine init time
   - Clear error messages from Pydantic validators
   - User knows exactly which parameter is invalid

3. **Type safety:**
   - Pydantic coerces compatible types (e.g., `nfft="4096"` → `nfft=4096`)
   - Rejects incompatible types (e.g., `nfft="invalid"` → ValidationError)

4. **Range validation:**
   - Field constraints checked (e.g., `overlap < 1.0`, `nfft` power-of-2)
   - Custom validators run (e.g., `validate_power_of_2()`)

## Additional Technical Insights

### Pydantic Validation Modes

**Option 1: model_copy() (Recommended)**
```python
config = config.model_copy(update={"nfft": 2048})
# Pros: Creates new instance, full validation, immutability
# Cons: Slight overhead (new object creation)
```

**Option 2: Assignment validation (Alternative)**
```python
# Enable assignment validation in EngineConfig
class EngineConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

# Then setattr() would validate
setattr(config, "nfft", 2048)  # Now validates!
# Pros: No new object creation
# Cons: Mutates existing config, less explicit
```

**Recommendation:** Use `model_copy()` for immutability and clarity.

### Error Message Comparison

**Current (setattr):**
```
RuntimeError: CUDA error in executor initialization
  Expected int for nfft, got str
  at cpp/src/executors/batch_executor.cpp:72
```

**Fixed (model_copy):**
```
SigtekxConfigError: Invalid configuration override:
  Validation error for EngineConfig
  nfft
    Input should be a valid integer, got 'invalid' (type=str)
Hint: Check parameter types and ranges in EngineConfig schema
```

Much clearer! ✅

### Performance Impact

- `model_copy()` creates new EngineConfig instance
- Overhead: ~10-50µs (negligible compared to GPU init)
- Only happens once at Engine creation
- **Not** on hot path (process() calls)

## Implementation Tasks

- [ ] Open `src/sigtekx/core/engine.py`
- [ ] Locate override application code (lines 164-169)
- [ ] Replace `for key, value...` loop with `model_copy(update=overrides)`
- [ ] Wrap in `try-except` to catch Pydantic ValidationError
- [ ] Re-raise as `SigtekxConfigError` with helpful context
- [ ] Remove `hasattr()` check (Pydantic handles unknown keys)
- [ ] Update docstring to clarify validation behavior
- [ ] Add unit test: `test_engine_invalid_override_type()`
- [ ] Add unit test: `test_engine_invalid_override_range()`
- [ ] Add unit test: `test_engine_unknown_override_key()`
- [ ] Run existing tests to verify no regressions
- [ ] Commit: `fix(api): use model_copy for config overrides to enforce validation`

## Edge Cases to Handle

- **Unknown parameter name:**
  ```python
  Engine(preset='default', unknown_param=123)
  ```
  - Pydantic raises ValidationError: "Extra inputs not permitted"
  - Wrapped in SigtekxConfigError ✓

- **None value override:**
  ```python
  Engine(preset='default', nfft=None)
  ```
  - Pydantic validates None if field optional
  - Raises error if field required ✓

- **Empty overrides dict:**
  ```python
  Engine(preset='default', **{})
  ```
  - `model_copy(update={})` returns identical config
  - No overhead, no error ✓

- **Nested field override (if added later):**
  ```python
  Engine(preset='default', nested={'field': 'value'})
  ```
  - Pydantic handles nested validation ✓

## Testing Strategy

### Unit Tests (Add to `tests/test_engine.py`)

```python
import pytest
from sigtekx import Engine
from sigtekx.exceptions import SigtekxConfigError

def test_engine_invalid_override_type():
    """Test that invalid type in override raises SigtekxConfigError."""
    with pytest.raises(SigtekxConfigError) as exc_info:
        Engine(preset='default', nfft="not_a_number")

    assert "Invalid configuration override" in str(exc_info.value)
    assert "nfft" in str(exc_info.value)

def test_engine_invalid_override_range():
    """Test that out-of-range value in override raises error."""
    with pytest.raises(SigtekxConfigError) as exc_info:
        Engine(preset='default', overlap=1.5)  # Must be < 1.0

    assert "Invalid configuration override" in str(exc_info.value)
    assert "overlap" in str(exc_info.value)

def test_engine_unknown_override_key():
    """Test that unknown parameter name raises error."""
    with pytest.raises(SigtekxConfigError) as exc_info:
        Engine(preset='default', unknown_param=123)

    assert "Invalid configuration override" in str(exc_info.value)

def test_engine_valid_override_success():
    """Test that valid overrides work correctly."""
    engine = Engine(preset='default', nfft=2048, overlap=0.75)

    assert engine.config.nfft == 2048
    assert engine.config.overlap == 0.75

def test_engine_override_type_coercion():
    """Test that Pydantic coerces compatible types."""
    # String "4096" should be coerced to int 4096
    engine = Engine(preset='default', nfft="4096")

    assert engine.config.nfft == 4096  # Coerced from str to int
    assert isinstance(engine.config.nfft, int)

def test_engine_override_preserves_other_fields():
    """Test that overriding one field doesn't affect others."""
    engine = Engine(preset='default', nfft=2048)

    # Other preset fields should be unchanged
    assert engine.config.nfft == 2048  # Overridden
    assert engine.config.overlap == 0.5  # Default from preset
    assert engine.config.mode == 'batch'  # Default from preset
```

### Integration Test (Manual)

```python
# Test script: test_config_validation.py
from sigtekx import Engine
from sigtekx.exceptions import SigtekxConfigError

print("Testing invalid overrides...")

# Test 1: Invalid type
try:
    Engine(preset='default', nfft="invalid")
    print("❌ FAILED: Should have raised SigtekxConfigError")
except SigtekxConfigError as e:
    print(f"✅ PASS: {e}")

# Test 2: Out of range
try:
    Engine(preset='default', overlap=2.0)
    print("❌ FAILED: Should have raised SigtekxConfigError")
except SigtekxConfigError as e:
    print(f"✅ PASS: {e}")

# Test 3: Unknown key
try:
    Engine(preset='default', unknown=123)
    print("❌ FAILED: Should have raised SigtekxConfigError")
except SigtekxConfigError as e:
    print(f"✅ PASS: {e}")

# Test 4: Valid override
try:
    engine = Engine(preset='default', nfft=2048)
    print(f"✅ PASS: Valid override accepted, nfft={engine.config.nfft}")
except Exception as e:
    print(f"❌ FAILED: {e}")

print("\nAll validation tests complete!")
```

```bash
# Run manual test
python test_config_validation.py

# Expected output:
# Testing invalid overrides...
# ✅ PASS: Invalid configuration override: ...
# ✅ PASS: Invalid configuration override: ...
# ✅ PASS: Invalid configuration override: ...
# ✅ PASS: Valid override accepted, nfft=2048
# All validation tests complete!
```

## Acceptance Criteria

- [ ] `setattr()` loop replaced with `self._config = self._config.model_copy(update=overrides)`
- [ ] `try-except` block catches ValidationError and re-raises as SigtekxConfigError
- [ ] Error message includes parameter name and validation failure reason
- [ ] `hasattr()` check removed (Pydantic handles unknown keys)
- [ ] Docstring updated to document validation behavior
- [ ] Unit test `test_engine_invalid_override_type` passes
- [ ] Unit test `test_engine_invalid_override_range` passes
- [ ] Unit test `test_engine_unknown_override_key` passes
- [ ] Unit test `test_engine_valid_override_success` passes
- [ ] Unit test `test_engine_override_type_coercion` passes
- [ ] Unit test `test_engine_override_preserves_other_fields` passes
- [ ] All existing Engine tests pass (no regressions)
- [ ] Manual integration test shows clear error messages

## Benefits

- **Early Error Detection:** Invalid config caught at Engine init, not deep in C++
- **Clear Error Messages:** Pydantic provides detailed validation failures
- **Type Safety:** Automatic type coercion and validation
- **Pydantic Best Practices:** Uses recommended `model_copy()` approach
- **User Experience:** Developers immediately see what's wrong
- **Maintainability:** Adding new validators automatically applies to overrides
- **Production Readiness:** Robust validation prevents runtime surprises

---

**Labels:** `bug`, `team-3-python`, `python`, `validation`

**Estimated Effort:** 1 hour (refactor + comprehensive tests)

**Priority:** MEDIUM-HIGH (correctness issue, affects API reliability)

**Roadmap Phase:** Phase 0 (prerequisite for robust Python API)

**Dependencies:** None

**Blocks:** None (but improves API safety for all users)
