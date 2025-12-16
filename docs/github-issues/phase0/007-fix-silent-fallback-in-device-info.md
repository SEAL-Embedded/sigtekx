# Fix Silent Fallback in device_info Property

## Problem

The `device_info` property in the Engine class silently returns an empty dictionary when CUDA device queries fail, without logging the error or providing any diagnostic information to the user. This makes debugging device-related issues difficult and hides potentially important warnings.

**Impact:**
- Users get empty dict instead of helpful error message
- Device compatibility issues go unnoticed
- Difficult to diagnose CUDA driver or runtime problems
- Loss of diagnostic information in production logs

**Affected Code:**
```python
@property
def device_info(self) -> dict[str, Any]:
    try:
        # ... CUDA queries ...
    except Exception:  # ❌ Catches everything silently
        return {}  # ❌ No logging, no user feedback
```

**Failure Scenario:**
```python
from sigtekx import Engine

engine = Engine(preset='default')
info = engine.device_info

# If CUDA driver outdated or device incompatible:
print(info)  # {}  ← Empty dict, no indication of what failed
```

User has no idea:
- Why device info is empty
- What went wrong (driver version? CUDA error?)
- Whether device is even compatible

## Current Implementation

**File:** `src/sigtekx/core/engine.py` (lines 742-772)

```python
@property
def device_info(self) -> dict[str, Any]:
    """Get device information.

    Returns:
        Dictionary with device information, or empty dict if unavailable.
    """
    try:
        # Import here to avoid circular dependencies
        from sigtekx.utils import device

        info = device.get_device_info(self._config.device_index)

        # Add runtime info from executor if initialized
        if self._executor and self.is_initialized:
            try:
                runtime_info = self._executor.get_runtime_info()
                info['cuda_version'] = runtime_info.cuda_version
                # ... more fields ...
            except Exception:  # ❌ Nested silent catch
                pass  # ❌ No logging here either

        return info

    except Exception:  # ❌ Overly broad, catches everything
        return {}  # ❌ Silent failure
```

**What's Wrong:**

1. **Overly broad exception catching:**
   - `except Exception:` catches ALL exceptions
   - Masks ImportError, AttributeError, RuntimeError, etc.
   - Each error type needs different handling

2. **No logging:**
   - Error swallowed completely
   - Not even debug-level logging
   - Production deployments have no visibility

3. **No user feedback:**
   - Empty dict provides no clue what failed
   - User doesn't know if device unsupported or transient error

4. **Nested silent catch:**
   - Inner try-except (line 767) also silent
   - Compounds the diagnostic problem

## Proposed Solution

Add logging at appropriate levels and preserve partial information when possible.

### Fixed Implementation

```python
import logging

logger = logging.getLogger(__name__)

@property
def device_info(self) -> dict[str, Any]:
    """Get device information.

    Returns:
        Dictionary with device information. If device queries fail,
        returns partial info with 'error' field explaining the failure.

    Example:
        >>> engine = Engine(preset='default')
        >>> info = engine.device_info
        >>> if 'error' in info:
        ...     print(f"Warning: {info['error']}")
    """
    info = {}

    try:
        # Import here to avoid circular dependencies
        from sigtekx.utils import device

        info = device.get_device_info(self._config.device_index)

    except ImportError as e:
        # ✅ Specific exception: missing module
        logger.warning(
            f"Unable to query device info: device utils not available ({e})"
        )
        info['error'] = 'Device utilities not available'
        return info

    except RuntimeError as e:
        # ✅ Specific exception: CUDA error
        logger.warning(
            f"Unable to query CUDA device {self._config.device_index}: {e}"
        )
        info['error'] = f'CUDA device query failed: {e}'
        return info

    except Exception as e:
        # ✅ Catch-all with logging
        logger.debug(
            f"Unexpected error querying device info: {type(e).__name__}: {e}"
        )
        info['error'] = f'Device info unavailable: {type(e).__name__}'
        return info

    # Add runtime info from executor if initialized
    if self._executor and self.is_initialized:
        try:
            runtime_info = self._executor.get_runtime_info()
            info['cuda_version'] = runtime_info.cuda_version
            info['cuda_runtime_version'] = runtime_info.cuda_runtime_version
            info['cuda_driver_version'] = runtime_info.cuda_driver_version
            info['device_name'] = runtime_info.device_name

        except AttributeError:
            # ✅ Specific: RuntimeInfo not available (expected if not bound)
            logger.debug("RuntimeInfo not available from executor")
            # Don't add 'error' - this is expected if bindings incomplete

        except Exception as e:
            # ✅ Log but don't fail - partial info still useful
            logger.debug(
                f"Could not retrieve runtime info from executor: {e}"
            )
            info.setdefault('warnings', []).append(
                'Runtime info unavailable from executor'
            )

    return info
```

