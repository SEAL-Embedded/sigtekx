# Document Thread-Safety Contract for StreamingExecutor

## Problem

The StreamingExecutor's public API does not explicitly document its thread-safety guarantees, particularly for the async mode with background threads. Users attempting concurrent `submit()` calls from multiple threads may encounter race conditions or undefined behavior.

**Impact:**
- Undocumented API contract leads to misuse
- Potential race conditions when multiple threads call `submit_async()`
- Ring buffer access without synchronization in presence of concurrent background thread
- No guidance on safe usage patterns for async processing

**Roadmap Context:**
- Blocks Phase 1 work requiring multi-threaded workloads
- Real-time applications may attempt concurrent submission

## Current Implementation

**File:** `cpp/include/sigtekx/executors/streaming_executor.hpp` (class documentation)
**File:** `cpp/src/executors/streaming_executor.cpp` (lines 417-473)

**Observed Behavior:**

```cpp
// StreamingExecutor.hpp - No thread-safety documentation
class StreamingExecutor : public PipelineExecutor {
 public:
  StreamingExecutor();
  ~StreamingExecutor() override;

  // No mention of thread-safety constraints
  void initialize(const ExecutorConfig& config,
                  std::vector<std::unique_ptr<ProcessingStage>> stages) override;

  std::vector<float> submit(const float* input,
                            int samples_per_channel) override;

  // Async variant - thread safety unclear
  std::vector<float> submit_async(
      const float* input,
      int samples_per_channel,
      std::function<void(const std::vector<float>&)> callback,
      int timeout_ms = 1000) override;
};
```

**Problematic Access Pattern (lines 442-472 in streaming_executor.cpp):**

```cpp
// submit_async() implementation
std::vector<float> StreamingExecutor::submit_async(...) {
  // No mutex acquisition here!

  // Ring buffer access without locking
  while (input_ring_buffers_[0]->available() >= samples_needed_per_channel) {
    // ❌ If background thread (consumer_loop) is running, concurrent access!
    for (int ch = 0; ch < config_.channels; ++ch) {
      input_ring_buffers_[ch]->extract_frame(...);  // Race condition potential
    }
  }

  // Background thread also accesses input_ring_buffers_ (line 730)
  // RingBuffer uses lock-free atomics internally, but API contract unclear
}
```

**What's Unclear:**
1. Can multiple threads call `submit()` concurrently?
2. Is async mode single-producer only?
3. What synchronization guarantees exist for ring buffer access?
4. Can `initialize()` and `submit()` be called concurrently?

## Proposed Solution

Add comprehensive thread-safety documentation to the public API and clarify implementation constraints.

### API Documentation (streaming_executor.hpp)

```cpp
/**
 * @class StreamingExecutor
 * @brief Streaming pipeline executor with optional async processing
 *
 * ## Thread Safety
 *
 * **Single-Threaded Producer Requirement:**
 * - Only ONE thread may call submit() or submit_async() at any given time
 * - Multiple concurrent calls to submit() result in undefined behavior
 *
 * **Background Thread Semantics (when enable_background_thread=true):**
 * - Internal consumer thread processes data asynchronously
 * - Ring buffers use lock-free atomics for producer-consumer coordination
 * - Producer (caller of submit) and consumer (background thread) synchronized via:
 *   - Atomic operations in RingBuffer
 *   - Condition variable cv_data_ready_ for data availability
 *   - Mutex result_mutex_ for result queue protection
 *
 * **Safe Usage Patterns:**
 * ```cpp
 * // CORRECT: Single thread submits data
 * executor.submit(input1, size);
 * executor.submit(input2, size);
 *
 * // WRONG: Multiple threads submitting concurrently
 * std::thread t1([&] { executor.submit(input1, size); });
 * std::thread t2([&] { executor.submit(input2, size); });  // ❌ RACE!
 * ```
 *
 * **Shutdown Safety:**
 * - reset() and destructor properly join background thread
 * - Safe to call reset() from thread that created executor
 * - All pending async operations will be cancelled on reset()
 */
class StreamingExecutor : public PipelineExecutor {
  // ... rest of class
};
```

### Implementation Comments (streaming_executor.cpp)

**Add comment at line 442 (submit_async start):**

```cpp
std::vector<float> StreamingExecutor::submit_async(...) {
  // THREAD SAFETY NOTE:
  // This method assumes SINGLE-PRODUCER model. Concurrent calls from multiple
  // threads will result in race conditions accessing input_ring_buffers_.
  // RingBuffer uses lock-free atomics internally for producer-consumer sync,
  // but does NOT protect against multiple concurrent producers.

  // Background thread (consumer_loop) is the single consumer, synchronized via:
  //   - cv_data_ready_ condition variable
  //   - result_mutex_ for result queue

  // ... existing implementation
}
```

**Add comment at line 730 (consumer_loop wait):**

```cpp
void StreamingExecutor::consumer_loop() {
  // THREAD SAFETY: Consumer thread (this loop) is the single consumer.
  // Producer thread(s) push samples via submit() - assumed single producer.
  // Synchronization via:
  //   - RingBuffer lock-free atomics (producer writes, consumer reads)
  //   - cv_data_ready_ notified by producer when data available

  cv_data_ready_.wait(lock, [this, samples_needed_per_channel] {
    // ... predicate
  });
}
```

## Additional Technical Insights

### Lock-Free Ring Buffer Semantics

The `RingBuffer` class (ring_buffer.hpp) uses atomic operations for coordination:
```cpp
std::atomic<size_t> write_index_;  // Producer updates
std::atomic<size_t> read_index_;   // Consumer updates
```

