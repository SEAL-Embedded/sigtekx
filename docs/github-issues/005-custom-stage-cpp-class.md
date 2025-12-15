# Add CustomStage C++ Class for CUDA Kernel Function Pointers (Phase 2 Task 2.1)

## Problem

There is currently **no way to inject custom CUDA kernels at runtime**. The `ProcessingStage` interface only supports hardcoded stages (Window, FFT, Magnitude). This blocks the **core value proposition** of SigTekX: "Python users can add custom functionality without C++ knowledge."

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 2 Task 2.1):
- THE CORE NOVELTY: Custom stage ecosystem enabling Python users to inject DSP algorithms
- Target overhead: <10µs for custom stages vs built-in stages
- Foundation for Numba integration (Phase 2.2), PyTorch integration (Phase 2.3)
- Critical for methods paper: demonstrate soft real-time with custom Python workflows

**Impact:**
- Cannot demonstrate core novelty for v1.0 paper
- Scientists must modify C++ code to add custom algorithms
- No competitive advantage over CuPy/NumPy (fixed pipelines only)

## Current Implementation

**File:** `cpp/include/sigtekx/core/processing_stage.hpp` (lines 15-40)

```cpp
// Abstract interface - only supports built-in stages
class ProcessingStage {
public:
    virtual ~ProcessingStage() = default;
    virtual void initialize(const StageConfig& config) = 0;
    virtual void process(const DeviceBuffer<float>& input,
                        DeviceBuffer<float>& output,
                        cudaStream_t stream) = 0;
};
```

**File:** `cpp/src/core/stage_factory.cpp` (lines 25-45)

```cpp
// Hardcoded enum switch - not extensible
std::unique_ptr<ProcessingStage> StageFactory::create(StageType type) {
    switch (type) {
        case StageType::WINDOW:
            return std::make_unique<WindowStage>();
        case StageType::FFT:
            return std::make_unique<FFTStage>();
        case StageType::MAGNITUDE:
            return std::make_unique<MagnitudeStage>();
        default:
            throw std::invalid_argument("Unknown stage type");
    }
}
```

**Why custom stages don't exist:**
- Original design: assume all stages are built-in C++
- No mechanism to accept external kernel function pointers
- No interface for runtime kernel binding

## Proposed Solution

**Create `CustomStage` class accepting CUDA Driver API function pointers:**

```cpp
// cpp/include/sigtekx/core/custom_stage.hpp (NEW FILE)
#ifndef SIGTEKX_CORE_CUSTOM_STAGE_HPP
#define SIGTEKX_CORE_CUSTOM_STAGE_HPP

#include <cuda.h>
#include "sigtekx/core/processing_stage.hpp"
#include "sigtekx/core/device_buffer.hpp"

namespace sigtekx {

class CustomStage : public ProcessingStage {
public:
    // Constructor accepts CUDA Driver API function pointer
    // kernel_func: CUfunction from Numba/cuPy
    // grid, block: launch dimensions
    // workspace_bytes: persistent state buffer size (for IIR filters, etc.)
    CustomStage(CUfunction kernel_func,
                dim3 grid,
                dim3 block,
                size_t workspace_bytes = 0);

    ~CustomStage() override;

    void initialize(const StageConfig& config) override;

    void process(const DeviceBuffer<float>& input,
                DeviceBuffer<float>& output,
                cudaStream_t stream) override;

    // Access persistent state (for stateful algorithms)
    void* get_state_ptr() const { return workspace_.data(); }

private:
    CUfunction kernel_;           // CUDA Driver API function pointer
    dim3 grid_, block_;          // Launch configuration
    DeviceBuffer<uint8_t> workspace_;  // Persistent state buffer
    CUstream cu_stream_;         // CUDA Driver API stream handle
};

} // namespace sigtekx

#endif
```

