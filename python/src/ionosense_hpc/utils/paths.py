"""
Centralized paths for outputs and artifacts.

Policy:
- Default all volatile artifacts under the project build/ tree to align with RSE/RE norms.
- Allow overrides via env vars for research workflows and CI.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


def _repo_root() -> Path:
    """Best-effort project root (directory containing pyproject.toml)."""
    cur = Path(__file__).resolve()
    for parent in [cur] + list(cur.parents):
        if (parent.parent / "pyproject.toml").exists():
            return parent.parent
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: two levels up from utils/
    return Path(__file__).resolve().parents[3]


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


def get_output_root() -> Path:
    """Root for all outputs. Defaults to <repo>/build or <repo> if build/ missing."""
    env_root = os.environ.get("IONO_OUTPUT_ROOT")
    if env_root:
        return Path(env_root)

    root = _repo_root()
    build = root / "build"
    return build if build.exists() else root


def get_benchmarks_root() -> Path:
    """Root for benchmark result directories."""
    env = os.environ.get("IONO_BENCH_DIR")
    if env:
        return _ensure(Path(env))
    root = _repo_root() / "benchmark_results"
    return _ensure(root)


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
        return Path(env)
    return get_output_root() / "experiments"


def get_reports_root() -> Path:
    """Root for top-level reports (test, lint, etc.)."""
    env = os.environ.get("IONO_REPORTS_DIR")
    if env:
        return Path(env)
    return get_output_root() / "reports"
