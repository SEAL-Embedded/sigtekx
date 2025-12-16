# Fix Dangling Pointer in Python Bindings process() Return

## Problem

The Python bindings' `process()` method returns a NumPy array that **points directly to internal buffer memory** without proper lifetime management. If the Python executor object is deleted while the returned array is still referenced, accessing the array causes a **segmentation fault**.

**Impact:**
- **Critical safety issue** in Python API
- User code can easily trigger segfault
- Violates Python memory safety guarantees
- Affects all Python users of BatchExecutor and StreamingExecutor

**Example Failure Scenario:**
```python
executor = BatchExecutor()
executor.initialize(config)
output = executor.process(input)  # Returns array pointing to executor.output_buffer_
del executor  # ❌ executor destroyed, output_buffer_ freed
result = output[0, 0]  # ☠️ SEGFAULT - accessing freed memory
```

## Current Implementation

**File:** `cpp/bindings/bindings.cpp` (lines 83-88)

```cpp
std::vector<float> process(py::array_t<float, py::array::c_style | py::array::forcecast> input) {
  // ... validation and processing ...

  // ❌ UNSAFE: Returns array pointing to output_buffer_.data()
  return py::array(py::buffer_info(
      output_buffer_.data(),        // ← Pointer to member variable
      sizeof(float),
      py::format_descriptor<float>::format(),
      2,
      {static_cast<size_t>(config_.channels),
       static_cast<size_t>(config_.num_output_bins())},
      {static_cast<size_t>(config_.num_output_bins() * sizeof(float)),
       sizeof(float)}));
}
```

**What's Wrong:**
1. Returns `py::array` wrapping pointer to `output_buffer_.data()`
2. `output_buffer_` is a member variable (`std::vector<float>` at line 109)
3. pybind11 default return value policy is `automatic`, which doesn't keep executor alive
4. If Python deletes executor, `output_buffer_` is destroyed
5. Returned NumPy array becomes **dangling pointer**

## Proposed Solution

**Option 1: Reference Internal (Recommended - Zero Copy)**

Add explicit return value policy to keep executor alive while array referenced:

**File:** `cpp/bindings/bindings.cpp` (line 277)

```cpp
// In binding definition:
.def("process", &sigtekx::PyBatchExecutor::process,
     py::return_value_policy::reference_internal,  // ✅ Keeps executor alive
     py::arg("input"),
     "Processes a batch of input data.\n\n"
     "Returns a NumPy array referencing internal buffer.\n"
     "**Important:** Array is valid only while executor exists.")
```

**How It Works:**
- `reference_internal` tells pybind11 to keep Python executor object alive
- As long as NumPy array exists, executor won't be garbage collected
- Zero-copy: no data duplication
- User can still explicitly `del executor` but array keeps it alive internally

**Option 2: Copy (Safer but Slower)**

Alternatively, return a copy of the buffer:

```cpp
std::vector<float> process(...) {
  // ... processing ...

  // Create NEW vector (copy)
  std::vector<float> result = output_buffer_;

  // pybind11 auto-converts to NumPy array (copies again)
  return result;  // ✅ Safe: array owns data
}
```

**Trade-offs:**
- **Option 1:** Fast (zero-copy), requires documentation, slight complexity
- **Option 2:** Slow (2 copies), simple, foolproof

**Recommendation:** Use Option 1 for performance, document clearly

## Additional Technical Insights

- **pybind11 Return Value Policies:**
  - `automatic` (default): Heuristically chooses, unsafe for member pointers
  - `reference_internal`: Keeps `this` (executor) alive while return value referenced
  - `copy`: Always copies (safe but slow)
  - `move`: Takes ownership (not applicable here, executor still needs buffer)

- **NumPy Array Lifetime:**
  - NumPy arrays are reference-counted Python objects
  - pybind11's `reference_internal` adds executor as a "base" of the array
  - Python won't delete executor until array's refcount drops to zero

- **Performance Impact:**
  - Option 1: Zero overhead (pointer wrap only)
  - Option 2: 2× memory + 2× copy time (~10-50µs for typical output sizes)

- **User Experience:**
  - Option 1: Users can keep arrays after executor deleted (executor kept alive)
  - Option 2: Arrays always safe, but slower

## Implementation Tasks

- [ ] Open `cpp/bindings/bindings.cpp`
- [ ] Locate BatchExecutor binding (line 271-290)
- [ ] Add `py::return_value_policy::reference_internal` to `process()` method (line 277)
- [ ] Repeat for StreamingExecutor binding (line 295-310)
- [ ] Update docstring to document array lifetime: "Array is valid while executor exists"
- [ ] Add Python test: `tests/test_bindings.py::test_array_lifetime_after_del()`
- [ ] Add Python test: `tests/test_bindings.py::test_array_copy_if_needed()`
- [ ] Verify existing Python tests still pass (no regressions)
- [ ] Update Python API docs: document zero-copy behavior
- [ ] Commit: `fix(bindings): use reference_internal for process() array return`

## Edge Cases to Handle

