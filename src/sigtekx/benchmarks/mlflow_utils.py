"""MLflow logging utilities for benchmark scripts.

This module provides shared utilities for logging benchmark results to MLflow,
eliminating code duplication across benchmark runner scripts.
"""

import logging
import random
import time
from pathlib import Path
from typing import Any

import hydra
import mlflow
from omegaconf import DictConfig

logger = logging.getLogger(__name__)


def setup_mlflow(cfg: DictConfig, max_retries: int = 5) -> None:
    """Configure MLflow tracking URI and experiment.

    Resolves relative paths to absolute using the original working directory
    (required because Hydra multirun changes CWD per job). Retries on
    transient SQLite errors (``database is locked``) that can occur when
    multiple parallel Hydra jobs access the DB concurrently.

    Note:
        The Snakefile ``onstart`` handler pre-initializes the SQLite DB
        before any rules execute, preventing Alembic migration races.
        This retry logic is a safety net for remaining lock contention.

    Args:
        cfg: Hydra DictConfig containing cfg.mlflow.tracking_uri and
             cfg.mlflow.experiment_name.
        max_retries: Maximum number of attempts before giving up.
    """
    tracking_uri = cfg.mlflow.tracking_uri
    original_cwd = hydra.utils.get_original_cwd()

    # Resolve relative paths to absolute so the URI stays stable across
    # Hydra multirun jobs that each run in a different CWD.
    if tracking_uri.startswith("sqlite:///"):
        rel = tracking_uri[len("sqlite:///"):]
        if not Path(rel).is_absolute():
            tracking_uri = "sqlite:///" + str(Path(original_cwd) / rel)
    elif tracking_uri.startswith("file:"):
        rel = tracking_uri[len("file:"):]
        if not Path(rel).is_absolute():
            tracking_uri = "file:" + str(Path(original_cwd) / rel)

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            mlflow.set_tracking_uri(tracking_uri)
            mlflow.set_experiment(cfg.mlflow.experiment_name)
            return
        except Exception as exc:  # noqa: BLE001
            # Only retry on transient SQLite errors (locked / migration race).
            err_msg = str(exc).lower()
            is_transient = "database is locked" in err_msg or "already exists" in err_msg
            if not is_transient or attempt >= max_retries - 1:
                raise
            last_exc = exc
            wait = min(0.5 * (2 ** attempt) + random.uniform(0, 0.3), 5.0)
            logger.warning(
                "MLflow init attempt %d/%d hit transient error, retrying in %.1fs: %s",
                attempt + 1, max_retries, wait, exc,
            )
            time.sleep(wait)


def log_benchmark_errors(
    result: Any,
    output_dir: Path,
    config: dict,
    error_rate_threshold: float = 0.01
) -> None:
    """Log benchmark error metrics and artifacts to MLflow.

    This function extracts error metadata from a BenchmarkResult and logs:
    - error_count (total failed iterations)
    - error_rate (percentage of failures)
    - errors_{ExceptionType} (per-type breakdown)
    - errors.txt artifact (detailed error report)

    Args:
        result: BenchmarkResult with metadata containing error information
        output_dir: Directory to save error artifacts (typically cfg.paths.data)
        config: Benchmark config dict (for iteration count in logs)
        error_rate_threshold: Warn if error rate exceeds this (default: 1% for publication quality)

    Example:
        >>> result = benchmark.run()
        >>> log_benchmark_errors(result, Path(cfg.paths.data), result.config)

    Note:
        The 1% threshold is strict for publication-quality benchmarks. This aligns
        with methods paper requirements for demonstrating reliability.
    """
    error_count = result.metadata.get('error_count', 0)
    error_rate = result.metadata.get('error_rate', 0.0)
    error_type_counts = result.metadata.get('error_type_counts', {})

    # Log metrics to MLflow
    mlflow.log_metric('error_count', error_count)
    mlflow.log_metric('error_rate', error_rate)

    # Log per-error-type breakdown (for custom stage debugging)
    for error_type, count in error_type_counts.items():
        mlflow.log_metric(f'errors_{error_type}', count)

    # Save error log as artifact if errors occurred
    if error_count > 0:
        output_dir.mkdir(parents=True, exist_ok=True)

        error_log_path = output_dir / "errors.txt"
        with open(error_log_path, 'w', encoding='utf-8') as f:
            f.write("Benchmark Error Report\n")
            f.write(f"{'=' * 60}\n\n")
            f.write(f"Total iterations: {config.get('iterations', 'N/A')}\n")
            f.write(f"Failed iterations: {error_count}\n")
            f.write(f"Error rate: {error_rate:.2%}\n\n")

            # Error type breakdown
            if error_type_counts:
                f.write("Error Type Breakdown:\n")
                f.write(f"{'-' * 60}\n")
                for error_type, count in sorted(error_type_counts.items(),
                                               key=lambda x: x[1], reverse=True):
                    f.write(f"  {error_type}: {count} ({count/error_count*100:.1f}%)\n")
                f.write("\n")

            # Error messages preview
            error_messages = result.metadata.get('error_messages_preview', [])
            if error_messages:
                f.write(f"Error Messages (first {len(error_messages)}):\n")
                f.write(f"{'-' * 60}\n")
                for i, msg in enumerate(error_messages, 1):
                    f.write(f"{i}. {msg}\n")

            # Note if more errors exist
            total_errors = len(result.metadata.get('errors', []))
            if total_errors > len(error_messages):
                f.write(f"\n(... {total_errors - len(error_messages)} more errors not shown)\n")

        mlflow.log_artifact(str(error_log_path))

        # Warn if error rate exceeds publication threshold
        if error_rate > error_rate_threshold:
            logger.warning(
                f"⚠️  Error rate exceeds publication threshold: {error_rate:.2%} "
                f"({error_count}/{config.get('iterations', 'N/A')} iterations failed)"
            )
            if error_type_counts:
                logger.warning(f"   Error types: {dict(error_type_counts)}")
