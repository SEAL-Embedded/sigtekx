"""
python/src/ionosense_hpc/benchmarks/realtime.py
--------------------------------------------------------------------------------
Real-time streaming benchmark with deadline compliance analysis.
Upgraded to use BaseBenchmark framework for RSE/RE standards compliance.
"""

import time
from typing import Any

import numpy as np

from ionosense_hpc.benchmarks.base import BaseBenchmark, BenchmarkConfig
from ionosense_hpc.config import EngineConfig, Presets
from ionosense_hpc.core import Processor
from ionosense_hpc.utils import logger, make_test_batch


class RealtimeBenchmarkConfig(BenchmarkConfig):
    """Configuration for real-time streaming benchmark."""

    # Real-time specific parameters
    stream_duration_s: float = 10.0
    frame_deadline_ms: float | None = None  # Auto-calculated from hop_duration if None
    strict_timing: bool = True  # Use busy-wait for precise timing
    measure_jitter: bool = True
    drop_frame_threshold: int = 5  # Max consecutive dropped frames before abort

    # Streaming parameters
    buffer_ahead_frames: int = 2
    simulate_io_delay: bool = False
    io_delay_ms: float = 0.1


class RealtimeBenchmark(BaseBenchmark):
    """
    Real-time streaming benchmark with deadline compliance.
    
    Simulates a real-world streaming scenario where frames must be
    processed within strict deadlines, measuring both latency and
    timing jitter.
    """

    def __init__(self, config: RealtimeBenchmarkConfig | dict | None = None):
        """Initialize real-time benchmark."""
        if isinstance(config, dict):
            config = RealtimeBenchmarkConfig(**config)
        super().__init__(config or RealtimeBenchmarkConfig(name="Realtime"))
        self.config: RealtimeBenchmarkConfig = self.config

        self.processor = None
        self.engine_config = None
        self.test_data = None
        self.frame_times = []
        self.deadline_misses = []
        self.dropped_frames = 0

    def setup(self) -> None:
        """Initialize processor and prepare streaming infrastructure."""
        # Get engine configuration
        if self.config.engine_config:
            self.engine_config = EngineConfig(**self.config.engine_config)
        else:
            self.engine_config = Presets.realtime()

        # Calculate frame deadline
        if self.config.frame_deadline_ms is None:
            self.config.frame_deadline_ms = self.engine_config.hop_duration_ms

        # Initialize processor
        self.processor = Processor(self.engine_config)
        self.processor.initialize()

        # Pre-generate test data for consistent frames
        self.test_data = make_test_batch(
            self.engine_config.nfft,
            self.engine_config.batch,
            signal_type='noise',
            seed=self.config.seed
        )

        # Calculate total frames
        self.total_frames = int(
            self.config.stream_duration_s * 1000 / self.config.frame_deadline_ms
        )

        logger.info("Real-time benchmark initialized:")
        logger.info(f"  Duration: {self.config.stream_duration_s}s")
        logger.info(f"  Frame deadline: {self.config.frame_deadline_ms:.2f}ms")
        logger.info(f"  Total frames: {self.total_frames}")

    def execute_iteration(self) -> dict[str, float]:
        """Execute one complete streaming session."""
        metrics = {
            'frames_processed': 0,
            'frames_dropped': 0,
            'deadline_misses': 0,
            'mean_latency_ms': 0,
            'max_latency_ms': 0,
            'mean_jitter_ms': 0,
            'deadline_compliance_rate': 0
        }

        frame_latencies = []
        inter_frame_times = []
        consecutive_drops = 0

        # Start streaming simulation
        session_start = time.perf_counter()
        last_frame_time = session_start

        for frame_idx in range(self.total_frames):
            # Calculate when this frame should be processed
            target_time = session_start + (frame_idx * self.config.frame_deadline_ms / 1000)

            # Simulate frame arrival timing
            if self.config.strict_timing:
                # Busy-wait for precise timing
                while time.perf_counter() < target_time:
                    pass
            else:
                # Sleep-based timing (less precise)
                sleep_time = target_time - time.perf_counter()
                if sleep_time > 0:
                    time.sleep(sleep_time)

            frame_arrival_time = time.perf_counter()

            # Check if we're already late
            arrival_delay = (frame_arrival_time - target_time) * 1000
            if arrival_delay > self.config.frame_deadline_ms * 0.5:
                # Frame arrived too late, drop it
                metrics['frames_dropped'] += 1
                consecutive_drops += 1

                if consecutive_drops >= self.config.drop_frame_threshold:
                    logger.warning(f"Too many consecutive drops ({consecutive_drops}), aborting")
                    break
                continue
            else:
                consecutive_drops = 0

            # Process frame
            process_start = time.perf_counter()

            try:
                # Simulate I/O delay if configured
                if self.config.simulate_io_delay:
                    time.sleep(self.config.io_delay_ms / 1000)

                # Process the frame
                output = self.processor.process(self.test_data)

                # Ensure GPU sync for accurate timing
                self.processor._engine.synchronize()

            except Exception as e:
                logger.error(f"Frame {frame_idx} processing failed: {e}")
                metrics['frames_dropped'] += 1
                continue

            process_end = time.perf_counter()

            # Calculate metrics
            frame_latency_ms = (process_end - process_start) * 1000
            frame_latencies.append(frame_latency_ms)

            # Check deadline compliance
            total_frame_time = (process_end - frame_arrival_time) * 1000
            if total_frame_time > self.config.frame_deadline_ms:
                metrics['deadline_misses'] += 1
                self.deadline_misses.append(frame_idx)

            # Track inter-frame timing for jitter
            if frame_idx > 0:
                inter_frame_time = (frame_arrival_time - last_frame_time) * 1000
                inter_frame_times.append(inter_frame_time)

            last_frame_time = frame_arrival_time
            metrics['frames_processed'] += 1

            # Progress reporting
            if self.config.verbose and frame_idx % 100 == 0:
                compliance_rate = 1 - (metrics['deadline_misses'] / max(1, frame_idx))
                logger.debug(f"Frame {frame_idx}/{self.total_frames}: "
                           f"Compliance={compliance_rate:.1%}")

        # Calculate final metrics
        if frame_latencies:
            metrics['mean_latency_ms'] = float(np.mean(frame_latencies))
            metrics['max_latency_ms'] = float(np.max(frame_latencies))
            metrics['p99_latency_ms'] = float(np.percentile(frame_latencies, 99))

        if inter_frame_times:
            expected_inter_frame = self.config.frame_deadline_ms
            jitters = np.abs(np.array(inter_frame_times) - expected_inter_frame)
            metrics['mean_jitter_ms'] = float(np.mean(jitters))
            metrics['max_jitter_ms'] = float(np.max(jitters))

        metrics['deadline_compliance_rate'] = (
            1 - (metrics['deadline_misses'] / max(1, metrics['frames_processed']))
        )

        # Store for analysis
        self.frame_times.extend(frame_latencies)

        return metrics

    def teardown(self) -> None:
        """Clean up resources."""
        if self.processor:
            self.processor.reset()
            self.processor = None
        self.test_data = None

    def analyze_results(self, result: 'BenchmarkResult') -> dict[str, Any]:
        """
        Analyze real-time performance characteristics.
        
        Returns:
            Dictionary with real-time specific analysis
        """
        analysis = {}

        # Frame timing analysis
        if self.frame_times:
            analysis['timing_stability'] = self._analyze_timing_stability()

        # Deadline compliance patterns
        if self.deadline_misses:
            analysis['deadline_patterns'] = self._analyze_deadline_patterns()

        # System capability assessment
        analysis['system_capability'] = self._assess_system_capability(result)

        return analysis

    def _analyze_timing_stability(self) -> dict:
        """Analyze timing stability and predictability."""
        times = np.array(self.frame_times)

        # Detect timing modes (e.g., bimodal from CPU frequency scaling)
        from scipy import stats
        kde = stats.gaussian_kde(times)
        x = np.linspace(times.min(), times.max(), 100)
        density = kde(x)

        # Find peaks in distribution
        from scipy.signal import find_peaks
        peaks, _ = find_peaks(density, height=np.max(density) * 0.1)

        return {
            'coefficient_of_variation': float(np.std(times) / np.mean(times)),
            'timing_modes': len(peaks),
            'stable': len(peaks) == 1 and np.std(times) / np.mean(times) < 0.1,
            'predictability_score': float(1.0 / (1.0 + np.std(times) / np.mean(times)))
        }

    def _analyze_deadline_patterns(self) -> dict:
        """Analyze patterns in deadline misses."""
        if not self.deadline_misses:
            return {'pattern': 'none', 'clustered': False}

        misses = np.array(self.deadline_misses)

        # Check for clustering
        gaps = np.diff(misses)
        clustered = np.std(gaps) > np.mean(gaps) if len(gaps) > 0 else False

        # Identify pattern
        if clustered:
            pattern = 'clustered'
        elif len(misses) > 10 and np.corrcoef(misses, np.arange(len(misses)))[0, 1] > 0.8:
            pattern = 'increasing'  # Getting worse over time
        else:
            pattern = 'random'

        return {
            'pattern': pattern,
            'clustered': clustered,
            'miss_indices': misses.tolist()
        }

    def _assess_system_capability(self, result: 'BenchmarkResult') -> dict:
        """Assess system's real-time capability."""
        stats = result.statistics

        # Calculate headroom
        mean_latency = stats.get('mean_latency_ms', 0)
        p99_latency = stats.get('p99_latency_ms', mean_latency)
        deadline = self.config.frame_deadline_ms

        headroom_mean = (deadline - mean_latency) / deadline
        headroom_p99 = (deadline - p99_latency) / deadline

        # Determine capability level
        if headroom_p99 > 0.5:
            capability = 'excellent'
        elif headroom_p99 > 0.2:
            capability = 'good'
        elif headroom_p99 > 0:
            capability = 'marginal'
        else:
            capability = 'insufficient'

        return {
            'capability_level': capability,
            'headroom_mean_pct': float(headroom_mean * 100),
            'headroom_p99_pct': float(headroom_p99 * 100),
            'recommended_deadline_ms': float(p99_latency * 1.2),  # 20% safety margin
            'max_sustainable_fps': float(1000 / p99_latency) if p99_latency > 0 else 0
        }


if __name__ == '__main__':
    import argparse
    import json

    parser = argparse.ArgumentParser(description='Real-time streaming benchmark')
    parser.add_argument('--duration', type=float, default=10.0,
                       help='Stream duration in seconds')
    parser.add_argument('--preset', default='realtime',
                       help='Engine configuration preset')
    parser.add_argument('--output', help='Output file for results')
    parser.add_argument('--strict', action='store_true',
                       help='Use strict timing (busy-wait)')

    args = parser.parse_args()

    # Create configuration
    config = RealtimeBenchmarkConfig(
        name='realtime_streaming',
        stream_duration_s=args.duration,
        strict_timing=args.strict,
        iterations=1  # One streaming session
    )

    # Load engine preset
    config.engine_config = getattr(Presets, args.preset)().model_dump()

    # Run benchmark
    benchmark = RealtimeBenchmark(config)
    result = benchmark.run()

    # Analyze
    analysis = benchmark.analyze_results(result)
    result.metadata['analysis'] = analysis

    # Output results
    if args.output:
        from ionosense_hpc.benchmarks.base import save_benchmark_results
        save_benchmark_results(result, args.output)
    else:
        print(json.dumps(result.to_dict(), indent=2, default=str))
