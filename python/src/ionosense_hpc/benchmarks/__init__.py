"""
Ionosense-HPC Benchmarking Suite.

This module provides a collection of scripts for performance, accuracy,
and stability testing of the signal processing engine.

Each benchmark can be run as a standalone script or imported as a function.
The main entry point for the full suite is the `suite` module.
"""

from .accuracy import (
    benchmark_accuracy,
    benchmark_numerical_stability,
    benchmark_window_accuracy,
)
from .latency import (
    benchmark_jitter,
    benchmark_latency,
)
from .realtime import benchmark_realtime
from .suite import run_full_suite
from .throughput import (
    benchmark_batch_scaling,
    benchmark_throughput,
)

# __all__ defines the public API for the benchmarks module.
__all__ = [
    "benchmark_accuracy",
    "benchmark_window_accuracy",
    "benchmark_numerical_stability",
    "benchmark_latency",
    "benchmark_jitter",
    "benchmark_throughput",
    "benchmark_batch_scaling",
    "benchmark_realtime",
    "run_full_suite",
]