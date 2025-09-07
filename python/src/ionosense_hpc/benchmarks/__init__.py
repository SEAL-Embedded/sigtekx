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
    # Functional benchmarks are available as classes in submodules
    # (accuracy, latency, throughput, realtime), but are not imported here
    # to keep package import light and avoid optional dependency issues.
]
