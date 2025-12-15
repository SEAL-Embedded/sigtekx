# Add Per-Stage Timing Infrastructure (Phase 1 Task 1.2)

## Problem

The benchmarking infrastructure cannot measure **per-stage latency** (Window, FFT, Magnitude), making it impossible to:
- Validate custom stage overhead (<10µs target in Phase 2)
- Identify bottlenecks within the pipeline
- Measure non-compute overhead (pipeline management, buffer swaps)

**Current state:**
- Only **total latency** is measured (entire pipeline)
- Benchmark config has `measure_components=false` (placeholder)
- Cannot validate Phase 2 claim: "Custom stages add <10µs overhead"

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 1 Task 1.2):
- Expected metrics: Window ~5-10µs, FFT ~30-40µs, Magnitude ~5-10µs
- Target total overhead: <20µs (non-stage time)
- Critical for Phase 2 validation experiments

## Current Implementation

**File:** `cpp/include/sigtekx/core/processing_stage.hpp` (lines 25-45)

```cpp
class ProcessingStage {
public:
    virtual void initialize(const StageConfig& config, cudaStream_t stream) = 0;
    virtual void process(void* input, void* output, size_t num_elements, cudaStream_t stream) = 0;

    // NO TIMING INSTRUMENTATION
    // No way to measure how long process() takes
};
```

**File:** `benchmarks/latency.py` (lines 180-200)

```python
class LatencyBenchmark(BaseBenchmark):
    def execute_iteration(self) -> float:
        # Measure total pipeline latency only
        start = time.perf_counter()
        result = self.engine.process(self.test_data)
        end = time.perf_counter()

        return (end - start) * 1e6  # Convert to microseconds

        # NO PER-STAGE METRICS
        # Cannot see Window vs FFT vs Magnitude breakdown
```

**File:** `experiments/conf/benchmark/profiling.yaml` (lines 15-18)

```yaml
# Placeholder - not implemented
measure_components: false  # Would enable per-stage timing if true
```

## Proposed Solution

**Step 1: Add CUDA event timers to ProcessingStage**

```cpp
// In cpp/include/sigtekx/core/processing_stage.hpp

class ProcessingStage {
public:
    // Existing interface
    virtual void initialize(const StageConfig& config, cudaStream_t stream) = 0;
    virtual void process(void* input, void* output, size_t num_elements, cudaStream_t stream) = 0;
    virtual std::string name() const = 0;

    // NEW: Performance metrics interface
    virtual void enable_timing(bool enabled) {
        timing_enabled_ = enabled;
        if (enabled && !start_event_) {
            CUDA_CHECK(cudaEventCreate(&start_event_));
            CUDA_CHECK(cudaEventCreate(&stop_event_));
        }
    }

    virtual float get_last_duration_us() const {
        if (!timing_enabled_ || !start_event_) return 0.0f;

        float duration_ms = 0.0f;
        CUDA_CHECK(cudaEventElapsedTime(&duration_ms, start_event_, stop_event_));
        return duration_ms * 1000.0f;  // Convert to microseconds
    }

protected:
    // Wrapped process call with timing
    void process_with_timing(void* input, void* output, size_t num_elements, cudaStream_t stream) {
        if (timing_enabled_) {
            CUDA_CHECK(cudaEventRecord(start_event_, stream));
        }

        // Call actual implementation
        process(input, output, num_elements, stream);

        if (timing_enabled_) {
            CUDA_CHECK(cudaEventRecord(stop_event_, stream));
            CUDA_CHECK(cudaEventSynchronize(stop_event_));  // Ensure completion
        }
    }

private:
    bool timing_enabled_ = false;
    cudaEvent_t start_event_ = nullptr;
    cudaEvent_t stop_event_ = nullptr;
};
```

**Step 2: Expose stage metrics to Python via bindings**

```cpp
// In cpp/bindings/bindings.cpp

py::class_<Engine>(m, "Engine")
    // ... existing methods ...

    .def("enable_stage_timing", [](Engine& self, bool enabled) {
        // Enable timing for all stages in pipeline
        for (auto& stage : self.impl_->stages_) {
            stage->enable_timing(enabled);
        }
    })

    .def("get_stage_metrics", [](Engine& self) -> py::dict {
        py::dict metrics;
        for (const auto& stage : self.impl_->stages_) {
            std::string name = stage->name();
            float duration_us = stage->get_last_duration_us();
            metrics[py::str(name)] = duration_us;
        }
        return metrics;
    });
```

