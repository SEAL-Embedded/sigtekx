# Fix Broken Condition Variable Wait in StreamingExecutor

## Problem

The StreamingExecutor's `submit()` method in async mode creates a **temporary condition variable** instead of using the member `cv_data_ready_`, causing async processing to fail completely. The wait never actually waits on the correct CV, leading to immediate timeouts or undefined behavior.

**Impact:**
- Async streaming mode is non-functional
- `submit()` with callback returns before processing completes
- Timeouts occur immediately (wait on temp CV that's never notified)
- Critical for real-time applications using background processing

**Roadmap Context:**
- Blocks Phase 1 work that may stress async execution paths
- Real-time mode (Issue #013 RTF validation) requires reliable async processing

## Current Implementation

**File:** `cpp/src/executors/streaming_executor.cpp` (lines 337-348)

```cpp
// BUGGY CODE - Creates temporary CV!
if (enable_background_thread_) {
  if (std::cv_status::timeout ==
      std::condition_variable_any().wait_until(lock, deadline)) {  // ❌ BUG: temporary CV
    throw std::runtime_error("Async processing timeout: no result after " +
                             std::to_string(timeout_ms) + "ms");
  }

  if (!result_queue_.empty()) {
    result = std::move(result_queue_.front());
    result_queue_.pop();
  }
}
```

**What's Wrong:**
1. `std::condition_variable_any()` creates a **new temporary object**
2. The temporary is destroyed immediately after `wait_until()` returns
3. The actual member `cv_data_ready_` (line 813) is **never used** for waiting
4. Background thread notifies `cv_data_ready_` (line 759), but main thread waits on different CV
5. Result: wait returns immediately or behaves unpredictably

## Proposed Solution

Use the member `cv_data_ready_` with proper wait predicate:

**File:** `cpp/src/executors/streaming_executor.cpp` (lines 337-348)

```cpp
// FIXED CODE - Use member CV with predicate
if (enable_background_thread_) {
  // Wait with predicate checking both result availability and stop condition
  if (std::cv_status::timeout ==
      cv_data_ready_.wait_until(lock, deadline, [this] {
        return !result_queue_.empty() || stop_flag_.load(std::memory_order_acquire);
      })) {
    // Timeout occurred - check why
    if (stop_flag_.load(std::memory_order_acquire)) {
      throw std::runtime_error("Async processing stopped during wait");
    }
    throw std::runtime_error("Async processing timeout: no result after " +
                             std::to_string(timeout_ms) + "ms");
  }

  // Result must be available (predicate was true)
  if (!result_queue_.empty()) {
    result = std::move(result_queue_.front());
    result_queue_.pop();
  }
}
```

**Key Changes:**
1. Replace `std::condition_variable_any()` with `cv_data_ready_` (member reference)
2. Add wait predicate lambda checking `result_queue_` and `stop_flag_`
3. Distinguish timeout from stop condition in error handling
4. Ensure result availability after successful wait

## Additional Technical Insights

- **Spurious Wakeups:** The predicate prevents spurious wakeups from causing incorrect behavior
  - CV can wake spuriously (POSIX spec allows this)
  - Predicate ensures we only return when result truly available

- **Memory Ordering:**
  - `stop_flag_` uses `memory_order_acquire` to synchronize with producer's `release` store
  - Ensures visibility of result_queue modifications

- **Exception Safety:**
  - Lock (`result_mutex_`) is held throughout wait, automatically released on exception
  - `std::unique_lock` RAII ensures no deadlocks

- **Performance:**
  - Predicate-based wait is standard practice, zero overhead vs manual check
  - Avoids busy-waiting or multiple wake-sleep cycles

## Implementation Tasks

- [ ] Open `cpp/src/executors/streaming_executor.cpp`
- [ ] Locate `submit()` method async mode section (line 337)
- [ ] Replace `std::condition_variable_any().wait_until(lock, deadline)` with:
  ```cpp
  cv_data_ready_.wait_until(lock, deadline, [this] {
      return !result_queue_.empty() || stop_flag_.load(std::memory_order_acquire);
  })
  ```
- [ ] Add check for stop condition after timeout (distinguish from timeout)
- [ ] Add assertion after wait: `assert(!result_queue_.empty() || timeout || stopped)`
- [ ] Test async mode with real workload (see Testing Strategy)
- [ ] Add unit test: `StreamingExecutorTest.AsyncProcessingWithTimeout`
- [ ] Add unit test: `StreamingExecutorTest.AsyncProcessingStopDuringWait`
- [ ] Update comments explaining predicate logic
- [ ] Commit: `fix(executor): use member CV with predicate in streaming async wait`

## Edge Cases to Handle

- **Stop During Wait:**
  - If `stop_flag_` set while waiting, wake immediately
  - Throw different exception: "Async processing stopped" vs "Timeout"

- **Empty Queue After Wake:**
  - Predicate ensures queue non-empty OR stop flag set
  - If stop flag, throw; if queue empty after wake, assert failure (bug)

- **Multiple Consumers (Not Current Design):**
  - Current design assumes single consumer thread
  - If extended to multiple consumers, needs queue locking revisited

- **Very Short Timeouts (<1ms):**
  - May timeout before background thread starts processing
  - Document minimum recommended timeout (e.g., 10ms)

## Testing Strategy

### Unit Test (Add to `cpp/tests/executors/test_streaming_executor.cpp`):

```cpp
TEST_F(StreamingExecutorTest, AsyncProcessingWithTimeout) {
  // Config with async mode enabled
  ExecutorConfig config = create_test_config();
  config.mode = ExecutorMode::STREAMING;
  config.enable_background_thread = true;

  executor_.initialize(config, std::move(stages));

  // Submit with callback and reasonable timeout
  std::vector<float> result;
  auto start = std::chrono::steady_clock::now();

  EXPECT_NO_THROW({
    result = executor_.submit([](const std::vector<float>& output) {
      // Callback: simulate brief processing
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
    });
  });

  auto elapsed = std::chrono::steady_clock::now() - start;
  EXPECT_GT(elapsed, std::chrono::milliseconds(50));  // At least processing time
  EXPECT_LT(elapsed, std::chrono::milliseconds(500)); // But not full timeout
  EXPECT_FALSE(result.empty());
}

TEST_F(StreamingExecutorTest, AsyncTimeoutOccurs) {
  ExecutorConfig config = create_test_config();
  config.mode = ExecutorMode::STREAMING;
  config.enable_background_thread = true;

  executor_.initialize(config, std::move(stages));

  // Submit with callback that takes longer than timeout
  EXPECT_THROW({
    executor_.submit([](const std::vector<float>&) {
      std::this_thread::sleep_for(std::chrono::seconds(10));  // Too slow
    }, 100);  // 100ms timeout
  }, std::runtime_error);
}

TEST_F(StreamingExecutorTest, AsyncStopDuringWait) {
  ExecutorConfig config = create_test_config();
  config.mode = ExecutorMode::STREAMING;
  config.enable_background_thread = true;

  executor_.initialize(config, std::move(stages));

  // Start async operation
  std::thread stopper([this]() {
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    executor_.reset();  // Triggers stop_flag
  });

  // Should throw "stopped" not "timeout"
  EXPECT_THROW({
    executor_.submit([](const std::vector<float>&) {
      std::this_thread::sleep_for(std::chrono::seconds(1));
    }, 5000);
  }, std::runtime_error);

  stopper.join();
}
```

### Integration Test (Manual):

```bash
# Build with fixed code
cmake --build build --target sigtekx_tests

# Run streaming executor tests
./build/sigtekx_tests --gtest_filter="StreamingExecutorTest.*Async*"

# Expected: All 3 async tests PASS
```

### Real-World Test:

```python
# Test from Python (if bindings expose async mode)
from sigtekx import StreamingExecutor, EngineConfig

config = EngineConfig(mode='streaming', enable_background_thread=True)
executor = StreamingExecutor()
executor.initialize(config)

# Should complete without timeout
result = executor.submit(input_data, callback=lambda x: print("Done"))
assert len(result) > 0
```

## Acceptance Criteria

- [ ] `std::condition_variable_any()` replaced with `cv_data_ready_` member
- [ ] Wait predicate checks both `result_queue_` and `stop_flag_`
- [ ] Timeout exception distinct from stop exception
- [ ] Unit test `AsyncProcessingWithTimeout` passes
- [ ] Unit test `AsyncTimeoutOccurs` passes
- [ ] Unit test `AsyncStopDuringWait` passes
- [ ] Existing `StreamingExecutorTest` suite still passes (no regressions)
- [ ] Manual test with real workload completes successfully
- [ ] Code review confirms CV semantics correct
- [ ] Documentation updated with async mode behavior

## Benefits

- **Fixes Critical Bug:** Async streaming mode becomes functional
- **Enables Real-Time Workflows:** Background processing works as designed
- **Proper Thread Synchronization:** Correct use of CV with predicate
- **Clear Error Messages:** Timeout vs stop conditions distinguished
- **Testability:** Unit tests prevent regression
- **Phase 1 Readiness:** Removes blocker for stress-testing async paths

---

**Labels:** `bug`, `team-1-cpp`, `c++`, `reliability`

**Estimated Effort:** 1-2 hours (fix + tests)

**Priority:** CRITICAL (blocks async mode usage)

**Roadmap Phase:** Phase 0 (prerequisite for Phase 1)

**Dependencies:** None

**Blocks:** Issue #013 (RTF validation - may use async mode)
