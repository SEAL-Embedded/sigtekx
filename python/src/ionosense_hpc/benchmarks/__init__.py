"""
Ionose H-Performance Computing (HPC) Benchmark Suite.

This module provides a collection of standardized tests for evaluating the
performance, accuracy, and stability of the signal processing engine.

The benchmarks can be run individually or as a complete suite via the CLI:
`python -m ionosense_hpc.benchmarks.suite`
"""

from .accuracy import (
    benchmark_accuracy,
    benchmark_window_accuracy,
    benchmark_numerical_stability,
)
from .latency import benchmark_latency, benchmark_jitter
from .throughput import benchmark_throughput, benchmark_batch_scaling
from .suite import run_full_suite

# Define the public API for this module
__all__ = [
    "benchmark_accuracy",
    "benchmark_window_accuracy",
    "benchmark_numerical_stability",
    "benchmark_latency",
    "benchmark_jitter",
    "benchmark_throughput",
    "benchmark_batch_scaling",
    "run_full_suite",
]

