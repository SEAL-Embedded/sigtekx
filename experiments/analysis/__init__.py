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
    AnalysisEngine,
    LatencyAnalyzer,
    ThroughputAnalyzer,
    AccuracyAnalyzer,
    RealtimeAnalyzer,
    ScientificMetricsAnalyzer,
)
from .models import (
    BenchmarkType,
    StatisticalMetrics,
    BenchmarkMetadata,
    BenchmarkResult,
    ComparisonResult,
    ScalingAnalysis,
    ExperimentSummary,
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
