# Enable Persistent State Buffers for Stateful Algorithms (Phase 2 Task 2.4)

## Problem

The `ProcessingStage` interface is **stateless** - there is no mechanism for IIR filters, running statistics, or algorithms that need persistent memory across frames. Custom stages can only implement FIR-style (stateless) processing.

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 2 Task 2.4):
- Enable stateful algorithms: IIR filters, running averages, anomaly detection with history
- Add `get_state_ptr()` to ProcessingStage interface
- Extend `StageConfig` with `workspace_bytes`
- Allocate persistent `DeviceBuffer` in `initialize()`

**Impact:**
- Cannot implement IIR filters (require feedback from previous frames)
- Cannot track running statistics (mean, variance over time)
- Cannot build anomaly detectors with historical context
- Limits custom stage usefulness (many DSP algorithms are stateful)

## Current Implementation

**File:** `cpp/include/sigtekx/core/processing_stage.hpp` (lines 15-40)

```cpp
class ProcessingStage {
public:
    virtual ~ProcessingStage() = default;

    virtual void initialize(const StageConfig& config) = 0;

    virtual void process(const DeviceBuffer<float>& input,
                        DeviceBuffer<float>& output,
                        cudaStream_t stream) = 0;

    // NO mechanism for persistent state!
};
```

**Why state doesn't exist:**
- Original design assumed stateless FIR-style processing
- No workspace buffer allocation
- No state pointer accessor

## Proposed Solution

**Add `get_state_ptr()` method and workspace allocation:**

```cpp
// cpp/include/sigtekx/core/processing_stage.hpp (ENHANCED)
class ProcessingStage {
public:
    virtual ~ProcessingStage() = default;

    virtual void initialize(const StageConfig& config) = 0;

    virtual void process(const DeviceBuffer<float>& input,
                        DeviceBuffer<float>& output,
                        cudaStream_t stream) = 0;

    // NEW: Access persistent state buffer
    // Returns nullptr if stage is stateless
    virtual void* get_state_ptr() { return nullptr; }

    // NEW: Get state buffer size in bytes
    virtual size_t get_state_size() const { return 0; }
};
```

```cpp
// cpp/include/sigtekx/core/stage_config.hpp (ENHANCED)
struct StageConfig {
    // ... existing fields ...

    // NEW: Workspace buffer size for persistent state
    size_t workspace_bytes = 0;
};
```

```cpp
// Example: IIR filter with persistent state
// cpp/src/stages/iir_filter_stage.cpp (EXAMPLE)
class IIRFilterStage : public ProcessingStage {
public:
    void initialize(const StageConfig& config) override {
        // Allocate state buffer (e.g., for filter history)
        if (config.workspace_bytes > 0) {
            state_buffer_.resize(config.workspace_bytes / sizeof(float));
            // Initialize to zero
            CUDA_CHECK(cudaMemset(state_buffer_.data(), 0, config.workspace_bytes));
        }
    }

    void process(const DeviceBuffer<float>& input,
                DeviceBuffer<float>& output,
                cudaStream_t stream) override {
        // Launch kernel with state pointer
        iir_filter_kernel<<<grid, block, 0, stream>>>(
            input.data(),
            output.data(),
            state_buffer_.data(),  // Persistent state
            alpha_,
            input.size()
        );
    }

    void* get_state_ptr() override {
        return state_buffer_.data();
    }

    size_t get_state_size() const override {
        return state_buffer_.size() * sizeof(float);
    }

private:
    DeviceBuffer<float> state_buffer_;  // Persistent state
    float alpha_;  // IIR coefficient
};
```

```python
# Example user code (Python)
from numba import cuda
from sigtekx import PipelineBuilder

@cuda.jit
def iir_filter(input, output, state, n, alpha):
    """First-order IIR filter: y[n] = alpha * x[n] + (1-alpha) * y[n-1]"""
    i = cuda.grid(1)
    if i < n:
        # Read previous output from state buffer
        prev_output = state[0] if i == 0 else output[i-1]

        # Compute IIR
        output[i] = alpha * input[i] + (1 - alpha) * prev_output

        # Save state for next frame (only channel 0)
        if i == n - 1:
            state[0] = output[i]

pipeline = (PipelineBuilder()
    .add_custom(iir_filter, workspace_mb=0.001)  # 1 KB state
    .build())
```

## Additional Technical Insights

- **Workspace Size**: User specifies in MB (Python API), converted to bytes (C++)

- **State Initialization**: Allocated in `initialize()`, zeroed by default. User can set initial state.

- **Multi-Instance Isolation**: Each stage instance has its own state buffer (no shared state).

- **State Persistence**: Buffer persists for lifetime of stage (not freed until destructor).

- **GPU Memory**: State buffer lives on GPU (DeviceBuffer). For CPU-side state, use PinnedHostBuffer.

- **State Size Calculation**: User computes based on algorithm needs. Example: IIR filter needs `sizeof(float) * num_channels` bytes.

