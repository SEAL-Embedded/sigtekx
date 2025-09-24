"""
Ionosense-HPC Benchmarking package.

This module exposes the core benchmarking primitives and lazily loads
individual benchmark implementations. Legacy suite/sweep orchestration has
been removed in favour of the Hydra/Snakemake workflow introduced in 0.9.1.
"""

from .base import (
    BaseBenchmark,
    BenchmarkConfig,
    BenchmarkContext,
    BenchmarkResult,
    calculate_statistics,
    load_benchmark_config,
    save_benchmark_results,
)


def get_latency_benchmark():
    from .latency import LatencyBenchmark, StreamingLatencyBenchmark
    return LatencyBenchmark, StreamingLatencyBenchmark


def get_throughput_benchmark():
    from .throughput import MemoryStressBenchmark, ScalingBenchmark, ThroughputBenchmark
    return ThroughputBenchmark, ScalingBenchmark, MemoryStressBenchmark


def get_accuracy_benchmark():
    from .accuracy import AccuracyBenchmark
    return AccuracyBenchmark


def get_realtime_benchmark():
    from .realtime import RealtimeBenchmark
    return RealtimeBenchmark


__all__ = [
    "BaseBenchmark",
    "BenchmarkConfig",
    "BenchmarkContext",
    "BenchmarkResult",
    "calculate_statistics",
    "load_benchmark_config",
    "save_benchmark_results",
    "get_latency_benchmark",
    "get_throughput_benchmark",
    "get_accuracy_benchmark",
    "get_realtime_benchmark",
]
