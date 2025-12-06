# SigTekX Library - Public C++ API

## Overview

This directory contains the public C++ header files that define the core API for the SigTekX High-Performance Computing FFT engine. The headers are designed following modern C++ best practices and Research Software Engineering (RSE) principles to provide a clean, efficient, and maintainable interface for CUDA-accelerated signal processing.

## Architecture

The API follows several key design patterns to ensure robustness and performance:

- **Pimpl Idiom**: Implementation details are hidden behind private implementation classes, reducing compile-time dependencies and providing a stable ABI
- **RAII (Resource Acquisition Is Initialization)**: All CUDA resources are automatically managed through C++ destructors
- **Strategy Pattern**: Processing stages are interchangeable components that implement a common interface
- **Modern C++17**: Leveraging move semantics, smart pointers, and exception safety

## Header Files

### `research_engine.hpp` - Main Processing Engine

The primary interface for the signal processing pipeline.

#### Key Classes

**`IPipelineEngine`** - Abstract base class defining the engine contract:
```cpp
class IPipelineEngine {
public:
    virtual void initialize(const EngineConfig& config) = 0;
    virtual void process(const float* input, float* output, size_t num_samples) = 0;
    virtual ProcessingStats get_stats() const = 0;
    virtual RuntimeInfo get_runtime_info() const = 0;
    virtual bool is_initialized() const = 0;
};
```

**Executors** - Concrete implementations for different processing modes:
- **`BatchExecutor`** - High-throughput batch processing
- **`StreamingExecutor`** - Low-latency streaming (v0.9.4+)

Exposed via pybind11 in the `_native` module:
```python
import sigtekx.core._native as _native

# Create and configure executor
executor = _native.BatchExecutor()
config = _native.ExecutorConfig()
config.nfft = 1024
config.channels = 4
config.mode = _native.ExecutionMode.BATCH
executor.initialize(config)

# Process data
output = executor.process(input_data)
stats = executor.get_stats()
```

#### Configuration Structures

**`EngineConfig`** - Global engine parameters:
- `nfft`: FFT size (must be power of 2)
- `batch`: Number of parallel processing channels
- `overlap`: Frame overlap factor [0.0, 1.0)
- `sample_rate_hz`: Input signal sampling rate
- `stream_count`: Number of CUDA streams for parallelism
- `pinned_buffer_count`: Host memory buffers for async operations

**`RuntimeInfo`** - CUDA environment information:
- Device capabilities and memory status
- CUDA runtime and driver versions
- cuFFT library version information

### `processing_stage.hpp` - Modular Pipeline Components

Defines the Strategy pattern implementation for pipeline stages.

#### Core Interfaces

**`IProcessingStage`** - Abstract stage interface:
```cpp
class IProcessingStage {
public:
    virtual void initialize(const StageConfig& config, cudaStream_t stream) = 0;
    virtual void process(void* input, void* output, size_t num_elements, cudaStream_t stream) = 0;
    virtual std::string name() const = 0;
    virtual bool supports_inplace() const = 0;
    virtual size_t get_workspace_size() const = 0;
};
```

#### Concrete Stages

**`WindowStage`** - Applies windowing functions (Hann, etc.):
```cpp
auto window_stage = std::make_unique<WindowStage>();
StageConfig config{};
config.nfft = 1024;
config.window_type = StageConfig::WindowType::HANN;
window_stage->initialize(config, stream);
```

**`FFTStage`** - cuFFT-based Fast Fourier Transform:
- Real-to-complex (R2C) transforms
- Batched processing for multiple channels
- Optimized memory layout for performance

**`MagnitudeStage`** - Complex-to-magnitude conversion:
- Configurable scaling policies (none, 1/N, 1/√N)
- Vectorized CUDA kernels for high throughput

#### Factory Pattern

**`StageFactory`** - Centralized stage creation:
```cpp
// Create individual stages
auto fft_stage = StageFactory::create(StageType::FFT);

// Create complete pipeline
auto pipeline = StageFactory::create_default_pipeline();
```

#### Configuration Options

**`StageConfig`** - Unified stage configuration:
- Window parameters (`WindowType`, `WindowNorm`)
- Scaling policies (`ScalePolicy`)
- Output modes (`OutputMode`)
- Performance hints (`inplace`, `warmup_iters`)

### `cuda_wrappers.hpp` - RAII CUDA Resource Management

Provides exception-safe, move-only wrappers for CUDA resources.

#### Resource Wrappers

**`CudaStream`** - CUDA stream management:
```cpp
CudaStream stream;  // Creates non-blocking stream
stream.synchronize();  // Block until completion
bool ready = stream.query();  // Non-blocking status check
```

**`CudaEvent`** - Event-based synchronization:
```cpp
CudaEvent event;
event.record(stream.get());
event.synchronize();
float elapsed = event.elapsed_ms(start_event);
```

**`DeviceBuffer<T>`** - GPU memory management:
```cpp
DeviceBuffer<float> buffer(1024);  // Allocate 1024 floats
buffer.copy_from_host(host_data, 1024, stream.get());
buffer.copy_to_host(host_result, 1024, stream.get());
```

**`PinnedHostBuffer<T>`** - Page-locked host memory:
```cpp
PinnedHostBuffer<float> pinned(1024);
float* data = pinned.get();  // Direct access
// Faster H2D/D2H transfers compared to pageable memory
```

