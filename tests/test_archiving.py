"""Tests for manifest locking and concurrency safeguards in DataArchiver."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from filelock import FileLock, Timeout

from sigtekx.utils.archiving import DataArchiver


def test_concurrent_manifest_updates(tmp_path: Path) -> None:
    """Concurrent manifest updates should not lose entries."""
    archiver = DataArchiver(tmp_path / "archive_concurrency")
    experiment = "concurrent_test"

    def append_entry(idx: int) -> None:
        archiver._update_manifest(
            experiment,
            f"result_{idx}.json",
            datetime.now() + timedelta(seconds=idx),
        )

    threads = [threading.Thread(target=append_entry, args=(i,)) for i in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    manifest = archiver._load_manifest()
    entries = manifest.get(experiment, [])
    assert len(entries) == 10
    assert {entry["filename"] for entry in entries} == {f"result_{i}.json" for i in range(10)}


def test_manifest_lock_timeout(tmp_path: Path) -> None:
    """Lock contention should time out and recover cleanly once released."""
    archiver = DataArchiver(tmp_path / "archive_lock_timeout")
    archiver._manifest_lock_timeout = 0.1
    manifest_path = archiver.base_dir / "manifest.json"
    lock = FileLock(str(manifest_path.with_suffix(".json.lock")), timeout=0.1)

    lock.acquire()
    try:
        with pytest.raises(Timeout):
            archiver._update_manifest("blocked", "result.json", datetime.now())
    finally:
        lock.release()

    # Should recover and write once the stale lock clears.
    archiver._update_manifest("blocked", "result.json", datetime.now())
    manifest = archiver._load_manifest()
    assert manifest["blocked"][0]["filename"] == "result.json"
