"""MLflow logging utilities for benchmark scripts.

This module provides shared utilities for logging benchmark results to MLflow,
eliminating code duplication across benchmark runner scripts.
"""

import logging
from pathlib import Path
from typing import Any

import mlflow

logger = logging.getLogger(__name__)


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
