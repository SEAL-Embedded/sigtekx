# StreamingExecutor Condition Variable Fix: A Deep Dive

**Author:** Senior Engineer & PhD Professor Mode
**Date:** 2025-12-16
**Context:** Fix for broken async processing in StreamingExecutor
**Files Modified:** `cpp/src/executors/streaming_executor.cpp`, `cpp/tests/executors/test_streaming_executor.cpp`

---

## Table of Contents

- [Part 1: The Theoretical Foundation](#part-1-the-theoretical-foundation)
- [Part 2: What Was Broken](#part-2-what-was-broken)
- [Part 3: Line-by-Line Walkthrough](#part-3-line-by-line-walkthrough)
- [Part 4: The Test Suite](#part-4-the-test-suite)
- [Part 5: Connecting the Dots](#part-5-connecting-the-dots)
- [Part 6: Key Takeaways](#part-6-key-takeaways)
- [Part 7: Beyond This Fix](#part-7-beyond-this-fix)
- [Questions to Test Your Understanding](#questions-to-test-your-understanding)

---

## 🎓 Part 1: The Theoretical Foundation (Professor Mode)

### What We're Solving: The Producer-Consumer Problem

This is a **classic synchronization problem** from concurrent programming theory, first formalized by Dijkstra in the 1960s. Let me explain the mental model:

**The Setup:**
- **Producer Thread** (main thread): Calls `submit()`, wants a result back
- **Consumer Thread** (background thread): Processes data in a loop, produces results
- **Shared Resource**: `result_queue_` (a FIFO queue)
- **Synchronization Challenge**: How does the producer know when a result is ready?

**Three Fundamental Approaches:**

#### 1. Busy-waiting (polling) ❌

```cpp
while (result_queue_.empty()) {
  // Spin! Burn CPU!
}
```

- Simple but wastes 100% CPU core
- Producer checks millions of times per second

#### 2. Sleep-polling (timed backoff) ⚠️

```cpp
while (result_queue_.empty()) {
  std::this_thread::sleep_for(10ms);
}
```

- Better but still wastes CPU
- Trade-off: shorter sleep = more CPU, longer sleep = higher latency

#### 3. Condition Variables (event-driven) ✅

```cpp
cv.wait(lock, [&]{ return !result_queue_.empty(); });
```

- **Zero CPU** while waiting (OS scheduler knows thread is blocked)
- **Instant wake-up** when notified (microsecond latency)
- **Predicate-based**: Protects against spurious wakeups

### Why Condition Variables?

They implement **Mesa-style monitors** (Lampson & Redell, 1980):

- **Mutual exclusion**: Only one thread modifies shared state at a time (mutex)
- **Condition synchronization**: Threads wait for logical conditions to become true (CV)
- **No busy-waiting**: OS scheduler deschedules the waiting thread

---

## 🔧 Part 2: What Was Broken (Senior Engineer Mode)

### The Bug: Creating a Temporary CV

Let me show you the critical line:

```cpp
// BEFORE (BROKEN):
std::condition_variable_any().wait_until(lock, deadline)
                            ^^
                    This creates a NEW object!
```

**What's happening here?**

1. `std::condition_variable_any()` - This is a **constructor call**, creating a temporary object
2. `.wait_until(lock, deadline)` - We call wait on this temporary
3. After the statement ends, the temporary is **destroyed**

**The Problem:**

Meanwhile, in the consumer thread (line 790 after our fix):

```cpp
cv_data_ready_.notify_one();  // Notifies the MEMBER variable
```

So we have:
- Consumer notifying `cv_data_ready_` (member variable, lives for executor lifetime)
- Producer waiting on `std::condition_variable_any()` (temporary, lives for one statement)

These are **completely different objects**! It's like:
- Consumer: "Hey, result is ready!" *shouts into room A*
- Producer: "I'm waiting for a result..." *listens in room B*

They'll never communicate!

### Why Didn't the Compiler Stop Us?

This is syntactically valid C++. The compiler sees:

```cpp
condition_variable_any temp;  // Construct
temp.wait_until(lock, deadline);  // Use
// Destroy temp
```

Perfectly legal code. Just semantically wrong for our use case.

---

## 📝 Part 3: Line-by-Line Walkthrough

### Change 1: The Producer's Wait (lines 334-346)

**Context:** This is inside `StreamingExecutor::submit()`, the main thread that user code calls.

#### BEFORE (lines 334-341 old):

```cpp
while (result_queue_.empty() &&
       std::chrono::steady_clock::now() < deadline) {
  // Wait with timeout, checking periodically
  if (std::cv_status::timeout ==
      std::condition_variable_any().wait_until(lock, deadline)) {
    break;  // Timeout reached
  }
}
```

**Professor says:** This is a **hybrid approach** - manually implementing timeout logic with busy-polling.

**Breakdown:**
- `while (result_queue_.empty()` - Check if result available
- `&& std::chrono::steady_clock::now() < deadline)` - Check if timeout expired
- **Problem 1**: Manual loop = vulnerable to **spurious wakeups** (more below)
- **Problem 2**: Redundant - CV already supports timeouts!

```cpp
if (std::cv_status::timeout ==
    std::condition_variable_any().wait_until(lock, deadline)) {
  break;  // Timeout reached
}
```

**Engineer says:** This is the smoking gun 🔫

**Breakdown:**
- `std::condition_variable_any()` - **Creates a NEW, temporary CV**
- `.wait_until(lock, deadline)` - Wait on this temporary
- `if (std::cv_status::timeout == ...)` - Check return value
- **Problem**: The temporary CV is **never notified** by the consumer!

**What actually happens:**
1. Temporary CV constructed
2. `wait_until()` called → thread sleeps
3. **EITHER:**
   - a) Deadline expires → returns `cv_status::timeout`, breaks loop
   - b) **Spurious wakeup** (OS randomly wakes thread) → returns `cv_status::no_timeout`, continues loop
4. Temporary CV destroyed
5. Loop repeats, creating ANOTHER temporary CV

So this is effectively **sleep-polling** with extra steps!

---

#### AFTER (lines 334-346 new):

```cpp
// Wait with predicate checking both result availability and stop condition
if (!cv_data_ready_.wait_until(lock, deadline, [this] {
      return !result_queue_.empty() || stop_flag_.load(std::memory_order_acquire);
    })) {
  // Predicate returned false (timeout occurred)
  if (stop_flag_.load(std::memory_order_acquire)) {
    throw std::runtime_error(
        "Async processing stopped during wait");
  }
  throw std::runtime_error(
      "Async processing timeout: no result after " +
      std::to_string(config_.timeout_ms > 0 ? config_.timeout_ms : 2000) + "ms");
}
```

**Professor says:** This is the **canonical form** of predicate-based CV wait.

Let me unpack this carefully:

#### Line 1: The comment

```cpp
// Wait with predicate checking both result availability and stop condition
```

- Documents **what** we're waiting for (result OR stop)
- Critical for maintainability - you need to know the invariant!

#### Line 2: The CV wait call

```cpp
if (!cv_data_ready_.wait_until(lock, deadline, [this] {
```

Breaking this down:
- `cv_data_ready_` - **THE MEMBER VARIABLE** that consumer notifies
- `.wait_until(` - Timed wait variant (has deadline)
- `lock` - The mutex lock (already held, `result_mutex_`)
- `deadline` - When to give up
- `[this] {` - Lambda predicate (captures `this` to access member variables)

**How `wait_until` works with predicate:**

The C++ standard specifies this **expands to**:

```cpp
while (!predicate()) {  // While condition NOT met
  if (wait_until_internal(lock, deadline) == cv_status::timeout) {
    return predicate();  // Return final predicate state
  }
}
return true;  // Predicate became true
```

So the library **automatically** handles:
1. **Spurious wakeups** - loops until predicate actually true
2. **Timeout checking** - stops looping if deadline passes
3. **Return value** - `true` if predicate satisfied, `false` if timeout

#### Line 3: The predicate lambda

```cpp
return !result_queue_.empty() || stop_flag_.load(std::memory_order_acquire);
```

**Professor says:** This is a **disjunctive predicate** (logical OR).

Breaking it down:
- `!result_queue_.empty()` - **Primary condition**: "Result is ready for me"
- `||` - Logical OR
- `stop_flag_.load(std::memory_order_acquire)` - **Secondary condition**: "Executor is shutting down"

**Why OR, not AND?**
- We want to wake up if **EITHER** condition becomes true
- **Use case 1**: Result arrives → proceed normally
- **Use case 2**: User calls `reset()` → exit gracefully instead of waiting forever

#### The `memory_order_acquire` detail

**Professor says:** This is about the **C++ memory model** (C++11 onwards).

Without going too deep:
- `stop_flag_` is an `std::atomic<bool>` (thread-safe boolean)
- `.load(memory_order_acquire)` means:
  - "Give me the value"
  - "AND ensure all memory writes that happened-before the corresponding `store()` are visible to me"

**Why this matters:**

```cpp
// Consumer thread (somewhere else):
result_queue_.push(result);                        // (1) Write result
stop_flag_.store(true, memory_order_release);      // (2) Set flag

// Producer thread (our code):
if (stop_flag_.load(memory_order_acquire)) {       // (3) Read flag
  // We're GUARANTEED to see the result from (1)
}
```

This is **synchronization** without locks! The acquire/release pair creates a **happens-before relationship**.

**In practice:** If `stop_flag_` is true, we're guaranteed the result queue is in a consistent state (either has result or is being shut down cleanly).

---

#### Lines 4-11: Timeout handling

```cpp
  })) {
  // Predicate returned false (timeout occurred)
  if (stop_flag_.load(std::memory_order_acquire)) {
    throw std::runtime_error(
        "Async processing stopped during wait");
  }
  throw std::runtime_error(
      "Async processing timeout: no result after " +
      std::to_string(config_.timeout_ms > 0 ? config_.timeout_ms : 2000) + "ms");
}
```

**Engineer says:** Notice the **inversion**: `if (!wait_until(...))` checks for `false` return.

**Control flow:**
- `wait_until` returns `false` → timeout occurred (predicate never became true)
- `wait_until` returns `true` → predicate satisfied (either result ready OR stopped)

**Inside the `if (false)` block:**

```cpp
if (stop_flag_.load(std::memory_order_acquire)) {
  throw std::runtime_error("Async processing stopped during wait");
}
```

**Why check `stop_flag_` again?**

**Professor says:** This handles a **race condition**:
1. Deadline expires while `stop_flag_` is false → timeout
2. Before we throw, another thread calls `reset()` → `stop_flag_` becomes true
3. We re-check and throw the **more accurate** exception

This is **defensive programming** - give the user the most helpful error message.

```cpp
throw std::runtime_error(
    "Async processing timeout: no result after " +
    std::to_string(config_.timeout_ms > 0 ? config_.timeout_ms : 2000) + "ms");
```

**Engineer says:** This is a **user-friendly error message**.

- Tells them what went wrong: "timeout"
- Tells them the timeout value (helps debugging)
- Actionable: user can increase timeout or investigate why processing is slow

---

#### Lines 348-358: Post-wait validation

```cpp
// Predicate ensures result is available (unless stopped)
if (stop_flag_.load(std::memory_order_acquire)) {
  throw std::runtime_error(
      "Async processing stopped before result ready");
}
```

**Engineer says:** This is **belt-and-suspenders** safety.

**If we get here:**
- `wait_until` returned `true` (predicate was true)
- Predicate: `!result_queue_.empty() || stop_flag_`

**Two possibilities:**
1. `!result_queue_.empty()` is true → we have a result!
2. `stop_flag_` is true → executor is stopping

This check handles **case 2** - we woke up due to shutdown, not due to result.

```cpp
// Result must be available if we reach here
if (result_queue_.empty()) {
  throw std::runtime_error(
      "Internal error: result queue empty after CV wait returned");
}
```

**Professor says:** This is an **invariant check** (assertion without `assert()`).

**The invariant:** "If we reach this line, `result_queue_` MUST be non-empty."

**Why?**
- We just checked `stop_flag_` is false (didn't throw above)
- Predicate was true
- Predicate is `!result_queue_.empty() || stop_flag_`
- Since `stop_flag_` is false, `!result_queue_.empty()` MUST be true

**So why check?**

**Engineer says:** **Defensive programming** + **Debugging aid**.

If this throws, it means:
- **BUG in the CV logic** (library bug? unlikely)
- **BUG in our predicate** (logic error)
- **BUG in notification** (consumer not notifying correctly)

This error message is **for developers** (you!), not end users. It says "something impossible happened - investigate the synchronization logic!"

```cpp
result = std::move(result_queue_.front());
result_queue_.pop();
got_result = true;
```

**Engineer says:** Standard queue pattern.

- `std::move` - Transfer ownership (avoid copy, these might be large vectors)
- `.pop()` - Remove from queue
- `got_result = true` - Flag for later processing

**Mutex note:** We're still holding `result_mutex_` (the `lock` from line 326), so this is thread-safe.

---

### Change 2: The Consumer's Notification (line 790)

**Context:** This is in `consumer_loop()`, the background thread that processes data.

#### BEFORE (lines 770-774 old):

```cpp
// Store result in queue
{
  std::lock_guard<std::mutex> lock(result_mutex_);
  result_queue_.push(std::move(result));
}
```

**Engineer says:** The consumer produces a result and enqueues it... **but never tells anyone**!

This is like:
- Chef: *finishes cooking meal*
- Chef: *puts meal on shelf*
- Chef: *walks away without ringing bell*
- Waiter: *stands at door waiting for bell that never rings*

---

#### AFTER (lines 785-790 new):

```cpp
// Store result in queue and notify waiting producer
{
  std::lock_guard<std::mutex> lock(result_mutex_);
  result_queue_.push(std::move(result));
}
cv_data_ready_.notify_one();  // Wake producer (outside lock for efficiency)
```

**Line-by-line:**

```cpp
// Store result in queue and notify waiting producer
```

**Engineer says:** Comment updated to reflect new behavior - **always document synchronization!**

```cpp
{
  std::lock_guard<std::mutex> lock(result_mutex_);
  result_queue_.push(std::move(result));
}
```

**No change here** - still need mutex to protect queue modification.

**Why the scope `{ }`?**

**Professor says:** The braces create a **scope** for the lock guard.

When we exit the `}`, the `lock` destructor runs → mutex unlocked.

**Why unlock before notify?**

```cpp
cv_data_ready_.notify_one();  // Wake producer (outside lock for efficiency)
```

**Professor says:** This is a **performance optimization** based on how OS schedulers work.

**Two approaches:**

**Approach A (notify inside lock):**

```cpp
{
  std::lock_guard<std::mutex> lock(result_mutex_);
  result_queue_.push(result);
  cv.notify_one();  // Inside lock
}  // Unlock here
```

**What happens:**
1. Consumer holds `result_mutex_`
2. Consumer calls `notify_one()` → OS wakes up producer
3. **Producer wakes up**, tries to acquire `result_mutex_`
4. **Producer blocks** (consumer still holds mutex!)
5. Consumer releases lock
6. Producer **finally** acquires lock
7. Producer proceeds

**Approach B (notify outside lock):**

```cpp
{
  std::lock_guard<std::mutex> lock(result_mutex_);
  result_queue_.push(result);
}  // Unlock here
cv.notify_one();  // Outside lock
```

**What happens:**
1. Consumer holds `result_mutex_`
2. Consumer releases `result_mutex_`
3. Consumer calls `notify_one()` → OS wakes up producer
4. **Producer wakes up**, tries to acquire `result_mutex_`
5. **Producer acquires immediately** (no contention!)
6. Producer proceeds

**The difference:** Approach B **eliminates a context switch**.

In Approach A:
- Producer wakes up → tries lock → blocks → **sleeps again** → wakes when lock released

In Approach B:
- Producer wakes up → tries lock → **succeeds immediately** → proceeds

**Benchmark impact:** Can save **microseconds** of latency (matters for your RTF < 0.3 target!).

**Is it safe to notify outside the lock?**

**Yes!** The C++ standard says:
> "The `notify_one()` and `notify_all()` functions may be called regardless of whether the mutex associated with the condition variable is locked or not."

The only guarantee: threads waiting on the CV when `notify_one()` is called will wake up. It doesn't matter if the mutex is locked.

**Why it works:**
- The predicate check happens **inside the wait** (while holding the lock)
- When producer wakes and re-checks `!result_queue_.empty()`, it will acquire the lock and see the new value
- The notification itself doesn't access shared state - it's just an OS signal

---

## 🧪 Part 4: The Test Suite (Teaching by Example)

Now let's look at the tests. **Good tests are documentation** - they show how the code should be used and what edge cases matter.

### Test 1: AsyncProcessingSuccess

```cpp
config_.enable_background_thread = true;
config_.timeout_ms = 2000;  // 2 second timeout
```

**Engineer says:** This is the **happy path test**.

**What it validates:**
- Normal async operation works
- Results are produced correctly
- Latency is acceptable (< 500ms)
- Output is non-zero (sanity check)

**Why 2000ms timeout but expect < 500ms?**

This is **defensive test design**:
- **Expected case**: Process completes in ~100ms
- **Assertion**: `EXPECT_LT(elapsed, 500ms)` - ensures it's fast
- **Timeout**: 2000ms - safety margin prevents **flaky tests**

If the test machine is under load, we might take 300ms instead of 100ms. That's okay! But 2000ms would indicate a real problem.

---

### Test 2: AsyncProcessingTimeout

```cpp
config_.timeout_ms = 50;  // Very short timeout

// Submit HALF the required samples - consumer will wait forever for complete frame
auto input = generate_sinusoid(input_size / 2, 10.0f);

// Should timeout because consumer waits for complete frame that never arrives
EXPECT_THROW({
  executor.submit(input.data(), output.data(), input_size / 2);
}, std::runtime_error);
```

**Professor says:** This tests **liveness** (system makes progress) and **timeout correctness**.

**Why submit half the samples?**

**The setup:**
- Consumer's predicate (in `consumer_loop()` line 730-741) waits for:
  ```cpp
  input_ring_buffers_[ch]->available() >= samples_needed_per_channel
  ```
- We need `nfft` samples to process a frame
- We submit `nfft/2` samples

**Result:**
- Consumer waits for more data (predicate never true)
- Producer waits for result (predicate never true)
- **Deadlock scenario** - nobody can make progress

**But we have timeout!**
- After 50ms, producer's `wait_until` returns `false` (timeout)
- Producer throws exception
- Test validates exception is thrown

**Why this test matters:**

In a real system, you might:
- Have a slow input device that stops sending data
- Have network issues in a distributed system
- Have the producer crash

The timeout ensures your system **fails safely** instead of hanging forever.

**Why 50ms specifically?**

**Engineer says:** Fast enough to keep test suite quick, slow enough to be reliable.

- Too short (1ms): Might timeout even during normal processing (flaky test)
- Too long (5000ms): Test suite takes forever
- 50ms: Sweet spot for this test

---

### Test 3: AsyncProcessingStopDuringWait

```cpp
std::thread submit_thread([&]() {
  EXPECT_THROW({
    executor.submit(input.data(), output.data(), input_size / 2);
  }, std::runtime_error);
});

std::this_thread::sleep_for(std::chrono::milliseconds(100));
executor.reset();  // Triggers stop_flag_

submit_thread.join();
```

**Professor says:** This tests **graceful shutdown** - can we stop cleanly while threads are waiting?

**The scenario:**
1. Thread A calls `submit()` with insufficient data → waits forever
2. Main thread sleeps 100ms (ensures Thread A is blocked)
3. Main thread calls `reset()` → sets `stop_flag_ = true` → notifies CV
4. Thread A wakes up, sees `stop_flag_`, throws exception
5. Test validates exception is thrown, thread joins cleanly

**Why this test matters:**

**Real-world scenario:**

```cpp
// User code
StreamingExecutor executor;
executor.initialize(...);

std::thread worker([&]() {
  while (running) {
    executor.submit(data);  // Might be waiting here
  }
});

// User hits Ctrl+C
signal_handler() {
  running = false;
  executor.reset();  // Must wake up the worker thread!
}

worker.join();  // Must not hang forever
```

Without proper stop handling:
- `worker.join()` would **hang forever** waiting for the blocked `submit()` call
- User would have to force-kill the process
- No clean shutdown, potential resource leaks

**With our fix:**
- `reset()` sets `stop_flag_` and notifies CV
- `submit()` wakes up, checks flag, throws exception
- Worker thread catches exception, exits loop
- `join()` completes

**The 100ms sleep:**

**Engineer says:** This is a **synchronization timing assumption**.

We assume 100ms is enough for:
1. Thread A to start
2. Thread A to call `submit()`
3. Thread A to enter `wait_until()` and block

**Is this guaranteed?** No! Threads could be preempted, OS could be slow.

**Is it good enough?** Yes, for a unit test:
- If Thread A hasn't blocked yet, `reset()` sets flag, `submit()` sees it immediately
- If Thread A has blocked, `reset()` wakes it up
- Either way, test should pass

**Could it flake?** In theory yes, in practice rarely:
- 100ms is **enormous** in CPU time (millions of cycles)
- Even on a loaded CI system, thread should be blocked within 100ms

---

### Test 4: MultipleAsyncSubmits

```cpp
// Submit 3 frames consecutively (limited to avoid ring buffer overflow with overlap)
// Ring buffer capacity is 3*nfft, and with 0.75 overlap, each frame leaves
// 0.75*nfft samples in buffer, so 3 submits = 3*nfft samples ≈ capacity limit
for (int i = 0; i < 3; ++i) {
  ...
  executor.submit(...);
  ...
  std::this_thread::sleep_for(std::chrono::milliseconds(10));
}
```

**Professor says:** This tests **system capacity** and **backpressure handling**.

**The deep dive:**

**Understanding overlap:**
- `nfft = 1024`, `overlap = 0.75`
- `hop_size = nfft * (1 - overlap) = 1024 * 0.25 = 256`
- Each frame **consumes** 1024 samples but only **advances** 256 samples
- **768 samples remain** in the ring buffer (the "overlap")

**Ring buffer capacity:**
- `capacity = 3 * nfft = 3072` samples (from exploration)

**Submit 1:**
- Add 1024 samples → buffer has 1024
- Consumer processes: extracts 1024, advances 256
- **Buffer now has: 768 samples**

**Submit 2:**
- Add 1024 samples → buffer has 768 + 1024 = 1792
- Consumer processes: extracts 1024, advances 256
- **Buffer now has: 1536 samples**

**Submit 3:**
- Add 1024 samples → buffer has 1536 + 1024 = 2560
- **Still under capacity!** (2560 < 3072)
- Consumer processes: extracts 1024, advances 256
- **Buffer now has: 1792 samples**

**Submit 4 (if we tried):**
- Add 1024 samples → would need 1792 + 1024 = 2816
- Still okay! But getting close...

**Submit 5 (if we tried):**
- Add 1024 samples → would need 2560 + 1024 = 3584
- **Overflow!** (3584 > 3072)
- `push()` throws exception

**Why only 3 submits in the test?**

**Engineer says:** **Conservative test design** + **Documentation of system limits**.

The comment explains:
```cpp
// Submit 3 frames consecutively (limited to avoid ring buffer overflow with overlap)
```

This teaches users:
- "Ah, I can't submit unlimited frames rapidly"
- "The ring buffer has finite capacity"
- "Overlap affects how many frames I can queue"

**The 10ms sleep:**

```cpp
std::this_thread::sleep_for(std::chrono::milliseconds(10));
```

**Why?**

Give the consumer thread time to **drain the buffer**. Without this:
- Submits happen at CPU speed (~microseconds apart)
- Consumer can't keep up
- Buffer fills faster than it drains
- Overflow!

With the sleep:
- ~10ms between submits
- Consumer has time to process and free space
- Test passes reliably

**In production code:**

You'd handle this with **backpressure**:

```cpp
while (!executor.has_space_for_frame()) {
  std::this_thread::yield();  // Wait for consumer to drain
}
executor.submit(data);
```

Or use a **blocking submit**:

```cpp
executor.submit_blocking(data);  // Waits internally if buffer full
```

(These are future enhancements - see the plan's "Future Work" section!)

---

## 🔗 Part 5: Connecting the Dots (System View)

Let me show you how this fits into the **bigger picture** of the file.

### The Three-Thread Architecture

Looking at the broader file structure:

**Thread 1: User Thread (Producer)**

```cpp
// File: streaming_executor.cpp, lines 280-415
void submit(input, output, num_samples) {
  // (lines 290-309) Add samples to ring buffer

  if (enable_background_thread_) {
    // (line 319) Notify consumer: "Data ready!"
    cv_data_ready_.notify_one();

    // (lines 334-362) [OUR FIX] Wait for result from consumer
    cv_data_ready_.wait_until(lock, deadline, predicate);

    // (lines 365-382) Copy result to output
  } else {
    // (lines 384-414) Synchronous mode: process inline
  }
}
```

**Thread 2: Consumer Thread (Background Processor)**

```cpp
// File: streaming_executor.cpp, lines 716-793
void consumer_loop() {
  while (!stop_flag_) {
    // (lines 728-746) Wait for input data
    cv_data_ready_.wait(lock, [this] {
      return have_enough_samples() || stop_flag_;
    });

    // (lines 748-775) Process all available frames
    while (have_enough_samples()) {
      process_one_batch(result);

      // (lines 785-790) [OUR FIX] Enqueue result and notify
      {
        lock result_queue_;
        result_queue_.push(result);
      }
      cv_data_ready_.notify_one();  // Wake producer!
    }
  }
}
```

**Thread 3: OS Scheduler**
- Manages which thread runs when
- Puts threads to sleep when they wait on CV
- Wakes threads up when CV is notified

### The Synchronization Flow

**Full cycle:**

```
User Thread                    Consumer Thread                  OS Scheduler
===========                    ===============                  ============
submit()                       [sleeping in wait()]
  |
  ├─ Add samples to buffer
  |
  ├─ cv.notify_one() ────────────> [OS wakeup signal] ──────────> Wake consumer
  |                                      │
  ├─ cv.wait_until() ─────────> [OS sleep signal] ──────────> Sleep producer
  |  [Producer sleeps]                   │
  |                              <wait returns, has lock>
  |                                      │
  |                              Process frame (FFT, etc)
  |                                      │
  |                              Lock result_mutex
  |                              Push result to queue
  |                              Unlock result_mutex
  |                                      │
  |                              cv.notify_one() ──────────────> Wake producer
  |                                      │
  <─ [OS wakeup signal] <────────────────┘
  |  <wait returns>
  |
  ├─ Check predicate:
  │  !result_queue_.empty() ✓
  |
  ├─ result = result_queue_.front()
  |
  └─ Return to user
```

### The Member Variables (State)

Looking at lines 800-812:

```cpp
// State tracking
bool initialized_ = false;
uint64_t frame_counter_ = 0;
ProcessingStats stats_{};

// Async producer-consumer infrastructure (v0.9.5+)
std::thread consumer_thread_;            // Background processing thread
std::atomic<bool> stop_flag_{false};     // Signal to stop consumer thread
std::condition_variable cv_data_ready_;  // Notify consumer of new data [USED IN FIX]
std::mutex cv_mutex_;                    // Mutex for condition variable only
std::queue<std::vector<float>>
    result_queue_;         // Completed results from consumer [USED IN FIX]
std::mutex result_mutex_;  // Protects result_queue_ [USED IN FIX]
```

**The synchronization primitives:**

| Variable | Type | Purpose | Used By |
|----------|------|---------|---------|
| `cv_data_ready_` | `condition_variable` | **Bidirectional signaling**: Producer→Consumer (data ready), Consumer→Producer (result ready) | Both threads |
| `cv_mutex_` | `mutex` | Protects CV wait in consumer (for input data availability check) | Consumer only |
| `result_mutex_` | `mutex` | Protects result queue access | Both threads |
| `result_queue_` | `queue<vector<float>>` | Transfer processed results Consumer→Producer | Both threads |
| `stop_flag_` | `atomic<bool>` | Graceful shutdown signal | Both threads |

### Design Note: One CV vs Two CVs

**Professor asks:** "Why use ONE CV for bidirectional signaling instead of TWO CVs?"

**Answer:**

**Option A (Two CVs):**

```cpp
std::condition_variable cv_data_ready_;    // Producer → Consumer
std::condition_variable cv_result_ready_;  // Consumer → Producer
```

**Option B (One CV, current design):**

```cpp
std::condition_variable cv_data_ready_;  // Bidirectional
```

**Tradeoffs:**

**Option A Pros:**
- Clearer semantics ("this CV is ONLY for results")
- Easier to reason about

**Option A Cons:**
- More member variables
- More complexity

**Option B Pros:**
- Simpler (fewer variables)
- Works because predicates distinguish the conditions

**Option B Cons:**
- Less obvious semantically
- Both threads wake on EVERY notification (but predicate filters)

**For this codebase:**

Option B is fine because:
- There's only ONE producer and ONE consumer (simple topology)
- The predicates are different enough that there's no confusion
- Performance is fine (only 2 threads, minimal contention)

In a **complex system** (multiple producers, multiple consumers), you'd use separate CVs per queue/condition.

---

## 🎯 Part 6: Key Takeaways (What You Should Remember)

### Synchronization Primitives 101

**Mutex (Mutual Exclusion):**
- **Purpose:** Protect shared data from concurrent access
- **Cost:** ~25ns (uncontended), ~200ns (contended, context switch)
- **When:** Modifying shared state (`result_queue_.push()`)

**Condition Variable:**
- **Purpose:** Wait for a condition to become true
- **Cost:** ~1μs (wake-up latency)
- **When:** Waiting for data/events (`!result_queue_.empty()`)

**Atomic:**
- **Purpose:** Thread-safe primitive operations
- **Cost:** ~5ns (much faster than mutex!)
- **When:** Simple flags/counters (`stop_flag_`)

### Predicate-Based Wait Pattern

**Always use a predicate with CV wait:**

✅ **Correct:**

```cpp
cv.wait(lock, [&]{ return condition_is_true; });
```

❌ **Wrong:**

```cpp
cv.wait(lock);
if (condition_is_true) { ... }  // Vulnerable to spurious wakeups!
```

**Why?** The library handles spurious wakeups for you.

### Memory Model Basics

For atomics, remember:

| Order | When | What it means |
|-------|------|---------------|
| `memory_order_relaxed` | Counters that don't synchronize | "Just make it atomic, no ordering guarantees" |
| `memory_order_acquire` | **Reading** shared state | "See all writes from the release store" |
| `memory_order_release` | **Writing** shared state | "Make all my writes visible to acquire loads" |
| `memory_order_seq_cst` | Default (safest) | "Total order visible to all threads" |

**In this code:**

```cpp
// Consumer:
stop_flag_.store(true, memory_order_release);  // Publish changes

// Producer:
if (stop_flag_.load(memory_order_acquire)) {   // See published changes
```

This creates a **synchronizes-with** relationship without a mutex!

### Test Design Principles

1. **Test the happy path** (AsyncProcessingSuccess)
2. **Test edge cases** (Timeout, Stop, Multiple)
3. **Make tests deterministic** (or accept rare flakes)
4. **Document timing assumptions** (sleep durations, timeouts)
5. **Test invariants** (queue not empty after wait)

---

## 🚀 Part 7: Beyond This Fix (Your Roadmap)

Now that you understand this deeply, here's where this fits in the **bigger picture** of SigTekX:

### Current State (After This Fix):

- ✅ Async mode **works** (was completely broken)
- ✅ Proper CV-based synchronization (was busy-spinning)
- ✅ Graceful shutdown (wasn't possible before)

### Phase 1 (Next): Memory Optimization

- Remove `h_batch_staging_` buffer (zero-copy from ring buffer)
- **Why this fix matters:** Phase 1 will stress async mode more (higher throughput)
- **What you'll learn:** DMA, pinned memory, CUDA memory model

### Phase 2: Custom Stages

- Add Numba/PyTorch integration
- **Why this fix matters:** Custom stages run in consumer thread (needs stable async)
- **What you'll learn:** JIT compilation, FFI, device function pointers

### Phase 3: Dual-Plane Architecture

- Snapshot buffers, event queues
- **Why this fix matters:** This IS dual-plane (data=consumer, control=producer)
- **What you'll learn:** Lock-free queues, SPSC/MPSC patterns

---

## ❓ Questions to Test Your Understanding

### Easy:

1. Why can't we use a local `condition_variable` instead of a member variable?
2. What's the difference between `notify_one()` and `notify_all()`?

### Medium:

3. What would happen if we removed the predicate and just used `cv.wait_until(lock, deadline)`?
4. Why do we check `stop_flag_` twice (in predicate AND after wait)?

### Hard:

5. Could we deadlock if we called `notify_one()` INSIDE the mutex lock? Why or why not?
6. What happens if the consumer crashes while holding `result_mutex_`?

### Expert:

7. Design a triple-buffer system where producer never blocks (sketch the synchronization).
8. How would you change this code to support multiple consumer threads?

---

## Answers to Questions

<details>
<summary>Click to reveal answers (try solving first!)</summary>

### Easy Answers:

**1. Why can't we use a local condition_variable?**

Because the consumer thread notifies a specific CV object. If the producer creates a new local CV each time, it's waiting on a different object than the one being notified. The CV must be shared between threads, hence a member variable.

**2. What's the difference between `notify_one()` and `notify_all()`?**

- `notify_one()`: Wakes up **one** waiting thread (arbitrary which one)
- `notify_all()`: Wakes up **all** waiting threads

Use `notify_one()` when only one thread needs to handle the event (like our case - one producer waiting). Use `notify_all()` when multiple threads might need to respond (e.g., broadcast shutdown signal to worker pool).

### Medium Answers:

**3. What happens without predicate?**

```cpp
cv.wait_until(lock, deadline);  // No predicate
```

**Spurious wakeups** would break the logic. The CV could wake up even though:
- No result is ready
- No timeout occurred
- Just random OS behavior

You'd proceed thinking result is ready, but `result_queue_.empty()` is still true → crash or wrong behavior.

**4. Why check `stop_flag_` twice?**

**First check (in predicate):** Main purpose - wake up when stopping, don't wait forever.

**Second check (after wait):** Distinguish WHY we woke up:
- Woke due to timeout but flag set during that instant → throw "stopped" not "timeout"
- Woke due to stop flag → throw "stopped"
- Woke due to result → proceed normally

Gives more accurate error messages to user.

### Hard Answers:

**5. Deadlock with notify inside lock?**

**No deadlock**, but performance hit:

```cpp
{
  lock(mutex);
  notify_one();  // Inside lock
}
```

**Why no deadlock:**
- The waiting thread doesn't hold the mutex when sleeping (CV releases it)
- When notified, waiting thread tries to re-acquire the mutex
- Eventually the notifying thread releases mutex, waiting thread gets it

**Why slower:**
- Waiting thread wakes up, immediately blocks on mutex
- Extra context switch (sleep → wake → block → wake)

**6. Consumer crashes while holding `result_mutex_`?**

**Deadlock forever!**

- Producer will call `wait_until(lock, deadline, ...)`
- Tries to acquire `result_mutex_`
- Blocks forever (consumer is dead, will never release)
- Eventually timeout fires (if using `wait_until` not `wait`)
- Producer throws timeout exception

**Mitigation strategies:**
- Always use timeouts (we do!)
- Implement watchdog thread that detects stuck state
- Use RAII so crash triggers cleanup (but doesn't help if thread truly dies)
- Process isolation (separate processes can't deadlock each other)

### Expert Answers:

**7. Triple-buffer design (producer never blocks):**

**Concept:** Three buffers rotating between states:

```
Buffer A: Producer writing
Buffer B: Consumer processing
Buffer C: Ready for display
```

**Synchronization (lock-free):**

```cpp
struct TripleBuffer {
  std::array<Buffer, 3> buffers;
  std::atomic<int> producer_idx{0};  // Which buffer producer writes to
  std::atomic<int> consumer_idx{1};  // Which buffer consumer processes
  std::atomic<int> ready_idx{2};     // Which buffer is ready

  Buffer* get_write_buffer() {
    return &buffers[producer_idx.load(memory_order_acquire)];
  }

  void flip_producer() {
    int ready = ready_idx.exchange(producer_idx.load(), memory_order_acq_rel);
    producer_idx.store(ready, memory_order_release);
  }
};
```

**Producer never waits** - always has a buffer to write to. Consumer processes at its own pace.

**8. Multiple consumer threads:**

**Changes needed:**

```cpp
// Instead of single result queue:
std::queue<WorkItem> work_queue_;     // Input work
std::mutex work_mutex_;
std::condition_variable work_cv_;

std::queue<Result> result_queue_;     // Output results
std::mutex result_mutex_;
std::condition_variable result_cv_;

// Consumer thread pool:
std::vector<std::thread> consumer_threads_;

void consumer_loop() {
  while (!stop_flag_) {
    WorkItem work;
    {
      std::unique_lock lock(work_mutex_);
      work_cv_.wait(lock, [this] {
        return !work_queue_.empty() || stop_flag_;
      });
      if (stop_flag_) return;
      work = work_queue_.front();
      work_queue_.pop();
    }

    Result result = process(work);

    {
      std::lock_guard lock(result_mutex_);
      result_queue_.push(result);
    }
    result_cv_.notify_one();
  }
}
```

**Key changes:**
- Separate work queue and result queue
- Each consumer waits on `work_cv_`
- Producer waits on `result_cv_`
- All queue access protected by appropriate mutex

</details>

---

## Summary

This fix transformed async mode from **completely broken** to **production-ready**:

- ❌ **Before**: Temporary CV, busy-spinning, no shutdown
- ✅ **After**: Member CV, predicate-based wait, graceful shutdown

**Core lesson:** Synchronization is hard. Use the standard patterns (predicate-based wait), understand the theory (producer-consumer, memory model), and test thoroughly (happy path + edge cases).

Now you're ready for Phase 1! 🚀
