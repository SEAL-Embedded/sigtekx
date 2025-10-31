"""
Enhanced Analysis Engine
=========================

Modular analysis engine for GPU benchmark data with caching,
incremental computation, and extensible analyzer framework.

Key Fixes:
- Imports EngineConfig from core (not duplicate EngineConfiguration)
- Added ScientificMetricsAnalyzer for ionosphere research metrics

Architecture:
- Individual analyzers (LatencyAnalyzer, ThroughputAnalyzer, etc.) analyze specific benchmark types
- AnalysisEngine orchestrates all analyzers and provides caching, scaling analysis, comparisons
"""

from __future__ import annotations

import hashlib
import pickle
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

from ionosense_hpc.config import EngineConfig  # Import from core
from .models import (
    BenchmarkResult,
    BenchmarkType,
    BenchmarkMetadata,
    ComparisonResult,
    ExperimentSummary,
    ScalingAnalysis,
    StatisticalMetrics,
)


class AnalyzerBase(ABC):
    """Base class for modular analyzers."""

    @abstractmethod
    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Perform analysis on the data."""
        pass

    @abstractmethod
    def get_metrics(self) -> List[str]:
        """Return list of metrics this analyzer produces."""
        pass

    def validate_data(self, data: pd.DataFrame) -> bool:
        """Validate that required columns exist."""
        return True


class LatencyAnalyzer(AnalyzerBase):
    """Analyzer for latency benchmark data."""

    def get_metrics(self) -> List[str]:
        return [
            'mean_latency_us',
            'p95_latency_us',
            'p99_latency_us',
            'jitter_us',
            'stability_score'
        ]

    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze latency characteristics."""
        results = {}

        if 'mean_latency_us' not in data.columns:
            return results

        # Group by configuration
        for (nfft, channels), group in data.groupby(['engine_nfft', 'engine_channels']):
            config_key = f"{nfft}_{channels}"

            latencies = group['mean_latency_us'].values

            # Compute statistics
            stats_metrics = StatisticalMetrics.from_array(latencies)

            # Compute jitter (variation between consecutive measurements)
            if len(latencies) > 1:
                jitter = np.std(np.diff(latencies))
            else:
                jitter = 0.0

            # Stability score (inverse of CV, bounded 0-1)
            stability = 1.0 / (1.0 + stats_metrics.cv) if stats_metrics.cv >= 0 else 0.0

            results[config_key] = {
                'statistics': stats_metrics.dict(),
                'jitter_us': float(jitter),
                'stability_score': float(stability),
                'outlier_ratio': stats_metrics.n_outliers / stats_metrics.n_samples
            }

            # Tail latency analysis
            if 'p95_latency_us' in group.columns:
                tail_ratio = group['p95_latency_us'].mean() / group['mean_latency_us'].mean()
                results[config_key]['tail_ratio'] = float(tail_ratio)

        return results


class ThroughputAnalyzer(AnalyzerBase):
    """Analyzer for throughput benchmark data."""

    def get_metrics(self) -> List[str]:
        return [
            'frames_per_second',
            'gb_per_second',
            'samples_per_second',
            'efficiency_score',
            'gpu_utilization'
        ]

    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze throughput and efficiency."""
        results = {}

        if 'frames_per_second' not in data.columns:
            return results

        # Theoretical limits (customize based on hardware)
        MAX_MEMORY_BW_GBS = 936.2  # RTX 3090 Ti

        for (nfft, channels), group in data.groupby(['engine_nfft', 'engine_channels']):
            config_key = f"{nfft}_{channels}"

            fps = group['frames_per_second'].values

            # Compute statistics
            stats_metrics = StatisticalMetrics.from_array(fps)

            # Efficiency analysis
            if 'gb_per_second' in group.columns:
                gb_per_sec = group['gb_per_second'].mean()
                memory_efficiency = gb_per_sec / MAX_MEMORY_BW_GBS
            else:
                gb_per_sec = 0.0
                memory_efficiency = 0.0

            # Compute theoretical limits
            samples_per_frame = nfft * channels
            bytes_per_frame = samples_per_frame * 8  # Complex float32
            theoretical_max_fps = MAX_MEMORY_BW_GBS * 1e9 / bytes_per_frame

            efficiency_score = stats_metrics.mean / theoretical_max_fps

            results[config_key] = {
                'statistics': stats_metrics.dict(),
                'memory_efficiency': float(memory_efficiency),
                'efficiency_score': float(min(efficiency_score, 1.0)),
                'theoretical_max_fps': float(theoretical_max_fps),
                'gb_per_second': float(gb_per_sec)
            }

            # GPU utilization if available
            if 'gpu_utilization' in group.columns:
                results[config_key]['gpu_utilization'] = float(group['gpu_utilization'].mean())

        return results


class AccuracyAnalyzer(AnalyzerBase):
    """Analyzer for accuracy benchmark data."""

    def get_metrics(self) -> List[str]:
        return [
            'pass_rate',
            'mean_snr_db',
            'mean_error',
            'max_error',
            'reliability_score'
        ]

    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze accuracy and numerical stability."""
        results = {}

        if 'pass_rate' not in data.columns:
            return results

        for (nfft, channels), group in data.groupby(['engine_nfft', 'engine_channels']):
            config_key = f"{nfft}_{channels}"

            pass_rates = group['pass_rate'].values

            # Compute statistics
            stats_metrics = StatisticalMetrics.from_array(pass_rates)

            # Reliability score (combination of mean pass rate and consistency)
            reliability = stats_metrics.mean * (1.0 - stats_metrics.cv)

            results[config_key] = {
                'statistics': stats_metrics.dict(),
                'reliability_score': float(reliability),
                'all_passed': bool(np.all(pass_rates >= 0.99))
            }

            # SNR analysis if available
            if 'mean_snr_db' in group.columns:
                results[config_key]['snr_statistics'] = StatisticalMetrics.from_array(
                    group['mean_snr_db'].values
                ).dict()

        return results


