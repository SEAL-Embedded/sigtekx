"""Performance metrics and statistical analysis utilities."""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class Statistics:
    """Container for statistical measurements."""
    mean: float
    median: float
    std: float
    min: float
    max: float
    p25: float
    p50: float
    p75: float
    p95: float
    p99: float
    count: int
    
    @classmethod
    def from_data(cls, data: List[float]) -> 'Statistics':
        """Calculate statistics from raw data."""
        if not data:
            return cls(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        
        arr = np.array(data)
        return cls(
            mean=float(np.mean(arr)),
            median=float(np.median(arr)),
            std=float(np.std(arr)),
            min=float(np.min(arr)),
            max=float(np.max(arr)),
            p25=float(np.percentile(arr, 25)),
            p50=float(np.percentile(arr, 50)),
            p75=float(np.percentile(arr, 75)),
            p95=float(np.percentile(arr, 95)),
            p99=float(np.percentile(arr, 99)),
            count=len(data)
        )
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            'mean': self.mean,
            'median': self.median,
            'std': self.std,
            'min': self.min,
            'max': self.max,
            'p25': self.p25,
            'p50': self.p50,
            'p75': self.p75,
            'p95': self.p95,
            'p99': self.p99,
            'count': self.count
        }


class PerformanceMetrics:
    """Calculate and track performance metrics."""
    
    def __init__(self):
        self.latencies: List[float] = []
        self.throughputs: List[float] = []
        self.timestamps: List[float] = []
        
    def add_latency(self, latency_ms: float, timestamp: Optional[float] = None):
        """Add a latency measurement."""
        self.latencies.append(latency_ms)
        if timestamp is not None:
            self.timestamps.append(timestamp)
    
    def add_throughput(self, throughput: float):
        """Add a throughput measurement."""
        self.throughputs.append(throughput)
    
    def get_latency_stats(self) -> Statistics:
        """Get latency statistics."""
        return Statistics.from_data(self.latencies)
    
    def get_throughput_stats(self) -> Statistics:
        """Get throughput statistics."""
        return Statistics.from_data(self.throughputs)
    
    def calculate_jitter(self) -> float:
        """Calculate jitter (variance in latency)."""
        if len(self.latencies) < 2:
            return 0.0
        
        diffs = np.diff(self.latencies)
        return float(np.std(diffs))
    
    def calculate_deadline_misses(self, deadline_ms: float) -> Dict[str, Any]:
        """Calculate deadline miss statistics."""
        if not self.latencies:
            return {'count': 0, 'percentage': 0.0}
        
        misses = sum(1 for l in self.latencies if l > deadline_ms)
        return {
            'count': misses,
            'percentage': (misses / len(self.latencies)) * 100,
            'deadline_ms': deadline_ms
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        summary = {}
        
        if self.latencies:
            summary['latency'] = self.get_latency_stats().to_dict()
            summary['jitter_ms'] = self.calculate_jitter()
        
        if self.throughputs:
            summary['throughput'] = self.get_throughput_stats().to_dict()
        
        return summary


def compare_metrics(baseline: Dict[str, Any], 
                   comparison: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare two sets of metrics and calculate improvements.
    
    Args:
        baseline: Baseline metrics (e.g., CPU or no-graphs)
        comparison: Comparison metrics (e.g., GPU or with-graphs)
        
    Returns:
        Dictionary with comparison results
    """
    results = {}
    
    # Compare latencies if available
    if 'latency' in baseline and 'latency' in comparison:
        base_lat = baseline['latency']
        comp_lat = comparison['latency']
        
        results['latency_improvement'] = {
            'mean_reduction_pct': ((base_lat['mean'] - comp_lat['mean']) / base_lat['mean'] * 100) 
                                  if base_lat['mean'] > 0 else 0,
            'median_reduction_pct': ((base_lat['median'] - comp_lat['median']) / base_lat['median'] * 100)
                                   if base_lat['median'] > 0 else 0,
            'p99_reduction_pct': ((base_lat['p99'] - comp_lat['p99']) / base_lat['p99'] * 100)
                                if base_lat['p99'] > 0 else 0,
            'speedup_factor': base_lat['mean'] / comp_lat['mean'] if comp_lat['mean'] > 0 else 0
        }
    
    # Compare throughput if available
    if 'throughput' in baseline and 'throughput' in comparison:
        base_tp = baseline['throughput']
        comp_tp = comparison['throughput']
        
        results['throughput_improvement'] = {
            'mean_increase_pct': ((comp_tp['mean'] - base_tp['mean']) / base_tp['mean'] * 100)
                                if base_tp['mean'] > 0 else 0,
            'speedup_factor': comp_tp['mean'] / base_tp['mean'] if base_tp['mean'] > 0 else 0
        }
    
    # Compare jitter if available
    if 'jitter_ms' in baseline and 'jitter_ms' in comparison:
        results['jitter_reduction_pct'] = ((baseline['jitter_ms'] - comparison['jitter_ms']) / 
                                          baseline['jitter_ms'] * 100) if baseline['jitter_ms'] > 0 else 0
    
    return results


def format_metric(value: float, metric_type: str = 'time') -> str:
    """
    Format a metric value for display.
    
    Args:
        value: The metric value
        metric_type: Type of metric ('time', 'throughput', 'percentage', 'count')
        
    Returns:
        Formatted string
    """
    if metric_type == 'time':
        if value == 0:
            return "N/A"
        elif value >= 1:
            return f"{value:.3f} ms"
        else:
            return f"{value * 1000:.3f} μs"
    
    elif metric_type == 'throughput':
        if value >= 1e9:
            return f"{value/1e9:.2f} G/s"
        elif value >= 1e6:
            return f"{value/1e6:.2f} M/s"
        elif value >= 1e3:
            return f"{value/1e3:.2f} k/s"
        else:
            return f"{value:.2f} /s"
    
    elif metric_type == 'percentage':
        return f"{value:.1f}%"
    
    elif metric_type == 'count':
        return f"{value:,.0f}"
    
    else:
        return str(value)