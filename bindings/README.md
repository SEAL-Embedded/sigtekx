# Python Bindings Layer

Pybind11 interface exposing the C++ FFT engine to Python with zero-copy buffer access.

## Architecture Overview

```
Python numpy.ndarray
        ↓
py::array_t (pybind11 wrapper)
        ↓
Pinned Memory (zero-copy view)
        ↓
CUDA Operations (async)
```

## Key Design Decisions

### Zero-Copy Buffer Strategy

Traditional approach (SLOW):
```cpp
// Copies data - avoid this
.def("get_output", [](Engine& self) {
    std::vector<float> data = self.get_output();
    return py::array_t<float>(data.size(), data.data());
});
```

Our approach (FAST):
```cpp
// Zero-copy view into pinned memory
.def("pinned_output", [](RtFftEngine &self, int stream_idx) {
    float* ptr = self.pinned_output(stream_idx);  // Direct pointer
    return py::array_t<float>(make_buf(ptr, rows, cols));  // View, not copy
})
```

### Buffer Info Helper

```cpp
static inline py::buffer_info make_buf(float* ptr, int rows, int cols) {
    return py::buffer_info(
        ptr,                                     // Pointer to buffer
        sizeof(float),                           // Size of one element
        py::format_descriptor<float>::format(), // Python format code ('f')
        2,                                       // Number of dimensions
        { rows, cols },                          // Shape (batch, bins)
        { sizeof(float) * cols,                 // Strides (row-major)
          sizeof(float) }
    );
}
```

## Binding Structure

### Configuration Class

```cpp
py::class_<ionosense::RtFftConfig>(m, "RtFftConfig")
    .def(py::init<>())  // Default constructor
    
    // Keyword constructor for Python convenience
    .def(py::init([](int nfft, int batch, bool use_graphs, bool verbose) {
        ionosense::RtFftConfig cfg;
        cfg.nfft = nfft;
        cfg.batch = batch;
        cfg.use_graphs = use_graphs;
        cfg.verbose = verbose;
        return cfg;
    }),
    py::arg("nfft"),
    py::arg("batch"),
    py::arg("use_graphs") = true,    // Default value
    py::arg("verbose") = false)
    
    // Direct field access
    .def_readwrite("nfft", &ionosense::RtFftConfig::nfft)
    .def_readwrite("batch", &ionosense::RtFftConfig::batch);
```

### Engine Class

```cpp
py::class_<ionosense::RtFftEngine>(m, "RtFftEngine")
    // Primary constructor with config
    .def(py::init<const ionosense::RtFftConfig&>())
    
    // Convenience constructor bypassing config
    .def(py::init([](int nfft, int batch, bool use_graphs, bool verbose) {
        ionosense::RtFftConfig cfg;
        cfg.nfft = nfft;
        cfg.batch = batch;
        cfg.use_graphs = use_graphs;
        cfg.verbose = verbose;
        return std::make_unique<ionosense::RtFftEngine>(cfg);
    }))
```

## Memory Safety

### Array Validation

```cpp
.def("set_window", [](ionosense::RtFftEngine &self,
                      py::array_t<float, py::array::c_style | 
                                  py::array::forcecast> arr) {
    // Validate size
    if (arr.size() != self.get_fft_size()) {
        throw std::runtime_error("Window size must match FFT size.");
    }
    
    // Pass raw pointer to C++
    self.set_window(arr.data(0));
})
```

### Lifetime Management

**Problem**: Python might garbage collect while GPU is using buffer.

**Solution**: Pinned memory owned by C++ engine, Python gets non-owning view.

```cpp
// Buffer lifetime tied to engine, not Python
float* ptr = self.pinned_input(stream_idx);  // C++ owns
return py::array_t<float>(buffer_info);      // Python views
```

## Properties vs Methods

### Properties (Pythonic)

```cpp
.def_property("use_graphs",
    &RtFftEngine::get_use_graphs,    // Getter
    &RtFftEngine::set_use_graphs)    // Setter

// Python usage: engine.use_graphs = True
```