**Single-Producer/Single-Consumer (SPSC) Guarantee:**
- Atomics provide happens-before relationship between producer and consumer
- No mutex needed for SPSC pattern
- **BREAKS** if multiple producers (Multiple-Producer/Single-Consumer would require locks)

### Background Thread Lifecycle

**Initialization (line 720-725):**
```cpp
if (config_.enable_background_thread) {
  cudaSetDevice(config_.device_index);
  consumer_thread_ = std::thread(&StreamingExecutor::consumer_loop, this);
}
```

**Shutdown (line 237-248):**
```cpp
if (consumer_thread_.joinable()) {
  stop_flag_.store(true, std::memory_order_release);
  cv_data_ready_.notify_all();  // Wake thread from wait
  consumer_thread_.join();      // Block until exit
}
```

Thread is **always joined** before reset() returns, ensuring no dangling thread.

## Implementation Tasks

- [ ] Open `cpp/include/sigtekx/executors/streaming_executor.hpp`
- [ ] Add "Thread Safety" section to class docstring (line 45-55)
- [ ] Document single-producer requirement
- [ ] Explain async mode background thread coordination
- [ ] Add safe/unsafe usage examples
- [ ] Open `cpp/src/executors/streaming_executor.cpp`
- [ ] Add thread-safety comment at `submit_async()` start (line 442)
- [ ] Add thread-safety comment at `consumer_loop()` start (line 720)
- [ ] Explain ring buffer SPSC assumptions
- [ ] Document synchronization primitives used
- [ ] Update user-facing documentation in `docs/api/executors.md` (if exists)
- [ ] Add multi-threading example to Python docs showing WRONG pattern
- [ ] Add unit test documenting expected behavior: `StreamingExecutorTest.ConcurrentSubmitUnsafe`

## Edge Cases to Handle

- **Concurrent initialize() and submit():**
  - Currently no protection - undefined behavior
  - Document: "Do not call initialize() while submit() is running"

- **Multiple Executors, One Thread Each:**
  - Safe - each executor has its own resources
  - Document as recommended pattern for multi-threaded workflows

- **Reset During Active Submit:**
  - Background thread will be stopped, submit may fail
  - Document expected behavior: "submit() may throw after reset()"

## Testing Strategy

### Documentation Test (Add to `cpp/tests/executors/test_streaming_executor.cpp`)

```cpp
TEST_F(StreamingExecutorTest, ThreadSafetyDocumentation) {
  // This test DOCUMENTS the expected behavior, not necessarily tests it
  // (testing race conditions is non-deterministic)

  ExecutorConfig config = create_test_config();
  config.mode = ExecutorMode::STREAMING;
  config.enable_background_thread = true;

  executor_.initialize(config, std::move(stages));

  // CORRECT USAGE: Single thread
  std::vector<float> input(config.nfft);
  std::fill(input.begin(), input.end(), 1.0f);

  EXPECT_NO_THROW(executor_.submit(input.data(), config.nfft));
  EXPECT_NO_THROW(executor_.submit(input.data(), config.nfft));

  // DOCUMENTED UNSAFE USAGE (not tested to avoid flaky tests):
  // std::thread t1([&] { executor_.submit(input.data(), config.nfft); });
  // std::thread t2([&] { executor_.submit(input.data(), config.nfft); });
  // // ❌ Race condition - undefined behavior
}

TEST_F(StreamingExecutorTest, MultipleExecutorsSafe) {
  // SAFE: Each thread has its own executor
  ExecutorConfig config = create_test_config();
  config.mode = ExecutorMode::STREAMING;

  auto run_executor = [&]() {
    StreamingExecutor executor;
    executor.initialize(config, create_test_stages());

    std::vector<float> input(config.nfft, 1.0f);
    for (int i = 0; i < 10; ++i) {
      executor.submit(input.data(), config.nfft);
    }
  };

  std::thread t1(run_executor);
  std::thread t2(run_executor);

  EXPECT_NO_THROW(t1.join());
  EXPECT_NO_THROW(t2.join());
}
```

### Manual Verification

```bash
# Build with ThreadSanitizer (detects data races)
cmake -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS="-fsanitize=thread" ..
cmake --build .

# Run tests - should NOT report races (since single-threaded usage)
./build/sigtekx_tests --gtest_filter="StreamingExecutorTest.*"

# Expected: All tests PASS, no ThreadSanitizer warnings
```

## Acceptance Criteria

- [ ] Class docstring includes "Thread Safety" section with:
  - [ ] Single-producer requirement clearly stated
  - [ ] Async mode synchronization explained
  - [ ] Safe usage example
  - [ ] Unsafe usage example (commented as "WRONG")
- [ ] Implementation comments added at key synchronization points
- [ ] Documentation test added showing correct single-threaded usage
- [ ] Multi-executor test added showing safe parallel pattern
- [ ] User-facing documentation updated (if exists)
- [ ] Code review confirms thread-safety contract is clear
- [ ] No new compiler warnings introduced

## Benefits

- **Clear API Contract:** Users understand thread-safety limitations
- **Prevents Misuse:** Explicit documentation reduces debugging time
- **Educational Value:** Comments explain lock-free synchronization patterns
- **Future Extensibility:** Clear contract allows safe evolution to multi-producer if needed
- **Developer Confidence:** Thread-safety guarantees explicitly stated
- **Reduced Support Burden:** Fewer "why does async mode crash?" questions

---

**Labels:** `documentation`, `team-1-cpp`, `c++`, `thread-safety`

**Estimated Effort:** 2-3 hours (documentation + tests)

**Priority:** HIGH (blocks safe multi-threaded usage)

**Roadmap Phase:** Phase 0 (prerequisite for Phase 1)

**Dependencies:** None

**Blocks:** Multi-threaded benchmark workflows, concurrent experiment runs
