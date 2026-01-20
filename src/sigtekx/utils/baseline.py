"""Baseline management for persistent experiment snapshots.

PERSISTENT BASELINE STORAGE
────────────────────────────
Provides snapshot archiving for regression tracking across development phases.
Baselines survive `sigx clean` and are manually managed in baselines/ directory.

ARCHITECTURE: TWO-TIER EXPERIMENT TRACKING
───────────────────────────────────────────
SigTekX uses different tools for different experiment lifespans:

┌─────────────────────────────────────────────────────────────────┐
│ Tier 1: EPHEMERAL EXPERIMENTS (artifacts/)                      │
│ ────────────────────────────────────────────────────────────── │
│ Purpose:  Day-to-day development, fast iteration               │
│ Tools:    MLflow + CSV files                                   │
│ Deleted:  `sigx clean` wipes artifacts/                        │
│ Lifespan: Days/weeks (regenerated from code)                   │
│                                                                 │
│ MLflow provides:                                                │
│   - Experiment tracking with web UI                            │
│   - Parameter and metric storage                               │
│   - Run history and comparison                                 │
│   - Artifact management                                         │
│                                                                 │
│ CSV provides:                                                   │
│   - Dashboard data (Streamlit)                                 │
│   - Unique filenames prevent race conditions                   │
│   - Pandas-friendly analysis                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Tier 2: PERSISTENT BASELINES (baselines/)                      │
│ ────────────────────────────────────────────────────────────── │
│ Purpose:  Regression tracking, phase milestones                │
│ Tools:    BaselineManager (this module)                        │
│ Survives: `sigx clean` does NOT delete baselines/              │
│ Lifespan: Months/years (manually managed)                      │
│                                                                 │
│ BaselineManager provides:                                       │
│   - Explicit snapshot tagging (pre/post phase)                 │
│   - Statistical comparison between baselines                   │
│   - Git commit tracking                                         │
│   - Phase-aligned organization                                  │
└─────────────────────────────────────────────────────────────────┘

USAGE EXAMPLE
─────────────
    # 1. Run benchmarks
    python benchmarks/run_latency.py +benchmark=latency

    # 2. Save baseline before Phase 1 work
    sigx baseline save pre-phase1 --phase 1 --message "Before zero-copy"

    # 3. Clean artifacts (baselines/ survives!)
    sigx clean

    # 4. Do Phase 1 work, run benchmarks again
    # ... code changes ...
    python benchmarks/run_latency.py +benchmark=latency

    # 5. Save new baseline
    sigx baseline save post-phase1 --phase 1 --message "After zero-copy"

    # 6. Compare (statistical regression analysis)
    sigx baseline compare pre-phase1 post-phase1

CONCURRENCY SAFETY
──────────────────
Manifest operations (_update_manifest, _remove_from_manifest) use file locking
to prevent race conditions during concurrent baseline operations.

See: docs/benchmarking/experiment-logging-system.md
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock

__all__ = ["BaselineManager"]


class BaselineManager:
    """Manage experiment baselines for regression tracking and phase comparisons.

    Baselines are stored in baselines/ directory (repo root, not gitignored).
    Each baseline contains:
    - metadata.json: Baseline info, git state, metrics
    - data/: CSV summaries from artifacts/data/
    - mlruns/: MLflow tracking (optional, scope=standard/full)
    - README.md: Human-readable summary

    Scope options:
    - minimal: CSV only (~1MB)
    - standard: CSV + MLflow (~41MB, default)
    - full: CSV + MLflow + Parquet + profiling (~100MB+)
    """

    def __init__(self, baselines_dir: Path | None = None):
        """Initialize baseline manager.

        Args:
            baselines_dir: Custom baselines directory. If None, uses repo_root/baselines/
        """
        if baselines_dir is None:
            # Default: repo root / baselines/
            repo_root = self._find_repo_root()
            self.baselines_dir = repo_root / "baselines"
        else:
            self.baselines_dir = Path(baselines_dir)

        # Ensure baselines directory exists
        self.baselines_dir.mkdir(parents=True, exist_ok=True)

        # Artifacts source directory
        repo_root = self._find_repo_root()
        self.artifacts_dir = repo_root / "artifacts"

    def save_baseline(
        self,
        name: str,
        phase: int | None = None,
        scope: str = "standard",
        message: str = ""
    ) -> Path:
        """Save current artifacts as a baseline.

        Args:
            name: Baseline name (e.g., "pre-phase1", "post-phase1")
            phase: Optional phase number (1-4)
            scope: Archive scope - "minimal", "standard" (default), or "full"
            message: Description of this baseline

        Returns:
            Path to saved baseline directory

        Raises:
            FileNotFoundError: If artifacts/data/ doesn't exist
            ValueError: If baseline name already exists
        """
        # Validate artifacts exist
        artifacts_data_dir = self.artifacts_dir / "data"
        if not artifacts_data_dir.exists():
            raise FileNotFoundError(
                f"No artifacts found at {artifacts_data_dir}. "
                "Run benchmarks first: snakemake --cores 4"
            )

        # Check if baseline already exists
        baseline_dir = self.baselines_dir / name
        if baseline_dir.exists():
            raise ValueError(
                f"Baseline '{name}' already exists at {baseline_dir}. "
                "Use a different name or delete the existing baseline first."
            )

        # Create baseline directory
        baseline_dir.mkdir(parents=True, exist_ok=True)

        # Copy artifacts based on scope
        if scope in ["minimal", "standard", "full"]:
            # All scopes include CSV summaries
            data_dest = baseline_dir / "data"
            shutil.copytree(artifacts_data_dir, data_dest)

        if scope in ["standard", "full"]:
            # Standard and full include MLflow tracking
            mlruns_src = self.artifacts_dir / "mlruns"
            if mlruns_src.exists():
                mlruns_dest = baseline_dir / "mlruns"
                shutil.copytree(mlruns_src, mlruns_dest)

        if scope == "full":
            # Full scope includes profiling data
            profiling_src = self.artifacts_dir / "profiling"
            if profiling_src.exists():
                profiling_dest = baseline_dir / "profiling"
                shutil.copytree(profiling_src, profiling_dest)

        # Generate metadata
        metadata = self._create_metadata(name, phase, scope, message, baseline_dir)

        # Save metadata.json
        metadata_path = baseline_dir / "metadata.json"
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        # Generate README.md
        readme_content = self._generate_readme(metadata)
        readme_path = baseline_dir / "README.md"
        with readme_path.open("w", encoding="utf-8") as f:
            f.write(readme_content)

        # Update global baseline manifest
        self._update_manifest(name, metadata)

        return baseline_dir

    def load_baseline_metadata(self, name: str) -> dict[str, Any] | None:
        """Load metadata for a baseline.

        Args:
            name: Baseline name

        Returns:
            Metadata dict or None if not found
        """
        baseline_dir = self.baselines_dir / name
        metadata_path = baseline_dir / "metadata.json"

        if not metadata_path.exists():
            return None

        with metadata_path.open(encoding="utf-8") as f:
            return json.load(f)

    def list_baselines(self, phase_filter: int | None = None) -> list[dict[str, Any]]:
        """List all saved baselines.

        Args:
            phase_filter: Optional filter by phase number

        Returns:
            List of baseline metadata dicts
        """
        baselines = []

        # Scan baselines directory
        for baseline_dir in self.baselines_dir.iterdir():
            if not baseline_dir.is_dir():
                continue

            # Load metadata
            metadata = self.load_baseline_metadata(baseline_dir.name)
            if metadata:
                # Apply phase filter if specified
                if phase_filter is not None:
                    if metadata.get('phase') != phase_filter:
                        continue

                baselines.append(metadata)

        # Sort by creation time (newest first)
        baselines.sort(key=lambda x: x.get('created', ''), reverse=True)

        return baselines

    def compare_baselines(self, name1: str, name2: str) -> dict[str, Any]:
        """Compare two baselines.

        Args:
            name1: First baseline name
            name2: Second baseline name

        Returns:
            Comparison results dict with keys:
            - baseline1: metadata dict for first baseline
            - baseline2: metadata dict for second baseline
            - metrics: dict mapping metric name to comparison data
                {value1, value2, delta, pct_change}
            - summary: overall comparison summary

        Raises:
            FileNotFoundError: If either baseline doesn't exist
        """
        # Load metadata for both baselines
        metadata1 = self.load_baseline_metadata(name1)
        metadata2 = self.load_baseline_metadata(name2)

        if metadata1 is None:
            raise FileNotFoundError(f"Baseline '{name1}' not found")
        if metadata2 is None:
            raise FileNotFoundError(f"Baseline '{name2}' not found")

        # RE-EXTRACT metrics from saved CSV files (future-proof, backward compatible)
        # This ensures old baselines get new metrics and CSV changes are automatically reflected
        baseline1_dir = self.baselines_dir / name1
        baseline2_dir = self.baselines_dir / name2

        metrics1 = self._extract_metrics(baseline1_dir / "data") if (baseline1_dir / "data").exists() else {}
        metrics2 = self._extract_metrics(baseline2_dir / "data") if (baseline2_dir / "data").exists() else {}

        # Compare metrics
        metrics_comparison = {}
        all_metric_keys = set(metrics1.keys()) | set(metrics2.keys())

        for key in all_metric_keys:
            val1 = metrics1.get(key)
            val2 = metrics2.get(key)

            if val1 is not None and val2 is not None:
                delta = val2 - val1
                pct_change = (delta / val1 * 100) if val1 != 0 else 0.0
                metrics_comparison[key] = {
                    'value1': val1,
                    'value2': val2,
                    'delta': delta,
                    'pct_change': pct_change
                }
            elif val1 is not None:
                metrics_comparison[key] = {
                    'value1': val1,
                    'value2': None,
                    'delta': None,
                    'pct_change': None
                }
            else:
                metrics_comparison[key] = {
                    'value1': None,
                    'value2': val2,
                    'delta': None,
                    'pct_change': None
                }

        return {
            'baseline1': metadata1,
            'baseline2': metadata2,
            'metrics': metrics_comparison,
            'summary': {
                'baseline1_name': name1,
                'baseline2_name': name2,
                'baseline1_phase': metadata1.get('phase'),
                'baseline2_phase': metadata2.get('phase'),
                'baseline1_created': metadata1.get('created'),
                'baseline2_created': metadata2.get('created'),
            }
        }

    def delete_baseline(self, name: str, force: bool = False) -> bool:
        """Delete a baseline.

        Args:
            name: Baseline name
            force: Skip confirmation if True (confirmation handled by CLI)

        Returns:
            True if deleted successfully

        Raises:
            FileNotFoundError: If baseline doesn't exist
        """
        baseline_dir = self.baselines_dir / name

        if not baseline_dir.exists():
            raise FileNotFoundError(f"Baseline '{name}' not found at {baseline_dir}")

        # Delete baseline directory
        shutil.rmtree(baseline_dir)

        # Update global manifest
        self._remove_from_manifest(name)

        return True

    def export_baseline(self, name: str, destination: Path, format: str = "zip") -> Path:
        """Export baseline as archive (Phase 2 feature - stub for now).

        Args:
            name: Baseline name
            destination: Destination directory
            format: Archive format ("zip" or "tar")

        Returns:
            Path to exported archive

        Raises:
            NotImplementedError: This is a Phase 2 feature
        """
        raise NotImplementedError(
            "Baseline export is a Phase 2 feature. "
            "Current MVP includes save and list only."
        )

    # ========== Private Helper Methods ==========

    def _find_repo_root(self) -> Path:
        """Find repository root directory.

        Returns:
            Path to repository root

        Raises:
            RuntimeError: If not in a git repository
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True
            )
            return Path(result.stdout.strip())
        except subprocess.CalledProcessError:
            # Fallback: assume this file is in src/sigtekx/utils/
            # Go up 3 levels: utils -> sigtekx -> src -> repo_root
            return Path(__file__).parent.parent.parent.parent

    def _create_metadata(
        self,
        name: str,
        phase: int | None,
        scope: str,
        message: str,
        baseline_dir: Path
    ) -> dict[str, Any]:
        """Create baseline metadata.

        Args:
            name: Baseline name
            phase: Phase number (1-4) or None
            scope: Archive scope
            message: User-provided description
            baseline_dir: Path to baseline directory

        Returns:
            Metadata dictionary
        """
        # Get git info
        git_commit, git_branch = self._get_git_info()

        # Calculate size
        size_mb = self._calculate_directory_size(baseline_dir)

        # Extract key metrics from CSV summaries
        metrics = self._extract_metrics(baseline_dir / "data")

        # Get hardware info
        hardware_info = self._get_hardware_info()

        # Build metadata
        metadata = {
            "name": name,
            "phase": phase,
            "scope": scope,
            "message": message,
            "created": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit,
            "git_branch": git_branch,
            "size_mb": size_mb,
            "hardware": hardware_info,
            "metrics": metrics
        }

        return metadata

    def _get_hardware_info(self) -> dict[str, Any]:
        """Get hardware and system information.

        Returns:
            Dictionary with GPU, CPU, RAM, OS info
        """
        import platform
        import psutil

        hardware = {
            "os": platform.system(),
            "os_version": platform.version(),
            "cpu": platform.processor(),
            "cpu_cores": psutil.cpu_count(logical=False),
            "cpu_threads": psutil.cpu_count(logical=True),
            "ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        }

        # Try to get GPU info
        try:
            import torch
            if torch.cuda.is_available():
                hardware["gpu_count"] = torch.cuda.device_count()
                hardware["gpu_name"] = torch.cuda.get_device_name(0)
                hardware["cuda_version"] = torch.version.cuda

                # Get GPU memory
                props = torch.cuda.get_device_properties(0)
                hardware["gpu_memory_gb"] = round(props.total_memory / (1024**3), 2)
                hardware["gpu_compute_capability"] = f"{props.major}.{props.minor}"
            else:
                hardware["gpu_available"] = False
        except (ImportError, RuntimeError):
            hardware["gpu_available"] = False

        # Try to get NVIDIA driver version
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                check=True
            )
            hardware["nvidia_driver"] = result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        return hardware

    def _get_git_info(self) -> tuple[str, str]:
        """Get current git commit and branch.

        Returns:
            Tuple of (commit_hash, branch_name)
        """
        try:
            # Get commit hash
            commit_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )
            commit = commit_result.stdout.strip()

            # Get branch name
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=True
            )
            branch = branch_result.stdout.strip()

            return commit, branch

        except subprocess.CalledProcessError:
            return "unknown", "unknown"

    def _calculate_directory_size(self, path: Path) -> float:
        """Calculate directory size in MB.

        Args:
            path: Directory path

        Returns:
            Size in megabytes
        """
        total_size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
        return total_size / (1024 * 1024)  # Convert to MB

    def _extract_metrics(self, data_dir: Path) -> dict[str, Any]:
        """Extract comprehensive metrics from CSV summaries.

        Args:
            data_dir: Path to data directory with CSV files

        Returns:
            Dictionary of key metrics organized by benchmark type and configuration
        """
        metrics = {}
        import csv

        # Helper to safely extract float
        def safe_float(value):
            try:
                return float(value) if value else None
            except (ValueError, TypeError):
                return None

        # Extract LATENCY metrics (organized by sample rate and mode)
        for csv_path in data_dir.glob("latency_summary_*.csv"):
            try:
                with csv_path.open(encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        sample_rate = row.get('engine_sample_rate_hz', '')
                        mode = row.get('engine_mode', '')

                        # Create hierarchical key: latency_48k_streaming_mean_us
                        rate_key = '48k' if sample_rate == '48000' else '100k'
                        prefix = f"latency_{rate_key}_{mode}"

                        if 'mean_latency_us' in row:
                            metrics[f"{prefix}_mean_us"] = safe_float(row['mean_latency_us'])
                        if 'p95_latency_us' in row:
                            metrics[f"{prefix}_p95_us"] = safe_float(row['p95_latency_us'])
                        if 'p99_latency_us' in row:
                            metrics[f"{prefix}_p99_us"] = safe_float(row['p99_latency_us'])
            except (csv.Error, OSError):
                pass

        # Extract THROUGHPUT metrics
        for csv_path in data_dir.glob("throughput_summary_*.csv"):
            try:
                with csv_path.open(encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        sample_rate = row.get('engine_sample_rate_hz', '')
                        mode = row.get('engine_mode', '')

                        rate_key = '48k' if sample_rate == '48000' else '100k'
                        prefix = f"throughput_{rate_key}_{mode}"

                        if 'frames_per_second' in row:
                            metrics[f"{prefix}_fps"] = safe_float(row['frames_per_second'])
                        if 'gb_per_second' in row:
                            metrics[f"{prefix}_gbps"] = safe_float(row['gb_per_second'])
                        if 'rtf' in row:
                            metrics[f"{prefix}_rtf"] = safe_float(row['rtf'])
                        if 'gpu_utilization' in row:
                            metrics[f"{prefix}_gpu_util"] = safe_float(row['gpu_utilization'])
            except (csv.Error, OSError):
                pass

        # Extract REALTIME metrics
        for csv_path in data_dir.glob("realtime_summary_*.csv"):
            try:
                with csv_path.open(encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        sample_rate = row.get('engine_sample_rate_hz', '')
                        rate_key = '48k' if sample_rate == '48000' else '100k'
                        prefix = f"realtime_{rate_key}"

                        if 'deadline_compliance_rate' in row:
                            metrics[f"{prefix}_compliance"] = safe_float(row['deadline_compliance_rate'])
                        if 'mean_latency_ms' in row:
                            metrics[f"{prefix}_mean_latency_ms"] = safe_float(row['mean_latency_ms'])
                        if 'p99_latency_ms' in row:
                            metrics[f"{prefix}_p99_latency_ms"] = safe_float(row['p99_latency_ms'])
                        if 'mean_jitter_ms' in row:
                            metrics[f"{prefix}_jitter_ms"] = safe_float(row['mean_jitter_ms'])
                        if 'rtf' in row:
                            metrics[f"{prefix}_rtf"] = safe_float(row['rtf'])
                        if 'deadline_misses' in row:
                            metrics[f"{prefix}_deadline_misses"] = safe_float(row['deadline_misses'])
            except (csv.Error, OSError):
                pass

        # Extract ACCURACY metrics
        for csv_path in data_dir.glob("accuracy_details_*.csv"):
            try:
                with csv_path.open(encoding="utf-8") as f:
                    reader = csv.DictReader(f)

                    # Aggregate across signal types
                    snr_values = []
                    passed_count = 0
                    total_count = 0

                    for row in reader:
                        total_count += 1
                        if row.get('passed', '').lower() == 'true':
                            passed_count += 1

                        snr = safe_float(row.get('snr_db'))
                        if snr is not None:
                            snr_values.append(snr)

                    if total_count > 0:
                        metrics['accuracy_pass_rate'] = passed_count / total_count
                    if snr_values:
                        metrics['accuracy_mean_snr_db'] = sum(snr_values) / len(snr_values)
                        metrics['accuracy_min_snr_db'] = min(snr_values)
            except (csv.Error, OSError):
                pass

        return metrics

    def _generate_readme(self, metadata: dict[str, Any]) -> str:
        """Generate README content for baseline.

        Args:
            metadata: Baseline metadata

        Returns:
            README markdown content
        """
        name = metadata.get('name', 'Unknown')
        phase = metadata.get('phase', 'N/A')
        message = metadata.get('message', 'No description provided')
        created = metadata.get('created', 'Unknown')[:19]  # Trim timestamp
        git_commit = metadata.get('git_commit', 'unknown')
        git_branch = metadata.get('git_branch', 'unknown')
        scope = metadata.get('scope', 'standard')
        size_mb = metadata.get('size_mb', 0)

        readme = f"""# Baseline: {name}

**Created**: {created}
**Phase**: {phase}
**Scope**: {scope} ({size_mb:.1f} MB)
**Git Commit**: {git_commit}
**Git Branch**: {git_branch}

## Description

{message}

## Contents

- `metadata.json` - Baseline metadata and metrics
- `data/` - CSV summaries from artifacts/data/
"""

        if scope in ["standard", "full"]:
            readme += "- `mlruns/` - MLflow experiment tracking\n"

        if scope == "full":
            readme += "- `profiling/` - Nsight profiling reports\n"

        readme += """
## Usage

### Compare with Current State

```bash
# Run current benchmarks
snakemake --cores 4 --snakefile experiments/Snakefile

# Compare (Phase 1 feature - coming soon)
sigx baseline compare """ + name + """ <current_baseline>
```

### Load This Baseline

```bash
sigx baseline load """ + name + """
```

### Regenerate This Data

```bash
# Checkout git commit
git checkout """ + git_commit + """

# Rebuild and re-run benchmarks
sigx build --release
snakemake --cores 4 --snakefile experiments/Snakefile
```

---
*Generated by SigTekX Baseline Management System*
"""

        return readme

    def _update_manifest(self, name: str, metadata: dict[str, Any]) -> None:
        """Atomically update baseline manifest to avoid concurrent write loss.

        Args:
            name: Baseline name
            metadata: Baseline metadata
        """
        manifest_path = self.baselines_dir / ".baseline_manifest.json"
        lock_path = manifest_path.with_suffix(".json.lock")

        with FileLock(str(lock_path), timeout=10.0):
            # Load existing manifest (inside lock)
            if manifest_path.exists():
                with manifest_path.open(encoding="utf-8") as f:
                    manifest = json.load(f)
            else:
                manifest = {"baselines": []}

            # Add new baseline (inside lock)
            manifest["baselines"].append({
                "name": name,
                "created": metadata["created"],
                "phase": metadata.get("phase"),
                "scope": metadata.get("scope"),
            })

            # Save manifest (inside lock)
            with manifest_path.open("w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

    def _remove_from_manifest(self, name: str) -> None:
        """Atomically remove baseline from manifest to avoid concurrent write loss.

        Args:
            name: Baseline name to remove
        """
        manifest_path = self.baselines_dir / ".baseline_manifest.json"
        lock_path = manifest_path.with_suffix(".json.lock")

        with FileLock(str(lock_path), timeout=10.0):
            # Early exit if manifest doesn't exist (inside lock for consistency)
            if not manifest_path.exists():
                return  # No manifest to update

            # Load existing manifest (inside lock)
            with manifest_path.open(encoding="utf-8") as f:
                manifest = json.load(f)

            # Remove baseline from list (inside lock)
            manifest["baselines"] = [
                b for b in manifest["baselines"] if b["name"] != name
            ]

            # Save updated manifest (inside lock)
            with manifest_path.open("w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
