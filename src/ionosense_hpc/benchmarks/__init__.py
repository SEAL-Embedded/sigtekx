"""
Ionosense-HPC Benchmarking package.

This module exposes the core benchmarking primitives and lazily loads
individual benchmark implementations. Legacy suite/sweep orchestration has
been removed in favour of the Hydra/Snakemake workflow introduced in 0.9.1.
"""

from importlib import import_module
from typing import Any, TYPE_CHECKING

from .base import (
    BaseBenchmark,
    BenchmarkConfig,
    BenchmarkContext,
    BenchmarkResult,
    calculate_statistics,
    load_benchmark_config,
    save_benchmark_results,
)

if TYPE_CHECKING:
    from .accuracy import AccuracyBenchmark, AccuracyBenchmarkConfig
    from .latency import (
        LatencyBenchmark,
        LatencyBenchmarkConfig,
        StreamingLatencyBenchmark,
    )
    from .realtime import RealtimeBenchmark, RealtimeBenchmarkConfig
    from .throughput import (
        MemoryStressBenchmark,
        ScalingBenchmark,
        ThroughputBenchmark,
        ThroughputBenchmarkConfig,
    )

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "LatencyBenchmark": ("latency", "LatencyBenchmark"),
    "LatencyBenchmarkConfig": ("latency", "LatencyBenchmarkConfig"),
    "StreamingLatencyBenchmark": ("latency", "StreamingLatencyBenchmark"),
    "ThroughputBenchmark": ("throughput", "ThroughputBenchmark"),
    "ThroughputBenchmarkConfig": ("throughput", "ThroughputBenchmarkConfig"),
    "ScalingBenchmark": ("throughput", "ScalingBenchmark"),
    "MemoryStressBenchmark": ("throughput", "MemoryStressBenchmark"),
    "AccuracyBenchmark": ("accuracy", "AccuracyBenchmark"),
    "AccuracyBenchmarkConfig": ("accuracy", "AccuracyBenchmarkConfig"),
    "RealtimeBenchmark": ("realtime", "RealtimeBenchmark"),
    "RealtimeBenchmarkConfig": ("realtime", "RealtimeBenchmarkConfig"),
}


def _load_export(module: str, attr: str) -> Any:
    module_obj = import_module(f"{__name__}.{module}")
    return getattr(module_obj, attr)


def __getattr__(name: str) -> Any:
    """Lazy-load benchmark implementations when accessed as attributes."""
    if name in _LAZY_EXPORTS:
        module, attr = _LAZY_EXPORTS[name]
        obj = _load_export(module, attr)
        globals()[name] = obj
        return obj
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


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
    "LatencyBenchmark",
    "LatencyBenchmarkConfig",
    "StreamingLatencyBenchmark",
    "ThroughputBenchmark",
    "ThroughputBenchmarkConfig",
    "ScalingBenchmark",
    "MemoryStressBenchmark",
    "AccuracyBenchmark",
    "AccuracyBenchmarkConfig",
    "RealtimeBenchmark",
    "RealtimeBenchmarkConfig",
    "get_latency_benchmark",
    "get_throughput_benchmark",
    "get_accuracy_benchmark",
    "get_realtime_benchmark",
]
