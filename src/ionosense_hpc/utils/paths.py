"""
Centralized paths for outputs and artifacts.

Policy:
- Default derived artifacts under <repo>/artifacts so routine cleans preserve results.
- Allow overrides via env vars for research workflows and CI.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import pytest


def _repo_root() -> Path:

    """Find project root by searching for pyproject.toml"""

    path = Path(__file__).resolve()

    for parent in [path] + list(path.parents):
        if (parent / "pyproject.toml").exists():
            return parent

    raise FileNotFoundError(
        f"Project root not found: no project.toml in {path} or any parent directory. "
        f"Set IONO_OUTPUT_ROOT environment  variable to override"
    )

def _sanitize_component(name: str) -> str:
    """Return a filesystem safe name limited to simple characters."""
    cleaned = ''.join(ch if (ch.isalnum() or ch in ('-', '_')) else '-' for ch in name.strip())
    cleaned = cleaned.strip('-_')
    return cleaned or 'benchmark'


def _ensure(path: Path) -> Path:
    """Create path if missing and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_benchmark_name(name: str) -> str:
    """Return a sanitized benchmark name for filesystem usage."""
    return _sanitize_component(name)


ARTIFACTS_ROOT_NAME = "artifacts"


def get_artifacts_root() -> Path:
    """Root directory for long-lived artifacts."""
    env_root = os.environ.get("IONO_OUTPUT_ROOT")
    if env_root:
        return _ensure(Path(env_root))

    root = _repo_root()
    return _ensure(root / ARTIFACTS_ROOT_NAME)


def get_output_root() -> Path:
    """Alias for artifact root for backwards compatibility."""
    return get_artifacts_root()


def get_benchmarks_root() -> Path:
    """Root for benchmark result directories."""
    env = os.environ.get("IONO_BENCH_DIR")
    if env:
        return _ensure(Path(env))
    return _ensure(get_artifacts_root() / "benchmarks")


def get_benchmark_run_dir(name: str) -> Path:
    """Directory for a specific benchmark name (sanitized)."""
    safe = normalize_benchmark_name(name)
    return _ensure(get_benchmarks_root() / safe)


def get_benchmark_result_path(
    name: str,
    *,
    timestamp: datetime | None = None,
    suffix: str = "json",
) -> Path:
    """Standardized path for benchmark outputs."""
    ts = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
    safe = normalize_benchmark_name(name)
    ext = suffix.lstrip('.')
    run_dir = get_benchmark_run_dir(safe)
    return run_dir / f"{safe}_{ts}.{ext}"


def get_experiments_root() -> Path:
    """Root for research workflow experiment directories."""
    env = os.environ.get("IONO_EXPERIMENTS_DIR")
    if env:
        return _ensure(Path(env))
    return _ensure(get_artifacts_root() / "experiments")


def get_reports_root() -> Path:
    """Root for top-level reports (test, lint, etc.)."""
    env = os.environ.get("IONO_REPORTS_DIR")
    if env:
        return _ensure(Path(env))
    return _ensure(get_artifacts_root() / "reports")