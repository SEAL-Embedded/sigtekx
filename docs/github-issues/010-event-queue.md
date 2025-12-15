# Add MPSC Event Queue for Asynchronous Pipeline Events (Phase 3 Task 3.2)

## Problem

There is **no mechanism for stages to emit events** (threshold triggers, anomalies) without blocking the pipeline. I/O callbacks (database writes, Slack alerts) would stall the entire data plane if executed inline.

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 3 Task 3.2):
- Event queue: lock-free MPSC (multi-producer, single-consumer)
- Stages call `emit_event(type, data)` without blocking
- Python polls `engine.get_events()` from control plane
- Target overhead: <2µs for event emission

**Impact:**
- Cannot trigger alerts on anomalies without blocking pipeline
- No way to log events to database in real-time
- Cannot send notifications (Slack, email) during continuous processing
- Tight coupling between detection and action (anti-pattern)

## Current Implementation

**No event mechanism exists.** User would need to:
1. Poll output buffer manually
2. Check for thresholds in Python (blocks pipeline)
3. Miss events during non-polling periods

This breaks real-time guarantees and misses transient events.

## Proposed Solution

**Create lock-free MPSC event queue with non-blocking emission:**

```cpp
// cpp/include/sigtekx/core/event_queue.hpp (NEW FILE)
#ifndef SIGTEKX_CORE_EVENT_QUEUE_HPP
#define SIGTEKX_CORE_EVENT_QUEUE_HPP

#include <string>
#include <queue>
#include <mutex>
#include <chrono>

namespace sigtekx {

struct Event {
    std::string type;           // Event type: "anomaly", "threshold", etc.
    std::string data;           // JSON payload or serialized data
    uint64_t timestamp_us;      // Microseconds since epoch
    size_t frame_id;            // Frame number when event occurred
};

// Lock-free MPSC event queue
// Multiple producer threads (stages) can emit, single consumer (Python)
class EventQueue {
public:
    EventQueue(size_t max_events = 10000);
    ~EventQueue();

    // Emit event from data plane (non-blocking)
    // Returns false if queue full
    bool emit(const std::string& type, const std::string& data, size_t frame_id);

    // Poll events from control plane (non-blocking)
    // Returns up to max_events, empty if none available
    std::vector<Event> poll(size_t max_events = 100);

    // Get queue size (approximate, for monitoring)
    size_t size() const;

private:
    std::queue<Event> queue_;    // FIFO event queue
    mutable std::mutex mutex_;   // Protects queue access
    size_t max_events_;          // Max queue size (prevent unbounded growth)
};

} // namespace sigtekx

#endif
```

```cpp
// cpp/src/core/event_queue.cpp (NEW FILE)
#include "sigtekx/core/event_queue.hpp"

namespace sigtekx {

EventQueue::EventQueue(size_t max_events) : max_events_(max_events) {}

EventQueue::~EventQueue() = default;

bool EventQueue::emit(const std::string& type, const std::string& data, size_t frame_id) {
    std::lock_guard<std::mutex> lock(mutex_);

    // Drop if queue full (prevent unbounded memory growth)
    if (queue_.size() >= max_events_) {
        return false;  // Event dropped
    }

    // Create event with timestamp
    Event event;
    event.type = type;
    event.data = data;
    event.frame_id = frame_id;
    event.timestamp_us = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::system_clock::now().time_since_epoch()
    ).count();

    queue_.push(event);
    return true;
}

std::vector<Event> EventQueue::poll(size_t max_events) {
    std::lock_guard<std::mutex> lock(mutex_);

    std::vector<Event> events;
    events.reserve(std::min(max_events, queue_.size()));

    size_t count = 0;
    while (!queue_.empty() && count < max_events) {
        events.push_back(queue_.front());
        queue_.pop();
        count++;
    }

    return events;
}

size_t EventQueue::size() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return queue_.size();
}

} // namespace sigtekx
```

```python
# src/sigtekx/core/engine.py (ENHANCED)
class Engine:
    # ... existing methods ...

    def get_events(self, max_events: int = 100, timeout: float = 0.1) -> list[dict]:
        """
        Poll events from pipeline (non-blocking).

        Args:
            max_events: Maximum events to retrieve
            timeout: Timeout in seconds (not implemented, for future async)

        Returns:
            List of events: [{"type": "anomaly", "data": {...}, "timestamp_us": ..., "frame_id": ...}, ...]

        Example:
            >>> engine = Engine(config)
            >>> engine.start()
            >>>
            >>> while True:
            >>>     for event in engine.get_events():
            >>>         if event['type'] == 'anomaly':
            >>>             send_slack_alert(event['data'])
            >>>     time.sleep(0.1)  # Poll every 100ms
        """
        return self._executor.poll_events(max_events)
```

## Additional Technical Insights

- **MPSC Pattern**: Multiple stages can emit (producers), single Python thread polls (consumer). Mutex protects shared queue.

- **Lock-Free Alternative**: Could use `boost::lockfree::queue` or `folly::MPMCQueue` for true lock-free (more complex). Mutex is sufficient for v1.0 (<2µs overhead).