## Implementation Tasks

- [ ] Open `cpp/include/sigtekx/core/processing_stage.hpp`
- [ ] Add `virtual void* get_state_ptr()` method (default returns nullptr)
- [ ] Add `virtual size_t get_state_size() const` method (default returns 0)
- [ ] Open `cpp/include/sigtekx/core/stage_config.hpp`
- [ ] Add `size_t workspace_bytes = 0;` field to `StageConfig`
- [ ] Open `cpp/src/core/custom_stage.cpp` (from Issue #005)
- [ ] Update `initialize()` to allocate workspace if `config.workspace_bytes > 0`
- [ ] Update `get_state_ptr()` to return `workspace_.data()`
- [ ] Add `get_state_size()` to return `workspace_.size()`
- [ ] Create example test: `cpp/tests/test_iir_filter.cpp`
  - Implement simple IIR filter kernel
  - Verify state persists across frames
  - Verify state is isolated per instance
- [ ] Update Python binding: expose `get_state_ptr()` and `get_state_size()`
- [ ] Update documentation: `docs/api/stateful-stages.md`
- [ ] Build: `./scripts/cli.ps1 build`
- [ ] Test: `./scripts/cli.ps1 test cpp`
- [ ] Commit: `feat(core): add persistent state support for stateful algorithms`

## Edge Cases to Handle

- **Workspace Allocation Failure**: Out of GPU memory
  - Mitigation: DeviceBuffer throws on allocation failure (user handles OOM)

- **State Size Mismatch**: User specifies wrong size for algorithm
  - Mitigation: User responsibility; document size calculation in API guide

- **State Not Initialized**: Garbage values in state buffer
  - Mitigation: Zero-initialize in `initialize()` by default

- **Multi-Stream State Access**: If multiple streams access same state, race condition
  - Mitigation: Document that state is per-stream; user must sync externally

## Testing Strategy

**Unit Test (C++):**

```cpp
// cpp/tests/test_stateful_stage.cpp
#include <gtest/gtest.h>
#include "sigtekx/core/processing_stage.hpp"

// Simple running sum kernel (stateful)
__global__ void running_sum_kernel(const float* input, float* output, float* state, size_t n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        output[i] = input[i] + state[0];  // Add previous sum
        if (i == n - 1) {
            state[0] = output[i];  // Update state
        }
    }
}

TEST(StatefulStageTest, PersistentStateAcrossFrames) {
    // Create stage with 4-byte state buffer (1 float)
    CustomStage stage(/*kernel_func*/, grid, block, sizeof(float));

    // Initialize state
    stage.initialize(config);
    float* state_ptr = static_cast<float*>(stage.get_state_ptr());
    ASSERT_NE(state_ptr, nullptr);
    EXPECT_EQ(stage.get_state_size(), sizeof(float));

    // Process frame 1: [1, 2, 3] → [1, 2, 3] (state=0)
    // Process frame 2: [1, 2, 3] → [4, 5, 6] (state=3 from previous)
    // Verify state persists

    // ... test implementation ...
}

TEST(StatefulStageTest, StatelessStageReturnsNullptr) {
    // Stage with no workspace
    CustomStage stage(/*kernel_func*/, grid, block, 0);

    EXPECT_EQ(stage.get_state_ptr(), nullptr);
    EXPECT_EQ(stage.get_state_size(), 0);
}
```

## Acceptance Criteria

- [ ] `get_state_ptr()` method added to `ProcessingStage` interface
- [ ] `get_state_size()` method added to `ProcessingStage` interface
- [ ] `workspace_bytes` field added to `StageConfig`
- [ ] `CustomStage` allocates workspace buffer if `workspace_bytes > 0`
- [ ] State buffer is zeroed on initialization
- [ ] State persists across `process()` calls (verified by test)
- [ ] Multiple stage instances have isolated state (verified by test)
- [ ] Python bindings expose `get_state_ptr()` and `get_state_size()`
- [ ] Documentation includes IIR filter example
- [ ] All C++ tests pass
- [ ] All Python tests pass

## Benefits

- **Stateful Algorithm Support**: IIR filters, running statistics, anomaly detection with history
- **Scientific Flexibility**: Expands custom stage use cases beyond FIR-style processing
- **Memory Efficiency**: Pre-allocated state (no dynamic allocation in hot path)
- **Multi-Instance Safety**: Isolated state per stage instance
- **Python API Simplicity**: User specifies `workspace_mb`, library handles allocation

---

**Labels:** `feature`, `team-1-cpp`, `c++`, `cuda`, `architecture`

**Estimated Effort:** 4-6 hours (interface extension, straightforward implementation)

**Priority:** Medium (Enables stateful algorithms - Phase 2 Task 2.4)

**Roadmap Phase:** Phase 2 (v0.9.7)

**Dependencies:** Issue #005 (CustomStage class must support workspace allocation)

**Blocks:** None (enhancement, not blocker)
