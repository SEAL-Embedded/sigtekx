"""Dataset registry for persistent benchmark result storage.

PERSISTENT DATASET STORAGE
──────────────────────────
Provides a named registry for whole-suite benchmark result sets that survive
`sigx clean`. Each dataset is a directory under `datasets/` containing CSV
summaries, optional MLflow runs, and a manifest with provenance metadata
(source machine, git SHA, hardware, notes).

TWO-TIER EXPERIMENT TRACKING
────────────────────────────
Tier 1 — EPHEMERAL (`artifacts/`): live scratchpad. Every benchmark run
writes here. `sigx clean` wipes it. MLflow + CSV.

Tier 2 — PERSISTENT (`datasets/`): named result sets. Managed by this module
(`sigx dataset save/list/compare/delete`). Holds local runs, cloud runs,
regression snapshots — anything you want to keep around. Survives `sigx clean`.

USAGE
─────
    # 1. Run benchmarks
    python benchmarks/run_latency.py +benchmark=latency

    # 2. Save the result set under a name
    sigx dataset save local-rtx-run1 --message "RTX 4090 baseline"

    # 3. Clean artifacts (datasets/ survives)
    sigx clean

    # 4. Run again, save another
    python benchmarks/run_latency.py +benchmark=latency
    sigx dataset save local-rtx-run2 --message "After optimization"

    # 5. Compare
    sigx dataset compare local-rtx-run1 local-rtx-run2

CONCURRENCY
───────────
Manifest operations use file locking to prevent races during concurrent saves.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

__all__ = ["DatasetRegistry"]


class DatasetRegistry:
    """Manage persistent named datasets for benchmark result storage.

    Datasets live under `datasets/` (repo root, git-ignored). Each dataset
    contains:

    - `manifest.json`: dataset info, git state, hardware, summary metrics
    - `data/`: CSV summaries copied from `artifacts/data/`
    - `mlruns/`: MLflow tracking (optional, scope=standard/full)
    - `README.md`: human-readable summary

    Scopes:

    - `minimal`: CSV only (~1 MB)
    - `standard`: CSV + MLflow (~40 MB, default)
    - `full`: CSV + MLflow + profiling (~100+ MB)
    """

    def __init__(self, datasets_dir: Path | None = None):
        """Initialize the dataset registry.

        Args:
            datasets_dir: Custom datasets directory. Defaults to `<repo>/datasets/`.
        """
        if datasets_dir is None:
            repo_root = self._find_repo_root()
            self.datasets_dir = repo_root / "datasets"
        else:
            self.datasets_dir = Path(datasets_dir)

        self.datasets_dir.mkdir(parents=True, exist_ok=True)

        repo_root = self._find_repo_root()
        self.artifacts_dir = repo_root / "artifacts"

    def save(
        self,
        name: str,
        tag: str | None = None,
        scope: str = "standard",
        message: str = "",
        source: str = "local",
    ) -> Path:
        """Save current artifacts as a named dataset.

        Args:
            name: Dataset name (e.g., "local-rtx-run1", "aws-20260415T120000Z").
            tag: Optional free-form tag (e.g., "pre-optimization", "phase1").
            scope: Archive scope — "minimal", "standard" (default), or "full".
            message: Human-readable description.
            source: Origin label ("local", "aws-ec2", etc.) for provenance.

        Returns:
            Path to the saved dataset directory.

        Raises:
            FileNotFoundError: If `artifacts/data/` is missing.
            ValueError: If a dataset with the same name already exists.
        """
        artifacts_data_dir = self.artifacts_dir / "data"
        if not artifacts_data_dir.exists():
            raise FileNotFoundError(
                f"No artifacts found at {artifacts_data_dir}. "
                "Run benchmarks first: snakemake --cores 4"
            )

        dataset_dir = self.datasets_dir / name
        if dataset_dir.exists():
            raise ValueError(
                f"Dataset '{name}' already exists at {dataset_dir}. "
                "Use a different name or delete the existing dataset first."
            )

        dataset_dir.mkdir(parents=True, exist_ok=True)

        if scope in {"minimal", "standard", "full"}:
            shutil.copytree(artifacts_data_dir, dataset_dir / "data")

        if scope in {"standard", "full"}:
            mlruns_src = self.artifacts_dir / "mlruns"
            if mlruns_src.exists():
                shutil.copytree(mlruns_src, dataset_dir / "mlruns")

        if scope == "full":
            profiling_src = self.artifacts_dir / "profiling"
            if profiling_src.exists():
                shutil.copytree(profiling_src, dataset_dir / "profiling")

        manifest = self._create_manifest(name, tag, scope, message, source, dataset_dir)

        manifest_path = dataset_dir / "manifest.json"
        with manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        readme_path = dataset_dir / "README.md"
        with readme_path.open("w", encoding="utf-8") as f:
            f.write(self._generate_readme(manifest))

        self._update_registry_manifest(name, manifest)

        return dataset_dir

    def load_manifest(self, name: str) -> dict[str, Any] | None:
        """Load manifest for a dataset.

        Args:
            name: Dataset name.

        Returns:
            Manifest dict, or None if not found.
        """
        dataset_dir = self.datasets_dir / name
        manifest_path = dataset_dir / "manifest.json"

        if not manifest_path.exists():
            return None

        with manifest_path.open(encoding="utf-8") as f:
            return json.load(f)

    def list_datasets(self, tag_filter: str | None = None) -> list[dict[str, Any]]:
        """List all saved datasets.

        Args:
            tag_filter: Optional filter by `tag` field.

        Returns:
            List of manifest dicts, newest first.
        """
        datasets: list[dict[str, Any]] = []

        for dataset_dir in self.datasets_dir.iterdir():
            if not dataset_dir.is_dir():
                continue
            if dataset_dir.name == "cpp":
                # C++ subtree is managed by the `sigxc` tool, not this registry.
                continue

            manifest = self.load_manifest(dataset_dir.name)
            if manifest:
                if tag_filter is not None and manifest.get("tag") != tag_filter:
                    continue
                datasets.append(manifest)

        datasets.sort(key=lambda x: x.get("created", ""), reverse=True)
        return datasets

    def compare_datasets(self, name1: str, name2: str) -> dict[str, Any]:
        """Compare two datasets by re-extracting metrics from their CSV data.

        Args:
            name1: First dataset name.
            name2: Second dataset name.

        Returns:
            Comparison dict with keys:
            - `dataset1`, `dataset2`: manifest dicts
            - `metrics`: dict mapping metric name → {value1, value2, delta, pct_change}
            - `summary`: names, tags, creation times

        Raises:
            FileNotFoundError: If either dataset is missing.
        """
        manifest1 = self.load_manifest(name1)
        manifest2 = self.load_manifest(name2)

        if manifest1 is None:
            raise FileNotFoundError(f"Dataset '{name1}' not found")
        if manifest2 is None:
            raise FileNotFoundError(f"Dataset '{name2}' not found")

        dataset1_dir = self.datasets_dir / name1
        dataset2_dir = self.datasets_dir / name2

        metrics1 = self._extract_metrics(dataset1_dir / "data") if (dataset1_dir / "data").exists() else {}
        metrics2 = self._extract_metrics(dataset2_dir / "data") if (dataset2_dir / "data").exists() else {}

        metrics_comparison: dict[str, dict[str, Any]] = {}
        all_metric_keys = set(metrics1.keys()) | set(metrics2.keys())

        for key in all_metric_keys:
            val1 = metrics1.get(key)
            val2 = metrics2.get(key)

            if val1 is not None and val2 is not None:
                delta = val2 - val1
                pct_change = (delta / val1 * 100) if val1 != 0 else 0.0
                metrics_comparison[key] = {
                    "value1": val1,
                    "value2": val2,
                    "delta": delta,
                    "pct_change": pct_change,
                }
            elif val1 is not None:
                metrics_comparison[key] = {"value1": val1, "value2": None, "delta": None, "pct_change": None}
            else:
                metrics_comparison[key] = {"value1": None, "value2": val2, "delta": None, "pct_change": None}

        return {
            "dataset1": manifest1,
            "dataset2": manifest2,
            "metrics": metrics_comparison,
            "summary": {
                "dataset1_name": name1,
                "dataset2_name": name2,
                "dataset1_tag": manifest1.get("tag"),
                "dataset2_tag": manifest2.get("tag"),
                "dataset1_created": manifest1.get("created"),
                "dataset2_created": manifest2.get("created"),
            },
        }

    def delete(self, name: str, force: bool = False) -> bool:
        """Delete a dataset.

        Args:
            name: Dataset name.
            force: Skip confirmation (confirmation is handled at the CLI layer).

        Returns:
            True on success.

        Raises:
            FileNotFoundError: If the dataset is missing.
        """
        dataset_dir = self.datasets_dir / name
        if not dataset_dir.exists():
            raise FileNotFoundError(f"Dataset '{name}' not found at {dataset_dir}")

        shutil.rmtree(dataset_dir)
        self._remove_from_registry_manifest(name)
        return True

    def export(self, name: str, destination: Path, format: str = "zip") -> Path:
        """Export a dataset as an archive (Phase 2 feature — stub)."""
        raise NotImplementedError(
            "Dataset export is a Phase 2 feature. Current MVP includes save, list, "
            "compare, and delete only."
        )

    # ========== Private helpers ==========

    def _find_repo_root(self) -> Path:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            return Path(result.stdout.strip())
        except subprocess.CalledProcessError:
            return Path(__file__).parent.parent.parent.parent

    def _create_manifest(
        self,
        name: str,
        tag: str | None,
        scope: str,
        message: str,
        source: str,
        dataset_dir: Path,
    ) -> dict[str, Any]:
        git_commit, git_branch = self._get_git_info()
        size_mb = self._calculate_directory_size(dataset_dir)
        metrics = self._extract_metrics(dataset_dir / "data")
        hardware_info = self._get_hardware_info()

        return {
            "name": name,
            "source": source,
            "tag": tag,
            "scope": scope,
            "message": message,
            "created": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit,
            "git_branch": git_branch,
            "size_mb": size_mb,
            "hardware": hardware_info,
            "metrics": metrics,
        }

    def _get_hardware_info(self) -> dict[str, Any]:
        import platform

        import psutil

        hardware: dict[str, Any] = {
            "os": platform.system(),
            "os_version": platform.version(),
            "cpu": platform.processor(),
            "cpu_cores": psutil.cpu_count(logical=False),
            "cpu_threads": psutil.cpu_count(logical=True),
            "ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        }

        try:
            import torch

            if torch.cuda.is_available():
                hardware["gpu_count"] = torch.cuda.device_count()
                hardware["gpu_name"] = torch.cuda.get_device_name(0)
                hardware["cuda_version"] = torch.version.cuda

                props = torch.cuda.get_device_properties(0)
                hardware["gpu_memory_gb"] = round(props.total_memory / (1024**3), 2)
                hardware["gpu_compute_capability"] = f"{props.major}.{props.minor}"
            else:
                hardware["gpu_available"] = False
        except (ImportError, RuntimeError):
            hardware["gpu_available"] = False

        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                check=True,
            )
            hardware["nvidia_driver"] = result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        return hardware

    def _get_git_info(self) -> tuple[str, str]:
        try:
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            return commit, branch
        except subprocess.CalledProcessError:
            return "unknown", "unknown"

    def _calculate_directory_size(self, path: Path) -> float:
        total_size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return total_size / (1024 * 1024)

    def _extract_metrics(self, data_dir: Path) -> dict[str, Any]:
        """Extract summary metrics from benchmark CSV files."""
        metrics: dict[str, Any] = {}
        import csv

        def safe_float(value: Any) -> float | None:
            try:
                return float(value) if value else None
            except (ValueError, TypeError):
                return None

        for csv_path in data_dir.glob("latency_summary_*.csv"):
            try:
                with csv_path.open(encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        sample_rate = row.get("engine_sample_rate_hz", "")
                        mode = row.get("engine_mode", "")
                        rate_key = "48k" if sample_rate == "48000" else "100k"
                        prefix = f"latency_{rate_key}_{mode}"
                        if "mean_latency_us" in row:
                            metrics[f"{prefix}_mean_us"] = safe_float(row["mean_latency_us"])
                        if "p95_latency_us" in row:
                            metrics[f"{prefix}_p95_us"] = safe_float(row["p95_latency_us"])
                        if "p99_latency_us" in row:
                            metrics[f"{prefix}_p99_us"] = safe_float(row["p99_latency_us"])
            except (csv.Error, OSError):
                pass

        for csv_path in data_dir.glob("throughput_summary_*.csv"):
            try:
                with csv_path.open(encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        sample_rate = row.get("engine_sample_rate_hz", "")
                        mode = row.get("engine_mode", "")
                        rate_key = "48k" if sample_rate == "48000" else "100k"
                        prefix = f"throughput_{rate_key}_{mode}"
                        if "frames_per_second" in row:
                            metrics[f"{prefix}_fps"] = safe_float(row["frames_per_second"])
                        if "gb_per_second" in row:
                            metrics[f"{prefix}_gbps"] = safe_float(row["gb_per_second"])
                        if "rtf" in row:
                            metrics[f"{prefix}_rtf"] = safe_float(row["rtf"])
                        if "gpu_utilization" in row:
                            metrics[f"{prefix}_gpu_util"] = safe_float(row["gpu_utilization"])
            except (csv.Error, OSError):
                pass

        for csv_path in data_dir.glob("realtime_summary_*.csv"):
            try:
                with csv_path.open(encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        sample_rate = row.get("engine_sample_rate_hz", "")
                        rate_key = "48k" if sample_rate == "48000" else "100k"
                        prefix = f"realtime_{rate_key}"
                        if "deadline_compliance_rate" in row:
                            metrics[f"{prefix}_compliance"] = safe_float(row["deadline_compliance_rate"])
                        if "mean_latency_ms" in row:
                            metrics[f"{prefix}_mean_latency_ms"] = safe_float(row["mean_latency_ms"])
                        if "p99_latency_ms" in row:
                            metrics[f"{prefix}_p99_latency_ms"] = safe_float(row["p99_latency_ms"])
                        if "mean_jitter_ms" in row:
                            metrics[f"{prefix}_jitter_ms"] = safe_float(row["mean_jitter_ms"])
                        if "rtf" in row:
                            metrics[f"{prefix}_rtf"] = safe_float(row["rtf"])
                        if "deadline_misses" in row:
                            metrics[f"{prefix}_deadline_misses"] = safe_float(row["deadline_misses"])
            except (csv.Error, OSError):
                pass

        for csv_path in data_dir.glob("accuracy_details_*.csv"):
            try:
                with csv_path.open(encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    snr_values: list[float] = []
                    passed_count = 0
                    total_count = 0
                    for row in reader:
                        total_count += 1
                        if row.get("passed", "").lower() == "true":
                            passed_count += 1
                        snr = safe_float(row.get("snr_db"))
                        if snr is not None:
                            snr_values.append(snr)
                    if total_count > 0:
                        metrics["accuracy_pass_rate"] = passed_count / total_count
                    if snr_values:
                        metrics["accuracy_mean_snr_db"] = sum(snr_values) / len(snr_values)
                        metrics["accuracy_min_snr_db"] = min(snr_values)
            except (csv.Error, OSError):
                pass

        return metrics

    def _generate_readme(self, manifest: dict[str, Any]) -> str:
        name = manifest.get("name", "Unknown")
        source = manifest.get("source", "local")
        tag = manifest.get("tag") or "—"
        message = manifest.get("message", "No description provided")
        created = manifest.get("created", "Unknown")[:19]
        git_commit = manifest.get("git_commit", "unknown")
        git_branch = manifest.get("git_branch", "unknown")
        scope = manifest.get("scope", "standard")
        size_mb = manifest.get("size_mb", 0)

        readme = f"""# Dataset: {name}

