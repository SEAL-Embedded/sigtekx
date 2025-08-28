# Development Guide

Technical documentation for contributors and maintainers of ionosense-hpc-lib.

## Architecture Overview

### System Layers

```
Application Layer (Python)
    ├── High-level API (FFTProcessor)
    ├── Analysis tools (metrics, validators)
    └── I/O utilities (signals, formats)
          ↓
Binding Layer (Pybind11)
    ├── Zero-copy buffer views
    ├── Exception translation
    └── Property exposure
          ↓
Core Engine (C++)
    ├── Stream management (3 concurrent)
    ├── Memory pools (pinned host/device)
    └── CUDA Graph orchestration
          ↓
CUDA Layer
    ├── cuFFT plans
    ├── Custom kernels (window, magnitude)
    └── Async memory operations
```

### Key Design Decisions

1. **3-Stream Concurrency**: Overlaps H2D, compute, D2H transfers
2. **CUDA Graphs**: Reduces kernel launch overhead to <10 μs
3. **Pinned Memory**: Enables async transfers and zero-copy Python access
4. **PIMPL Pattern**: Hides CUDA dependencies from header files

## Build System

### CMake Structure

```cmake
ionosense_hpc/
├── CMakeLists.txt          # Main build configuration
├── CMakePresets.json       # Platform-specific presets
├── src/
│   ├── fft_engine.cpp     # Host orchestration
│   └── ops_fft.cu         # CUDA kernels
├── bindings/
│   └── bindings.cpp       # Pybind11 wrapper
└── tests/
    └── test_fft_engine.cpp # GoogleTest suite
```

### Build Options

```bash
# Debug build with symbols
cmake --preset linux-debug

# Release with all optimizations
cmake --preset linux-rel

# Custom options
cmake -DIONO_WITH_GRAPHS=OFF  # Disable CUDA Graphs
cmake -DIONO_WITH_PYTHON=OFF  # Skip Python bindings
cmake -DCMAKE_CUDA_ARCHITECTURES="75;86"  # Target specific GPUs
```

### Platform Notes

**Linux/WSL**:
- Uses GCC 14 from conda-forge
- Links against static CUDA runtime

**Windows**:
- Uses VS2022 build tools (via conda)
- Copies CUDA DLLs to `.libs/windows/`
- Supports both Ninja and VS generators

## Code Organization

### C++ Core (`src/`, `include/`)

```cpp
// include/ionosense/fft_engine.hpp
class RtFftEngine {
public:
    // Public API - stable
    void execute_async(int stream_idx);
    void sync_stream(int stream_idx);
    
private:
    // PIMPL to hide CUDA types
    struct Impl;
    Impl* p_;
};

// src/fft_engine.cpp
struct RtFftEngine::Impl {
    // All CUDA resources here
    cudaStream_t streams_[3];
    cufftHandle plans_[3];
    // ...
};
```

### CUDA Kernels (`src/ops_fft.cu`)

```cuda
// Keep kernels simple and focused
__global__ void applyWindowKernel(float* data, const float* window, 
                                  int nfft, int batch) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= nfft * batch) return;
    
    int sample_idx = idx % nfft;
    data[idx] *= window[sample_idx];
}

// Thin wrapper for launch
void apply_window_async(float* d_data, const float* d_window,
                       int nfft, int batch, cudaStream_t stream) {
    dim3 threads(256);
    dim3 blocks((nfft * batch + threads.x - 1) / threads.x);
    applyWindowKernel<<<blocks, threads, 0, stream>>>(
        d_data, d_window, nfft, batch);
}
```

### Python Bindings (`bindings/bindings.cpp`)

```cpp
// Zero-copy numpy views
.def("pinned_input", [](RtFftEngine &self, int idx) {
    float* ptr = self.pinned_input(idx);
    return py::array_t<float>(/* buffer_info */);
})

// Property exposure
.def_property("use_graphs",
    &RtFftEngine::get_use_graphs,
    &RtFftEngine::set_use_graphs)
```

## Testing

### C++ Unit Tests

```bash
# Run all C++ tests
ctest --preset linux-tests

# Run specific test
./build/linux-rel/test_engine --gtest_filter=FftEngineTest.BufferAccess*

# With verbose output
ctest --preset linux-tests -V
```

### Python Tests

```bash
# Run all Python tests
pytest python/tests -v

# Run with coverage
pytest python/tests --cov=ionosense_hpc --cov-report=html

# Run specific test
pytest python/tests/test_engine.py::test_runtime_graph_toggle
```

### Integration Tests

