# Ionosense HPC - Architecture Documentation

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![CUDA 13.0+](https://img.shields.io/badge/CUDA-13.0+-green.svg)](https://developer.nvidia.com/cuda-toolkit)
[![IEEE Standards](https://img.shields.io/badge/IEEE-Standards-blue.svg)](https://www.ieee.org/)

High-performance CUDA FFT engine architecture following Research Software Engineering (RSE) best practices and IEEE documentation standards.

## Table of Contents

1. [Introduction](#introduction)
2. [Architecture Overview](#architecture-overview)
3. [Class Architecture](#class-architecture)
4. [Processing Pipeline](#processing-pipeline)
5. [Component Architecture](#component-architecture)
6. [Memory Management](#memory-management)
7. [Design Patterns](#design-patterns)
8. [Performance Considerations](#performance-considerations)
9. [Implementation Guidelines](#implementation-guidelines)

## Introduction

The Ionosense HPC library implements a sophisticated, production-ready CUDA-accelerated signal processing engine optimized for real-time applications. The architecture emphasizes:

- **High Performance**: Sub-200μs latency with multi-GB/s throughput
- **Resource Safety**: RAII-based automatic resource management
- **Modularity**: Flexible pipeline composition via Strategy pattern
- **Maintainability**: Clean separation of concerns with Pimpl idiom
- **Testability**: Comprehensive unit and integration testing
- **Professional Standards**: IEEE-compliant documentation and RSE practices

### Key Performance Characteristics

| Metric | Value | Context |
|--------|-------|---------|
| Latency | < 200μs | End-to-end processing (1024-point FFT) |
| Throughput | > 10 GB/s | Sustained data processing rate |
| Memory Bandwidth | ~25 GB/s | PCIe transfers with pinned memory |
| Concurrent Streams | 3 | H2D, Compute, D2H pipeline overlap |
| Batch Processing | 2-128 | Configurable batch sizes |

## Architecture Overview

The library follows a layered architecture with clear separation between host and device code, public APIs, and internal implementation details.

### Design Principles

1. **RAII Resource Management**: All CUDA resources (streams, events, memory) use RAII wrappers
2. **Pimpl Idiom**: Public headers hide CUDA dependencies for clean client code
3. **Strategy Pattern**: Flexible processing pipeline composition
4. **Exception Safety**: Strong exception guarantees throughout
5. **Zero-Copy Operations**: Minimize host-device transfers via pinned memory staging

## Class Architecture

The core architecture centers around the `ResearchEngine` class implementing the `IPipelineEngine` interface, with modular processing stages and comprehensive CUDA resource management.

![Class Architecture](diagrams/generated/class-architecture.svg)

*Figure 1: Complete class hierarchy showing design patterns and relationships*

### Core Components

#### Public API Layer
- **`IPipelineEngine`**: Abstract interface defining the processing contract
- **`ResearchEngine`**: Main implementation using Pimpl idiom to hide CUDA dependencies
- **`ResearchEngine::Impl`**: Private implementation containing all CUDA-specific code

#### Processing Stage Layer
- **`IProcessingStage`**: Strategy pattern interface for pipeline stages
- **`WindowStage`**: Applies window functions (Hann, Hamming, etc.)
- **`FFTStage`**: CUDA FFT computation via cuFFT library
- **`MagnitudeStage`**: Complex-to-magnitude conversion
- **`StageFactory`**: Creates and configures processing stages

#### CUDA Resource Management
- **`CudaStream`**: RAII wrapper for CUDA streams with move semantics
- **`CudaEvent`**: RAII wrapper for CUDA events with timing support
- **`DeviceBuffer<T>`**: Type-safe device memory management
- **`PinnedHostBuffer<T>`**: Page-locked host memory for fast transfers
- **`CufftPlan`**: Manages cuFFT plans and work areas

## Processing Pipeline

The processing pipeline implements a sophisticated asynchronous execution model using multiple CUDA streams for optimal GPU utilization.

![Processing Pipeline](diagrams/generated/sequence-pipeline.svg)

*Figure 2: Asynchronous processing pipeline showing stream overlap and synchronization*

### Pipeline Stages

1. **Host-to-Device Transfer (Stream 0)**
   - Asynchronous copy from host to GPU memory
   - Uses pinned memory staging for maximum bandwidth
   - Records completion event for dependency tracking

2. **Compute Pipeline (Stream 1)**
   - **Window Stage**: Apply window function (Hann, Hamming, etc.)
   - **FFT Stage**: Real-to-complex FFT using cuFFT
   - **Magnitude Stage**: Complex magnitude calculation
   - All operations use the same stream for optimal scheduling

3. **Device-to-Host Transfer (Stream 2)**
   - Asynchronous copy of results back to host
   - Waits for compute completion event
   - Returns control when transfer completes

### Synchronization Model

- **Event-based Dependencies**: CUDA events coordinate stream execution
- **Non-blocking Overlap**: H2D, compute, and D2H operations overlap
- **Deterministic Timing**: Precise latency measurement using CUDA events
- **Error Propagation**: CUDA errors propagated as C++ exceptions

## Component Architecture

The component architecture shows the relationship between major subsystems and their dependencies.

![Component Architecture](diagrams/generated/component-architecture.svg)

*Figure 3: High-level component relationships and data flow*

### Layer Responsibilities

#### Python Bindings Layer
- **PyResearchEngine**: Python wrapper providing NumPy integration
- **pybind11 Module**: Automatic type conversion and error handling

#### C++ Public API
- **ResearchEngine**: Main user interface
- **Configuration**: Type-safe configuration management
- **Statistics**: Performance metrics collection

#### Processing Pipeline
- **Modular Stages**: Pluggable processing components
- **Stage Factory**: Dynamic stage creation and configuration

#### CUDA Resource Management
- **Memory Management**: Safe allocation/deallocation
- **Stream Management**: Asynchronous execution coordination
- **Plan Management**: cuFFT plan optimization and reuse

## Memory Management

The memory management system implements a sophisticated multi-level hierarchy optimized for high-throughput streaming applications.

![Memory Management](diagrams/generated/memory-management.svg)

*Figure 4: Memory layout and data flow patterns*

### Memory Hierarchy

#### Host Memory Space
- **Input/Output Buffers**: User-provided data arrays
- **Pinned Host Buffers**: Page-locked staging areas for fast PCIe transfers
- **Double Buffering**: Ping-pong buffers for continuous streaming

#### Device Memory Space
- **Input Buffers**: Raw signal data (float arrays)
- **Intermediate Buffers**: Complex FFT output (float2 arrays)
- **Output Buffers**: Final magnitude spectrum (float arrays)
- **Cached Resources**: Pre-computed window coefficients, cuFFT work areas

#### Transfer Optimization
- **Pinned Memory**: ~25 GB/s PCIe bandwidth via page-locked allocations
- **Asynchronous Copies**: Non-blocking transfers with stream synchronization
- **Memory Coalescing**: Optimized access patterns for GPU efficiency

### Memory Layout Details

| Buffer Type | Size Formula | Layout | Purpose |
|-------------|--------------|--------|---------|
| Input | `nfft * batch * sizeof(float)` | Interleaved | Raw time-domain samples |
| Intermediate | `(nfft/2+1) * batch * sizeof(float2)` | Complex | FFT output (Hermitian) |
| Output | `(nfft/2+1) * batch * sizeof(float)` | Real | Magnitude spectrum |
| Window | `nfft * sizeof(float)` | Linear | Cached coefficients |

## Design Patterns

### RAII (Resource Acquisition Is Initialization)

All CUDA resources use RAII wrappers ensuring deterministic cleanup:

```cpp
class CudaStream {
private:
    cudaStream_t stream_;
    bool owned_;

public:
    CudaStream() : owned_(true) {
        CUDA_CHECK(cudaStreamCreate(&stream_));
    }

    ~CudaStream() {
        if (owned_) {
            cudaStreamDestroy(stream_);  // Always called
        }
    }

    // Move-only semantics prevent accidental copying
    CudaStream(const CudaStream&) = delete;
    CudaStream& operator=(const CudaStream&) = delete;
    CudaStream(CudaStream&& other) noexcept;
    CudaStream& operator=(CudaStream&& other) noexcept;
};
```

### Pimpl (Pointer to Implementation)

The `ResearchEngine` uses Pimpl to hide CUDA dependencies from public headers:

```cpp
// Public header (clean, no CUDA includes)
class ResearchEngine : public IPipelineEngine {
private:
    class Impl;  // Forward declaration
    std::unique_ptr<Impl> pImpl;  // Hidden implementation

public:
    ResearchEngine();
    ~ResearchEngine();
    // ... public interface
};

// Private implementation (CUDA-specific)
class ResearchEngine::Impl {
private:
    std::vector<CudaStream> streams_;
    std::vector<DeviceBuffer<float>> buffers_;
    // ... CUDA resources
};
```

### Strategy Pattern

Processing stages implement a common interface for flexible pipeline composition:

```cpp
class IProcessingStage {
public:
    virtual ~IProcessingStage() = default;
    virtual void initialize(const StageConfig& config, cudaStream_t stream) = 0;
    virtual void process(void* input, void* output, size_t num_elements, cudaStream_t stream) = 0;
    virtual std::string name() const = 0;
    virtual bool supports_inplace() const = 0;
};

// Flexible pipeline construction
std::vector<std::unique_ptr<IProcessingStage>> pipeline;
pipeline.push_back(StageFactory::create(StageType::WINDOW));
pipeline.push_back(StageFactory::create(StageType::FFT));
pipeline.push_back(StageFactory::create(StageType::MAGNITUDE));
```

## Performance Considerations

### Latency Optimization

1. **Stream Overlap**: H2D, compute, and D2H operations execute concurrently
2. **Memory Coalescing**: Optimal GPU memory access patterns
3. **Batch Processing**: Amortize kernel launch overhead across multiple frames
4. **Pinned Memory**: Eliminate host memory pagination delays

### Throughput Optimization

1. **Double Buffering**: Continuous streaming without stalls
2. **Kernel Fusion**: Combine operations to reduce memory bandwidth
3. **Occupancy Tuning**: Optimize thread block dimensions for target GPU
4. **Work Area Reuse**: Cache cuFFT plans and temporary buffers

### Memory Efficiency

1. **In-place Operations**: Minimize memory allocations and copies
2. **Memory Pool**: Reuse allocations across processing frames
3. **Alignment**: Ensure optimal memory alignment for vectorized operations
4. **Shared Memory**: Utilize on-chip memory for frequently accessed data

## Implementation Guidelines

### Error Handling

```cpp
// CUDA error checking macro
#define CUDA_CHECK(call) do { \
    cudaError_t error = call; \
    if (error != cudaSuccess) { \
        throw CudaException(error, #call, __FILE__, __LINE__); \
    } \
} while(0)

// Strong exception safety guarantee
void ResearchEngine::Impl::process(const float* input, float* output, size_t num_samples) {
    try {
        // All operations or none
        copy_to_device(input, num_samples);
        execute_pipeline();
        copy_from_device(output);
    } catch (...) {
        // Automatic cleanup via RAII
        throw;  // Re-throw for caller
    }
}
```

### Thread Safety

- **Single-threaded Design**: Each engine instance is not thread-safe
- **Multiple Instances**: Create separate engines for concurrent processing
- **CUDA Context**: Each thread should use separate CUDA contexts
- **Resource Isolation**: No shared global state between instances

### Testing Strategy

1. **Unit Tests**: Individual components with mock dependencies
2. **Integration Tests**: End-to-end pipeline validation
3. **Performance Tests**: Latency and throughput benchmarking
4. **Regression Tests**: Automated CI/CD with baseline comparisons
5. **Hardware Tests**: Validation across different GPU architectures

### Documentation Standards

This documentation follows IEEE standards for software architecture documentation:

- **IEEE 1016**: Software Design Descriptions
- **IEEE 1471**: Architecture Description
- **IEEE 829**: Software Test Documentation

All diagrams are generated from PlantUML source files located in `docs/diagrams/` to ensure maintainability and version control integration.

---

**Author**: Kevin Rahsaz
**Version**: 0.9.2
**Last Updated**: September 2025
**License**: MIT

For implementation details, see [API Documentation](API.md) and [Development Guide](DEVELOPMENT.md).