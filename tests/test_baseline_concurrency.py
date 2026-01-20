"""Tests for concurrent baseline operations."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from filelock import FileLock, Timeout

from sigtekx.utils.baseline import BaselineManager


def test_concurrent_baseline_saves(tmp_path: Path) -> None:
    """Verify concurrent baseline saves don't lose entries in manifest."""
    manager = BaselineManager(baselines_dir=tmp_path / "baselines")

    # Create dummy artifacts directory
    artifacts_dir = tmp_path / "artifacts" / "data"
    artifacts_dir.mkdir(parents=True)

    def save_baseline(idx: int) -> None:
        # Create dummy CSV
        csv_path = artifacts_dir / f"latency_summary_{idx}.csv"
        csv_path.write_text("nfft,latency\n4096,100\n")

        # Save baseline
        manager.save_baseline(
            name=f"baseline-{idx}",
            phase=1,
            message=f"Test baseline {idx}"
        )

    # Spawn 10 threads saving concurrently
    threads = [
        threading.Thread(target=save_baseline, args=(i,))
        for i in range(10)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify all 10 baselines are in manifest
    baselines = manager.list_baselines()
    assert len(baselines) == 10

    # Verify all names present
    names = {b["name"] for b in baselines}
    expected = {f"baseline-{i}" for i in range(10)}
    assert names == expected


def test_concurrent_baseline_delete(tmp_path: Path) -> None:
    """Verify concurrent baseline deletes don't corrupt manifest."""
    manager = BaselineManager(baselines_dir=tmp_path / "baselines")

    # Create dummy artifacts directory
    artifacts_dir = tmp_path / "artifacts" / "data"
    artifacts_dir.mkdir(parents=True)

    # Create 5 baselines first
    for i in range(5):
        csv_path = artifacts_dir / f"latency_summary_{i}.csv"
        csv_path.write_text("nfft,latency\n4096,100\n")

        manager.save_baseline(
            name=f"baseline-{i}",
            phase=1,
            message=f"Test baseline {i}"
        )

    # Delete 3 of them concurrently
    def delete_baseline(idx: int) -> None:
        manager.delete_baseline(f"baseline-{idx}", force=True)

    threads = [
        threading.Thread(target=delete_baseline, args=(i,))
        for i in range(3)  # Delete 0, 1, 2
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify only 2 baselines remain (3, 4)
    baselines = manager.list_baselines()
    assert len(baselines) == 2

    names = {b["name"] for b in baselines}
    assert names == {"baseline-3", "baseline-4"}


def test_manifest_lock_timeout(tmp_path: Path) -> None:
    """Verify lock timeout recovery for stale locks."""
    manager = BaselineManager(baselines_dir=tmp_path / "baselines")
    manifest_path = manager.baselines_dir / ".baseline_manifest.json"
    lock_path = manifest_path.with_suffix(".json.lock")

    # Acquire lock externally to simulate stale lock
    external_lock = FileLock(str(lock_path), timeout=0.1)
    external_lock.acquire()

    try:
        # BaselineManager should timeout and raise
        with pytest.raises(Timeout):
            # Test the _update_manifest method directly (what we actually fixed)
            manager._update_manifest("blocked", {
                "created": "2026-01-09T00:00:00+00:00",
                "phase": 1,
                "scope": "minimal"
            })
    finally:
        external_lock.release()

    # Should recover after lock released
    manager._update_manifest("recovered", {
        "created": "2026-01-09T00:00:01+00:00",
        "phase": 1,
        "scope": "minimal"
    })

    # Verify manifest was updated (read manifest directly)
    import json
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)

    baselines = manifest.get("baselines", [])
    assert len(baselines) == 1
    assert baselines[0]["name"] == "recovered"
