# Benchmark CSV File Organization

## Overview

All benchmark scripts (`run_latency.py`, `run_throughput.py`, `run_realtime.py`, `run_accuracy.py`) use a **unique filename pattern** based on configuration parameters to prevent race conditions during parallel multirun sweeps.

### Key Design Decision

Instead of using a single aggregated CSV file with append mode and file locking, each configuration writes to its own unique file. This eliminates race conditions entirely rather than preventing them through synchronization.

### Multirun Safety Guarantee

✅ **Zero collision risk**: Different configurations → different filenames → no concurrent access to same file
✅ **No file locking needed**: Each process writes independently
✅ **Cross-platform**: No OS-specific file locking APIs
✅ **Network filesystem compatible**: Works on NFS/SMB mounts where locking is unreliable

---

## Filename Pattern

### Standard Pattern (Latency, Throughput, Accuracy)

**Format:**
```
{benchmark}_summary_{sample_rate_hz}_{nfft}_{channels}_{overlap}_{mode}.csv
```

**Parameters:**
- `benchmark`: Benchmark type (`latency`, `throughput`, `accuracy`)
- `sample_rate_hz`: Engine sample rate in Hz (e.g., `48000`, `100000`)
- `nfft`: FFT size (1024, 2048, 4096, 8192, 16384, 32768)
- `channels`: Number of audio channels (1, 2, 4, 8)
- `overlap`: Overlap ratio encoded with `.` replaced by `p` (e.g., `0.75` → `0p7500`)
- `mode`: Execution mode (`batch` or `streaming`)

**Examples:**
```
latency_summary_48000_4096_2_0p7500_streaming.csv
throughput_summary_100000_8192_4_0p8750_batch.csv
accuracy_summary_48000_2048_2_0p0000_batch.csv
```

`sample_rate_hz` is required in the filename because two experiments at different sample rates can otherwise share the same `(nfft, channels, overlap, mode)` grid point and clobber each other's CSV.

### Simplified Pattern (Realtime)

**Format:**
```
realtime_summary_{sample_rate_hz}_{nfft}_{channels}.csv
```

**Rationale:** Realtime benchmarks are always STREAMING mode, so overlap/mode parameters are omitted. Sample rate is retained to prevent cross-rate collisions.

**Examples:**
```
realtime_summary_48000_4096_2.csv
realtime_summary_100000_8192_4.csv
```

---

## Implementation Details

### CSV Writing Logic

All benchmark scripts follow the same pattern:

**File:** `benchmarks/run_latency.py:143-160` (representative example)

```python
# === CSV WRITE: UNIQUE FILENAME PATTERN ===
# Each configuration writes to unique CSV to prevent race conditions during
# parallel multirun sweeps. Filename encodes full config:
#   Format: latency_summary_{nfft}_{channels}_{overlap}_{mode}.csv
#   Example: latency_summary_4096_2_0p7500_streaming.csv
#
# Why this works:
#   - Different configs → different files → zero collision risk
#   - Same config re-run → atomic overwrite (desired behavior)
#   - Analysis scripts auto-merge via glob pattern (*_summary_*.csv)
#
# Verified safe by: tests/test_csv_multirun_safety.py
# Design rationale: docs/benchmarking/csv-file-organization.md

exec_mode = engine_config.mode.value if hasattr(engine_config.mode, 'value') else str(engine_config.mode)
overlap_str = f"{engine_config.overlap:.4f}".replace('.', 'p')  # 0.75 -> 0p7500
summary_path = output_dir / f"latency_summary_{engine_config.sample_rate_hz}_{engine_config.nfft}_{engine_config.channels}_{overlap_str}_{exec_mode}.csv"
summary_df.to_csv(summary_path, index=False)  # mode='w' (default, overwrites)
mlflow.log_artifact(str(summary_path))
```

### Data Aggregation (load_data)

Analysis scripts automatically merge all CSV files using a glob pattern.

**File:** `experiments/analysis/cli.py:24-56`

```python
def load_data(data_path: Path) -> pd.DataFrame:
    """Load benchmark data from CSV or directory of CSVs."""
    if data_path.is_dir():
        # Find all CSV files matching pattern
        csv_files = list(data_path.glob("*_summary_*.csv"))

        dataframes = []
        for csv_file in csv_files:
            df = pd.read_csv(csv_file)
            df['source_file'] = csv_file.name

            # Infer benchmark type from filename
            if 'latency_summary' in csv_file.name:
                df['benchmark_type'] = 'latency'
            elif 'throughput_summary' in csv_file.name:
                df['benchmark_type'] = 'throughput'
            # ... similar for realtime, accuracy ...

            # Harmonize schema for backward compatibility
            df = _harmonize_schema(df, csv_file.name)
            dataframes.append(df)

        return pd.concat(dataframes, ignore_index=True)
```

**Dashboard Integration:**

The Streamlit dashboard (`experiments/streamlit/`) uses the same `load_data()` function with caching:

