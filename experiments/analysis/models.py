"""
Enhanced Analysis Pipeline - Core Data Models
==============================================

Structured data models for GPU benchmark results with validation,
statistical metadata, and comparison capabilities.

Key Fix: Imports EngineConfig from core instead of duplicating the model.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, field_validator

# Import EngineConfig from core to avoid duplication
from ionosense_hpc.config import EngineConfig


class BenchmarkType(str, Enum):
    """Supported benchmark types."""
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    ACCURACY = "accuracy"
    REALTIME = "realtime"
    MEMORY = "memory"
    POWER = "power"


class StatisticalMetrics(BaseModel):
    """Comprehensive statistical metrics for a measurement series."""

    mean: float
    median: float
    std: float
    variance: float
    min: float
    max: float
    q1: float  # 25th percentile
    q3: float  # 75th percentile
    p5: float  # 5th percentile
    p95: float  # 95th percentile
    p99: float  # 99th percentile
    iqr: float  # Interquartile range
    cv: float  # Coefficient of variation
    skewness: float | None = None
    kurtosis: float | None = None
    n_samples: int
    n_outliers: int = 0
    confidence_interval: tuple[float, float] = Field(default=(0.0, 0.0))

    @field_validator('cv')
    @classmethod
    def validate_cv(cls, v):
        """Ensure CV is non-negative."""
        if v < 0:
            raise ValueError("Coefficient of variation must be non-negative")
        return v

    @classmethod
    def from_array(cls, data: np.ndarray, confidence_level: float = 0.95) -> StatisticalMetrics:
        """Compute metrics from numpy array."""
        from scipy import stats

        n = len(data)
        mean_val = float(np.mean(data))
        std_val = float(np.std(data, ddof=1))

        # Compute confidence interval
        sem = std_val / np.sqrt(n)
        ci = stats.t.interval(confidence_level, n-1, loc=mean_val, scale=sem)

        # Detect outliers using IQR method
        q1, q3 = np.percentile(data, [25, 75])
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        n_outliers = np.sum((data < lower_bound) | (data > upper_bound))

        return cls(
            mean=mean_val,
            median=float(np.median(data)),
            std=std_val,
            variance=float(np.var(data, ddof=1)),
            min=float(np.min(data)),
            max=float(np.max(data)),
            q1=float(q1),
            q3=float(q3),
            p5=float(np.percentile(data, 5)),
            p95=float(np.percentile(data, 95)),
            p99=float(np.percentile(data, 99)),
            iqr=float(iqr),
            cv=std_val / abs(mean_val) if mean_val != 0 else 0.0,
            skewness=float(stats.skew(data)),
            kurtosis=float(stats.kurtosis(data)),
            n_samples=n,
            n_outliers=int(n_outliers),
            confidence_interval=(float(ci[0]), float(ci[1]))
        )


class BenchmarkMetadata(BaseModel):
    """Metadata for benchmark results (analysis-specific, not engine configuration)."""

    run_id: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    tags: list[str] = Field(default_factory=list)
    environment: dict[str, Any] = Field(default_factory=dict)

    # Scientific metrics (calculated from EngineConfig)
    hop_size: int | None = None
    time_resolution_ms: float | None = None
    freq_resolution_hz: float | None = None
    rtf: float | None = None  # Real-Time Factor (throughput only)

    # Streaming-specific metrics (realtime benchmark only)
    deadline_compliance_rate: float | None = None  # Fraction of frames meeting deadline
    mean_jitter_ms: float | None = None  # Mean timing jitter
    p99_jitter_ms: float | None = None  # 99th percentile jitter
    frames_dropped: int | None = None  # Number of frames dropped
    stream_duration_s: float | None = None  # Total stream duration
    mode: str | None = None  # Execution mode: 'streaming' or 'batch'


class BenchmarkResult(BaseModel):
    """Single benchmark measurement result."""

    benchmark_type: BenchmarkType
    engine_config: EngineConfig  # Use core EngineConfig, not duplicate
    metadata: BenchmarkMetadata = Field(default_factory=BenchmarkMetadata)

    # Core metrics (vary by benchmark type)
    primary_metric: float  # e.g., latency_us, fps, pass_rate
    metrics: dict[str, float] = Field(default_factory=dict)

    # Raw measurements (if available)
    raw_data: list[float] | None = None
    statistics: StatisticalMetrics | None = None

    def compute_statistics(self) -> None:
        """Compute statistical metrics from raw data."""
        if self.raw_data and len(self.raw_data) > 1:
            self.statistics = StatisticalMetrics.from_array(np.array(self.raw_data))


class ComparisonResult(BaseModel):
    """Statistical comparison between two result sets."""

    name: str
    baseline: StatisticalMetrics
    target: StatisticalMetrics

    # Comparison metrics
    mean_diff: float
    mean_diff_pct: float
    median_diff: float
    median_diff_pct: float

    # Statistical tests
    test_name: str
    test_statistic: float
    p_value: float
    is_significant: bool
    effect_size: float  # Cohen's d or similar

    # Performance indicators
    improvement: bool
    confidence: float

    @classmethod
    def compare(
        cls,
        name: str,
        baseline_data: np.ndarray,
        target_data: np.ndarray,
        test_type: str = "auto"
    ) -> ComparisonResult:
        """Perform statistical comparison between datasets."""
        from scipy import stats

        baseline_stats = StatisticalMetrics.from_array(baseline_data)
        target_stats = StatisticalMetrics.from_array(target_data)

        # Calculate differences
        mean_diff = target_stats.mean - baseline_stats.mean
        mean_diff_pct = (mean_diff / baseline_stats.mean * 100) if baseline_stats.mean != 0 else 0
        median_diff = target_stats.median - baseline_stats.median
        median_diff_pct = (median_diff / baseline_stats.median * 100) if baseline_stats.median != 0 else 0

        # Select appropriate statistical test
        if test_type == "auto":
            # Check normality
            _, p_norm_baseline = stats.normaltest(baseline_data)
            _, p_norm_target = stats.normaltest(target_data)

            if p_norm_baseline > 0.05 and p_norm_target > 0.05:
                # Both normal - use t-test
                test_name = "Welch's t-test"
                statistic, p_value = stats.ttest_ind(baseline_data, target_data, equal_var=False)
            else:
                # Non-normal - use Mann-Whitney U
                test_name = "Mann-Whitney U"
                statistic, p_value = stats.mannwhitneyu(baseline_data, target_data, alternative='two-sided')
        elif test_type == "ttest":
            test_name = "Welch's t-test"
            statistic, p_value = stats.ttest_ind(baseline_data, target_data, equal_var=False)
        elif test_type == "mannwhitney":
            test_name = "Mann-Whitney U"
            statistic, p_value = stats.mannwhitneyu(baseline_data, target_data, alternative='two-sided')
        else:
            raise ValueError(f"Unknown test type: {test_type}")

        # Calculate effect size (Cohen's d)
        pooled_std = np.sqrt((baseline_stats.variance + target_stats.variance) / 2)
        effect_size = mean_diff / pooled_std if pooled_std > 0 else 0

        # Determine improvement (lower is better for latency, higher for throughput)
        improvement = mean_diff < 0  # Assume lower is better by default

        return cls(
            name=name,
            baseline=baseline_stats,
            target=target_stats,
            mean_diff=mean_diff,
            mean_diff_pct=mean_diff_pct,
            median_diff=median_diff,
            median_diff_pct=median_diff_pct,
            test_name=test_name,
            test_statistic=float(statistic),
            p_value=float(p_value),
            is_significant=p_value < 0.05,
            effect_size=effect_size,
            improvement=improvement,
            confidence=1.0 - p_value
        )


class ScalingAnalysis(BaseModel):
    """Analysis of performance scaling patterns."""

    parameter: str  # e.g., "nfft", "channels"
    values: list[float]
    metrics: list[float]

    # Scaling characteristics
    correlation: float
    scaling_exponent: float  # From log-log fit
    scaling_type: str  # "linear", "sublinear", "superlinear", "saturated"

    # Model fit
    model_type: str  # "power", "linear", "logarithmic", "exponential"
    model_params: dict[str, float]
    model_r2: float
    model_rmse: float

    # Efficiency metrics
    ideal_scaling_efficiency: list[float]  # Actual vs theoretical ideal
    saturation_point: float | None = None

    @classmethod
    def analyze_scaling(
        cls,
        parameter: str,
        values: np.ndarray,
        metrics: np.ndarray
    ) -> ScalingAnalysis:
        """Analyze scaling patterns from data."""
        from scipy import stats
        from sklearn.metrics import mean_squared_error, r2_score

        # Calculate correlation
        correlation = float(np.corrcoef(values, metrics)[0, 1])

        # Fit power law (log-log)
        log_values = np.log(values)
        log_metrics = np.log(metrics)
        slope, intercept, _, _, _ = stats.linregress(log_values, log_metrics)

        # Determine scaling type
        if abs(slope - 1.0) < 0.1:
            scaling_type = "linear"
        elif slope < 1.0:
            scaling_type = "sublinear"
        elif slope > 1.0:
            scaling_type = "superlinear"
        else:
            scaling_type = "unknown"

        # Check for saturation
        if len(metrics) > 3:
            # Look for diminishing returns
            diffs = np.diff(metrics)
            if np.all(diffs[1:] < diffs[:-1]):
                # Find knee point
                second_diffs = np.diff(diffs)
                if len(second_diffs) > 0:
                    knee_idx = np.argmin(np.abs(second_diffs))
                    saturation_point = float(values[knee_idx + 1])
                else:
                    saturation_point = None
            else:
                saturation_point = None
        else:
            saturation_point = None

        # Calculate ideal scaling efficiency
        ideal_metrics = metrics[0] * (values / values[0]) ** slope
        efficiency = (metrics / ideal_metrics).tolist()

        # Model fit metrics
        predicted = np.exp(intercept) * values ** slope
        r2 = r2_score(metrics, predicted)
        rmse = np.sqrt(mean_squared_error(metrics, predicted))

        return cls(
            parameter=parameter,
            values=values.tolist(),
            metrics=metrics.tolist(),
            correlation=correlation,
            scaling_exponent=float(slope),
            scaling_type=scaling_type,
            model_type="power",
            model_params={"exponent": float(slope), "coefficient": float(np.exp(intercept))},
            model_r2=float(r2),
            model_rmse=float(rmse),
            ideal_scaling_efficiency=efficiency,
            saturation_point=saturation_point
        )


class ExperimentSummary(BaseModel):
    """Complete experiment analysis summary."""

    experiment_name: str
    timestamp: datetime

    # Data overview
    total_measurements: int
    benchmark_types: list[BenchmarkType]
    configurations_tested: list[EngineConfig]  # Use core EngineConfig

    # Results by type
    results: dict[BenchmarkType, list[BenchmarkResult]]

    # Statistical summaries
    statistics_by_config: dict[str, StatisticalMetrics]

    # Comparisons (if multiple configs)
    comparisons: list[ComparisonResult] = Field(default_factory=list)

    # Scaling analyses
    scaling_analyses: list[ScalingAnalysis] = Field(default_factory=list)

    # Key findings
    optimal_configs: dict[str, EngineConfig]  # Use core EngineConfig
    key_insights: list[str]
    warnings: list[str] = Field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert results to DataFrame for analysis."""
        records = []
        for bench_type, results in self.results.items():
            for result in results:
                record = {
                    'benchmark_type': bench_type,
                    'nfft': result.engine_config.nfft,
                    'channels': result.engine_config.channels,
                    'primary_metric': result.primary_metric,
                    'timestamp': result.metadata.timestamp,
                }
                record.update(result.metrics)
                records.append(record)

        return pd.DataFrame(records)

    def generate_insights(self) -> list[str]:
        """Generate human-readable insights from analysis."""
        insights = []

        # Performance insights
        for bench_type in self.benchmark_types:
            if bench_type in self.optimal_configs:
                config = self.optimal_configs[bench_type]
                insights.append(
                    f"Optimal {bench_type} configuration: "
                    f"NFFT={config.nfft}, Channels={config.channels}"
                )

        # Scaling insights
        for analysis in self.scaling_analyses:
            if analysis.scaling_type == "linear":
                insights.append(
                    f"{analysis.parameter} shows linear scaling "
                    f"(R²={analysis.model_r2:.3f})"
                )
            elif analysis.saturation_point:
                insights.append(
                    f"{analysis.parameter} saturates at "
                    f"{analysis.saturation_point:.0f}"
                )

        # Statistical insights
        for comparison in self.comparisons:
            if comparison.is_significant:
                direction = "improved" if comparison.improvement else "degraded"
                insights.append(
                    f"{comparison.name}: {direction} by "
                    f"{abs(comparison.mean_diff_pct):.1f}% "
                    f"(p={comparison.p_value:.4f})"
                )

        return insights