class RealtimeAnalyzer(AnalyzerBase):
    """Analyzer for real-time performance data."""

    def get_metrics(self) -> List[str]:
        return [
            'compliance_rate',
            'frames_dropped',
            'mean_latency_ms',
            'jitter_ms',
            'deadline_misses'
        ]

    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze real-time compliance and jitter."""
        results = {}

        # Key metric varies by data format
        compliance_col = None
        for col in ['compliance_rate', 'deadline_compliance_rate']:
            if col in data.columns:
                compliance_col = col
                break

        if not compliance_col:
            return results

        for (nfft, channels), group in data.groupby(['engine_nfft', 'engine_channels']):
            config_key = f"{nfft}_{channels}"

            compliance = group[compliance_col].values

            # Compute statistics
            stats_metrics = StatisticalMetrics.from_array(compliance)

            # Real-time capability score
            rt_score = stats_metrics.mean * stats_metrics.median  # Penalize outliers

            results[config_key] = {
                'statistics': stats_metrics.dict(),
                'rt_capability_score': float(rt_score),
                'fully_compliant': bool(np.all(compliance >= 0.99))
            }

            # Jitter analysis
            if 'mean_jitter_ms' in group.columns:
                jitter = group['mean_jitter_ms'].values
                results[config_key]['jitter_statistics'] = StatisticalMetrics.from_array(jitter).dict()

        return results


class ScientificMetricsAnalyzer(AnalyzerBase):
    """Analyzer for ionosphere research scientific metrics (RTF, time/frequency resolution)."""

    def get_metrics(self) -> List[str]:
        return [
            'rtf',  # Real-Time Factor
            'time_resolution_ms',
            'freq_resolution_hz',
            'hop_size',
            'effective_fps'
        ]

    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze scientific metrics for ionosphere research."""
        results = {}

        # These columns should be present from enriched CSVs
        required_cols = ['time_resolution_ms', 'freq_resolution_hz', 'hop_size']
        if not all(col in data.columns for col in required_cols):
            # Calculate from engine parameters if enriched columns missing
            if all(col in data.columns for col in ['engine_nfft', 'engine_sample_rate_hz', 'engine_overlap']):
                data = data.copy()
                data['hop_size'] = (data['engine_nfft'] * (1 - data['engine_overlap'])).astype(int)
                data['time_resolution_ms'] = (data['engine_nfft'] / data['engine_sample_rate_hz']) * 1000
                data['freq_resolution_hz'] = data['engine_sample_rate_hz'] / data['engine_nfft']
            else:
                return results  # Cannot compute without required data

        for (nfft, channels), group in data.groupby(['engine_nfft', 'engine_channels']):
            config_key = f"{nfft}_{channels}"

            # Get scientific metrics (should be constant within config group)
            time_res = group['time_resolution_ms'].iloc[0]
            freq_res = group['freq_resolution_hz'].iloc[0]
            hop_size = group['hop_size'].iloc[0]

            results[config_key] = {
                'time_resolution_ms': float(time_res),
                'freq_resolution_hz': float(freq_res),
                'hop_size': int(hop_size),
            }

            # RTF (Real-Time Factor) - only meaningful for throughput benchmarks
            if 'rtf' in group.columns:
                rtf = group['rtf'].values
                results[config_key]['rtf_statistics'] = StatisticalMetrics.from_array(rtf).dict()
                results[config_key]['rtf_mean'] = float(rtf.mean())

                # Classify real-time capability
                mean_rtf = rtf.mean()
                if mean_rtf >= 2.0:
                    capability = "excellent"  # Can handle 2+ real-time streams
                elif mean_rtf >= 1.0:
                    capability = "good"  # Can handle real-time processing
                elif mean_rtf >= 0.5:
                    capability = "marginal"  # Near real-time
                else:
                    capability = "insufficient"  # Cannot keep up

                results[config_key]['realtime_capability'] = capability

            # Effective FPS calculation
            if 'engine_sample_rate_hz' in group.columns:
                sample_rate = group['engine_sample_rate_hz'].iloc[0]
                effective_fps = sample_rate / hop_size
                results[config_key]['effective_fps'] = float(effective_fps)

                # Suitability for ionosphere phenomena
                results[config_key]['phenomena_suitability'] = self._assess_phenomena_suitability(
                    time_res, freq_res
                )

        return results

    def _assess_phenomena_suitability(self, time_res_ms: float, freq_res_hz: float) -> Dict[str, bool]:
        """Assess suitability for different ionosphere phenomena."""
        return {
            'lightning_sprites': time_res_ms < 10.0,  # Fast transients (<10ms time resolution)
            'sids': freq_res_hz < 1.0,  # Narrowband VLF transmitter detection (<1Hz freq resolution)
            'schumann_resonances': freq_res_hz < 0.5,  # Fine frequency resolution for resonant peaks
            'whistlers': time_res_ms < 50.0 and freq_res_hz < 25.0,  # VLF dispersive phenomena
            'general_vlf': freq_res_hz < 100.0,  # Broad VLF band (3-30 kHz)
        }


