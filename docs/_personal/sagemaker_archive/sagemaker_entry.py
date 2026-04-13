#!/usr/bin/env python3
"""SageMaker Processing Job entry point for SigTekX benchmarks.

This script runs inside the Docker container on a SageMaker Processing Job.
It executes a subset of benchmark experiments and writes results to the
SageMaker output directory, which gets automatically uploaded to S3.

Environment:
    /opt/ml/processing/output/ — SageMaker output directory (auto-synced to S3)

Usage (inside container):
    python sagemaker_entry.py                        # Run all demo experiments
    python sagemaker_entry.py --experiments ionosphere_test  # Run specific experiment
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# SageMaker Processing Job output directory
SAGEMAKER_OUTPUT = Path("/opt/ml/processing/output")

# Default experiments for cloud demo (ordered by runtime)
DEFAULT_EXPERIMENTS = [
    "ionosphere_test",                  # Quick validation (~1 min)
    "ionosphere_streaming",             # Core use case (~5 min)
    "baseline_batch_100k_latency",      # Methods Paper baseline (~5 min)
]


def run_benchmark(experiment: str, benchmark_type: str = "latency") -> bool:
    """Run a single benchmark experiment.

    Args:
        experiment: Hydra experiment config name.
        benchmark_type: Benchmark type (latency or throughput).

    Returns:
        True if the benchmark succeeded.
    """
    script = f"benchmarks/run_{benchmark_type}.py"
    cmd = [
        sys.executable, script,
        f"experiment={experiment}",
        f"+benchmark={benchmark_type}",
    ]

    print(f"\n{'='*60}")
    print(f"Running: {' '.join(cmd)}")
    print(f"{'='*60}\n")

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"FAILED: {experiment} (exit code {result.returncode})")
        return False

    print(f"SUCCESS: {experiment}")
    return True


def main():
    parser = argparse.ArgumentParser(description="SigTekX SageMaker benchmark runner")
    parser.add_argument(
        "--experiments",
        nargs="+",
        default=DEFAULT_EXPERIMENTS,
        help="Experiment config names to run",
    )
    args = parser.parse_args()

    # Route all output to SageMaker's output directory
    output_dir = SAGEMAKER_OUTPUT if SAGEMAKER_OUTPUT.exists() else Path("artifacts")
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ["SIGX_OUTPUT_ROOT"] = str(output_dir)

    print(f"SigTekX SageMaker Entry Point")
    print(f"Output directory: {output_dir}")
    print(f"Experiments: {args.experiments}")
    print(f"Python: {sys.version}")
    print()

    # Quick import check
    try:
        import sigtekx
        print(f"SigTekX version: {sigtekx.__version__}")
    except ImportError as e:
        print(f"ERROR: Cannot import sigtekx: {e}")
        sys.exit(1)

    # Run experiments
    results = {}
    for experiment in args.experiments:
        # Determine benchmark type from experiment name
        if "throughput" in experiment:
            benchmark_type = "throughput"
        else:
            benchmark_type = "latency"

        success = run_benchmark(experiment, benchmark_type)
        results[experiment] = "PASS" if success else "FAIL"

    # Print summary
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    for exp, status in results.items():
        print(f"  {status}: {exp}")

    failed = sum(1 for s in results.values() if s == "FAIL")
    print(f"\n{len(results) - failed}/{len(results)} experiments passed.")

    # List output files
    print(f"\nOutput files in {output_dir}:")
    for f in sorted(output_dir.rglob("*.csv")):
        print(f"  {f.relative_to(output_dir)}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
