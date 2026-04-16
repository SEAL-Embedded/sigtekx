"""Tests for concurrent dataset registry operations."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from filelock import FileLock, Timeout

from sigtekx.utils.datasets import DatasetRegistry


def test_concurrent_dataset_saves(tmp_path: Path) -> None:
    """Verify concurrent saves don't lose entries in the registry manifest."""
    registry = DatasetRegistry(datasets_dir=tmp_path / "datasets")

    artifacts_dir = tmp_path / "artifacts" / "data"
    artifacts_dir.mkdir(parents=True)

    # Monkey-patch artifacts source so the registry reads from our temp dir.
    registry.artifacts_dir = tmp_path / "artifacts"

    def save_one(idx: int) -> None:
        csv_path = artifacts_dir / f"latency_summary_{idx}.csv"
        csv_path.write_text("engine_nfft,mean_latency_us\n4096,100\n")
        registry.save(
            name=f"dataset-{idx}",
            tag="test",
            message=f"test dataset {idx}",
        )

    threads = [threading.Thread(target=save_one, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    datasets = registry.list_datasets()
    assert len(datasets) == 10
    names = {d["name"] for d in datasets}
    assert names == {f"dataset-{i}" for i in range(10)}


def test_concurrent_dataset_deletes(tmp_path: Path) -> None:
    """Verify concurrent deletes don't corrupt the registry manifest."""
    registry = DatasetRegistry(datasets_dir=tmp_path / "datasets")

    artifacts_dir = tmp_path / "artifacts" / "data"
    artifacts_dir.mkdir(parents=True)
    registry.artifacts_dir = tmp_path / "artifacts"

    for i in range(5):
        csv_path = artifacts_dir / f"latency_summary_{i}.csv"
        csv_path.write_text("engine_nfft,mean_latency_us\n4096,100\n")
        registry.save(name=f"dataset-{i}", tag="test", message=f"d{i}")

    def delete_one(idx: int) -> None:
        registry.delete(f"dataset-{idx}", force=True)

    threads = [threading.Thread(target=delete_one, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    datasets = registry.list_datasets()
    assert len(datasets) == 2
    names = {d["name"] for d in datasets}
    assert names == {"dataset-3", "dataset-4"}


def test_registry_lock_timeout(tmp_path: Path) -> None:
    """Verify lock timeout recovery for stale locks."""
    registry = DatasetRegistry(datasets_dir=tmp_path / "datasets")
    manifest_path = registry.datasets_dir / ".dataset_manifest.json"
    lock_path = manifest_path.with_suffix(".json.lock")

    external_lock = FileLock(str(lock_path), timeout=0.1)
    external_lock.acquire()

    try:
        with pytest.raises(Timeout):
            registry._update_registry_manifest(
                "blocked",
                {"created": "2026-01-09T00:00:00+00:00", "tag": "t", "scope": "minimal"},
            )
    finally:
        external_lock.release()

    registry._update_registry_manifest(
        "recovered",
        {"created": "2026-01-09T00:00:01+00:00", "tag": "t", "scope": "minimal"},
    )

    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)

    entries = manifest.get("datasets", [])
    assert len(entries) == 1
    assert entries[0]["name"] == "recovered"