class ScalingAnalyzer:
    """Analyze scaling patterns across parameters."""

    @staticmethod
    def analyze_parameter_scaling(
        data: pd.DataFrame,
        parameter: str,
        metric: str,
        fixed_params: Optional[Dict[str, Any]] = None
    ) -> Optional[ScalingAnalysis]:
        """Analyze how a metric scales with a parameter."""

        # Filter data if fixed parameters specified
        filtered_data = data.copy()
        if fixed_params:
            for param, value in fixed_params.items():
                if param in filtered_data.columns:
                    filtered_data = filtered_data[filtered_data[param] == value]

        if len(filtered_data) < 3:
            return None

        # Group by parameter and aggregate metric
        grouped = filtered_data.groupby(parameter)[metric].mean()

        if len(grouped) < 3:
            return None

        values = np.array(grouped.index)
        metrics = np.array(grouped.values)

        return ScalingAnalysis.analyze_scaling(parameter, values, metrics)

    @staticmethod
    def find_optimal_point(
        data: pd.DataFrame,
        optimize_for: str,
        minimize: bool = True
    ) -> Dict[str, Any]:
        """Find optimal configuration point."""

        if optimize_for not in data.columns:
            return {}

        if minimize:
            optimal_idx = data[optimize_for].idxmin()
        else:
            optimal_idx = data[optimize_for].idxmax()

        optimal_row = data.loc[optimal_idx]

        return {
            'configuration': {
                'nfft': int(optimal_row['engine_nfft']),
                'channels': int(optimal_row['engine_channels'])
            },
            'metric_value': float(optimal_row[optimize_for]),
            'all_metrics': optimal_row.to_dict()
        }


