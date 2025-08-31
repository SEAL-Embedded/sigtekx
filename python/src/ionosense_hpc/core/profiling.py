"""
ionosense_hpc.core.profiling: Performance profiling and statistics.

Provides integration with NVIDIA profiling tools and performance metrics
tracking for research and optimization.
"""

from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional, Dict, Any
import time

# NVTX integration for Nsight Systems profiling
try:
    import nvtx
    NVTX_AVAILABLE = True
except ImportError:
    NVTX_AVAILABLE = False


@dataclass
class PipelineStats:
    """
    Performance statistics from the pipeline engine.
    
    Attributes:
        total_executions: Total number of FFT operations executed.
        avg_latency_ms: Average latency in milliseconds.
        min_latency_ms: Minimum observed latency.
        max_latency_ms: Maximum observed latency.
        throughput_per_sec: Operations per second.
    """
    total_executions: int = 0
    avg_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0
    throughput_per_sec: float = 0.0
    
    @classmethod
    def _from_cpp(cls, cpp_stats) -> PipelineStats:
        """Create from C++ PipelineStats object."""
        return cls(
            total_executions=cpp_stats.total_executions,
            avg_latency_ms=cpp_stats.avg_latency_ms,
            min_latency_ms=cpp_stats.min_latency_ms,
            max_latency_ms=cpp_stats.max_latency_ms,
            throughput_per_sec=cpp_stats.throughput_per_sec()
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'total_executions': self.total_executions,
            'avg_latency_ms': self.avg_latency_ms,
            'min_latency_ms': self.min_latency_ms,
            'max_latency_ms': self.max_latency_ms,
            'throughput_per_sec': self.throughput_per_sec,
            'avg_latency_us': self.avg_latency_ms * 1000,
        }
    
    def __str__(self) -> str:
        """Human-readable statistics summary."""
        if self.total_executions == 0:
            return "PipelineStats: No executions yet"
        
        return (
            f"PipelineStats:\n"
            f"  Executions: {self.total_executions:,}\n"
            f"  Throughput: {self.throughput_per_sec:,.1f} ops/sec\n"
            f"  Latency (ms): avg={self.avg_latency_ms:.3f}, "
            f"min={self.min_latency_ms:.3f}, max={self.max_latency_ms:.3f}"
        )


@contextmanager
def nvtx_range(name: str, color: str = "blue"):
    """
    Context manager for NVTX profiling ranges.
    
    Creates labeled ranges visible in Nsight Systems for identifying
    performance bottlenecks.
    
    Args:
        name: Label for the profiling range.
        color: Color in Nsight timeline (name or ARGB hex).
    
    Example:
        >>> with nvtx_range("DataPrep"):
        ...     prepare_data()
    """
    if NVTX_AVAILABLE:
        with nvtx.annotate(message=name, color=color):
            yield
    else:
        yield


@contextmanager
def time_section(name: str) -> float:
    """
    Simple timing context manager for CPU sections.
    
    Args:
        name: Section name for logging.
    
    Yields:
        Elapsed time in seconds.
    
    Example:
        >>> with time_section("Processing") as elapsed:
        ...     process_data()
        >>> print(f"Took {elapsed():.3f} seconds")
    """
    start = time.perf_counter()
    elapsed_fn = lambda: time.perf_counter() - start
    
    try:
        yield elapsed_fn
    finally:
        if name:
            elapsed = elapsed_fn()
            print(f"[{name}] {elapsed*1000:.3f} ms")


class PerformanceMonitor:
    """
    Accumulates performance metrics across multiple runs.
    
    Useful for benchmarking and statistical analysis of performance.
    """
    
    def __init__(self, name: str = "Monitor"):
        """Initialize a new performance monitor."""
        self.name = name
        self.timings: list[float] = []
        self.markers: Dict[str, float] = {}
    
    def record(self, value: float, unit: str = "ms") -> None:
        """Record a timing measurement."""
        # Convert to ms for consistency
        if unit == "us":
            value = value / 1000.0
        elif unit == "s":
            value = value * 1000.0
        self.timings.append(value)
    
    def mark(self, label: str) -> None:
        """Mark a specific point in time."""
        self.markers[label] = time.perf_counter()
    
    def get_stats(self) -> Dict[str, float]:
        """Calculate statistics from recorded timings."""
        if not self.timings:
            return {}
        
        import numpy as np
        arr = np.array(self.timings)
        
        return {
            'count': len(self.timings),
            'mean_ms': float(np.mean(arr)),
            'std_ms': float(np.std(arr)),
            'min_ms': float(np.min(arr)),
            'max_ms': float(np.max(arr)),
            'median_ms': float(np.median(arr)),
            'p95_ms': float(np.percentile(arr, 95)),
            'p99_ms': float(np.percentile(arr, 99)),
        }
    
    def reset(self) -> None:
        """Clear all recorded data."""
        self.timings.clear()
        self.markers.clear()