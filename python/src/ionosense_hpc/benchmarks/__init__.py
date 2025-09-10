"""
Ionosense-HPC Benchmarking Suite package.

Public API re-exports the core benchmarking primitives and convenience
functions while keeping submodules importable directly.
"""

# Core primitives and utilities
from .base import (
    BaseBenchmark,
    BenchmarkConfig,
    BenchmarkContext,
    BenchmarkResult,
    calculate_statistics,
    load_benchmark_config,
    save_benchmark_results,
)

# Suite orchestration
from .suite import (
    BenchmarkSuite,
    SuiteConfig,
    run_default_suite,
)

# Parameter sweeps
from .sweep import (
    ExperimentConfig,
    ExperimentRun,
    ParameterSpec,
    ParameterSweep,
)

# Lazy loaders for benchmark classes (avoid heavy imports at module import time)
def get_latency_benchmark():
    from .latency import LatencyBenchmark, StreamingLatencyBenchmark
    return LatencyBenchmark, StreamingLatencyBenchmark


def get_throughput_benchmark():
    from .throughput import ThroughputBenchmark, ScalingBenchmark, MemoryStressBenchmark
    return ThroughputBenchmark, ScalingBenchmark, MemoryStressBenchmark


def get_accuracy_benchmark():
    from .accuracy import AccuracyBenchmark
    return AccuracyBenchmark


def get_realtime_benchmark():
    from .realtime import RealtimeBenchmark
    return RealtimeBenchmark

__all__ = [
    # Core primitives
    "BaseBenchmark",
    "BenchmarkConfig",
    "BenchmarkContext",
    "BenchmarkResult",
    "calculate_statistics",
    "load_benchmark_config",
    "save_benchmark_results",
    # Suite
    "BenchmarkSuite",
    "SuiteConfig",
    "run_default_suite",
    # Sweep
    "ExperimentConfig",
    "ExperimentRun",
    "ParameterSpec",
    "ParameterSweep",
    # Lazy loaders for benchmark classes
    "get_latency_benchmark",
    "get_throughput_benchmark",
    "get_accuracy_benchmark",
    "get_realtime_benchmark",
]