```cpp
// cpp/src/core/custom_stage.cpp (NEW FILE)
#include "sigtekx/core/custom_stage.hpp"
#include "sigtekx/core/cuda_utils.hpp"

namespace sigtekx {

CustomStage::CustomStage(CUfunction kernel_func, dim3 grid, dim3 block, size_t workspace_bytes)
    : kernel_(kernel_func), grid_(grid), block_(block) {

    // Validate kernel function pointer
    if (kernel_func == nullptr) {
        throw std::invalid_argument("CustomStage: kernel_func cannot be null");
    }

    // Allocate workspace buffer if needed (persistent state)
    if (workspace_bytes > 0) {
        workspace_.resize(workspace_bytes);
    }
}

CustomStage::~CustomStage() {
    // Workspace buffer auto-cleaned by DeviceBuffer destructor
}

void CustomStage::initialize(const StageConfig& config) {
    // Convert cudaStream_t to CUstream for Driver API
    cu_stream_ = reinterpret_cast<CUstream>(config.stream);
}

void CustomStage::process(const DeviceBuffer<float>& input,
                         DeviceBuffer<float>& output,
                         cudaStream_t stream) {
    // Update stream handle
    cu_stream_ = reinterpret_cast<CUstream>(stream);

    // Prepare kernel arguments
    void* args[] = {
        const_cast<float**>(&input.data()),   // Input pointer
        &output.data(),                        // Output pointer
        &input.size(),                         // Size parameter
        workspace_.data() ? &workspace_.data() : nullptr  // State pointer
    };

    // Launch kernel using CUDA Driver API
    CUresult result = cuLaunchKernel(
        kernel_,
        grid_.x, grid_.y, grid_.z,    // Grid dimensions
        block_.x, block_.y, block_.z,  // Block dimensions
        0,                             // Shared memory bytes
        cu_stream_,                    // Stream
        args,                          // Kernel arguments
        nullptr                        // Extra options
    );

    if (result != CUDA_SUCCESS) {
        const char* error_str;
        cuGetErrorString(result, &error_str);
        throw std::runtime_error(std::string("CustomStage kernel launch failed: ") + error_str);
    }
}

} // namespace sigtekx
```

## Additional Technical Insights

- **CUDA Driver API vs Runtime API**: Uses `CUfunction` (Driver API) instead of `__global__` templates (Runtime API). Driver API is lower-level but enables runtime kernel binding from Python.

- **Numba Integration Path**: Numba's `@cuda.jit` decorator exposes `kernel.driver_function.handle.value` which is a `CUfunction` pointer. This class accepts it directly.

- **Workspace Buffer for Persistent State**: Enables IIR filters, running statistics, anomaly detection with history. Pre-allocated on GPU, passed as kernel argument.

- **Grid/Block Configuration**: User-specified dimensions allow different kernel sizes. Example: 1D grid for element-wise ops, 2D grid for matrix ops.

