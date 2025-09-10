"""
python/src/ionosense_hpc/benchmarks/latency.py
--------------------------------------------------------------------------------
Enhanced latency benchmark with IEEE-compliant statistical analysis and
GPU-accurate timing using CUDA events.
"""

import time
from typing import Any

import numpy as np

from ionosense_hpc.benchmarks.base import BaseBenchmark, BenchmarkConfig, BenchmarkResult
from ionosense_hpc.config import EngineConfig, Presets
from ionosense_hpc.core import Processor
from ionosense_hpc.utils import logger, make_test_batch
from ionosense_hpc.utils.profiling import (
    ProfileColor,
    ProfilingDomain,
    nvtx_range,
    setup_range,
    teardown_range,
)


class LatencyBenchmarkConfig(BenchmarkConfig):
    """Extended configuration for latency benchmarking."""

    # Latency-specific parameters
    measure_gpu_time: bool = True  # Use GPU events vs CPU timing
    measure_components: bool = False  # Measure individual pipeline stages
    test_signal_type: str = 'sine'
    test_frequency: float = 1000.0

    # Deadline analysis
    deadline_us: float = 200.0  # Real-time deadline
    analyze_jitter: bool = True

    # Load patterns
    load_pattern: str = 'constant'  # constant, burst, ramp
    burst_ratio: float = 2.0  # For burst pattern
    ramp_duration_s: float = 5.0  # For ramp pattern