**Step 3: Update latency benchmark to collect stage metrics**

```python
# In benchmarks/latency.py

class LatencyBenchmark(BaseBenchmark):
    def setup(self) -> None:
        """Initialize engine with per-stage timing enabled."""
        super().setup()

        # NEW: Enable component timing if requested
        if self.config.measure_components:
            self.engine.enable_stage_timing(True)
            logger.info("Per-stage timing enabled")

    def execute_iteration(self) -> dict[str, float] | float:
        """Execute latency measurement with optional component breakdown."""
        start = time.perf_counter()
        result = self.engine.process(self.test_data)
        end = time.perf_counter()

        total_latency_us = (end - start) * 1e6

        # NEW: Collect per-stage metrics if enabled
        if self.config.measure_components:
            stage_metrics = self.engine.get_stage_metrics()
            return {
                'total_latency_us': total_latency_us,
                'window_us': stage_metrics.get('window', 0.0),
                'fft_us': stage_metrics.get('fft', 0.0),
                'magnitude_us': stage_metrics.get('magnitude', 0.0),
                'overhead_us': total_latency_us - sum(stage_metrics.values())
            }
        else:
            return total_latency_us  # Legacy single-value return
```

**Step 4: Update benchmark config to enable component timing**

```yaml
# In experiments/conf/benchmark/profiling.yaml

# Enable per-stage timing
measure_components: true

# Expected stage breakdown (for validation):
# - window: 5-10µs
# - fft: 30-40µs
# - magnitude: 5-10µs
# - overhead: <20µs
```

## Additional Technical Insights

- **CUDA Events vs CPU Timers**: CUDA events are more accurate for GPU operations (account for async execution, minimize CPU overhead)

- **Synchronization Overhead**: `cudaEventSynchronize` adds ~1-2µs per stage, but necessary for accurate measurement

- **Overhead Calculation**: `overhead_us = total - sum(stages)` reveals pipeline management cost (buffer swaps, synchronization)

- **Multi-Metric Return**: Benchmark now returns dict when `measure_components=true`, float otherwise (backward compatible)

- **Dashboard Integration**: Streamlit dashboard can display stage breakdown as stacked bar chart

- **Validation Target**: Sum of stage times should be ≤ 90% of total (≤10% overhead acceptable)

## Implementation Tasks

**Part 1: C++ Timing Infrastructure**

- [ ] Open `cpp/include/sigtekx/core/processing_stage.hpp`
- [ ] Add `timing_enabled_` bool member (default false)
- [ ] Add `start_event_`, `stop_event_` cudaEvent_t members
- [ ] Add `enable_timing(bool)` method (creates events if enabled)
- [ ] Add `get_last_duration_us()` method (returns last execution time)
- [ ] Add `process_with_timing()` protected method (wraps process with events)
- [ ] Update WindowStage/FFTStage/MagnitudeStage to use process_with_timing
- [ ] Add event cleanup in destructors (cudaEventDestroy)

**Part 2: Python Bindings**

- [ ] Open `cpp/bindings/bindings.cpp`
- [ ] Add `enable_stage_timing(bool)` binding to Engine class
- [ ] Add `get_stage_metrics()` binding (returns py::dict)
- [ ] Test binding: `python -c "from sigtekx import Engine; e = Engine(); e.enable_stage_timing(True)"`

**Part 3: Benchmark Integration**

- [ ] Open `benchmarks/latency.py`
- [ ] Add `measure_components: bool` to LatencyBenchmarkConfig
- [ ] Update `setup()` to call `enable_stage_timing(self.config.measure_components)`
- [ ] Update `execute_iteration()` to return dict when measure_components=true
- [ ] Add `overhead_us` calculation (total - sum of stages)
- [ ] Update `BenchmarkResult` handling to support multi-metric dicts

**Part 4: Config Updates**

