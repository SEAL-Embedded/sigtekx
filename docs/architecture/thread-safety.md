# Thread Safety - v0.9.3

**Version:** 0.9.3
**Last Updated:** October 2025
**Status:** Production Ready

---

## Table of Contents

1. [Threading Terminology](#1-threading-terminology)
2. [Library Thread Safety Model](#2-library-thread-safety-model)
3. [Class Thread Safety Reference](#3-class-thread-safety-reference)
4. [CUDA Threading Considerations](#4-cuda-threading-considerations)
5. [Python Multi-Threading](#5-python-multi-threading)
6. [Usage Examples](#6-usage-examples)
7. [Known Issues & Limitations](#7-known-issues--limitations)
8. [Future Plans](#8-future-plans-v094)

---

## 1. Threading Terminology

This library follows **Google's threading terminology** for classifying thread safety guarantees. Understanding these terms is essential for correct multi-threaded usage.

### 1.1 Thread-Safe

> **Thread-Safe**: A class or function is thread-safe if multiple threads can invoke methods on the **same object instance** concurrently without external synchronization.

**Example (hypothetical)**:
```cpp
// Thread-safe class (NOT the case for our executors)
ThreadSafeExecutor exec;

std::thread t1([&]{ exec.submit(data1); });  // ✅ Safe
std::thread t2([&]{ exec.submit(data2); });  // ✅ Safe - internal locking
```

**Guarantee**: The class internally handles all necessary synchronization (mutexes, atomics, etc.).

### 1.2 Thread-Compatible

> **Thread-Compatible**: A class or function is thread-compatible if concurrent use of **different object instances** is safe, but concurrent use of the **same instance** requires external synchronization.

**Example (our executors)**:
```cpp
// Thread-compatible class (our design)
BatchExecutor exec1, exec2;

std::thread t1([&]{ exec1.submit(data1); });  // ✅ Safe - different instances
std::thread t2([&]{ exec2.submit(data2); });  // ✅ Safe - different instances

// UNSAFE without external synchronization:
BatchExecutor shared_exec;
std::thread t3([&]{ shared_exec.submit(data3); });  // ❌ Data race!
std::thread t4([&]{ shared_exec.submit(data4); });  // ❌ Data race!
```

**Guarantee**: Different instances do not share mutable state.

### 1.3 Thread-Hostile

> **Thread-Hostile**: A function or class is thread-hostile if it is unsafe to use even with external synchronization, typically because it uses non-reentrant global state (e.g., `strtok`, `rand`).

**Example (avoided in our library)**:
```cpp
// Thread-hostile function (NOT used in production code)
float generate_noise() {
    return static_cast<float>(rand()) / RAND_MAX;  // ❌ Thread-hostile - global state
}
```

**Guarantee**: None. Cannot be made thread-safe without refactoring.

### 1.4 API Race

> **API Race**: Incorrect program behavior resulting from poorly synchronized calls to a thread-compatible API, even when individual operations are internally consistent.

**Example**:
```cpp
BatchExecutor exec;

// API Race: Two threads modifying same executor
std::thread t1([&]{ exec.initialize(config1); });  // ❌ API Race
std::thread t2([&]{ exec.initialize(config2); });  // ❌ Undefined behavior
```

**Characteristic**: No data race (no undefined behavior per C++ standard), but logically incorrect program state.

### 1.5 Data Race

> **Data Race**: Undefined behavior per C++ memory model when two or more threads access the same memory location concurrently, and at least one access is a write, without proper synchronization.

**Example**:
```cpp
BatchExecutor exec;

// Data Race: Concurrent submit() calls on same instance
std::thread t1([&]{ exec.submit(data1, output1, size); });  // ❌ Data race
std::thread t2([&]{ exec.submit(data2, output2, size); });  // ❌ Undefined behavior

// Reason: Both threads write to frame_counter_, stats_, buffers without synchronization
```

**Characteristic**: Undefined behavior (UB) in C++. Can manifest as crashes, corruption, or silent errors.

---

## 2. Library Thread Safety Model

### 2.1 Design Philosophy

Ionosense HPC follows the **thread-compatible** design pattern, similar to industry-standard high-performance libraries:

| Library | Thread Safety Model |
|---------|---------------------|
| **Ionosense HPC** | Thread-compatible |
| `std::vector` | Thread-compatible |
| Eigen | Thread-compatible |
| cuBLAS | Thread-compatible (per-handle) |
| OpenCV | Thread-compatible (per-object) |

**Rationale**:
- ✅ **Performance**: No locking overhead for single-threaded use (common case)
- ✅ **Simplicity**: Clear ownership model (one instance = one thread)
- ✅ **Scalability**: True parallelism via instance-per-thread pattern
- ✅ **CUDA Compatibility**: Aligns with CUDA's stream-based concurrency model

### 2.2 Intended Usage Pattern

**✅ Recommended: Per-Thread Instances**

```cpp
void worker_thread(int thread_id, const std::vector<float>& data) {
    // Each thread creates its own executor
    BatchExecutor executor;
    ExecutorConfig config = get_config();

    executor.initialize(config);
    executor.submit(data.data(), output.data(), data.size());
}

// Launch multiple workers
std::vector<std::thread> threads;
for (int i = 0; i < num_threads; ++i) {
    threads.emplace_back(worker_thread, i, dataset[i]);
}

for (auto& t : threads) t.join();
```

**❌ Incorrect: Shared Instance Without Synchronization**

```cpp
// DANGEROUS - Data race!
BatchExecutor shared_exec;
shared_exec.initialize(config);

std::thread t1([&]{ shared_exec.submit(data1, out1, size); });  // ❌ Race!
std::thread t2([&]{ shared_exec.submit(data2, out2, size); });  // ❌ Race!
```

### 2.3 Lifetime Management

**Initialization**: ✅ Thread-compatible
- Different threads can initialize different instances concurrently
- ❌ Do not initialize the same instance from multiple threads

**Processing**: ✅ Thread-compatible
- Different threads can call `submit()` on different instances concurrently
- ❌ Do not call `submit()` on the same instance from multiple threads

**Destruction**: ✅ Thread-compatible
- Different instances can be destroyed concurrently
- ❌ Do not destroy an instance while another thread is using it

---

## 3. Class Thread Safety Reference

### 3.1 Summary Table

| Class | Thread-Safe | Thread-Compatible | Thread-Hostile | Notes |
|-------|:-----------:|:-----------------:|:--------------:|-------|
| **CUDA Wrappers** ||||
| `CudaStream` | ❌ | ✅ | ❌ | Different streams safe; same stream requires sync |
| `CudaEvent` | ❌ | ✅ | ❌ | Different events safe |
| `DeviceBuffer<T>` | ❌ | ✅ | ❌ | Move-only, no shared state |
| `PinnedHostBuffer<T>` | ❌ | ✅ | ❌ | Move-only, no shared state |
| `CufftPlan` | ❌ | ✅ | ❌ | Instance-isolated |
| **Processing Stages** ||||
| `WindowStage` | ❌ | ✅ | ❌ | Not safe for concurrent `process()` |
| `FFTStage` | ❌ | ✅ | ❌ | Not safe for concurrent `process()` |
| `MagnitudeStage` | ❌ | ✅ | ❌ | Not safe for concurrent `process()` |
| **Executors** ||||
| `BatchExecutor` | ❌ | ✅ | ❌ | **Not safe for concurrent `submit()`** |
| `StreamingExecutor` | ❌ | ✅ | ❌ | Delegates to `BatchExecutor` |
| **Engines** ||||
| `ResearchEngine` | ❌ | ✅ | ❌ | Wraps executor |
| `AntennaEngine` | ❌ | ✅ | ❌ | Wraps executor |
| **Python Bindings** ||||
| `PyResearchEngine` | ❌ | ✅ | ❌ | No GIL release in v0.9.3 |

### 3.2 Detailed Class Analysis

#### `BatchExecutor`

**Thread Safety**: ❌ Not thread-safe, ✅ Thread-compatible

**Rationale**: Contains mutable state modified without synchronization:
```cpp
// Internal state (simplified)
uint64_t frame_counter_;              // Incremented in submit()
ProcessingStats stats_;               // Written in submit()
std::vector<DeviceBuffer<T>> buffers_; // Accessed in submit()
```

**Safe Usage**:
```cpp
// ✅ Per-thread instances
void thread_func(int id) {
    BatchExecutor exec;  // Thread-local instance
    exec.initialize(config);
    exec.submit(data, output, size);
}
```

**Unsafe Usage**:
```cpp
// ❌ Shared instance
BatchExecutor shared_exec;
std::thread t1([&]{ shared_exec.submit(...); });  // Data race!
std::thread t2([&]{ shared_exec.submit(...); });  // Data race!
```

#### `CudaStream`

**Thread Safety**: ❌ Not thread-safe, ✅ Thread-compatible

**CUDA Guarantee**:
- Operations on **different streams** from **different host threads** are safe
- Operations on the **same stream** from **multiple threads** require external synchronization

**Safe Usage**:
```cpp
// ✅ Different streams
CudaStream stream1, stream2;
std::thread t1([&]{ cudaMemcpyAsync(..., stream1); });
std::thread t2([&]{ cudaMemcpyAsync(..., stream2); });
```

#### `DeviceBuffer<T>` and `PinnedHostBuffer<T>`

**Thread Safety**: ❌ Not thread-safe, ✅ Thread-compatible

**Characteristics**:
- Move-only (non-copyable)
- No shared state between instances
- RAII cleanup is thread-safe (different instances)

**Safe Usage**:
```cpp
// ✅ Different buffers
DeviceBuffer<float> buf1(1024), buf2(1024);
std::thread t1([&]{ buf1.copy_from_host(...); });
std::thread t2([&]{ buf2.copy_from_host(...); });
```

---

## 4. CUDA Threading Considerations

### 4.1 CUDA Runtime Thread Safety

The CUDA Runtime API has specific thread safety guarantees:

| CUDA API Category | Thread Safety |
|-------------------|---------------|
| Device management (`cudaSetDevice`) | Thread-compatible (per-context) |
| Stream operations (`cudaMemcpyAsync`) | Thread-compatible (per-stream) |
| Memory allocation (`cudaMalloc`) | Thread-safe |
| Synchronization (`cudaDeviceSynchronize`) | Thread-safe |
| cuFFT operations | Thread-compatible (per-plan) |

### 4.2 Device Context Management

**Per-Thread Device Affinity**:

```cpp
// ✅ Each thread can select a different device
void worker_thread(int thread_id, int device_id) {
    cudaSetDevice(device_id);  // Thread-local device context

    BatchExecutor exec;
    exec.initialize(config);
    // ... processing on selected device
}

// Multi-GPU parallelism
std::thread t0(worker_thread, 0, 0);  // GPU 0
std::thread t1(worker_thread, 1, 1);  // GPU 1
```

**Our Implementation**:
- `BatchExecutor::Impl` constructor calls `cudaSetDevice()` in constructor
- Each executor instance is bound to a specific device
- Safe for concurrent instances on different devices ✅

### 4.3 Stream-Based Concurrency

**CUDA Streams** enable asynchronous concurrency:

```cpp
// ✅ Multiple streams in same thread (our design)
BatchExecutor executor;
executor.initialize(config);  // Creates 3 streams: H2D, compute, D2H

// Internally:
// - H2D stream:      cudaMemcpyAsync (input)
// - Compute stream:  kernel launches (FFT, magnitude)
// - D2H stream:      cudaMemcpyAsync (output)
// All overlap asynchronously!
```

**Thread Safety**:
- Different threads using different streams: ✅ Safe
- Different threads using the same stream: ❌ Requires external sync

### 4.4 cuFFT Plan Thread Safety

**cuFFT Guarantee**: Plans are thread-compatible

```cpp
// ✅ Different plans in different threads
void worker_thread() {
    CufftPlan plan;
    plan.create_plan_many(...);  // Thread-local plan
    plan.exec_r2c(input, output);
}

std::thread t1(worker_thread);
std::thread t2(worker_thread);
```

**Our Implementation**:
- Each `FFTStage` instance owns its own `CufftPlan`
- Plans are created during `initialize()` (single-threaded per instance)
- Concurrent execution on different plans: ✅ Safe

---

## 5. Python Multi-Threading

### 5.1 Global Interpreter Lock (GIL)

Python's GIL serializes Python bytecode execution, but **C++ extensions can release it** during long-running operations.

**Current Status (v0.9.3)**: ❌ GIL is **NOT released** during processing

**Impact**:
```python
# ❌ Python threads will serialize through GIL
import threading
from ionosense import ResearchEngine

engine = ResearchEngine()
engine.initialize(config)

def process_data(data):
    output = engine.process(data)  # GIL held - other threads blocked

t1 = threading.Thread(target=process_data, args=(data1,))
t2 = threading.Thread(target=process_data, args=(data2,))
t1.start()
t2.start()
# Threads execute SEQUENTIALLY despite threading
```

### 5.2 Recommended Python Multi-Threading Pattern (v0.9.3)

**Option 1: Per-Thread Engines** (✅ Recommended)

```python
import threading
from ionosense import ResearchEngine

def worker_thread(thread_id, data):
    # Create engine per thread
    engine = ResearchEngine()
    engine.initialize(config)
    output = engine.process(data)
    return output

threads = []
for i in range(num_threads):
    t = threading.Thread(target=worker_thread, args=(i, dataset[i]))
    threads.append(t)
    t.start()

for t in threads:
    t.join()
```

**Option 2: Multiprocessing** (✅ For true parallelism)

```python
from multiprocessing import Process, Queue
from ionosense import ResearchEngine

def worker_process(data_queue, result_queue):
    engine = ResearchEngine()
    engine.initialize(config)

    while True:
        data = data_queue.get()
        if data is None:
            break
        output = engine.process(data)
        result_queue.put(output)

# Each process has separate GIL - true parallelism
processes = [Process(target=worker_process, args=(data_q, result_q))
             for _ in range(num_cpus)]
```

### 5.3 Future GIL Release (v0.9.4+)

Planned enhancement:
```cpp
// Future implementation
py::array_t<float> process(py::array_t<float> input) {
    {
        py::gil_scoped_release release;  // Release GIL
        engine_->process(input.data(), output_buffer_.data(), size);
        // Python threads can run during GPU processing
    }
    // GIL automatically reacquired
    return py::array(...);
}
```

---

## 6. Usage Examples

### 6.1 Single-Threaded Usage (Simple)

```cpp
#include "ionosense/engines/research_engine.hpp"

int main() {
    ionosense::ResearchEngine engine;
    ionosense::EngineConfig config;
    config.nfft = 1024;
    config.batch = 2;

    engine.initialize(config);

    std::vector<float> input(1024 * 2);
    std::vector<float> output((1024/2 + 1) * 2);

    engine.process(input.data(), output.data(), input.size());

    return 0;
}
```

### 6.2 Multi-Threaded Processing (Per-Thread Instances)

```cpp
#include <thread>
#include <vector>
#include "ionosense/executors/batch_executor.hpp"

void process_chunk(int thread_id,
                   const std::vector<float>& data,
                   std::vector<float>& output) {
    // ✅ Each thread creates its own executor
    ionosense::BatchExecutor executor;

    ionosense::ExecutorConfig config;
    config.nfft = 1024;
    config.batch = 4;
    config.stream_count = 3;

    auto stages = ionosense::StageFactory::create_default_pipeline();
    executor.initialize(config, std::move(stages));

    executor.submit(data.data(), output.data(), data.size());

    std::cout << "Thread " << thread_id << " completed\n";
}

int main() {
    const int num_threads = 4;
    std::vector<std::thread> threads;

    std::vector<std::vector<float>> datasets(num_threads);
    std::vector<std::vector<float>> outputs(num_threads);

    // Initialize data
    for (int i = 0; i < num_threads; ++i) {
        datasets[i].resize(1024 * 4);
        outputs[i].resize((1024/2 + 1) * 4);
    }

    // Launch threads with independent executor instances
    for (int i = 0; i < num_threads; ++i) {
        threads.emplace_back(process_chunk, i,
                           std::ref(datasets[i]),
                           std::ref(outputs[i]));
    }

    // Wait for completion
    for (auto& t : threads) {
        t.join();
    }

    return 0;
}
```

### 6.3 Multi-GPU Processing

```cpp
#include <thread>
#include "ionosense/executors/batch_executor.hpp"

void process_on_gpu(int gpu_id, const std::vector<float>& data) {
    // ✅ Bind thread to specific GPU
    cudaSetDevice(gpu_id);

    ionosense::BatchExecutor executor;
    ionosense::ExecutorConfig config;
    config.nfft = 2048;
    config.batch = 8;
    config.device_id = gpu_id;  // Explicit device selection

    auto stages = ionosense::StageFactory::create_default_pipeline();
    executor.initialize(config, std::move(stages));

    std::vector<float> output((2048/2 + 1) * 8);
    executor.submit(data.data(), output.data(), data.size());
}

int main() {
    int device_count;
    cudaGetDeviceCount(&device_count);

    std::vector<std::thread> gpu_threads;
    std::vector<std::vector<float>> datasets(device_count);

    // Distribute work across GPUs
    for (int gpu = 0; gpu < device_count; ++gpu) {
        gpu_threads.emplace_back(process_on_gpu, gpu, std::ref(datasets[gpu]));
    }

    for (auto& t : gpu_threads) {
        t.join();
    }

    return 0;
}
```

### 6.4 Python Multi-Processing Example

```python
from multiprocessing import Pool
from ionosense import ResearchEngine
import numpy as np

def process_signal(data_chunk):
    """Process one chunk of data (runs in separate process)"""
    engine = ResearchEngine()
    config = {
        'nfft': 1024,
        'batch': 4,
        'overlap': 0.75
    }
    engine.initialize(config)

    output = engine.process(data_chunk)
    return output

if __name__ == '__main__':
    # Load dataset
    dataset = [np.random.randn(1024 * 4) for _ in range(100)]

    # Process in parallel (4 processes, each with own engine)
    with Pool(processes=4) as pool:
        results = pool.map(process_signal, dataset)

    print(f"Processed {len(results)} chunks")
```

---

## 7. Known Issues & Limitations

### 7.1 Current Limitations (v0.9.3)

| Issue | Severity | Workaround | Planned Fix |
|-------|----------|------------|-------------|
| No GIL release in Python bindings | Low | Use multiprocessing instead of threading | v0.9.4 |
| `rand()` in test code | Low | Test-only, doesn't affect production | v0.9.4 |
| No thread-safe executor variant | Info | Use per-thread instances | Future (if needed) |
| No atomic frame counter | Low | Don't query stats during submit() | Future (if needed) |

### 7.2 What Is NOT Supported

❌ **Concurrent calls to the same executor instance**:
```cpp
BatchExecutor exec;
std::thread t1([&]{ exec.submit(data1, out1, size); });  // ❌ Data race
std::thread t2([&]{ exec.submit(data2, out2, size); });  // ❌ Undefined behavior
```

❌ **Querying stats during processing** (if using external threads):
```cpp
BatchExecutor exec;
std::thread t1([&]{ exec.submit(data, output, size); });
ProcessingStats stats = exec.get_stats();  // ❌ Potential data race
t1.join();
```

❌ **Destroying executor while another thread uses it**:
```cpp
BatchExecutor* exec = new BatchExecutor();
std::thread t1([&]{ exec->submit(data, output, size); });
delete exec;  // ❌ Use-after-free if t1 still running
```

### 7.3 Testing Considerations

**Test Code Issue** (cpp/tests/test_research_engine.cpp:86):
```cpp
// ⚠️ Thread-hostile function in test fixture
std::vector<float> generate_noise(int size) {
    srand(0);  // Global state - not thread-safe
    for (int i = 0; i < size; ++i) {
        signal[i] = (static_cast<float>(rand()) / RAND_MAX) * 2.0f - 1.0f;
    }
    return signal;
}
```

**Impact**:
- Only affects test code (not production)
- Tests are single-threaded (safe in current usage)
- Will be fixed in v0.9.4 with `std::mt19937`

---

## 8. Future Plans (v0.9.4+)

### 8.1 Planned Enhancements

**High Priority**:
1. **GIL Release in Python Bindings**
   - Add `py::gil_scoped_release` in `process()` and `process_async()`
   - Enable true Python multi-threading

2. **Thread-Safe Test Utilities**
   - Replace `rand()` with `std::mt19937` in test fixtures

**Medium Priority**:
3. **Atomic Statistics** (Optional)
   - Use `std::atomic<uint64_t>` for `frame_counter_`
   - Enable safe stats querying during processing

4. **Thread Safety Documentation in Headers**
   - Add Doxygen `@threadsafety` tags
   - Document expected usage patterns

**Low Priority (Future Consideration)**:
5. **Thread-Safe Executor Variant** (If needed)
   ```cpp
   class ThreadSafeExecutor {
       std::mutex submit_mutex_;
       // Internal synchronization for shared access
   };
   ```

### 8.2 Compatibility Guarantees

**Backward Compatibility**:
- Thread safety model will remain thread-compatible (no breaking changes)
- Adding GIL release is **non-breaking** (improves Python performance)
- Thread-safe variants (if added) will be **new classes**, not replacements

---

## Appendix A: Quick Reference

### Thread Safety Checklist

When using Ionosense HPC in multi-threaded contexts:

- [ ] ✅ Create separate executor instances per thread
- [ ] ✅ Use `cudaSetDevice()` if distributing across GPUs
- [ ] ❌ Do NOT share executor instances between threads
- [ ] ❌ Do NOT call `submit()` concurrently on same instance
- [ ] ❌ Do NOT destroy executor while another thread uses it
- [ ] ✅ Use Python multiprocessing (not threading) for parallelism in v0.9.3

### Common Patterns

| Pattern | Thread Safety | Use Case |
|---------|---------------|----------|
| Per-thread executors | ✅ Safe | Parallel batch processing |
| Multi-GPU with `cudaSetDevice()` | ✅ Safe | Distribute across GPUs |
| Python multiprocessing | ✅ Safe | Python parallelism (v0.9.3) |
| Shared executor with mutex | ⚠️ Safe but slow | Not recommended |
| Shared executor without sync | ❌ Unsafe | Never do this |

---

## References

1. Google C++ Style Guide - Thread Safety Annotations
   https://google.github.io/styleguide/cppguide.html#Thread_Annotations

2. CUDA C++ Programming Guide - Thread Safety
   https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#thread-safety

3. cuFFT Library Documentation - Thread Safety
   https://docs.nvidia.com/cuda/cufft/index.html#thread-safety

4. C++ Reference - Memory Model and Data Races
   https://en.cppreference.com/w/cpp/language/memory_model

5. Python Threading and the GIL
   https://docs.python.org/3/library/threading.html