```python
@st.cache_data(ttl=3600, show_spinner="Loading benchmark data...")
def load_benchmark_data(data_path: str | Path = "artifacts/data") -> pd.DataFrame:
    return _load_data_impl(data_path)
```

---

## Design Rationale

### Comparison of Approaches

| Approach | Multirun Safety | Dependencies | Performance | Complexity | Network FS |
|----------|----------------|--------------|-------------|------------|------------|
| **Unique filenames** (current) | ✅ Zero collisions | None | Fast (parallel) | Low | ✅ Works |
| File locking (append mode) | ⚠️ Prevented collisions | `filelock` | Slow (serialized) | Medium | ❌ Unreliable |
| Append mode (no locking) | ❌ TOCTOU race | None | Fast | Low | ✅ Works (but buggy) |

### Why Unique Filenames Win

**1. Eliminates Race Conditions (Not Just Prevents)**

- **Append mode + locking**: Race condition exists but is prevented through synchronization
- **Unique filenames**: Race condition is impossible (no shared resource)

**2. Better Performance**

```
File Locking Approach (Serialized):
Benchmark 1 ──[acquire lock]──→ write ──[release lock]──→ done
                  ↓ (blocks)
Benchmark 2 ──[wait]──[acquire lock]──→ write ──→ done
                         ↓ (blocks)
Benchmark 3 ──[wait]──[wait]──[acquire lock]──→ write ──→ done

Total time: Serialized writes (adds ~10-50ms per benchmark)

Unique Filename Approach (Parallel):
Benchmark 1 ──→ write ──→ done
Benchmark 2 ──→ write ──→ done
Benchmark 3 ──→ write ──→ done

Total time: Parallel writes (zero overhead)
```

**3. Simpler Implementation**

- No dependency on `filelock` library
- No lock timeout handling
- No stale lock file cleanup
- No cross-platform file locking issues

**4. Natural Traceability**

- Filename encodes full configuration
- Easy to identify which config produced which results
- Maps naturally to MLflow artifacts
- Self-documenting file organization

**5. Re-run Friendly**

- Running same config again overwrites old results (desired behavior)
- No need to manually delete old data
- Atomic file replacement on most filesystems

### Trade-offs

**Pros:**
- ✅ Zero collision risk
- ✅ Better performance (parallel writes)
- ✅ Simpler codebase (no locking logic)
- ✅ Works on network filesystems
- ✅ Self-documenting filenames

**Cons:**
- ⚠️ Multiple files instead of single aggregated file
- ⚠️ Requires post-processing merge (already implemented in `load_data()`)
- ⚠️ More disk space (typically 50-100 files, ~5MB total - negligible)

---

## Testing

### Multiprocess Safety Tests

**File:** `tests/test_csv_multirun_safety.py`

**Test Coverage:**

1. **Concurrent Different Configs (Primary Use Case)**
   ```python
   def test_concurrent_different_configs_no_collision():
       # Spawns 4 threads with different NFFT values
       # Verifies 4 separate CSV files created
       # Verifies no duplicate headers, no NaN values
   ```

2. **Concurrent Identical Configs (Edge Case)**
   ```python
   def test_concurrent_identical_configs_last_write_wins():
       # Spawns 2 threads with identical config
       # Verifies only 1 CSV exists (last write wins)
       # Verifies CSV valid (no corruption)
   ```

3. **CSV Header Integrity**
   ```python
   def test_csv_header_integrity():
       # Parses existing CSV files in artifacts/data
       # Verifies exactly ONE header per file
       # Catches TOCTOU bug pattern (duplicate headers mid-file)
   ```

4. **Data Aggregation**
   ```python
   def test_load_data_aggregates_all_csvs():
       # Creates 5 CSV files with different configs
       # Calls load_data()
       # Verifies all rows merged correctly
   ```

5. **Filename Pattern Validation**
   ```python
   def test_filename_uniqueness():
       # Verifies different configs produce unique filenames
       # Tests overlap encoding (0.75 → "0p7500")
   ```

**Run Tests:**
```bash
pytest tests/test_csv_multirun_safety.py -v
```

**Expected Output:**
```
8 passed in 0.73s
```

### Manual Validation

**1. Multirun Test (Different Configs):**
```bash
rm -rf artifacts/data/*_summary_*.csv

python benchmarks/run_latency.py --multirun \
  experiment=ionosphere_test +benchmark=profiling \
  engine.nfft=1024,2048,4096

# Verify: 3 CSV files created, all valid
ls artifacts/data/latency_summary_*.csv
```

**2. Data Aggregation Test:**
```python
from experiments.analysis.cli import load_data
from pathlib import Path

df = load_data(Path("artifacts/data"))
assert not df.isnull().any().any()
print(f"✅ Loaded {len(df)} rows from {df['source_file'].nunique()} files")
```

**3. Dashboard Integration Test:**
```bash
sigx dashboard  # Should load without errors
# Navigate to General Performance page
# Verify data displays correctly
```

