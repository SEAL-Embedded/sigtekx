# Ionosense HPC Architecture Refactor: Implementation Plan v0.9.3

## Executive Summary

Transform the ionosense-hpc-lib from a monolithic `ResearchEngine` into a flexible, composable HPC toolkit by separating the signal processing pipeline definition (the "what") from the execution strategy (the "how"). This branch (v0.9.3) will establish the new architecture without maintaining backwards compatibility.

### Core Principle: Pipeline vs Executor Separation
- **Pipeline**: Chain of `IProcessingStage` objects defining transformations
- **Executor**: Strategy for running the pipeline (batch, streaming, graph-based, etc.)
- **Engine**: User-facing facade combining pipeline + executor + configuration

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                     │
│  (User code - Python or C++)                            │
└────────────┬────────────────────────┬───────────────────┘
             │                        │
┌────────────▼──────────┐  ┌─────────▼──────────────────┐
│    Facade Engines     │  │   Direct Toolkit Usage     │
│  - ResearchEngine     │  │  - Custom pipelines        │
│  - AntennaEngine      │  │  - Custom executors        │
└────────────┬──────────┘  └─────────┬──────────────────┘
             │                        │
┌────────────▼────────────────────────▼───────────────────┐
│                    Toolkit Layer                        │
│  ┌──────────────────┐      ┌─────────────────┐        │
│  │ Pipeline Builder │      │    Executors     │        │
│  └──────────────────┘      └─────────────────┘        │
│  ┌──────────────────────────────────────────┐         │
│  │            Processing Stages             │         │
│  └──────────────────────────────────────────┘         │
└──────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────┐
│                 CUDA Resource Layer                    │
│  (Streams, Events, Buffers, cuFFT Plans)              │
└──────────────────────────────────────────────────────┘
```

## Detailed Design

### 1. Core Interfaces

#### IPipelineExecutor Interface
```cpp
// cpp/include/ionosense/core/pipeline_executor.hpp
class IPipelineExecutor {
public:
    virtual ~IPipelineExecutor() = default;
    
    // Lifecycle
    virtual void initialize(
        const ExecutorConfig& config,
        std::vector<std::unique_ptr<IProcessingStage>> stages) = 0;
    virtual void reset() = 0;
    
    // Execution
    virtual void submit(const float* input, float* output, 
                       size_t num_samples) = 0;
    virtual void submit_async(const float* input, size_t num_samples,
                             ResultCallback callback) = 0;
    virtual void synchronize() = 0;
    
    // Introspection
    virtual ProcessingStats get_stats() const = 0;
    virtual bool supports_streaming() const = 0;
    virtual size_t get_memory_usage() const = 0;
};
```

#### ExecutorConfig Structure
```cpp
struct ExecutorConfig : EngineConfig {
    // Inherits nfft, batch, overlap, etc.
    
    // Executor-specific settings
    enum class ExecutionMode {
        BATCH,           // Process complete batches
        STREAMING        // Continuous processing with ring buffer
    };
    ExecutionMode mode = ExecutionMode::BATCH;
    
    // Resource hints
    bool prefer_cuda_graphs = false;
    bool enable_profiling = false;
    int max_inflight_batches = 2;  // For streaming mode
};
```

### 2. Concrete Executor Implementations

#### BatchExecutor
- **Location**: `cpp/src/executors/batch_executor.cpp`
- **Responsibility**: Round-robin buffer management, stream orchestration
- **Owns**: CUDA streams, events, device buffers
- **Key Pattern**: Double/triple buffering with event-based synchronization
- **Implementation**: Extract current logic from `ResearchEngine::Impl`

#### StreamingExecutor
- **Location**: `cpp/src/executors/streaming_executor.cpp`
- **Responsibility**: Low-latency continuous processing
- **Key Features**:
  - Ring buffer for input accumulation
  - Callback-based output delivery
  - Minimal blocking operations
  - Optional CUDA graph optimization

### 3. Pipeline Management

#### PipelineBuilder
```cpp
// cpp/include/ionosense/core/pipeline_builder.hpp
class PipelineBuilder {
public:
    PipelineBuilder& add_stage(std::unique_ptr<IProcessingStage> stage);
    PipelineBuilder& add_window(StageConfig::WindowType type);
    PipelineBuilder& add_fft();
    PipelineBuilder& add_magnitude();
    PipelineBuilder& with_config(const StageConfig& config);
    