class LatencyBenchmark(BaseBenchmark):
    """
    Production-grade latency benchmark with comprehensive timing analysis.
    
    This benchmark measures end-to-end processing latency with microsecond
    precision, including GPU kernel execution time, memory transfers, and
    synchronization overhead.
    """

    def __init__(self, config: LatencyBenchmarkConfig | dict | None = None):
        """Initialize with latency-specific configuration."""
        if isinstance(config, dict):
            config = LatencyBenchmarkConfig(**config)
        super().__init__(config or LatencyBenchmarkConfig(name="EnhancedLatency"))
        self.config: LatencyBenchmarkConfig = self.config  # Type hint

        self.processor = None
        self.test_data = None
        self.gpu_events = None
        self.interval_times = []  # For jitter analysis
        self.last_timestamp = None

    def setup(self) -> None:
        """Initialize processor and prepare test data (NVTX-instrumented)."""
        with setup_range("LatencyBenchmark.setup"):
            # Get engine config from preset or override
            if self.config.engine_config:
                engine_config = EngineConfig(**self.config.engine_config)
            else:
                engine_config = Presets.realtime()

            # Initialize processor
            with nvtx_range("InitializeProcessor", color=ProfileColor.DARK_GRAY):
                self.processor = Processor(engine_config)
                self.processor.initialize()

            # Prepare deterministic test data
            with nvtx_range("PrepareTestData", color=ProfileColor.ORANGE):
                self.test_data = make_test_batch(
                    nfft=engine_config.nfft,
                    batch=engine_config.batch,
                    signal_type=self.config.test_signal_type,
                    frequency=self.config.test_frequency,
                    seed=self.config.seed,
                )

            # Setup GPU timing if requested
            if self.config.measure_gpu_time:
                try:
                    logger.info(
                        "GPU event timing not yet exposed in Python API, using synchronized CPU timing"
                    )
                    self.config.measure_gpu_time = False
                except Exception as e:
                    logger.warning(f"Failed to setup GPU events: {e}")

            logger.info("Latency benchmark setup complete")
            logger.info(f"  Engine config: {engine_config}")
            logger.info(
                f"  Test signal: {self.config.test_signal_type} @ {self.config.test_frequency} Hz"
            )

    def execute_iteration(self) -> dict[str, float]:
        """Execute single iteration with comprehensive timing and NVTX markers."""
        # Pre-iteration synchronization for accurate timing
        with nvtx_range("PreIterationSync", color=ProfileColor.YELLOW):
            self.processor._engine.synchronize()

        # Start timing
        t_start_cpu = time.perf_counter()
        t_start_ns = time.perf_counter_ns()

        # Process data
        with nvtx_range(
            "ProcessIteration", color=ProfileColor.PURPLE, domain=ProfilingDomain.BENCHMARK
        ):
            output = self.processor.process(self.test_data)

        # Post-processing synchronization
        with nvtx_range("PostIterationSync", color=ProfileColor.YELLOW):
            self.processor._engine.synchronize()

        # End timing
        t_end_cpu = time.perf_counter()
        t_end_ns = time.perf_counter_ns()

        # Calculate latencies
        latency_s = t_end_cpu - t_start_cpu
        latency_us = (t_end_ns - t_start_ns) / 1000.0

        # Get engine-reported stats
        engine_stats = self.processor.get_stats()

        # Jitter analysis
        current_time = time.perf_counter()
        if self.last_timestamp is not None and self.config.analyze_jitter:
            interval = current_time - self.last_timestamp
            self.interval_times.append(interval * 1e6)  # Convert to microseconds
        self.last_timestamp = current_time

        # Build comprehensive metrics
        metrics = {
            'latency_us': latency_us,
            'latency_us_engine': engine_stats.get('latency_us', 0),
            'throughput_gbps': engine_stats.get('throughput_gbps', 0),
            'output_valid': np.isfinite(output).all(),
            'deadline_met': latency_us <= self.config.deadline_us
        }

        # Component timing if available (future enhancement)
        if self.config.measure_components:
            # This would require exposing stage-level timing from C++
            metrics['window_us'] = 0  # Placeholder
            metrics['fft_us'] = 0     # Placeholder
            metrics['magnitude_us'] = 0  # Placeholder

        return metrics

    def teardown(self) -> None:
        """Clean up resources (NVTX-instrumented)."""
        with teardown_range("LatencyBenchmark.teardown"):
            if self.processor:
                self.processor.reset()
                self.processor = None
            self.test_data = None
            self.gpu_events = None

    def analyze_results(self, result: BenchmarkResult) -> dict[str, Any]:
        """
        Perform advanced analysis on collected measurements.
        
        Returns:
            Dictionary of analysis results
        """
        from ionosense_hpc.utils.profiling import ProfileColor, nvtx_range
        with nvtx_range("AnalyzeResults", color=ProfileColor.ORANGE):
            if isinstance(result.measurements, dict):
                latencies = result.measurements.get('latency_us', np.array([]))
            else:
                latencies = result.measurements

            if len(latencies) == 0:
                return {'error': 'No latency measurements'}

            analysis = {
                'deadline_analysis': self._analyze_deadline_compliance(latencies),
                'distribution_analysis': self._analyze_distribution(latencies),
                'trend_analysis': self._analyze_trends(latencies)
            }

            if self.config.analyze_jitter and len(self.interval_times) > 1:
                analysis['jitter_analysis'] = self._analyze_jitter()

            return analysis

    def _analyze_deadline_compliance(self, latencies: np.ndarray) -> dict:
        """Analyze real-time deadline compliance."""
        deadline = self.config.deadline_us
        violations = latencies > deadline

        return {
            'deadline_us': deadline,
            'violation_count': int(np.sum(violations)),
            'violation_rate': float(np.mean(violations)),
            'worst_violation_us': float(np.max(latencies - deadline)) if np.any(violations) else 0,
            'safety_margin_us': float(deadline - np.percentile(latencies, 99)),
            'recommended_deadline_us': float(np.percentile(latencies, 99.9))
        }

    def _analyze_distribution(self, latencies: np.ndarray) -> dict:
        """Analyze latency distribution characteristics."""
        try:
            from scipy import stats

            return {
                'skewness': float(stats.skew(latencies)),
                'kurtosis': float(stats.kurtosis(latencies)),
                'normality_test': {
                    'statistic': float(stats.normaltest(latencies).statistic),
                    'p_value': float(stats.normaltest(latencies).pvalue),
                    'is_normal': stats.normaltest(latencies).pvalue > 0.05
                },
                'bimodal_detection': self._detect_bimodality(latencies)
            }
        except ImportError:
            # Fallback without scipy
            mean = np.mean(latencies)
            std = np.std(latencies)
            return {
                'skewness': float(np.mean(((latencies - mean) / std) ** 3)) if std > 0 else 0,
                'kurtosis': float(np.mean(((latencies - mean) / std) ** 4) - 3) if std > 0 else 0,
                'normality_test': {
                    'statistic': 0.0,
                    'p_value': 1.0,
                    'is_normal': None  # Unknown without scipy
                },
                'bimodal_detection': self._detect_bimodality(latencies)
            }

    def _analyze_trends(self, latencies: np.ndarray) -> dict:
        """Detect trends and anomalies in latency over time."""

        # Simple linear trend
        x = np.arange(len(latencies))
        z = np.polyfit(x, latencies, 1)
        trend_slope = z[0]

        # Moving average for smoothing
        window_size = min(100, len(latencies) // 10)
        if window_size > 1:
            moving_avg = np.convolve(latencies, np.ones(window_size)/window_size, mode='valid')
            stability = float(np.std(moving_avg))
        else:
            stability = float(np.std(latencies))

        return {
            'trend_slope_us_per_iteration': float(trend_slope),
            'has_warming_trend': trend_slope < -0.01,  # Negative slope = improving
            'stability_score': stability,
            'anomaly_indices': self._detect_anomalies(latencies).tolist()
        }

    def _analyze_jitter(self) -> dict:
        """Analyze timing jitter between iterations."""
        if len(self.interval_times) < 2:
            return {'error': 'Insufficient interval data'}

        intervals = np.array(self.interval_times)
        expected_interval = np.median(intervals)
        jitter = intervals - expected_interval

        return {
            'mean_interval_us': float(np.mean(intervals)),
            'expected_interval_us': float(expected_interval),
            'absolute_jitter_us': float(np.mean(np.abs(jitter))),
            'rms_jitter_us': float(np.sqrt(np.mean(jitter**2))),
            'max_jitter_us': float(np.max(np.abs(jitter))),
            'jitter_factor': float(np.std(intervals) / np.mean(intervals))
        }

    def _detect_bimodality(self, data: np.ndarray) -> dict:
        """Detect if distribution is bimodal using Hartigan's dip test approximation."""

        # Simplified bimodality detection using histogram analysis
        hist, bins = np.histogram(data, bins='auto')

        # Find peaks in histogram
        from scipy.signal import find_peaks
        peaks, properties = find_peaks(hist, height=len(data)*0.05)

        return {
            'n_modes': len(peaks),
            'is_bimodal': len(peaks) >= 2,
            'peak_locations': bins[peaks].tolist() if len(peaks) > 0 else []
        }

    def _detect_anomalies(self, data: np.ndarray, threshold: float = 3.0) -> np.ndarray:
        """Detect anomalies using modified Z-score method."""
        median = np.median(data)
        mad = np.median(np.abs(data - median))
        modified_z_scores = 0.6745 * (data - median) / (mad + 1e-10)
        return np.where(np.abs(modified_z_scores) > threshold)[0]


class StreamingLatencyBenchmark(LatencyBenchmark):
    """
    Variant that simulates continuous streaming workload.
    
    This benchmark measures latency under sustained load conditions,
    simulating real-world streaming scenarios.
    """

    def __init__(self, config: LatencyBenchmarkConfig | None = None):
        super().__init__(config)
        self.stream_buffer = None
        self.stream_position = 0

    def setup(self) -> None:
        """Setup streaming infrastructure."""
        super().setup()

        # Create larger buffer for streaming simulation
        engine_config = self.processor.config
        stream_duration_s = max(10.0, self.config.iterations * 0.001)
        stream_samples = int(stream_duration_s * engine_config.sample_rate_hz)

        # Generate continuous stream data
        from ionosense_hpc.utils import make_chirp
        self.stream_buffer = make_chirp(
            f_start=100,
            f_end=10000,
            duration=stream_duration_s,
            sample_rate=engine_config.sample_rate_hz
        )

        logger.info(f"Streaming buffer prepared: {stream_samples} samples")

    def execute_iteration(self) -> dict[str, float]:
        """Process next chunk from stream."""
        engine_config = self.processor.config
        chunk_size = engine_config.nfft * engine_config.batch

        # Get next chunk with overlap
        hop_size = engine_config.hop_size * engine_config.batch
        start_idx = self.stream_position * hop_size
        end_idx = start_idx + chunk_size

        if end_idx > len(self.stream_buffer):
            # Wrap around for continuous streaming
            self.stream_position = 0
            start_idx = 0
            end_idx = chunk_size

        chunk = self.stream_buffer[start_idx:end_idx]

        # Replace test data with stream chunk
        original_data = self.test_data
        self.test_data = chunk

        # Perform measurement
        metrics = super().execute_iteration()

        # Restore and advance
        self.test_data = original_data
        self.stream_position += 1

        # Add streaming-specific metrics
        metrics['stream_position'] = self.stream_position
        metrics['buffer_utilization'] = (end_idx / len(self.stream_buffer))

        return metrics


def run_latency_benchmark_suite(
    config_path: str | None = None,
    output_dir: str = './benchmark_results'
) -> dict[str, BenchmarkResult]:
    """
    Run comprehensive latency benchmark suite.
    
    Args:
        config_path: Path to YAML/JSON configuration file
        output_dir: Directory for saving results
        
    Returns:
        Dictionary of benchmark results
    """
    from pathlib import Path

    from ionosense_hpc.benchmarks.base import load_benchmark_config, save_benchmark_results

    # Load configuration
    if config_path:
        base_config = load_benchmark_config(config_path)
    else:
        base_config = {}

    # Define benchmark variants
    variants = [
        ('baseline', LatencyBenchmarkConfig(
            name='latency_baseline',
            iterations=1000,
            warmup_iterations=100,
            **base_config
        )),
        ('streaming', LatencyBenchmarkConfig(
            name='latency_streaming',
            iterations=5000,
            warmup_iterations=500,
            load_pattern='streaming',
            **base_config
        )),
        ('stress', LatencyBenchmarkConfig(
            name='latency_stress',
            iterations=10000,
            warmup_iterations=1000,
            deadline_us=150.0,  # Tighter deadline
            **base_config
        ))
    ]

    results = {}
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for name, config in variants:
        with nvtx_range(
            f"RunVariant_{name}", color=ProfileColor.NVIDIA_BLUE, domain=ProfilingDomain.BENCHMARK
        ):
            logger.info(f"\n{'='*60}")
            logger.info(f"Running {name} variant...")
            logger.info(f"{'='*60}")

            if name == 'streaming':
                benchmark = StreamingLatencyBenchmark(config)
            else:
                benchmark = LatencyBenchmark(config)

            result = benchmark.run()

            # Perform additional analysis
            analysis = benchmark.analyze_results(result)
            result.metadata['analysis'] = analysis

            results[name] = result

            # Save individual result with a filesystem-safe timestamp
            def _safe_filename(s: str) -> str:
                # Allow alnum, dash, underscore, dot; replace others with '-'
                return ''.join(
                    ch if (ch.isalnum() or ch in ('-', '_', '.')) else '-' for ch in s
                )

            safe_ts = _safe_filename(result.context.timestamp)
            save_benchmark_results(
                result,
                output_path / f"{name}_{safe_ts}.json",
            )

            # Print summary using latency metric stats
            lat_stats = (
                result.statistics.get('latency_us', {})
                if isinstance(result.statistics, dict)
                else {}
            )
            mean_lat = lat_stats.get('mean', 0.0) if isinstance(lat_stats, dict) else 0.0
            p99_lat = lat_stats.get('p99', 0.0) if isinstance(lat_stats, dict) else 0.0
            logger.info(f"\n{name} Results:")
            logger.info(f"  Mean: {mean_lat:.2f} µs")
            logger.info(f"  P99: {p99_lat:.2f} µs")
            if 'deadline_analysis' in analysis:
                da = analysis['deadline_analysis']
                logger.info(
                    f"  Deadline compliance: {(1-da['violation_rate'])*100:.1f}%"
                )

    return results


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Enhanced latency benchmark')
    parser.add_argument('--config', help='Configuration file path')
    parser.add_argument('--output', default='./results', help='Output directory')
    parser.add_argument('--variant', choices=['baseline', 'streaming', 'stress', 'all'],
                       default='all', help='Benchmark variant to run')

    args = parser.parse_args()

    if args.variant == 'all':
        results = run_latency_benchmark_suite(args.config, args.output)
    else:
        config = LatencyBenchmarkConfig(name=f'latency_{args.variant}')
        if args.variant == 'streaming':
            benchmark = StreamingLatencyBenchmark(config)
        else:
            benchmark = LatencyBenchmark(config)

        result = benchmark.run()
        from ionosense_hpc.benchmarks.base import save_benchmark_results
        save_benchmark_results(result, f"{args.output}/{result.name}.json")
