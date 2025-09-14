"""
Centralized paths for outputs and artifacts.

Policy:
- Default all volatile artifacts under the project build/ tree to align with RSE/RE norms.
- Allow overrides via env vars for research workflows and CI.

Environment overrides:
- IONO_OUTPUT_ROOT: root directory for all outputs (benchmarks, experiments, reports)
- IONO_BENCH_DIR: benchmark results root (overrides benchmark path only)
- IONO_EXPERIMENTS_DIR: experiments root (overrides experiments path only)
- IONO_REPORTS_DIR: reports root (overrides reports path only)
"""

from __future__ import annotations

import os
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
        return Path(env)
    return get_output_root() / "benchmark_results"


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