### Read-Only Properties

```cpp
.def_property_readonly("fft_size", &RtFftEngine::get_fft_size)
.def_property_readonly("graphs_ready", &RtFftEngine::graphs_ready)

// Python usage: size = engine.fft_size  (no setter)
```

## Exception Translation

C++ exceptions are automatically translated to Python:

| C++ Exception | Python Exception |
|---------------|------------------|
| `std::runtime_error` | `RuntimeError` |
| `std::out_of_range` | `IndexError` |
| `std::invalid_argument` | `ValueError` |
| CUDA errors (via throw) | `RuntimeError` |

## Performance Critical Sections

### No-Copy Operations

```cpp
// Direct buffer access - zero overhead
.def("pinned_input", [](RtFftEngine &self, int idx) {
    float* ptr = self.pinned_input(idx);
    return py::array_t<float>(make_buf(...));
}, py::return_value_policy::reference_internal)
```

### GIL Release

For long-running operations (future):
```cpp
.def("execute_async", [](RtFftEngine &self, int idx) {
    py::gil_scoped_release release;  // Release Python GIL
    self.execute_async(idx);          // Can run parallel to Python
})
```

## Build Configuration

### CMake Integration

```cmake
pybind11_add_module(_engine bindings/bindings.cpp)
target_link_libraries(_engine PRIVATE
    "$<TARGET_OBJECTS:ion_engine>"   # Object files from static lib
    pybind11::module
    CUDA::cudart_static
    CUDA::cufft
)
```

### Output Location

```cmake
set(_ION_PY_OUT "${CMAKE_CURRENT_SOURCE_DIR}/python/ionosense_hpc/core")
set_target_properties(_engine PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${_ION_PY_OUT}"   # .so on Linux
    RUNTIME_OUTPUT_DIRECTORY "${_ION_PY_OUT}"   # .pyd on Windows
)
```

## Testing Bindings

### Python Test

```python
def test_buffer_shapes():
    engine = RtFftEngine(1024, 4)
    
    # Input shape: (batch, nfft)
    assert engine.pinned_input(0).shape == (4, 1024)
    
    # Output shape: (batch, nfft//2 + 1)  
    assert engine.pinned_output(0).shape == (4, 513)
```

### Memory Test

```python
def test_zero_copy():
    engine = RtFftEngine(1024, 2)
    
    # Get buffer view
    buf = engine.pinned_input(0)
    
    # Modify in place
    buf[0, :] = np.arange(1024)
    
    # Changes visible to C++/CUDA
    engine.execute_async(0)
```

## Debugging Bindings

### Verbose Build

```bash
cmake --build . --verbose  # See actual compiler commands
```

### Symbol Inspection

```bash
# Linux
nm -D _engine.so | grep RtFftEngine

# Windows  
dumpbin /EXPORTS _engine.pyd
```

### Python Import Debug

```python
import sys
sys.path.insert(0, '/path/to/module')

import _engine
print(dir(_engine))  # List all exposed symbols
```

## Common Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| `ImportError: undefined symbol` | ABI mismatch | Rebuild with same compiler |
| Segfault on buffer access | Using after free | Check engine lifetime |
| Wrong buffer values | Type mismatch | Ensure float32/numpy.float32 |
| Can't find module | Wrong path | Check CMake output directory |

## Future Enhancements

1. **Async/Await Support**: Python async interface for streams
2. **Buffer Protocol**: Custom buffer protocol for direct memoryview
3. **Capsule API**: Share GPU pointers with other extensions
4. **Docstrings**: Generate from C++ Doxygen comments

## Module Naming

```cpp
PYBIND11_MODULE(_engine, m) {
    m.doc() = "High-performance CUDA FFT engine";
    
    // Backward compatibility aliases
    m.attr("CudaFftEngine") = m.attr("RtFftEngine");
    m.attr("CudaFftConfig") = m.attr("RtFftConfig");
}
```

Python imports as:
```python
from ionosense_hpc.core._engine import RtFftEngine
```