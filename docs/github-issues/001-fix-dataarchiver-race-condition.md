# Fix DataArchiver Race Condition in Concurrent Benchmark Execution

## Problem

The `_update_manifest` method in `DataArchiver` (`src/sigtekx/utils/archiving.py`) has a classic race condition that can cause data loss when multiple benchmark processes run concurrently. The current implementation follows a non-atomic read-modify-write pattern that fails when Hydra multirun or Snakemake parallel execution spawn concurrent processes.

**Failure scenario:**
1. Process A reads `manifest.json` (contains 5 entries)
2. Process B reads `manifest.json` (contains 5 entries)
3. Process A appends entry #6, writes file (6 entries)
4. Process B appends entry #6 to its in-memory copy, writes file (6 entries - **Process A's entry is lost**)

**Impact:**
- Silent data loss during parallel benchmark execution
- Corrupted experiment manifests
- No error reporting when entries are lost
- Critical for Phase 4 experiments that use Snakemake with `--cores 4`

## Current Implementation

**File:** `src/sigtekx/utils/archiving.py` (lines 139-154)

```python
def _update_manifest(self, experiment_name: str, filename: str, timestamp: datetime) -> None:
    manifest_path = self.base_dir / "manifest.json"

    # RACE CONDITION: Non-atomic read
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8") as handle:
            manifest = json.load(handle)  # ← Process A reads
    else:
        manifest = {}

    # Modify in memory (no protection)
    entries = manifest.setdefault(experiment_name, [])
    entries.append({
        "filename": filename,
        "timestamp": timestamp.strftime("%Y%m%d_%H%M%S"),
    })

    # RACE CONDITION: Non-atomic write
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)  # ← Process B overwrites A's changes
```

**Problematic execution patterns:**

From `experiments/Snakefile`:
```bash
# Snakemake runs with --cores 4 (4 parallel rules)
snakemake --cores 4 --snakefile experiments/Snakefile
```

From Hydra multirun configs (`experiments/conf/experiment/ionosphere_resolution.yaml`):
```yaml
# Sweeps spawn 12 parallel jobs (4 NFFT × 3 overlap values)
hydra:
  mode: MULTIRUN
  sweeper:
    params:
      engine.nfft: 4096,8192,16384,32768
      engine.overlap: 0.5,0.75,0.875
```

## Proposed Solution

Use the cross-platform `filelock` library to make the read-modify-write operation atomic:

```python
from filelock import FileLock

def _update_manifest(self, experiment_name: str, filename: str, timestamp: datetime) -> None:
    """Update experiment manifest with file locking for concurrent safety."""
    manifest_path = self.base_dir / "manifest.json"
    lock_path = manifest_path.with_suffix('.json.lock')

    # Atomic read-modify-write protected by file lock
    with FileLock(str(lock_path), timeout=10):
        # Read
        if manifest_path.exists():
            with manifest_path.open(encoding="utf-8") as handle:
                manifest = json.load(handle)
        else:
            manifest = {}

        # Modify
        entries = manifest.setdefault(experiment_name, [])
        entries.append({
            "filename": filename,
            "timestamp": timestamp.strftime("%Y%m%d_%H%M%S"),
        })

        # Write (now protected - no interleaving possible)
        with manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
```

**Dependencies update** (`pyproject.toml`):
```toml
dependencies = [
    # ... existing deps ...
    "filelock>=3.12.0",
]
```

## Additional Technical Insights

- **Cross-Platform Safety**: `filelock` works consistently on Windows, Linux, and macOS (unlike platform-specific `fcntl` or `msvcrt`)

- **Lock Timeout**: The 10-second timeout prevents infinite blocking if a process crashes while holding the lock

- **Lock File Management**: Using `.json.lock` suffix keeps lock files organized and easily identifiable

- **Automatic Cleanup**: `filelock` automatically releases locks on context exit, even if exceptions occur

- **No Existing Locking**: Codebase has zero file locking mechanisms (only GPU clock locking via nvidia-smi)

- **Current Risk Level**: **Medium** - DataArchiver is not currently used in production benchmark runs (MLflow handles archiving), but this is a latent bug that would immediately surface if DataArchiver is adopted