**Created**: {created}
**Source**: {source}
**Tag**: {tag}
**Scope**: {scope} ({size_mb:.1f} MB)
**Git Commit**: {git_commit}
**Git Branch**: {git_branch}

## Description

{message}

## Contents

- `manifest.json` — dataset metadata and summary metrics
- `data/` — CSV summaries copied from `artifacts/data/`
"""

        if scope in {"standard", "full"}:
            readme += "- `mlruns/` — MLflow experiment tracking\n"
        if scope == "full":
            readme += "- `profiling/` — Nsight profiling reports\n"

        readme += f"""
## Usage

### Compare against another dataset

```bash
sigx dataset compare {name} <other-dataset>
```

### Regenerate this data

```bash
git checkout {git_commit}
sigx build --release
snakemake --cores 4 --snakefile experiments/Snakefile
```

---
*Generated by SigTekX DatasetRegistry*
"""
        return readme

    def _update_registry_manifest(self, name: str, manifest: dict[str, Any]) -> None:
        """Atomically add an entry to the top-level dataset manifest."""
        manifest_path = self.datasets_dir / ".dataset_manifest.json"
        lock_path = manifest_path.with_suffix(".json.lock")

        with FileLock(str(lock_path), timeout=10.0):
            if manifest_path.exists():
                with manifest_path.open(encoding="utf-8") as f:
                    registry = json.load(f)
            else:
                registry = {"datasets": []}

            registry["datasets"].append({
                "name": name,
                "created": manifest["created"],
                "source": manifest.get("source"),
                "tag": manifest.get("tag"),
                "scope": manifest.get("scope"),
            })

            with manifest_path.open("w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2)

    def _remove_from_registry_manifest(self, name: str) -> None:
        """Atomically remove an entry from the top-level dataset manifest."""
        manifest_path = self.datasets_dir / ".dataset_manifest.json"
        lock_path = manifest_path.with_suffix(".json.lock")

        with FileLock(str(lock_path), timeout=10.0):
            if not manifest_path.exists():
                return

            with manifest_path.open(encoding="utf-8") as f:
                registry = json.load(f)

            registry["datasets"] = [d for d in registry["datasets"] if d["name"] != name]

            with manifest_path.open("w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2)