- **Performance Target**: Overhead should be <10µs vs built-in stages. Measured via per-stage timing (Issue #004).

- **Error Handling**: Clear exceptions for invalid kernel pointers, launch failures. Driver API errors include error strings for debugging.

## Implementation Tasks

- [ ] Create `cpp/include/sigtekx/core/custom_stage.hpp` header file
- [ ] Implement `CustomStage` constructor (validate kernel, allocate workspace)
- [ ] Implement `initialize()` method (stream conversion)
- [ ] Implement `process()` method using `cuLaunchKernel()`
- [ ] Implement destructor (workspace auto-cleanup via DeviceBuffer)
- [ ] Add `get_state_ptr()` accessor for persistent state
- [ ] Create `cpp/src/core/custom_stage.cpp` implementation file
- [ ] Add CUDA Driver API includes (`#include <cuda.h>`)
- [ ] Update `cpp/CMakeLists.txt` to include custom_stage.cpp
- [ ] Create unit test: `cpp/tests/test_custom_stage.cpp`
  - Test: Simple element-wise multiply kernel
  - Test: Kernel with workspace buffer
  - Test: Invalid kernel pointer throws exception
  - Test: Grid/block dimension overflow detection
- [ ] Measure overhead vs built-in stage (target: <10µs)
- [ ] Build and verify: `./scripts/cli.ps1 build`
- [ ] Run C++ tests: `./scripts/cli.ps1 test cpp`
- [ ] Commit: `feat(core): add CustomStage class for runtime kernel binding`

## Edge Cases to Handle

- **Invalid Kernel Function Pointer**: `kernel_func == nullptr`
  - Mitigation: Validate in constructor, throw clear exception

- **Workspace Allocation Failure**: Out of GPU memory
  - Mitigation: DeviceBuffer throws on allocation failure (already handled)

- **Grid/Block Dimension Overflow**: Exceeds GPU limits (e.g., maxThreadsPerBlock)
  - Mitigation: CUDA Driver API will return error on launch, caught and re-thrown

- **Stream Synchronization**: Kernel launch is async, must sync before reading output
  - Mitigation: Executor handles stream sync (not CustomStage responsibility)

- **Kernel Signature Mismatch**: Kernel expects different arguments than provided
  - Mitigation: Runtime error on launch, user must match signature

## Testing Strategy

**Unit Test (C++):**

```cpp
// cpp/tests/test_custom_stage.cpp
#include <gtest/gtest.h>
#include "sigtekx/core/custom_stage.hpp"
#include <cuda.h>

// Simple kernel: y[i] = x[i] * 2.0
__global__ void double_kernel(const float* input, float* output, size_t n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        output[i] = input[i] * 2.0f;
    }
}

TEST(CustomStageTest, ElementWiseDoubleKernel) {
    // Get CUfunction from kernel
    CUfunction kernel_func;
    cuModuleGetFunction(&kernel_func, module, "double_kernel");

    // Create CustomStage
    dim3 grid((1024 + 255) / 256, 1, 1);
    dim3 block(256, 1, 1);
    CustomStage stage(kernel_func, grid, block);

    // Process test data
    DeviceBuffer<float> input(1024), output(1024);
    stage.process(input, output, stream);

    // Verify correctness (each output = input * 2.0)
    EXPECT_NEAR(output_host[0], input_host[0] * 2.0f, 1e-5);
}

TEST(CustomStageTest, InvalidKernelPointer) {
    EXPECT_THROW(CustomStage(nullptr, dim3(1,1,1), dim3(1,1,1)), std::invalid_argument);
}

TEST(CustomStageTest, WorkspaceAllocation) {
    CUfunction kernel_func = /* ... */;
    CustomStage stage(kernel_func, dim3(1,1,1), dim3(1,1,1), 1024);  // 1KB workspace
    EXPECT_NE(stage.get_state_ptr(), nullptr);
}
```

**Performance Test:**

```bash
# After Issue #004 (per-stage timing) is complete
python benchmarks/run_latency.py +benchmark=profiling
# Check per-stage metrics: CustomStage overhead should be <10µs
```

## Acceptance Criteria

- [ ] `CustomStage` class compiles without errors
- [ ] Can construct with `CUfunction` pointer, grid, block
- [ ] `process()` successfully launches kernel using `cuLaunchKernel()`
- [ ] Workspace buffer allocation works (if `workspace_bytes > 0`)
- [ ] `get_state_ptr()` returns valid pointer to workspace
- [ ] Invalid kernel pointer throws `std::invalid_argument`
- [ ] Unit tests pass: element-wise kernel, workspace, error handling
- [ ] Overhead < 10µs vs built-in stages (measured via Issue #004)
- [ ] All C++ tests pass
- [ ] Documentation includes usage example

## Benefits

- **Foundation for Numba Integration**: Enables Issue #006 (Python → C++ kernel bridge)
- **Core Novelty Demonstrated**: Python users can inject custom DSP algorithms
- **No Python GIL in Data Plane**: Kernels run at C++ speed
- **Persistent State Support**: Enables stateful algorithms (IIR filters, running stats)
- **Performance Target**: <10µs overhead maintains real-time requirements (RTF < 0.3)
- **Competitive Moat**: No other Python GPU DSP library offers this flexibility

---

**Labels:** `feature`, `team-1-cpp`, `c++`, `cuda`, `architecture`

**Estimated Effort:** 6-8 hours (CUDA Driver API integration, requires careful testing)

**Priority:** High (Core Novelty - Phase 2 Task 2.1)

**Roadmap Phase:** Phase 2 (v0.9.7)

**Dependencies:** Issue #004 (per-stage timing - needed to measure overhead)

**Blocks:** Issue #006 (Numba integration), Issue #007 (PyTorch integration), Issue #008 (persistent state)