    // Validation
    bool validate(std::string& error_msg) const;
    size_t estimate_memory_usage() const;
    
    // Build
    std::vector<std::unique_ptr<IProcessingStage>> build();
    
private:
    std::vector<std::unique_ptr<IProcessingStage>> stages_;
    StageConfig config_;
};
```

### 4. Engine Classes (New Architecture)

#### ResearchEngine (Simplified Facade)
```cpp
class ResearchEngine {
    std::unique_ptr<IPipelineExecutor> executor_;
    
public:
    ResearchEngine() {
        PipelineBuilder builder;
        auto stages = builder
            .add_window(StageConfig::WindowType::HANN)
            .add_fft()
            .add_magnitude()
            .build();
        
        executor_ = std::make_unique<BatchExecutor>();
        ExecutorConfig config;
        executor_->initialize(config, std::move(stages));
    }
    
    void process(const float* input, float* output, size_t n) {
        executor_->submit(input, output, n);
    }
    
    ProcessingStats get_stats() const { 
        return executor_->get_stats(); 
    }
};
```

#### AntennaEngine (New Specialized Engine)
```cpp
class AntennaEngine {
    std::unique_ptr<IPipelineExecutor> executor_;

public:
    AntennaEngine(const IonosphereConfig& config) {
        PipelineBuilder builder;
        auto stages = builder
            .with_config(config.stage_config)
            .add_window(StageConfig::WindowType::BLACKMAN)
            .add_fft()
            .add_magnitude()
            .add_stage(std::make_unique<IonoMetricsStage>())
            .build();

        executor_ = std::make_unique<StreamingExecutor>();
        ExecutorConfig exec_config(config);
        exec_config.mode = ExecutorConfig::ExecutionMode::STREAMING;
        executor_->initialize(exec_config, std::move(stages));
    }
};
```

## Implementation Tasks

### Core Refactor

#### Infrastructure Setup
- [ ] Create new directory structure
- [ ] Define `IPipelineExecutor` interface
- [ ] Define `ExecutorConfig` and related types
- [ ] Update CMakeLists.txt with new source files

#### BatchExecutor Extraction
- [ ] Create `BatchExecutor` class
- [ ] Move execution logic from `ResearchEngine::Impl`
- [ ] Move CUDA resource management (streams, events, buffers)
- [ ] Implement `IPipelineExecutor` interface
- [ ] Add NVTX profiling markers

#### Pipeline Builder
- [ ] Implement `PipelineBuilder` class
- [ ] Add validation logic
- [ ] Add memory estimation
- [ ] Create unit tests

#### ResearchEngine Refactor
- [ ] Replace `ResearchEngine::Impl` with executor delegation
- [ ] Remove redundant code
- [ ] Update all method implementations
- [ ] Verify performance parity

### Specialized Executors

#### StreamingExecutor Implementation
- [ ] Design ring buffer for input accumulation
- [ ] Implement streaming execution logic
- [ ] Add callback-based output delivery
- [ ] Optimize for low latency
- [ ] Add CUDA graph support (optional)

#### AntennaEngine
- [ ] Define `IonosphereConfig` structure
- [ ] Create facade class
- [ ] Define ionosphere-specific pipeline
- [ ] Add specialized metrics stage (future)

### Python Integration

#### Core Bindings
- [ ] Bind `IPipelineExecutor` interface
- [ ] Bind `PipelineBuilder`
- [ ] Bind `BatchExecutor` and `StreamingExecutor`
- [ ] Bind new engine classes

#### Python API Design
```python
# New Python API (v0.9.3)
from ionosense_hpc import (
    PipelineBuilder,
    BatchExecutor,
    StreamingExecutor,
    CustomEngine
)

# Build custom pipeline
builder = PipelineBuilder()
pipeline = (builder
    .with_config(config)
    .add_window(WindowType.BLACKMAN)
    .add_fft()
    .add_magnitude()
    .build())

# Create executor
executor = StreamingExecutor(exec_config)