**`CufftPlan`** - cuFFT plan management:
```cpp
CufftPlan plan;
int n[] = {1024};
plan.create_plan_many(1, n, nullptr, 1, 1024, nullptr, 1, 513, CUFFT_R2C, 2, stream.get());
plan.exec_r2c(input_buffer.get(), output_buffer.get());
```

#### Exception Handling

**`CudaException`** and **`CufftException`** - Automatic error checking:
```cpp
// Automatic error checking with macros
IONO_CUDA_CHECK(cudaMemcpy(dst, src, size, cudaMemcpyDeviceToHost));
IONO_CUFFT_CHECK(cufftExecR2C(plan, input, output));

// Detailed error messages with file/line information
```

## Design Principles

### Memory Management

- **RAII Everywhere**: No manual resource cleanup required
- **Move Semantics**: Efficient transfer of resource ownership
- **Exception Safety**: Strong guarantee - operations either succeed or leave state unchanged
- **Zero-Copy**: Direct pointer access where safe and efficient

### Performance Optimization

- **Asynchronous Operations**: All CUDA operations are stream-based and non-blocking
- **Memory Coalescing**: Data layouts optimized for GPU memory access patterns
- **Minimal API Overhead**: Direct pointer interfaces avoid unnecessary conversions
- **Resource Reuse**: Buffers and plans are reused across multiple process calls

### Error Handling

- **Exception-Based**: All errors converted to C++ exceptions with detailed context
- **Fail-Fast**: Invalid configurations detected at initialization time
- **Debuggable**: Clear error messages with file/line information

## Integration Guidelines

### CMake Integration

```cmake
find_package(sigtekx REQUIRED)
target_link_libraries(your_target sigtekx::core)
```

### Header Dependencies

The headers have minimal external dependencies:
- Standard C++17 library
- CUDA Runtime API (`cuda_runtime.h`)
- cuFFT library (`cufft.h`)

### Platform Support

- **Linux**: Primary development platform (Ubuntu 20.04+)
- **Windows**: Full support via MSVC and CUDA toolkit
- **WSL2**: Recommended for Windows development

## Usage Examples

### Basic Processing Pipeline

```cpp
#include <sigtekx/research_engine.hpp>
#include <vector>

// Configure engine
sigtekx::EngineConfig config{};
config.nfft = 1024;
config.batch = 2;
config.sample_rate_hz = 48000;

// Create and initialize
auto engine = sigtekx::create_engine("research");
engine->initialize(config);

// Process data
std::vector<float> input(2048);  // 1024 * 2 samples
std::vector<float> output(1026); // (1024/2+1) * 2 spectrum bins

// Fill input with signal data...
engine->process(input.data(), output.data(), input.size());

// Check performance
auto stats = engine->get_stats();
std::cout << "Latency: " << stats.latency_us << " μs\n";
```

### Custom Pipeline Construction

```cpp
#include <sigtekx/processing_stage.hpp>

using namespace sigtekx;

// Create custom pipeline
std::vector<std::unique_ptr<IProcessingStage>> stages;
stages.push_back(StageFactory::create(StageType::WINDOW));
stages.push_back(StageFactory::create(StageType::FFT));
stages.push_back(StageFactory::create(StageType::MAGNITUDE));

// Configure stages
StageConfig config{};
config.nfft = 2048;
config.window_type = StageConfig::WindowType::HANN;
config.scale_policy = StageConfig::ScalePolicy::ONE_OVER_N;

CudaStream stream;
for (auto& stage : stages) {
    stage->initialize(config, stream.get());
}
```

### Direct CUDA Resource Management

```cpp
#include <sigtekx/cuda_wrappers.hpp>

using namespace sigtekx;

// Create resources
CudaStream stream;
DeviceBuffer<float> d_input(1024);
DeviceBuffer<float2> d_output(513);
CudaEvent processing_done;

// Asynchronous processing
d_input.copy_from_host(host_input, 1024, stream.get());
// ... kernel launches on stream ...
processing_done.record(stream.get());

// Overlap computation with transfers
processing_done.synchronize();
d_output.copy_to_host(host_output, 513, stream.get());
```

## Performance Targets

The API is designed to meet stringent real-time requirements:

- **Latency**: <200 μs per dual-channel FFT pair (target <100 μs)
- **Throughput**: >10 GB/s memory bandwidth utilization
- **Accuracy**: IEEE 754 float32 precision, validated against FFTW/MKL references
- **Reliability**: 24/7 continuous operation capability

## Validation and Testing

All public API functions are validated through:
- Unit tests (GoogleTest framework)
- Integration tests with synthetic signals
- Accuracy comparisons with reference implementations
- Performance regression testing
- Memory leak detection (Valgrind, CUDA-MEMCHECK)

## References

1. **CUDA Programming Guide**: https://docs.nvidia.com/cuda/cuda-c-programming-guide/
2. **cuFFT Library Documentation**: https://docs.nvidia.com/cuda/cufft/
3. **Modern C++ Design**: Alexandrescu, A. (2001). Addison-Wesley.
4. **IEEE 754-2019**: IEEE Standard for Floating-Point Arithmetic
5. **Research Software Engineering**: Wilson, G. et al. (2014). Best Practices for Scientific Computing. PLOS Biology.