# Fix CSV Append Race Condition in Latency Benchmark

## Problem

The `run_latency.py` benchmark script has a **Time-of-Check-Time-of-Use (TOCTOU)** race condition when appending results to the summary CSV file. The script checks if the file exists, then appends with a header flag based on that check. If multiple benchmark processes run concurrently (e.g., in a Hydra multirun sweep), they can both check the file doesn't exist, then both write headers, resulting in CSV corruption.

**Impact:**
- CSV file corruption during parallel multirun sweeps
- Duplicate headers in middle of data
- Pandas fails to parse corrupted CSV
- Data loss requiring manual cleanup or re-run

**Affected Configuration:**
- Hydra multirun mode: `--multirun engine.nfft=1024,2048,4096`
- Parallel sweep execution
- Any scenario with concurrent latency benchmarks

**Failure Scenario:**
```bash
# Terminal 1: Hydra multirun launches 3 jobs in parallel
python benchmarks/run_latency.py --multirun engine.nfft=1024,2048,4096 +benchmark=latency

# Race condition timeline:
# T0: Job 1 checks summary.csv → doesn't exist
# T1: Job 2 checks summary.csv → doesn't exist
# T2: Job 1 writes header + data
# T3: Job 2 writes header + data  ← DUPLICATE HEADER!

# Corrupted CSV result:
# nfft,overlap,latency_us,...
# 1024,0.5,42.3,...
# nfft,overlap,latency_us,...  ← Second header in data!
# 2048,0.5,65.1,...
```

## Current Implementation

**File:** `benchmarks/run_latency.py` (lines 130-136)

```python
# Save summary CSV (append mode for multirun)
summary_path = output_dir / "summary.csv"
summary_df.to_csv(
    summary_path,
    mode='a',                          # Append mode
    header=not summary_path.exists(),  # ❌ RACE: Check-then-use
    index=False
)
```

**The Race Window:**

```
Time    Process 1                     Process 2
────────────────────────────────────────────────────────────
T0      summary_path.exists()         (not started)
        → False
T1      (preparing to write)          summary_path.exists()
                                      → False (file not created yet!)
T2      Write header + data row       (preparing to write)
        File now exists
T3      (done)                        Write header + data row
                                      ← DUPLICATE HEADER!
```

**Race window duration:** ~1-10ms (file creation to next process check)

**Why mode='a' doesn't help:**
- `mode='a'` opens file in append mode
- But `header=not summary_path.exists()` check happens **before** opening
- Between check and open, another process can create file

## Proposed Solution

Use **file locking** to ensure atomic check-and-write operation.

### Option 1: File Locking (Recommended)

Use `filelock` library for cross-process file locking:

```python
from filelock import FileLock

# Save summary CSV with file locking
summary_path = output_dir / "summary.csv"
lock_path = output_dir / "summary.csv.lock"

with FileLock(str(lock_path), timeout=30):
    # ✅ ATOMIC: Check and write inside lock
    file_exists = summary_path.exists()

    summary_df.to_csv(
        summary_path,
        mode='a',
        header=not file_exists,
        index=False
    )

# Lock released here, other processes can proceed
```

**How it works:**
1. Process acquires exclusive lock on `.lock` file
2. Check if CSV exists (inside lock)
3. Write with appropriate header flag
4. Release lock
5. Next process acquires lock and repeats

**Benefits:**
- Cross-process safe (works across Python interpreters)
- Cross-platform (Windows, Linux, macOS)
- Timeout prevents deadlock if process crashes
- `filelock` is pure Python, no C extensions

### Option 2: Pandas Locking (Alternative)

Use Pandas built-in append with lock (if available):

```python
import fcntl  # Unix only!

summary_path = output_dir / "summary.csv"

# Open file with exclusive lock
with open(summary_path, 'a') as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Acquire lock

    # Check if file was empty when opened
    file_empty = f.tell() == 0

    # Write with header if file was empty
    summary_df.to_csv(f, mode='a', header=file_empty, index=False)

    # Lock released on context exit
```

**Drawbacks:**
- `fcntl` not available on Windows
- Need `portalocker` library for cross-platform

**Recommendation:** Use Option 1 (`filelock`) for simplicity and cross-platform support.

### Option 3: Unique Filenames (Fallback)

Avoid append entirely - write to unique files and merge later:

```python
# Each process writes to its own file
run_id = str(uuid.uuid4())[:8]
summary_path = output_dir / f"summary_{run_id}.csv"

summary_df.to_csv(summary_path, index=False)  # Always write header

# Separate merge step (in analysis script):
# all_files = glob.glob("artifacts/data/summary_*.csv")
# combined = pd.concat([pd.read_csv(f) for f in all_files])
# combined.to_csv("artifacts/data/summary.csv", index=False)
```

**Drawbacks:**
- Requires post-processing step
- More complex workflow

**Use case:** If file locking is problematic (e.g., network filesystems)

## Additional Technical Insights

### TOCTOU Vulnerability Class

**TOCTOU (Time-of-Check-Time-of-Use)** is a classic race condition:
```python
# ❌ TOCTOU example:
if os.path.exists(path):  # Check
    with open(path, 'r') as f:  # Use
        data = f.read()
```

**Fix pattern:**
```python
# ✅ Atomic operation:
try:
    with open(path, 'r') as f:
        data = f.read()
except FileNotFoundError:
    data = None
```

### File Locking Implementation Details

**FileLock behavior:**
- Creates `.lock` file alongside target file
- Multiple processes block on `__enter__` until lock available
- Timeout raises `Timeout` exception if lock held too long
- Lock automatically released on `__exit__` (even on exception)

**Lock file cleanup:**
- `.lock` files persist after process exit (by design)
- Can be safely deleted manually if stale
- Don't block other operations (only lock acquisition)

### Performance Impact

**Locking overhead:**
- Lock acquire/release: ~100-500µs
- Negligible compared to benchmark duration (seconds to minutes)
- Only affects summary write (once per benchmark run)

**Concurrent execution:**
- Processes execute benchmarks in parallel ✓
- Only serialize during 1-2ms summary write
- No impact on measurement accuracy

## Implementation Tasks

- [ ] Open `benchmarks/run_latency.py`
- [ ] Add `filelock` import at top: `from filelock import FileLock`
- [ ] Locate summary CSV write (line 130-136)
- [ ] Define lock file path: `lock_path = output_dir / "summary.csv.lock"`
- [ ] Wrap CSV write in `with FileLock(str(lock_path), timeout=30):`
- [ ] Move `summary_path.exists()` check inside lock context
- [ ] Keep existing `mode='a'` and `header=not file_exists`
- [ ] Add comment explaining TOCTOU fix
- [ ] Add `filelock` to project dependencies (requirements.txt or pyproject.toml)
- [ ] Test multirun scenario: `--multirun engine.nfft=1024,2048,4096`
- [ ] Verify no duplicate headers in summary.csv
- [ ] Add unit test: `test_latency_csv_multiprocess_safe()`
- [ ] Commit: `fix(benchmarks): use file locking to prevent CSV append race condition`

## Edge Cases to Handle

- **Lock timeout:**
  - If process holds lock for >30s, other processes raise `Timeout`
  - Should be rare (CSV write is <1ms)
  - Can increase timeout if needed

- **Stale lock files:**
  - If process crashes, `.lock` file persists
  - FileLock handles this (lock file only matters during acquisition)
  - Can manually delete `.lock` files if suspicious

- **Network filesystems:**
  - NFS may not support reliable file locking
  - Use Option 3 (unique filenames) for network storage

- **Disk full:**
  - CSV write may fail inside lock
  - Lock is released on exception ✓
  - Other processes can proceed