# Create custom engine
engine = CustomEngine(pipeline, executor)
result = engine.process(data)
```

### Testing Strategy

#### Unit Tests
- [ ] `BatchExecutor` resource management
- [ ] `StreamingExecutor` ring buffer
- [ ] `PipelineBuilder` validation
- [ ] Memory leak detection

#### Integration Tests
- [ ] End-to-end signal processing
- [ ] Multi-stream synchronization
- [ ] Executor switching
- [ ] Python bindings

#### Performance Tests
- [ ] Throughput benchmarks
- [ ] Latency measurements
- [ ] Memory usage profiling
- [ ] CUDA graph performance

## File Organization

```
cpp/
├── include/ionosense/
│   ├── core/
│   │   ├── pipeline_executor.hpp      [NEW]
│   │   ├── pipeline_builder.hpp       [NEW]
│   │   └── executor_config.hpp        [NEW]
│   ├── executors/
│   │   ├── batch_executor.hpp         [NEW]
│   │   └── streaming_executor.hpp     [NEW]
│   ├── engines/
│   │   ├── research_engine.hpp        [REWRITTEN]
│   │   └── antenna_engine.hpp         [NEW]
│   ├── processing_stage.hpp           [UNCHANGED]
│   ├── cuda_wrappers.hpp              [UNCHANGED]
│   └── profiling_macros.hpp           [UNCHANGED]
├── src/
│   ├── executors/
│   │   ├── batch_executor.cpp         [NEW]
│   │   └── streaming_executor.cpp     [NEW]
│   ├── engines/
│   │   ├── research_engine.cpp        [REWRITTEN]
│   │   └── antenna_engine.cpp         [NEW]
│   ├── core/
│   │   └── pipeline_builder.cpp       [NEW]
│   ├── processing_stage.cpp           [UNCHANGED]
│   ├── ops_fft.cu                     [UNCHANGED]
│   └── profiling_nvtx.cu              [UNCHANGED]
└── tests/
    ├── test_executors.cpp              [NEW]
    ├── test_pipeline_builder.cpp       [NEW]
    └── test_research_engine.cpp        [REWRITTEN]
```

## Key Design Decisions

### Resource Ownership
- **Executors own**: CUDA streams, events, device buffers
- **Stages own**: Stage-specific resources (window coefficients, FFT plans)
- **Engines own**: Pipeline and executor instances
- **Clear lifetime**: Resources destroyed in reverse order of creation

### Error Handling
- Exceptions for configuration/initialization errors
- Error codes for runtime processing errors
- Detailed error context via `ProcessingStats`
- CUDA errors converted to exceptions via macros

### Memory Management
- RAII principles throughout
- Smart pointers for ownership transfer
- Pre-allocated buffers during initialization
- No dynamic allocation in processing path

### Performance Considerations
- Zero-copy operations where possible
- Stream-ordered memory operations
- Event-based synchronization
- Optional CUDA graph capture

## Success Metrics

- [ ] All tests pass
- [ ] No performance regression (target: <5% overhead)
- [ ] Memory usage unchanged or reduced
- [ ] Clean separation of concerns verified
- [ ] Python bindings fully functional
- [ ] Multiple executor types demonstrated

## Risk Mitigation

### Risk: Performance Regression
**Mitigation**: Profile at each step, maintain benchmark suite

### Risk: Resource Leaks
**Mitigation**: RAII enforcement, sanitizer testing

### Risk: Complexity Increase
**Mitigation**: Clear interfaces, comprehensive documentation

### Risk: CUDA Resource Conflicts
**Mitigation**: Clear ownership model, proper synchronization

## Future Extensions (Not in Current Scope)

- CUDA Graph-based executor
- Multi-GPU executor
- OpenCL/ROCm executors
- Distributed processing executor
- JIT compilation of custom stages
- Dynamic pipeline reconfiguration

## Implementation Notes

1. **Start with BatchExecutor**: Get the extraction working first
2. **Test continuously**: Run tests after each major change
3. **Profile extensively**: Use NVTX markers to verify behavior
4. **Document interfaces**: Clear contracts prevent confusion
5. **Focus on performance**: This refactor should improve, not degrade

## Version Notes

- **Current version**: v0.9.2
- **Target version**: v0.9.3
- **Branch strategy**: Feature branch with full testing before merge
- **API changes**: Breaking changes acceptable in this version