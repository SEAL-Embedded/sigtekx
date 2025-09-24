"""Benchmark data archiving helpers with standardized naming."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from ionosense_hpc.utils.paths import (
    get_benchmark_result_path,
    get_benchmark_run_dir,
    get_benchmarks_root,
    normalize_benchmark_name,
)

__all__ = ["DataArchiver"]


class DataArchiver:
    """Archive and manage benchmark data for reproducibility."""

    def __init__(self, base_dir: str | Path | None = None):
        self._custom_base = base_dir is not None
        self.base_dir = Path(base_dir) if base_dir is not None else get_benchmarks_root()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def archive_results(
        self,
        results: dict[str, Any],
        experiment_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Archive benchmark results with metadata."""
        timestamp = datetime.now()
        archive_path = self._build_target_path(experiment_name, timestamp)

        payload: dict[str, Any] = {
            "experiment": experiment_name,
            "timestamp": timestamp.isoformat(timespec="seconds"),
            "results": results,
            "metadata": metadata or {},
            "environment": self._capture_environment(),
        }

        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with archive_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

        self._update_manifest(experiment_name, archive_path.name, timestamp)
        return archive_path

    def load_results(self, experiment_name: str, version: str | None = None) -> dict[str, Any]:
        """Load archived results for an experiment."""
        exp_dir = self._resolve_experiment_dir(experiment_name)
        if not exp_dir.exists():
            raise FileNotFoundError(f"No archive for experiment: {experiment_name}")

        if version is None:
            files = sorted(exp_dir.glob("*.json"))
            if not files:
                raise FileNotFoundError(f"No results in archive: {experiment_name}")
            archive_path = files[-1]
        else:
            safe = normalize_benchmark_name(experiment_name)
            archive_path = exp_dir / f"{safe}_{version}.json"
            if not archive_path.exists():
                raise FileNotFoundError(f"Version not found: {version}")

        with archive_path.open(encoding="utf-8") as handle:
            return cast(dict[str, Any], json.load(handle))

    def compare_versions(
        self,
        experiment_name: str,
        version1: str,
        version2: str,
    ) -> dict[str, Any]:
        """Compare two archived versions of a benchmark result."""
        results1 = self.load_results(experiment_name, version1)
        results2 = self.load_results(experiment_name, version2)

        comparison: dict[str, Any] = {
            "experiment": experiment_name,
            "version1": version1,
            "version2": version2,
            "differences": {},
        }

        if "results" in results1 and "results" in results2:
            r1 = results1["results"]
            r2 = results2["results"]
            flat1 = self._flatten_dict(r1)
            flat2 = self._flatten_dict(r2)
            common_keys = flat1.keys() & flat2.keys()

            differences: dict[str, dict[str, float]] = {}
            for key in common_keys:
                v1 = flat1[key]
                v2 = flat2[key]
                if isinstance(v1, int | float) and isinstance(v2, int | float):
                    diff = v2 - v1
                    pct_change = (diff / v1 * 100) if v1 != 0 else 0.0
                    differences[key] = {
                        "v1": v1,
                        "v2": v2,
                        "diff": diff,
                        "pct_change": pct_change,
                    }
            comparison["differences"] = differences

        return comparison

    def _build_target_path(self, experiment_name: str, timestamp: datetime) -> Path:
        safe = normalize_benchmark_name(experiment_name)
        if self._custom_base:
            exp_dir = self.base_dir / safe
            exp_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{safe}_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
            return exp_dir / filename
        return get_benchmark_result_path(experiment_name, timestamp=timestamp)

    def _resolve_experiment_dir(self, experiment_name: str) -> Path:
        if self._custom_base:
            return self.base_dir / normalize_benchmark_name(experiment_name)
        return get_benchmark_run_dir(experiment_name)

    def _capture_environment(self) -> dict[str, Any]:
        import platform
        import sys

        return {
            "platform": platform.platform(),
            "python": sys.version,
            "cwd": str(Path.cwd()),
            "archive_version": "1.0",
        }

    def _update_manifest(self, experiment_name: str, filename: str, timestamp: datetime) -> None:
        manifest_path = self.base_dir / "manifest.json"
        if manifest_path.exists():
            with manifest_path.open(encoding="utf-8") as handle:
                manifest = json.load(handle)
        else:
            manifest = {}

        entries = manifest.setdefault(experiment_name, [])
        entries.append({
            "filename": filename,
            "timestamp": timestamp.strftime("%Y%m%d_%H%M%S"),
        })

        with manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)

    def _flatten_dict(self, data: dict[str, Any], parent_key: str = "") -> dict[str, Any]:
        items: dict[str, Any] = {}
        for key, value in data.items():
            new_key = f"{parent_key}.{key}" if parent_key else key
            if isinstance(value, dict):
                items.update(self._flatten_dict(value, new_key))
            else:
                items[new_key] = value
        return items