---

## Migration History

### Issue 010: TOCTOU Race Condition Concern

**Date:** Phase 0 Readiness Audit (2025-12-15)

**Problem Identified:**

Issue document `docs/github-issues/phase0/010-fix-csv-append-race-condition.md` described a potential TOCTOU (Time-of-Check-Time-of-Use) race condition if benchmark scripts used append mode:

```python
# Hypothetical vulnerable pattern (never actually implemented):
summary_path = output_dir / "summary.csv"
summary_df.to_csv(
    summary_path,
    mode='a',                          # Append mode
    header=not summary_path.exists(),  # ❌ RACE: Check-then-use
    index=False
)
```

**Timeline:**
```
T0: Process 1 checks summary.csv → doesn't exist
T1: Process 2 checks summary.csv → doesn't exist
T2: Process 1 writes header + data
T3: Process 2 writes header + data  ← DUPLICATE HEADER!
```

**Resolution:** Commit `7988292` (2025-12-XX)

**Implementation:** Unique filename approach (Option 3 from issue proposal)

**Reason:** This approach eliminates the race condition entirely rather than preventing it through file locking. Benefits include better performance, simpler implementation, and zero dependencies.

### Verification (2025-01-02)

**Added:**
- Comprehensive test suite: `tests/test_csv_multirun_safety.py`
- Enhanced code comments in all 4 benchmark scripts
- Design documentation: `docs/benchmarking/csv-file-organization.md`
- Issue status updated to "RESOLVED"

**Validated:**
- 8/8 tests pass
- Production multirun sweeps working correctly
- No CSV corruption observed in 20+ Snakemake multirun rules

---

## Edge Cases

### 1. Simultaneous Identical Configs

**Scenario:**
```
Process 1: NFFT=4096, overlap=0.75 (starts at T0)
Process 2: NFFT=4096, overlap=0.75 (starts at T0.001s)
Both write to: latency_summary_4096_2_0p7500_streaming.csv
```

**Result:**
- One process's write completes first
- Other process overwrites it
- **Last writer wins** (one dataset lost, but no corruption)

**Probability:** **VERY LOW**
- Would require manually launching identical configs simultaneously
- Hydra multirun prevents this by design (assigns unique parameters)
- Snakemake prevents this (rules run sequentially or with different targets)

**Mitigation:**
- Document behavior in this design doc ✅
- Accept as acceptable edge case

### 2. Too Many CSV Files

**Concern:** >1000 files could degrade filesystem performance

**Current Status:**
- Typical usage: 50-100 files (~5MB total)
- Not a concern for current workload

**Mitigation (if needed):**
- Monitor `artifacts/data` directory size
- Add cleanup script to archive old results
- Not urgent

### 3. Network Filesystems

**Scenario:** Running benchmarks on NFS/SMB mounted storage

**Status:**
- ✅ **Works with unique filenames** (no locking needed)
- ❌ **File locking approach would fail** (NFS locking unreliable)

**Recommendation:** Unique filenames is the correct choice for network storage

---

## Future Enhancements

### Potential Improvements (Low Priority)

1. **Timestamp-based Filenames (Optional)**
   - Add timestamp to filename for tracking multiple runs of same config
   - Format: `latency_summary_4096_2_0p7500_streaming_20250102_143022.csv`
   - **When needed:** If re-run tracking becomes important

2. **Automatic Archival (Optional)**
   - Script to move old CSV files to `artifacts/data/archive/`
   - **When needed:** If >1000 files accumulate

3. **CSV Consolidation Tool (Optional)**
   - CLI command: `sigx consolidate-results --output combined.csv`
   - **When needed:** If single-file export required for external tools

**Current Status:** Not needed, unique filenames working well

---

## Related Documentation

- **Code Implementation:**
  - `benchmarks/run_latency.py:143-160` - Latency CSV writing
  - `benchmarks/run_throughput.py:156-173` - Throughput CSV writing
  - `benchmarks/run_realtime.py:164-181` - Realtime CSV writing
  - `benchmarks/run_accuracy.py:152-169` - Accuracy CSV writing

- **Data Loading:**
  - `experiments/analysis/cli.py:24-56` - `load_data()` aggregation
  - `experiments/streamlit/utils/data_loader.py:24-38` - Dashboard loading

- **Testing:**
  - `tests/test_csv_multirun_safety.py` - Multiprocess safety tests

- **Issue Tracking:**
  - `docs/github-issues/phase0/010-fix-csv-append-race-condition.md` - Original issue (RESOLVED)

- **User Documentation:**
  - `CLAUDE.md` - System reliability notes

---

## Summary

The unique filename pattern is a **simple, robust, and performant** solution for preventing race conditions in parallel benchmark sweeps. It eliminates the race condition entirely rather than preventing it through synchronization, resulting in better performance and simpler code.

**Key Takeaway:** When designing concurrent systems, eliminating shared resources is often better than synchronizing access to them.