- **First run (directory doesn't exist):**
  - `output_dir` created earlier in script (line ~85)
  - No issue ✓

## Testing Strategy

### Unit Test (Add to `tests/test_benchmarks.py`)

```python
import pytest
import pandas as pd
import multiprocessing as mp
from pathlib import Path
from benchmarks.run_latency import save_summary_csv  # Extract function

def worker_write_csv(output_dir, nfft_value, worker_id):
    """Worker function that writes to shared CSV."""
    df = pd.DataFrame({
        'nfft': [nfft_value],
        'worker_id': [worker_id],
        'latency_us': [100.0 * worker_id]
    })

    # Use same locking logic as run_latency.py
    from filelock import FileLock

    summary_path = output_dir / "summary.csv"
    lock_path = output_dir / "summary.csv.lock"

    with FileLock(str(lock_path), timeout=30):
        file_exists = summary_path.exists()
        df.to_csv(summary_path, mode='a', header=not file_exists, index=False)

def test_latency_csv_multiprocess_safe(tmp_path):
    """Test that concurrent CSV writes don't corrupt file."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Spawn 10 workers writing concurrently
    nfft_values = [1024, 2048, 4096, 8192]
    workers = []

    for i, nfft in enumerate(nfft_values):
        p = mp.Process(target=worker_write_csv, args=(output_dir, nfft, i))
        p.start()
        workers.append(p)

    # Wait for all workers
    for p in workers:
        p.join()

    # Verify CSV is valid
    summary_path = output_dir / "summary.csv"
    assert summary_path.exists()

    df = pd.read_csv(summary_path)

    # Should have exactly 4 rows (one per worker)
    assert len(df) == 4

    # Should have exactly 1 header (column names)
    assert list(df.columns) == ['nfft', 'worker_id', 'latency_us']

    # All rows should have valid data
    assert df['nfft'].tolist() == [1024, 2048, 4096, 8192]
    assert df['worker_id'].tolist() == [0, 1, 2, 3]

    # No NaN values (would indicate malformed CSV)
    assert not df.isnull().any().any()
```

### Integration Test (Manual Hydra Multirun)

```bash
# Clean previous results
rm -rf artifacts/data/latency_summary.csv*

# Run multirun with 4 parallel jobs
python benchmarks/run_latency.py --multirun \
  engine.nfft=1024,2048,4096,8192 \
  +benchmark=latency \
  hydra.launcher.n_jobs=4

# Check CSV file
cat artifacts/data/latency_summary.csv

# Expected: Exactly ONE header line, then 4 data rows
# nfft,overlap,channels,mode,mean_us,std_us,...
# 1024,0.5,2,batch,42.3,5.1,...
# 2048,0.5,2,batch,65.8,7.2,...
# 4096,0.5,2,batch,120.4,12.3,...
# 8192,0.5,2,batch,230.1,18.5,...

# Verify with Pandas
python -c "import pandas as pd; df = pd.read_csv('artifacts/data/latency_summary.csv'); print(df); assert len(df) == 4"
```

### Stress Test (Many Concurrent Runs)

```bash
# Spawn 20 concurrent benchmark processes
for i in {1..20}; do
  python benchmarks/run_latency.py \
    experiment=profiling_latency \
    +benchmark=latency &
done

# Wait for all to complete
wait

# Check CSV integrity
python -c "
import pandas as pd
df = pd.read_csv('artifacts/data/latency_summary.csv')
print(f'Rows: {len(df)}')
print(f'Columns: {list(df.columns)}')
assert len(df) == 20, 'Should have 20 rows'
assert not df.isnull().any().any(), 'No NaN values'
print('✅ CSV integrity verified')
"
```

## Acceptance Criteria

- [ ] `filelock` added to project dependencies
- [ ] Import `FileLock` at top of `run_latency.py`
- [ ] Lock file path defined: `summary.csv.lock`
- [ ] CSV write wrapped in `with FileLock(str(lock_path), timeout=30):`
- [ ] `summary_path.exists()` check moved inside lock
- [ ] Comment added explaining TOCTOU prevention
- [ ] Unit test `test_latency_csv_multiprocess_safe` passes
- [ ] Manual multirun test shows single header in CSV
- [ ] Stress test with 20 concurrent runs produces valid CSV
- [ ] All existing latency benchmark tests pass (no regressions)
- [ ] CSV can be read by Pandas without errors
- [ ] No duplicate headers observed in any test scenario

## Benefits

- **Data Integrity:** Eliminates CSV corruption in parallel runs
- **Multirun Safety:** Hydra multirun sweeps now reliable
- **Production Readiness:** Safe for high-throughput experiment workflows
- **Cross-Platform:** Works on Windows, Linux, macOS
- **Minimal Overhead:** <1ms locking time per benchmark run
- **Automatic Cleanup:** Lock released even on exception
- **Phase 1 Readiness:** Enables safe parallel experiment sweeps

---

**Labels:** `bug`, `team-4-research`, `python`, `benchmarks`, `data-integrity`

**Estimated Effort:** 1-2 hours (dependency + fix + multiprocess test)

**Priority:** HIGH (data corruption issue affecting multirun)

**Roadmap Phase:** Phase 0 (critical for Phase 1 experiment sweeps)

**Dependencies:** `filelock` library (add to requirements)

**Blocks:** None, but improves reliability of all multirun benchmarks

**Related:** Hydra multirun documentation, parallel experiment workflows
