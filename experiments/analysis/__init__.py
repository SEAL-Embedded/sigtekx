"""
Ionosense HPC Benchmark Analysis Toolkit
==========================================

Modern analysis toolkit for GPU benchmark results with:
- Statistical rigor (confidence intervals, hypothesis testing, effect sizes)
- Interactive visualizations (Plotly + matplotlib)
- Modular architecture (plugin-based analyzers)
- Performance optimization (MD5-based caching)
- Ionosphere research focus (RTF, time/frequency resolution metrics)
"""

from .analyzer import (
    AccuracyAnalyzer,
    AnalysisEngine,
    LatencyAnalyzer,
    RealtimeAnalyzer,
    ScientificMetricsAnalyzer,
    ThroughputAnalyzer,
)
from .models import (
    BenchmarkMetadata,
    BenchmarkResult,
    BenchmarkType,
    ComparisonResult,
    ExperimentSummary,
    ScalingAnalysis,
    StatisticalMetrics,
)

__version__ = "1.0.0"

__all__ = [
    # Analysis Engine
    "AnalysisEngine",
    # Individual Analyzers
    "LatencyAnalyzer",
    "ThroughputAnalyzer",
    "AccuracyAnalyzer",
    "RealtimeAnalyzer",
    "ScientificMetricsAnalyzer",
    # Models
    "BenchmarkType",
    "StatisticalMetrics",
    "BenchmarkMetadata",
    "BenchmarkResult",
    "ComparisonResult",
    "ScalingAnalysis",
    "ExperimentSummary",
]