## Implementation Tasks

- [ ] Add `filelock>=3.12.0` to `pyproject.toml` dependencies section
- [ ] Import `FileLock` at top of `src/sigtekx/utils/archiving.py`
- [ ] Wrap `_update_manifest` body with `FileLock` context manager (line 142)
- [ ] Set lock path to `manifest_path.with_suffix('.json.lock')`
- [ ] Set timeout to 10 seconds
- [ ] Add docstring note about thread-safety guarantees
- [ ] Create test in `tests/test_archiving.py` (new file):
  - Test concurrent writes from multiple threads
  - Verify all entries are preserved (no data loss)
  - Test lock timeout behavior (simulate stale lock)
- [ ] Run tests: `pytest tests/test_archiving.py -v`
- [ ] Verify no regression in existing archiving tests
- [ ] Update `DataArchiver` class docstring to mention thread-safety
- [ ] Add `.json.lock` to `.gitignore` if not already covered by `*.lock` pattern

## Edge Cases to Handle

- **Stale Lock Files**: If a process crashes while holding the lock, the 10-second timeout allows recovery (lock acquisition will succeed after timeout)

- **Lock File Cleanup**: `filelock` automatically handles cleanup; no manual removal needed

- **Multiple Manifests**: Each manifest.json gets its own .lock file, so parallel writes to different manifests don't block each other

- **Permission Errors**: If lock file creation fails (permission denied), `FileLock` will raise `PermissionError` with clear context

## Testing Strategy

**Unit test** (`tests/test_archiving.py`):
```python
import threading
from pathlib import Path
from sigtekx.utils.archiving import DataArchiver

def test_concurrent_manifest_updates():
    """Verify no data loss when multiple threads update manifest concurrently."""
    archiver = DataArchiver(Path("artifacts/test_archive"))

    def archive_result(exp_name: str, idx: int):
        archiver.archive_results(
            experiment_name=exp_name,
            data={"result": idx},
            metadata={"index": idx}
        )

    # Spawn 10 threads writing to same experiment
    threads = [
        threading.Thread(target=archive_result, args=("concurrent_test", i))
        for i in range(10)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify all 10 entries exist in manifest
    manifest = archiver._load_manifest()
    assert len(manifest["concurrent_test"]) == 10
    assert set(e["filename"] for e in manifest["concurrent_test"]) == {
        f"concurrent_test_result_{i}.json" for i in range(10)
    }
```

**Integration test** (manual verification with Snakemake):
```bash
# Run parallel benchmarks
snakemake --cores 4 --snakefile experiments/Snakefile

# Verify manifest integrity
python -c "
import json
from pathlib import Path
manifest = json.loads(Path('artifacts/data/manifest.json').read_text())
print(f'Total experiments: {len(manifest)}')
for exp, entries in manifest.items():
    print(f'  {exp}: {len(entries)} entries')
"
```

## Acceptance Criteria

- [ ] `filelock` dependency added to `pyproject.toml`
- [ ] `_update_manifest` wrapped with `FileLock` context manager
- [ ] Timeout set to 10 seconds
- [ ] Lock file path uses `.json.lock` suffix
- [ ] Concurrent test added to verify no data loss (10 threads)
- [ ] Lock timeout test added to verify recovery from stale locks
- [ ] All existing tests pass
- [ ] Docstring updated to mention thread-safety
- [ ] `.gitignore` includes `.json.lock` files

## Benefits

- **Data Integrity**: Prevents silent loss of experiment results in parallel execution
- **CI/CD Safety**: Enables reliable parallel benchmark execution in GitHub Actions
- **Future-Proof**: Prepares for Phase 4 scaling experiments that use Snakemake parallelism
- **Low Cost**: Single dependency, ~10 lines of code change
- **Minimal Performance Impact**: File locks only held during JSON I/O (< 10ms typically)

---

**Labels:** `bug`, `team-3-python`, `python`, `reliability`, `good first issue`

**Estimated Effort:** 1-2 hours (including tests)

**Priority:** Medium (latent bug, but low current risk)

**Roadmap Phase:** Phase 0/1 (infrastructure hardening before Phase 4 experiments)