- **Queue Capacity**: Default 10,000 events prevents unbounded growth. Drops old events if full (user must poll faster or increase capacity).

- **Event Serialization**: Events stored as JSON strings for flexibility. User can serialize custom structs.

- **Timestamp**: Microsecond precision for event correlation and latency analysis.

- **Frame ID**: Links event to specific frame for debugging and analysis.

## Implementation Tasks

- [ ] Create `cpp/include/sigtekx/core/event_queue.hpp` header
- [ ] Define `Event` struct (type, data, timestamp, frame_id)
- [ ] Define `EventQueue` class (MPSC queue)
- [ ] Create `cpp/src/core/event_queue.cpp` implementation
- [ ] Implement `emit()` method (push to queue with timestamp)
- [ ] Implement `poll()` method (pop up to max_events)
- [ ] Implement `size()` method (queue size)
- [ ] Add `EventQueue` member to `StreamingExecutor`
- [ ] Expose `emit_event()` to stages (via executor context)
- [ ] Open `cpp/bindings/bindings.cpp`
- [ ] Expose `poll_events()` to Python (returns list of dicts)
- [ ] Open `src/sigtekx/core/engine.py`
- [ ] Add `get_events()` method
- [ ] Create test: `tests/test_event_queue.py`
  - Test: Emit 1000 events, verify no blocking
  - Test: Poll events, verify FIFO order
  - Test: Queue full drops events (returns false)
- [ ] Measure overhead: <2µs for emit
- [ ] Update documentation: `docs/api/event-system.md`
- [ ] Build: `./scripts/cli.ps1 build`
- [ ] Test: `./scripts/cli.ps1 test cpp && ./scripts/cli.ps1 test python`
- [ ] Commit: `feat(core): add lock-free event queue for async callbacks`

## Edge Cases to Handle

- **Queue Overflow**: More events emitted than consumed
  - Mitigation: Drop oldest events, return false from `emit()`, log warning

- **High-Frequency Emission**: 1000+ events/sec
  - Mitigation: Mutex overhead acceptable (<2µs). If becomes bottleneck, upgrade to lock-free.

- **Event Size**: Large JSON payloads (>1KB)
  - Mitigation: User responsibility to keep payloads small. Document max recommended size.

- **Thread Safety**: Multiple threads polling (not recommended)
  - Mitigation: Document single-consumer pattern. Mutex makes it safe but inefficient.

## Testing Strategy

**Integration Test (Python):**

```python
# tests/test_event_queue.py
import time
from sigtekx import Engine, EngineConfig

def test_event_emission_non_blocking():
    """Test that event emission doesn't block pipeline."""
    # Custom stage emits event on threshold
    @cuda.jit
    def threshold_detector(input, output, n, state):
        i = cuda.grid(1)
        if i < n:
            output[i] = input[i]
            if input[i] > 10.0:
                # Emit event (TODO: expose emit API to Numba)
                pass  # Would call emit_event("threshold", f"value={input[i]}")

    config = EngineConfig(nfft=4096)
    engine = Engine(config)
    engine.start()

    # Generate events
    time.sleep(0.5)

    # Poll events
    events = engine.get_events()
    assert len(events) > 0

    # Verify event structure
    event = events[0]
    assert 'type' in event
    assert 'data' in event
    assert 'timestamp_us' in event
    assert 'frame_id' in event

    engine.stop()

def test_event_fifo_order():
    """Test events maintain FIFO order."""
    # Emit events with sequential IDs
    # Poll and verify order preserved
    pass

def test_queue_overflow_drops_events():
    """Test queue drops events when full."""
    # Set small queue capacity
    # Emit more events than capacity
    # Verify emit returns false when full
    pass
```

## Acceptance Criteria

- [ ] `EventQueue` class implemented
- [ ] `emit()` method non-blocking (<2µs)
- [ ] `poll()` method returns events in FIFO order
- [ ] Queue capacity limit enforced (drops when full)
- [ ] Exposed to Python via `engine.get_events()`
- [ ] Test: 1000 events/sec doesn't block pipeline
- [ ] Test: Events maintain order
- [ ] Test: Overflow drops events correctly
- [ ] Documentation includes Slack alert example
- [ ] All tests pass

## Benefits

- **Async Event Handling**: Detect anomalies without blocking DSP
- **Real-Time Alerts**: Send Slack/email notifications during processing
- **Decoupled Architecture**: Separation of detection and action
- **Minimal Overhead**: <2µs emission (maintains RTF <0.3)
- **Foundation for Callbacks**: Enables Issue #011 (callback stages)
- **Production Pattern**: Standard observer pattern for real-time systems

---

**Labels:** `feature`, `team-1-cpp`, `team-3-python`, `c++`, `python`, `architecture`, `performance`

**Estimated Effort:** 8-10 hours (lock-free queue, Python binding, testing)

**Priority:** High (Control Plane - Phase 3 Task 3.2)

**Roadmap Phase:** Phase 3 (v0.9.8)

**Dependencies:** Issue #009 (snapshot buffer - same architectural pattern)

**Blocks:** Issue #011 (callback stage uses event queue)