```python
# python/tests/test_integration.py
def test_end_to_end_accuracy():
    """Validate against NumPy reference."""
    processor = FFTProcessor(fft_size=1024)
    
    # Known signal
    fs = 48000
    freq = 1000
    t = np.arange(1024) / fs
    signal = np.sin(2 * np.pi * freq * t).astype(np.float32)
    
    # Process
    gpu_result = processor.process(signal, signal)
    
    # Reference
    cpu_result = np.abs(np.fft.rfft(signal * np.hanning(1024)))
    
    # Compare
    rms_error = np.sqrt(np.mean((gpu_result[0] - cpu_result)**2))
    assert rms_error < 1e-5
```

## Profiling

### Nsight Systems (Timeline)

```bash
# Profile with NVTX markers
./scripts/cli.sh profile nsys raw_throughput -n 8192

# Open in GUI
nsys-ui build/nsight_reports/nsys_reports/raw_throughput_*.nsys-rep
```

### Nsight Compute (Kernel Analysis)

```bash
# Profile kernels
./scripts/cli.sh profile ncu verify_accuracy -n 4096

# Specific kernel
ncu --kernel-name applyWindowKernel --set full python benchmarks/fft/verify_accuracy.py
```

### Python Profiling

```python
# Add to benchmark scripts
from ionosense_hpc.core.profiling import nvtx_range

with nvtx_range("critical_section"):
    result = processor.process(data)
```

## Contributing

### Development Setup

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/ionosense-hpc-lib.git
cd ionosense-hpc-lib

# Create feature branch
git checkout -b feature/your-feature

# Setup pre-commit hooks (future)
pre-commit install
```

### Code Style

**C++**:
- Follow Google C++ Style Guide
- Use `snake_case` for variables, `PascalCase` for classes
- Keep lines under 100 characters
- Document with Doxygen-style comments

**Python**:
- Follow PEP 8
- Use type hints for public APIs
- Docstrings in NumPy style
- Black formatter (line length 100)

**CUDA**:
- Kernel names end with `Kernel`
- Use `__restrict__` for pointer arguments
- Check bounds explicitly
- Prefer `float` over `double` for performance

### Commit Messages

```
type(scope): brief description

Longer explanation if needed. Reference issues.

Fixes #123
```

Types: `feat`, `fix`, `docs`, `test`, `perf`, `refactor`, `build`

### Pull Request Process

1. **Create PR** from feature branch
2. **Pass CI** - all tests must pass
3. **Benchmarks** - include performance impact
4. **Review** - address feedback
5. **Squash merge** - maintain clean history

## Debugging

### CUDA Errors

```bash
# Enable detailed CUDA errors
export CUDA_LAUNCH_BLOCKING=1
./scripts/cli.sh test

# Check for memory leaks
cuda-memcheck python python/tests/test_engine.py
```

### Python Debugging

```python
# Enable verbose engine output
engine = RtFftEngine(4096, 32, use_graphs=True, verbose=True)

# Use pdb
import pdb; pdb.set_trace()
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `cudaErrorInvalidDevice` | Check GPU availability with `nvidia-smi` |
| `cufftInvalidPlan` | Ensure FFT size is power of 2 |
| Import error on Windows | Check `.libs/windows/` for CUDA DLLs |
| Segfault in tests | Run with `cuda-gdb` or check buffer sizes |

## Performance Optimization

### Current Bottlenecks

1. **Memory Transfers**: ~40% of latency
   - Solution: Larger batches, persistent kernels
   
2. **Kernel Launch**: ~15% without graphs
   - Solution: CUDA Graphs (implemented)
   
3. **cuFFT Planning**: One-time cost
   - Solution: Plan reuse (implemented)

### Future Optimizations

- **Persistent Kernels**: Reduce launch overhead further
- **Tensor Cores**: Mixed precision for magnitude calculation
- **Multi-GPU**: Distribute across multiple devices
- **NVSHMEM**: Direct GPU-to-GPU communication

## Release Process

```bash
# 1. Update version
# python/ionosense_hpc/__init__.py
__version__ = "0.1.0"

# 2. Run full test suite
./scripts/cli.sh test
pytest python/tests --cov=ionosense_hpc

# 3. Benchmark
./scripts/cli.sh bench raw_throughput
./scripts/cli.sh bench verify_accuracy

# 4. Tag release
git tag -a v0.1.0 -m "Release v0.1.0: Feature description"
git push origin v0.1.0

# 5. Build wheels (future automation)
python -m build --wheel python/
```

## Resources

- [CUDA Programming Guide](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)
- [cuFFT Documentation](https://docs.nvidia.com/cuda/cufft/)
- [CUDA Graphs](https://developer.nvidia.com/blog/cuda-graphs/)
- [Pybind11 Documentation](https://pybind11.readthedocs.io/)