**Key Improvements:**

1. **Specific exception handling:**
   - `ImportError` → Missing module
   - `RuntimeError` → CUDA error
   - `Exception` → Unexpected (logged at debug)

2. **Tiered logging:**
   - `logger.warning()` for important failures (CUDA errors)
   - `logger.debug()` for expected cases (RuntimeInfo not bound yet)
   - Respects user's log level configuration

3. **Partial information preserved:**
   - Returns dict with 'error' field instead of empty dict
   - User can detect failure: `if 'error' in info:`
   - Still includes any partial data retrieved before error

4. **User feedback:**
   - Error message in returned dict
   - User knows what failed without needing logs

## Additional Technical Insights

### Logging Levels in Python

| Level | Severity | Use Case | Example |
|-------|----------|----------|---------|
| `ERROR` | 40 | Unexpected failures | CUDA initialization failed |
| `WARNING` | 30 | Degraded functionality | Device info unavailable |
| `INFO` | 20 | Normal operation | Engine initialized |
| `DEBUG` | 10 | Development diagnostics | Executor config details |

**Recommendation for this case:**
- `WARNING` for CUDA errors (user should know device might not work)
- `DEBUG` for expected failures (RuntimeInfo not bound yet)

### Exception Specificity Best Practice

```python
# ❌ BAD: Overly broad
try:
    operation()
except Exception:
    pass

# ✅ GOOD: Specific exceptions
try:
    operation()
except ImportError:
    logger.warning("Module not available")
except RuntimeError as e:
    logger.warning(f"Operation failed: {e}")
except Exception as e:
    logger.debug(f"Unexpected: {e}")
```

### Partial vs Complete Failure

**Current behavior (all-or-nothing):**
- Any error → return `{}`
- User gets zero information

**Proposed behavior (graceful degradation):**
- Device info fails → return `{'error': '...'}`
- Runtime info fails → return device info + warning
- User gets best available information

## Implementation Tasks

- [ ] Open `src/sigtekx/core/engine.py`
- [ ] Locate `device_info` property (line 742)
- [ ] Add `logger` import at module level (if not present)
- [ ] Replace outer `except Exception:` with specific handlers:
  - [ ] `except ImportError` with warning log
  - [ ] `except RuntimeError` with warning log
  - [ ] `except Exception` with debug log (catch-all)
- [ ] Add 'error' field to returned dict on failure
- [ ] Replace inner `except Exception:` (line 767) with specific handlers:
  - [ ] `except AttributeError` with debug log (expected if RuntimeInfo not bound)
  - [ ] `except Exception` with debug log + warning in dict
- [ ] Update docstring to document 'error' field
- [ ] Add usage example showing error detection
- [ ] Add unit test: `test_device_info_logs_errors()`
- [ ] Add unit test: `test_device_info_partial_failure()`
- [ ] Run existing tests to verify no regressions
- [ ] Commit: `fix(api): add logging and error reporting to device_info property`

## Edge Cases to Handle

- **CUDA not available:**
  - `device.get_device_info()` raises RuntimeError
  - Log warning, return `{'error': 'CUDA device query failed: ...'}`

- **Device index out of range:**
  - CUDA error in `get_device_info()`
  - Log warning, return error dict ✓

- **Executor not initialized:**
  - `self._executor is None` or `not self.is_initialized`
  - Skip runtime info section, return device info only ✓

- **RuntimeInfo not bound (bindings incomplete):**
  - `get_runtime_info()` raises AttributeError
  - Log at debug (expected), don't add error field ✓

- **Concurrent access to device:**
  - CUDA may return transient errors
  - User can retry by re-accessing property ✓

## Testing Strategy

### Unit Tests (Add to `tests/test_engine.py`)