class AnalysisEngine:
    """
    Main analysis engine coordinating all analyzers.

    This is an orchestration engine that runs multiple analyzer classes
    (LatencyAnalyzer, ThroughputAnalyzer, etc.) and provides caching,
    scaling analysis, and statistical comparisons.

    Not to be confused with ionosense_hpc.Engine (GPU processing engine).
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize the analysis engine."""
        self.cache_dir = cache_dir or Path("artifacts/analysis_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Register analyzers
        self.analyzers: Dict[BenchmarkType, AnalyzerBase] = {
            BenchmarkType.LATENCY: LatencyAnalyzer(),
            BenchmarkType.THROUGHPUT: ThroughputAnalyzer(),
            BenchmarkType.ACCURACY: AccuracyAnalyzer(),
            BenchmarkType.REALTIME: RealtimeAnalyzer(),
        }

        # Scientific metrics analyzer (for all benchmark types)
        self.scientific_analyzer = ScientificMetricsAnalyzer()
        self.scaling_analyzer = ScalingAnalyzer()

    def _get_cache_key(self, data: pd.DataFrame) -> str:
        """Generate cache key for dataset."""
        # Use data shape and column hash
        data_repr = f"{data.shape}_{sorted(data.columns.tolist())}_{data.iloc[0].to_dict()}"
        return hashlib.md5(data_repr.encode()).hexdigest()

    def _load_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Load cached analysis results."""
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)
            except Exception:
                pass
        return None

    def _save_to_cache(self, cache_key: str, results: Dict[str, Any]) -> None:
        """Save analysis results to cache."""
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(results, f)
        except Exception:
            pass

    def analyze_benchmark_type(
        self,
        data: pd.DataFrame,
        benchmark_type: BenchmarkType
    ) -> Dict[str, Any]:
        """Analyze data for a specific benchmark type."""

        if benchmark_type not in self.analyzers:
            return {}

        # Check cache
        cache_key = f"{benchmark_type}_{self._get_cache_key(data)}"
        cached = self._load_from_cache(cache_key)
        if cached is not None:
            return cached

        # Run analysis
        analyzer = self.analyzers[benchmark_type]
        results = analyzer.analyze(data)

        # Cache results
        self._save_to_cache(cache_key, results)

        return results

    def analyze_scientific_metrics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze scientific metrics (RTF, time/frequency resolution)."""
        return self.scientific_analyzer.analyze(data)

    def analyze_scaling(
        self,
        data: pd.DataFrame,
        parameters: List[str] = ['engine_nfft', 'engine_channels'],
        metrics: Optional[List[str]] = None
    ) -> List[ScalingAnalysis]:
        """Analyze scaling patterns for multiple parameters and metrics."""

        analyses = []

        # Auto-detect metrics if not specified
        if metrics is None:
            metrics = []
            for col in data.columns:
                if any(keyword in col for keyword in ['latency', 'fps', 'throughput', 'rate', 'rtf']):
                    metrics.append(col)

        for parameter in parameters:
            if parameter not in data.columns:
                continue

            for metric in metrics:
                if metric not in data.columns:
                    continue

                # Analyze scaling with other parameters fixed
                unique_values = data[parameter].nunique()
                if unique_values < 3:
                    continue

                # Fix other parameters to their median values
                fixed_params = {}
                for other_param in parameters:
                    if other_param != parameter:
                        median_val = data[other_param].median()
                        # Use closest actual value
                        closest = data[other_param].unique()
                        closest_val = min(closest, key=lambda x: abs(x - median_val))
                        fixed_params[other_param] = closest_val

                analysis = self.scaling_analyzer.analyze_parameter_scaling(
                    data, parameter, metric, fixed_params
                )

                if analysis:
                    analyses.append(analysis)

        return analyses

    def compare_configurations(
        self,
        data: pd.DataFrame,
        config1: Dict[str, Any],
        config2: Dict[str, Any],
        metric: str
    ) -> Optional[ComparisonResult]:
        """Statistically compare two configurations."""

        # Filter data for each configuration
        data1 = data.copy()
        data2 = data.copy()

        for key, value in config1.items():
            if key in data1.columns:
                data1 = data1[data1[key] == value]

        for key, value in config2.items():
            if key in data2.columns:
                data2 = data2[data2[key] == value]

        if len(data1) == 0 or len(data2) == 0:
            return None

        if metric not in data1.columns or metric not in data2.columns:
            return None

        values1 = data1[metric].values
        values2 = data2[metric].values

        if len(values1) < 2 or len(values2) < 2:
            return None

        comparison_name = f"{config1} vs {config2}"
        return ComparisonResult.compare(comparison_name, values1, values2)

    def generate_summary(
        self,
        data: pd.DataFrame,
        experiment_name: str = "GPU Benchmark Analysis"
    ) -> ExperimentSummary:
        """Generate comprehensive experiment summary."""

        from datetime import datetime

        # Detect benchmark types
        benchmark_types = []
        if 'benchmark_type' in data.columns:
            benchmark_types = [BenchmarkType(bt) for bt in data['benchmark_type'].unique()]
        else:
            # Infer from columns
            if 'mean_latency_us' in data.columns:
                benchmark_types.append(BenchmarkType.LATENCY)
            if 'frames_per_second' in data.columns:
                benchmark_types.append(BenchmarkType.THROUGHPUT)
            if 'pass_rate' in data.columns:
                benchmark_types.append(BenchmarkType.ACCURACY)
            if 'compliance_rate' in data.columns or 'deadline_compliance_rate' in data.columns:
                benchmark_types.append(BenchmarkType.REALTIME)

        # Extract configurations (use EngineConfig from core)
        configs = []
        for (nfft, channels), _ in data.groupby(['engine_nfft', 'engine_channels']):
            # Get additional parameters if available
            config_dict = {'nfft': int(nfft), 'channels': int(channels)}

            # Add optional parameters if present in data
            group_data = data[(data['engine_nfft'] == nfft) & (data['engine_channels'] == channels)]
            if 'engine_overlap' in group_data.columns:
                config_dict['overlap'] = float(group_data['engine_overlap'].iloc[0])
            if 'engine_sample_rate_hz' in group_data.columns:
                config_dict['sample_rate_hz'] = int(group_data['engine_sample_rate_hz'].iloc[0])

            configs.append(EngineConfig(**config_dict))

        # Run analyses
        results_by_type = {}
        statistics_by_config = {}

        for bench_type in benchmark_types:
            # Filter data for this type
            if 'benchmark_type' in data.columns:
                type_data = data[data['benchmark_type'] == bench_type.value]
            else:
                type_data = data

            if len(type_data) == 0:
                continue

            # Analyze
            analysis_results = self.analyze_benchmark_type(type_data, bench_type)

            # Convert to BenchmarkResult objects
            bench_results = []
            for config_key, config_analysis in analysis_results.items():
                nfft, channels = map(int, config_key.split('_'))

                # Find primary metric
                if bench_type == BenchmarkType.LATENCY:
                    primary = config_analysis['statistics']['mean']
                elif bench_type == BenchmarkType.THROUGHPUT:
                    primary = config_analysis['statistics']['mean']
                elif bench_type == BenchmarkType.ACCURACY:
                    primary = config_analysis['statistics']['mean']
                else:
                    primary = config_analysis['statistics']['mean']

                # Find matching config
                matching_config = next((c for c in configs if c.nfft == nfft and c.channels == channels), None)
                if not matching_config:
                    matching_config = EngineConfig(nfft=nfft, channels=channels)

                result = BenchmarkResult(
                    benchmark_type=bench_type,
                    engine_config=matching_config,
                    primary_metric=primary,
                    metrics=config_analysis
                )
                bench_results.append(result)

                # Store statistics
                statistics_by_config[config_key] = StatisticalMetrics(**config_analysis['statistics'])

            results_by_type[bench_type] = bench_results

        # Find optimal configurations
        optimal_configs = {}

        if BenchmarkType.LATENCY in results_by_type:
            latency_data = data[data['benchmark_type'] == BenchmarkType.LATENCY.value] if 'benchmark_type' in data.columns else data
            if 'mean_latency_us' in latency_data.columns:
                optimal = self.scaling_analyzer.find_optimal_point(latency_data, 'mean_latency_us', minimize=True)
                if optimal:
                    optimal_configs[BenchmarkType.LATENCY.value] = EngineConfig(**optimal['configuration'])

        if BenchmarkType.THROUGHPUT in results_by_type:
            throughput_data = data[data['benchmark_type'] == BenchmarkType.THROUGHPUT.value] if 'benchmark_type' in data.columns else data
            if 'frames_per_second' in throughput_data.columns:
                optimal = self.scaling_analyzer.find_optimal_point(throughput_data, 'frames_per_second', minimize=False)
                if optimal:
                    optimal_configs[BenchmarkType.THROUGHPUT.value] = EngineConfig(**optimal['configuration'])

        # Scaling analyses
        scaling_analyses = self.analyze_scaling(data)

        # Generate summary
        summary = ExperimentSummary(
            experiment_name=experiment_name,
            timestamp=datetime.now(),
            total_measurements=len(data),
            benchmark_types=benchmark_types,
            configurations_tested=configs,
            results=results_by_type,
            statistics_by_config=statistics_by_config,
            scaling_analyses=scaling_analyses,
            optimal_configs=optimal_configs,
            key_insights=[]
        )

        # Generate insights
        summary.key_insights = summary.generate_insights()

        return summary
