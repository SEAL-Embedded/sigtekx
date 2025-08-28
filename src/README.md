# Source Code Architecture

Core C++/CUDA implementation of the ionosense FFT engine.

## File Structure

```
src/
├── fft_engine.cpp    # Host orchestration, stream management, memory lifecycle
└── ops_fft.cu        # CUDA kernel implementations
```

## Component Responsibilities

### fft_engine.cpp (Host Control)

**Primary Role**: Orchestrates the multi-stream FFT pipeline without exposing CUDA types to headers.

**Key Components**:

```cpp
struct RtFftEngine::Impl {
    // Constants
    static constexpr int kNumStreams = 3;  // H2D, Compute, D2H overlap
    
    // Per-stream resources
    cudaStream_t streams_[kNumStreams];
    cufftHandle plans_[kNumStreams];
    float* h_inputs_[kNumStreams];   // Pinned host memory
    float* h_outputs_[kNumStreams];  // Pinned host memory
    
    // CUDA Graph resources
    cudaGraph_t graphs_[kNumStreams];
    cudaGraphExec_t graphs_execs_[kNumStreams];
};
```

**Pipeline Stages**:
1. H2D Transfer → `cudaMemcpyAsync(..., cudaMemcpyHostToDevice)`
2. Window Application → `ops::apply_window_async()`
3. FFT Execution → `cufftExecR2C()`
4. Magnitude Calculation → `ops::magnitude_async()`
5. D2H Transfer → `cudaMemcpyAsync(..., cudaMemcpyDeviceToHost)`

**Graph Capture**:
```cpp
void capture_graph(int idx) {
    cudaStreamBeginCapture(streams_[idx], cudaStreamCaptureModeGlobal);
    execute_pipeline_operations(idx);  // Records all operations
    cudaStreamEndCapture(streams_[idx], &graphs_[idx]);
    cudaGraphInstantiate(&graphs_execs_[idx], graphs_[idx], ...);
}
```

### ops_fft.cu (CUDA Kernels)

**Design Philosophy**: Kernels are kept minimal with single responsibilities. Complex orchestration stays in the host code.

**Kernel Specifications**:

| Kernel | Purpose | Grid Config | Memory Pattern |
|--------|---------|-------------|----------------|
| `applyWindowKernel` | Element-wise multiply | 1D, 256 threads/block | Coalesced read/write |
| `magnitudeKernel` | Complex→magnitude | 1D, 256 threads/block | Coalesced read, write |

**Launch Configuration**:
```cuda
// Optimal for Ampere/Ada architectures
dim3 threads(256);  // 8 warps per block
dim3 blocks((total_elements + threads.x - 1) / threads.x);
```

## Memory Management

### Allocation Strategy

```cpp
// Per-stream allocation sizes
size_t input_bytes = sizeof(float) * nfft * batch;        // Real input
size_t spec_bytes = sizeof(cufftComplex) * bins * batch;  // Complex spectrum
size_t output_bytes = sizeof(float) * bins * batch;       // Magnitude output

// Host (pinned)
cudaHostAlloc(&h_inputs_[i], input_bytes, cudaHostAllocDefault);

// Device
cudaMalloc(&d_inputs_[i], input_bytes);
cudaMalloc(&d_specs_[i], spec_bytes);
cudaMalloc(&d_mags_[i], output_bytes);
```

### Memory Pool Configuration (CUDA Graphs)

```cpp
if (use_graphs_) {
    cudaMemPool_t mempool;
    cudaDeviceGetDefaultMemPool(&mempool, 0);
    uint64_t threshold = UINT64_MAX;  // Never release
    cudaMemPoolSetAttribute(mempool, 
        cudaMemPoolAttrReleaseThreshold, &threshold);
}
```

## Stream Synchronization

### Event-Based Synchronization

```cpp
// Each stream has an event for lightweight sync
cudaEventCreateWithFlags(&events_[i], cudaEventDisableTiming);

// After work submission
cudaEventRecord(events_[idx], streams_[idx]);

// Client synchronization
cudaEventSynchronize(events_[idx]);  // Lighter than cudaStreamSynchronize
```

### Stream Rotation Pattern

```cpp
// Round-robin across streams for continuous processing
stream_idx = (stream_idx + 1) % kNumStreams;
```

## Error Handling

### Macro Strategy

```cpp
#define CUDA_CHECK(err) do { \
    cudaError_t e = (err); \
    if (e != cudaSuccess) { \
        fprintf(stderr, "CUDA Error in %s at line %d: %s\n", \
                __FILE__, __LINE__, cudaGetErrorString(e)); \
        throw std::runtime_error(cudaGetErrorString(e)); \
    } \
} while(0)
```

### Exception Safety

- All allocations in constructor's init function
- RAII via destructor cleanup
- No naked `new`/`delete` for CUDA resources
- Graph resources destroyed before stream resources

## Performance Considerations

### Optimization Choices

1. **Pinned Memory**: 2x faster transfers vs pageable
2. **Async Operations**: Complete pipeline overlap
3. **Stream Reuse**: Amortizes stream creation cost
4. **Plan Reuse**: cuFFT plans created once
5. **Graph Mode**: Reduces launch overhead from ~30μs to ~5μs

### Profiling Hooks

```cpp
// Conditional profiling events
if (enable_profiling_) {
    cudaEventRecord(prof_start_[idx], streams_[idx]);
    // ... work ...
    cudaEventRecord(prof_end_[idx], streams_[idx]);
    
    // Later: retrieve timing
    float ms;
    cudaEventElapsedTime(&ms, prof_start_[idx], prof_end_[idx]);
}
```

## Build Dependencies

- CUDA Toolkit ≥12.0 (cuFFT, CUDA Runtime)
- C++17 compiler
- CMake ≥3.26

## Testing

Unit tests in `tests/test_fft_engine.cpp` cover:
- Stream management
- Buffer allocation
- Graph capture/execution
- Error conditions

## Critical Invariants

1. `batch % 2 == 0` - Dual-channel requirement
2. `nfft` is power of 2 - cuFFT requirement  
3. Graph capture after warmup - CUDA requirement
4. Streams synchronized before cleanup - Safety requirement