```python
import logging
from unittest.mock import patch, MagicMock
from sigtekx import Engine

def test_device_info_logs_cuda_error(caplog):
    """Test that CUDA errors are logged at WARNING level."""
    with patch('sigtekx.utils.device.get_device_info') as mock_device_info:
        # Simulate CUDA error
        mock_device_info.side_effect = RuntimeError("CUDA error 999")

        engine = Engine(preset='default')

        with caplog.at_level(logging.WARNING):
            info = engine.device_info

        # Should return dict with error field
        assert 'error' in info
        assert 'CUDA device query failed' in info['error']

        # Should log warning
        assert len(caplog.records) > 0
        assert caplog.records[0].levelname == 'WARNING'
        assert 'CUDA error 999' in caplog.text

def test_device_info_logs_import_error(caplog):
    """Test that ImportError is logged when device utils unavailable."""
    with patch('sigtekx.utils.device.get_device_info') as mock_device_info:
        mock_device_info.side_effect = ImportError("No module named 'pycuda'")

        engine = Engine(preset='default')

        with caplog.at_level(logging.WARNING):
            info = engine.device_info

        assert 'error' in info
        assert 'Device utilities not available' in info['error']
        assert 'WARNING' in caplog.text

def test_device_info_partial_success():
    """Test that partial info returned when runtime info fails."""
    engine = Engine(preset='default')
    engine._executor = MagicMock()

    # Device info succeeds
    with patch('sigtekx.utils.device.get_device_info') as mock_device_info:
        mock_device_info.return_value = {
            'name': 'NVIDIA RTX 3090 Ti',
            'compute_capability': (8, 6)
        }

        # Runtime info fails
        engine._executor.get_runtime_info.side_effect = AttributeError(
            "RuntimeInfo not bound"
        )

        info = engine.device_info

    # Should have device info
    assert 'name' in info
    assert info['name'] == 'NVIDIA RTX 3090 Ti'

    # Should NOT have runtime info
    assert 'cuda_version' not in info

    # Should NOT have error (runtime failure expected)
    # But may have warning
    # assert 'error' not in info  # Don't fail on missing runtime info

def test_device_info_success_case():
    """Test that device_info works correctly in success case."""
    engine = Engine(preset='default')

    with patch('sigtekx.utils.device.get_device_info') as mock_device_info:
        mock_device_info.return_value = {
            'name': 'NVIDIA RTX 4090',
            'compute_capability': (8, 9),
            'total_memory': 24 * 1024 * 1024 * 1024
        }

        info = engine.device_info

    assert 'name' in info
    assert 'error' not in info
    assert info['name'] == 'NVIDIA RTX 4090'
```

### Manual Verification

```python
# Test script: test_device_info_logging.py
import logging
from sigtekx import Engine

# Enable debug logging to see all messages
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

print("Testing device_info property...")

engine = Engine(preset='default')
info = engine.device_info

if 'error' in info:
    print(f"❌ Device info failed: {info['error']}")
else:
    print(f"✅ Device info retrieved successfully:")
    for key, value in info.items():
        print(f"  {key}: {value}")
```

```bash
# Run manual test
python test_device_info_logging.py

# Expected output (success case):
# Testing device_info property...
# ✅ Device info retrieved successfully:
#   name: NVIDIA RTX 3090 Ti
#   compute_capability: (8, 6)
#   total_memory: 25769803776

# Expected output (failure case):
# Testing device_info property...
# WARNING: Unable to query CUDA device 0: CUDA error 999
# ❌ Device info failed: CUDA device query failed: CUDA error 999
```

## Acceptance Criteria

- [ ] `except Exception:` replaced with specific exception handlers
- [ ] ImportError handler logs at WARNING level
- [ ] RuntimeError handler logs at WARNING level
- [ ] Generic Exception handler logs at DEBUG level
- [ ] Failed queries return dict with 'error' field
- [ ] Partial failures preserve available information
- [ ] Inner runtime info exception handler logs at DEBUG
- [ ] Docstring updated with 'error' field documentation
- [ ] Usage example added to docstring
- [ ] Unit test `test_device_info_logs_cuda_error` passes
- [ ] Unit test `test_device_info_logs_import_error` passes
- [ ] Unit test `test_device_info_partial_success` passes
- [ ] Unit test `test_device_info_success_case` passes
- [ ] All existing Engine tests pass (no regressions)
- [ ] Manual test shows appropriate log messages

## Benefits

- **Better Diagnostics:** Users can see why device info unavailable
- **Production Visibility:** Errors logged for monitoring/debugging
- **Graceful Degradation:** Partial info better than no info
- **User-Friendly:** Clear error messages in returned dict
- **Debugging Aid:** Logs help diagnose CUDA driver/runtime issues
- **Best Practices:** Specific exception handling, appropriate log levels

---

**Labels:** `bug`, `team-3-python`, `python`, `logging`, `diagnostics`

**Estimated Effort:** 1-2 hours (refactor + comprehensive tests)

**Priority:** MEDIUM (improves debugging experience)

**Roadmap Phase:** Phase 0 (nice to have before Phase 1)

**Dependencies:** None

**Blocks:** None (but improves developer experience)
