"""
Enhanced GPU Pipeline Analysis Package
======================================

A comprehensive analysis system for GPU benchmark data with:
- Statistical rigor and hypothesis testing
- Modular, extensible analyzer framework
- Caching and incremental computation
- Interactive visualizations
- Publication-quality reports

Quick Start:
    from analysis import AnalysisEngine, DataLoader
    
    # Load data
    data = DataLoader.load_from_directory("artifacts/data")
    
    # Run analysis
    engine = AnalysisEngine()
    summary = engine.generate_summary(data)
    
    # Generate report
    from analysis.visualization import ReportGenerator
    report = ReportGenerator()
    report.generate_full_report(summary, Path("report.html"))
"""

from .engine import (
    AnalysisEngine,
    AnalyzerBase,
    LatencyAnalyzer,
    ThroughputAnalyzer,
    AccuracyAnalyzer,
    RealtimeAnalyzer,
    ScalingAnalyzer,
)

from .models import (
    BenchmarkType,
    BenchmarkResult,
    ComparisonResult,
    EngineConfiguration,
    ExperimentSummary,
    ScalingAnalysis,
    StatisticalMetrics,
)

from .visualization import (
    VisualizationConfig,
    StatisticalPlotter,
    PerformancePlotter,
    ReportGenerator,
)

__version__ = "2.0.0"

__all__ = [
    # Engine
    "AnalysisEngine",
    "AnalyzerBase",
    "LatencyAnalyzer",
    "ThroughputAnalyzer",
    "AccuracyAnalyzer",
    "RealtimeAnalyzer",
    "ScalingAnalyzer",
    # Models
    "BenchmarkType",
    "BenchmarkResult",
    "ComparisonResult",
    "EngineConfiguration",
    "ExperimentSummary",
    "ScalingAnalysis",
    "StatisticalMetrics",
    # Visualization
    "VisualizationConfig",
    "StatisticalPlotter",
    "PerformancePlotter",
    "ReportGenerator",
]
