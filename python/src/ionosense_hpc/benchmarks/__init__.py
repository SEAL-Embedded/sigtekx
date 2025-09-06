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

# Convenience functional benchmarks
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
from .throughput import (
    benchmark_batch_scaling,
    benchmark_throughput,
)

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
    # Functional benchmarks
    "benchmark_accuracy",
    "benchmark_window_accuracy",
    "benchmark_numerical_stability",
    "benchmark_latency",
    "benchmark_jitter",
    "benchmark_throughput",
    "benchmark_batch_scaling",
    "benchmark_realtime",
]