- [ ] Open `experiments/conf/benchmark/profiling.yaml`
- [ ] Change `measure_components: false` → `measure_components: true`
- [ ] Add comment explaining expected stage breakdown
- [ ] Open `experiments/conf/benchmark/latency.yaml`
- [ ] Add `measure_components: false` (production runs don't need it)

**Part 5: Testing & Validation**

- [ ] Run profiling benchmark: `python benchmarks/run_latency.py +benchmark=profiling`
- [ ] Verify output includes stage breakdown
- [ ] Verify overhead < 20µs (if higher, investigate)
- [ ] Verify sum(stages) ≈ total - overhead (within 5%)
- [ ] Run accuracy test to ensure timing doesn't affect correctness
- [ ] Update Streamlit dashboard to display stage breakdown (optional)

**Part 6: Documentation**

- [ ] Add docstring to `enable_stage_timing()` explaining when to use it
- [ ] Add comment in benchmark explaining overhead calculation
- [ ] Update `docs/performance/` with timing methodology (optional)

## Edge Cases to Handle

- **Timing Disabled (Default)**: If `measure_components=false`, no events created (zero overhead)

- **Event Synchronization Cost**: Synchronizing events adds 1-2µs per stage, but necessary for accuracy

- **Pipeline Ordering**: Stage metrics should match pipeline order (window → fft → magnitude)

- **Multi-Stream Execution**: If multiple streams used, events must be stream-specific (current design: single stream)

- **Custom Stages (Phase 2)**: Custom stages inherit `ProcessingStage`, automatically get timing support

## Testing Strategy

**Validation Test:**

```python
def test_stage_timing_breakdown():
    """Verify per-stage timing sums to total latency."""
    from sigtekx import Engine
    from sigtekx.config import get_preset

    config = get_preset('default')
    engine = Engine(config=config)
    engine.enable_stage_timing(True)

    # Process one frame
    test_data = np.random.randn(config.channels, config.nfft).astype(np.float32)
    result = engine.process(test_data)

    # Get stage metrics
    metrics = engine.get_stage_metrics()

    # Validate
    assert 'window' in metrics
    assert 'fft' in metrics
    assert 'magnitude' in metrics

    # Verify reasonable values
    assert 5 <= metrics['window'] <= 15  # 5-15µs
    assert 20 <= metrics['fft'] <= 50    # 20-50µs
    assert 5 <= metrics['magnitude'] <= 15  # 5-15µs

    # Sum should be close to total
    total_stages = sum(metrics.values())
    assert total_stages < 100  # Total should be < 100µs
```

**Before/After Comparison:**

```bash
# Before (no component timing)
python benchmarks/run_latency.py +benchmark=latency
# Output: Mean latency: 85.3µs (no breakdown)

# After (with component timing)
python benchmarks/run_latency.py +benchmark=profiling
# Output:
#   Mean latency: 87.1µs (slightly higher due to sync overhead)
#   Window: 7.2µs
#   FFT: 38.1µs
#   Magnitude: 6.8µs
#   Overhead: 35.0µs
```

## Acceptance Criteria

- [ ] `ProcessingStage::enable_timing(bool)` implemented
- [ ] `ProcessingStage::get_last_duration_us()` implemented
- [ ] CUDA events created/destroyed correctly (no leaks)
- [ ] Python binding `Engine.enable_stage_timing()` exposed
- [ ] Python binding `Engine.get_stage_metrics()` returns dict
- [ ] `LatencyBenchmark.execute_iteration()` returns dict when measure_components=true
- [ ] `benchmark/profiling.yaml` has measure_components=true
- [ ] Profiling run shows stage breakdown in output
- [ ] Overhead calculation accurate (total - sum(stages))
- [ ] All tests pass
- [ ] Streamlit dashboard displays stage breakdown (optional)

## Benefits

- **Custom Stage Validation**: Can measure custom stage overhead in Phase 2 (<10µs target)
- **Bottleneck Identification**: See which stage is slowest (FFT expected)
- **Overhead Visibility**: Measure pipeline management cost (buffer swaps, sync)
- **Phase 2 Readiness**: Infrastructure ready for custom stage benchmarking
- **Debugging Tool**: Helps diagnose performance regressions

---

**Labels:** `feature`, `team-1-cpp`, `team-3-python`, `c++`, `python`, `performance`, `cuda`

**Estimated Effort:** 4-6 hours (C++/Python integration)

**Priority:** High (Phase 1 Task 1.2 - needed for Phase 2 validation)

**Roadmap Phase:** Phase 1 (v0.9.6)

**Dependencies:** None

**Blocks:** Phase 2 custom stage overhead validation
