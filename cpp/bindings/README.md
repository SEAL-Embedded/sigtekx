# Python Bindings for Ionosense HPC Library

## Overview

This directory contains the pybind11 bindings that expose the C++ CUDA FFT engine to Python, enabling seamless integration with scientific Python workflows including NumPy, pandas, and visualization libraries.

## Architecture

The Python bindings follow a clean, direct design:

1. **Direct C++ Bindings**: pybind11 wrappers expose `BatchExecutor` and `StreamingExecutor` classes
2. **Python Wrapper**: High-level `Engine` class provides NumPy array handling and Pythonic interface

### Key Design Decisions

- **Zero-Copy Data Transfer**: Where possible, NumPy arrays are accessed directly without copying
- **Exception Safety**: C++ exceptions are properly translated to Python exceptions
- **Memory Management**: RAII principles ensure proper cleanup of CUDA resources
- **Type Safety**: Strong typing with automatic NumPy dtype validation

## Files

### `bindings.cpp`
Main pybind11 module definition exposing:

- `BatchExecutor` - High-throughput batch processing
- `StreamingExecutor` - Low-latency streaming (v0.9.4+)
- `ExecutorConfig` - Executor configuration (extends SignalConfig)
- `SignalConfig` - Base signal configuration parameters
- `StageConfig` - Processing stage configuration
- `ProcessingStats` - Performance metrics
- Utility functions for device management (`get_available_devices`, `select_best_device`)

## API Reference

### _native Module (pybind11 bindings)

```python
from sigtekx.core import _native

executor = _native.BatchExecutor()
config = _native.ExecutorConfig()
config.nfft = 1024
config.batch = 2
engine.initialize(config)

# Process NumPy array
import numpy as np
input_data = np.random.randn(2048).astype(np.float32)
spectrum = engine.process(input_data)  # Returns shape (batch, num_bins)
```

#### Methods

- `initialize(config: EngineConfig)` - Initialize engine with configuration
- `process(input: np.ndarray) -> np.ndarray` - Process input signal, return magnitude spectrum
- `reset()` - Reset engine to uninitialized state
- `synchronize()` - Synchronize all CUDA streams
- `get_stats() -> ProcessingStats` - Get latest performance metrics
- `get_runtime_info() -> RuntimeInfo` - Get CUDA environment info
- `is_initialized -> bool` - Check initialization status

#### Input Requirements

- **Data Type**: `np.float32` (automatic casting applied)
- **Shape**: 1D array with length `nfft * batch`
- **Memory Layout**: C-contiguous (automatic conversion if needed)

#### Output Format

- **Data Type**: `np.float32`
- **Shape**: `(batch, num_output_bins)` where `num_output_bins = nfft//2 + 1`
- **Units**: Magnitude spectrum (linear scale)

## Configuration Classes

### EngineConfig

Controls overall engine behavior:

```python
config = EngineConfig()
config.nfft = 1024              # FFT size (power of 2)
config.batch = 2                # Number of parallel channels
config.overlap = 0.5            # Frame overlap [0.0, 1.0)
config.sample_rate_hz = 48000   # Input sample rate
config.stream_count = 3         # CUDA streams for parallelism
config.warmup_iters = 1         # GPU warmup iterations
```

### StageConfig

Controls individual processing stages:

```python
from sigtekx.core import StageConfig, WindowType, ScalePolicy

stage_config = StageConfig()
stage_config.nfft = 1024
stage_config.window_type = WindowType.HANN
stage_config.scale_policy = ScalePolicy.ONE_OVER_N
```

## Performance Considerations

### Memory Management

- **Pinned Memory**: Engine uses page-locked host memory for optimal transfer performance
- **Buffer Reuse**: Internal buffers are reused across process() calls
- **GPU Memory**: Device memory is pre-allocated during initialization

### Threading

- **GIL Release**: Processing calls release Python's GIL for parallel execution
- **Stream Parallelism**: Multiple CUDA streams enable concurrent H2D, compute, and D2H operations
- **Asynchronous Operations**: All CUDA operations are asynchronous when possible

### Optimization Guidelines

```python
# Good: Reuse executor instance
executor = _native.BatchExecutor()
executor.initialize(config)
for data_batch in signal_stream:
    spectrum = executor.process(data_batch)

# Avoid: Recreating executor frequently
for data_batch in signal_stream:
    executor = _native.BatchExecutor()  # Expensive!
    executor.initialize(config)
    spectrum = executor.process(data_batch)
```

## Error Handling

All C++ exceptions are translated to appropriate Python exceptions:

- `RuntimeError` - Engine initialization or processing errors
- `ValueError` - Invalid input array dimensions or configuration
- `CudaException` - CUDA runtime errors (custom exception type)
- `CufftException` - cuFFT library errors (custom exception type)

## Build Integration

The bindings are compiled as part of the main CMake build:

```bash
# Build with CMake presets
cmake --preset linux-rel
cmake --build build/linux-rel --target _engine

# Python package installation
pip install -e python/
```

## Testing

Python bindings are tested via pytest:

```bash
pytest tests/test_bindings.py -v
```

Test coverage includes:
- NumPy array conversion accuracy
- Error handling for invalid inputs  
- Memory leak detection
- Performance regression tests

## Debugging

### Memory Issues

```python
# Enable CUDA synchronous mode for debugging
import os
os.environ['CUDA_LAUNCH_BLOCKING'] = '1'
```

### Profiling

```python
engine.set_profiling_enabled(True)
stats = engine.get_stats()
print(f"Latency: {stats.latency_us:.2f} μs")
print(f"Throughput: {stats.throughput_gbps:.2f} GB/s")
```

## Version Compatibility

- **Python**: 3.11+ (managed via Conda)
- **NumPy**: 1.26 (specified in pyproject.toml)
- **pybind11**: 2.11+ (build dependency)
- **CUDA**: 13.0+ (runtime requirement)

## References

1. pybind11 documentation: https://pybind11.readthedocs.io/
2. NumPy C API: https://numpy.org/doc/stable/reference/c-api/
3. CUDA Python interoperability: https://docs.nvidia.com/cuda/cuda-runtime-api/