- **Explicit Copy When Needed:**
  - Users wanting to delete executor immediately can copy: `output.copy()`
  - Document this pattern in API docs

- **Circular References:**
  - Keeping executor alive via array is safe (Python GC handles cycles)
  - No memory leak as long as user eventually releases array

- **Multiple Arrays from Same Executor:**
  - Each array call creates new view of `output_buffer_`
  - All views keep executor alive independently
  - Safe: last view to be released allows executor cleanup

- **Context Manager Usage:**
  - With `with Engine() as engine:`, executor may be explicitly closed
  - Array returned from process() keeps executor alive even after `__exit__`
  - Safe: executor resources cleaned up after array released

## Testing Strategy

### Python Unit Test (Add to `tests/test_bindings.py`):

```python
import numpy as np
from sigtekx import BatchExecutor, EngineConfig

def test_array_lifetime_after_executor_deleted():
    """Test that returned array remains valid after executor deleted."""
    config = EngineConfig(nfft=1024, channels=1, mode='batch')

    # Create executor and get result
    executor = BatchExecutor()
    executor.initialize(config)
    input_data = np.random.randn(1, 1024).astype(np.float32)
    output = executor.process(input_data)

    # Copy some values before deleting executor
    first_value = output[0, 0]

    # Delete executor - should NOT crash due to reference_internal
    del executor

    # Array should still be valid (executor kept alive internally)
    assert output[0, 0] == first_value  # ✅ Should NOT segfault
    assert output.shape[1] > 0  # ✅ Can still access shape

    # Explicitly release array
    del output
    # Now executor can be cleaned up


def test_multiple_arrays_keep_executor_alive():
    """Test that multiple arrays from same executor all keep it alive."""
    config = EngineConfig(nfft=1024, channels=1, mode='batch')

    executor = BatchExecutor()
    executor.initialize(config)
    input_data = np.random.randn(1, 1024).astype(np.float32)

    # Get multiple outputs
    output1 = executor.process(input_data)
    output2 = executor.process(input_data)
    output3 = executor.process(input_data)

    # Delete executor
    del executor

    # All arrays should still be valid
    assert output1.shape == output2.shape == output3.shape

    # Delete two arrays
    del output1, output2

    # Third array still valid
    assert output3.shape[1] > 0

    # Delete last array - now executor can be cleaned up
    del output3


def test_array_copy_breaks_lifetime_link():
    """Test that copying array breaks lifetime dependency."""
    config = EngineConfig(nfft=1024, channels=1, mode='batch')

    executor = BatchExecutor()
    executor.initialize(config)
    input_data = np.random.randn(1, 1024).astype(np.float32)

    output = executor.process(input_data)
    output_copy = output.copy()  # Explicit copy

    # Delete executor AND original array
    del executor
    del output

    # Copy should still be valid (owns its own data)
    assert output_copy.shape[1] > 0
```

### Integration Test (Manual):

```bash
# Run Python tests
pytest tests/test_bindings.py::test_array_lifetime_after_executor_deleted -v

# Expected: PASS (no segfault)

# Run all binding tests
pytest tests/test_bindings.py -v

# Expected: All tests PASS
```

### Stress Test:

```python
# Stress test with many executors and arrays
import gc

for i in range(1000):
    executor = BatchExecutor()
    executor.initialize(config)
    outputs = [executor.process(input_data) for _ in range(10)]
    del executor  # Executor kept alive by 10 arrays

    # Access all arrays (should not crash)
    for out in outputs:
        _ = out[0, 0]

    del outputs  # Now executor can be cleaned up

    if i % 100 == 0:
        gc.collect()  # Force GC to test cleanup

print("✅ 1000 iterations, no crashes")
```

## Acceptance Criteria

- [ ] `py::return_value_policy::reference_internal` added to both executor bindings
- [ ] Docstring documents array lifetime behavior
- [ ] Python test `test_array_lifetime_after_executor_deleted` passes
- [ ] Python test `test_multiple_arrays_keep_executor_alive` passes
- [ ] Python test `test_array_copy_breaks_lifetime_link` passes
- [ ] All existing Python tests pass (no regressions)
- [ ] Stress test with 1000 iterations completes without segfault
- [ ] API documentation updated with zero-copy behavior note
- [ ] No memory leaks detected (use valgrind or AddressSanitizer if available)

## Benefits

- **Fixes Critical Safety Bug:** Eliminates segfault risk in Python API
- **Zero Performance Cost:** No additional copies vs unsafe version
- **Python Memory Safety:** Conforms to Python's reference counting model
- **User Confidence:** Safe to use returned arrays after executor scope
- **Phase 1 Readiness:** Critical Python API now safe for production use
- **Standards Compliance:** Follows pybind11 best practices

---

**Labels:** `bug`, `team-3-python`, `python`, `reliability`

**Estimated Effort:** 30 minutes (binding change + tests)

**Priority:** CRITICAL (safety issue)

**Roadmap Phase:** Phase 0 (prerequisite for safe Python usage)

**Dependencies:** None

**Blocks:** All Python-based workflows (benchmarks, experiments, user applications)
