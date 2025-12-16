"""
src/sigtekx/benchmarks/throughput.py
--------------------------------------------------------------------------------
Enhanced throughput benchmark with memory bandwidth analysis and
scaling characterization following HPC benchmarking standards.
"""

import gc
import logging
import time
from typing import Any

import numpy as np

from sigtekx import Engine
from sigtekx.benchmarks.base import BaseBenchmark, BenchmarkConfig
from sigtekx.config import EngineConfig, ExecutionMode, get_preset
from sigtekx.utils import get_memory_usage, make_test_batch
from sigtekx.utils.paths import get_benchmark_run_dir, normalize_benchmark_name
from sigtekx.utils.profiling import (
    ProfileColor,
    ProfilingDomain,
    compute_range,
    nvtx_range,
    setup_range,
    teardown_range,
)

logger = logging.getLogger(__name__)


class ThroughputBenchmarkConfig(BenchmarkConfig):
    """Configuration for throughput benchmarking."""

    # Throughput-specific parameters
    warmup_duration_s: float | None = None  # Optional warmup duration when warmup_iterations > 0
    test_duration_s: float = 10.0  # Duration for sustained throughput test
    data_size_gb: float | None = None  # Total data to process (overrides duration)

    # Scaling analysis
    test_channel_counts: list[int] = [1, 2, 4, 8, 16, 32, 64, 128]
    test_nfft_sizes: list[int] = [256, 512, 1024, 2048, 4096]

    # Memory analysis
    measure_memory_bandwidth: bool = True
    measure_pcie_bandwidth: bool = True

    # Load patterns
    load_pattern: str = 'sustained'  # sustained, burst, variable
    burst_duration_s: float = 1.0
    burst_interval_s: float = 0.1

    # Resource monitoring
    monitor_gpu_utilization: bool = True
    monitor_temperature: bool = True
    monitor_power: bool = True


class ThroughputBenchmark(BaseBenchmark):
    """
    Comprehensive throughput benchmark with resource utilization analysis.

    This benchmark measures sustained processing throughput, memory bandwidth
    utilization, and scaling characteristics across different configurations.
    """

    def __init__(self, config: ThroughputBenchmarkConfig | dict | None = None):
        """Initialize throughput benchmark."""
        if isinstance(config, dict):
            config = ThroughputBenchmarkConfig(**config)
        super().__init__(config or ThroughputBenchmarkConfig(name="Throughput"))
        self.config: ThroughputBenchmarkConfig = self.config

        self.engine: Engine | None = None
        self.engine_config: EngineConfig | None = None
        self.test_data: np.ndarray | None = None
        self.resource_samples: list[dict[str, Any]] = []
        self._in_warmup: bool = False

    def setup(self) -> None:
        """Initialize engine for throughput testing (NVTX-instrumented)."""
        with setup_range("ThroughputBenchmark.setup"):
            # Use throughput-optimized preset
            if self.config.engine_config:
                self.engine_config = EngineConfig(**self.config.engine_config)
                # Default to BATCH mode for throughput if not explicitly set in config
                if 'mode' not in self.config.engine_config:
                    self.engine_config.mode = ExecutionMode.BATCH
            else:
                self.engine_config = get_preset('default')
                self.engine_config.mode = ExecutionMode.BATCH

            with nvtx_range("InitializeEngine", color=ProfileColor.DARK_GRAY):
                self.engine = Engine(config=self.engine_config)

            # Pre-generate test data
            with nvtx_range("GenerateTestData", color=ProfileColor.ORANGE):
                self.test_data = make_test_batch(
                    'noise',
                    self.engine_config,
                    rng=np.random.default_rng(self.config.seed),
                )

            # Force garbage collection before measurement
            gc.collect()

            logger.info("Throughput benchmark initialized")
            logger.info(f"  Configuration: {self.engine_config}")

    def execute_iteration(self) -> dict[str, float]:
        """Execute throughput measurement (NVTX-instrumented)."""
        assert self.engine is not None
        assert self.engine_config is not None
        assert self.test_data is not None
        with nvtx_range("ThroughputMeasurement", color=ProfileColor.NVIDIA_BLUE, domain=ProfilingDomain.BENCHMARK):
            metrics: dict[str, float] = {}

            warmup_duration_s = (
                self.config.warmup_duration_s
                if self._in_warmup and self.config.warmup_duration_s is not None
                else None
            )
            duration_s = warmup_duration_s or self.config.test_duration_s

            # Determine test parameters
            bytes_per_sample = 4  # float32
            samples_per_batch = self.engine_config.nfft * self.engine_config.channels
            bytes_per_batch = samples_per_batch * bytes_per_sample

            if self.config.data_size_gb is not None:
                total_bytes = self.config.data_size_gb * (1024**3)
                n_batches = int(total_bytes / bytes_per_batch)
                test_mode = 'data_size'
            else:
                estimated_fps = 1000
                n_batches = int(duration_s * estimated_fps)
                test_mode = 'warmup_duration' if warmup_duration_s is not None else 'duration'

            if self.config.measure_memory_bandwidth:
                initial_mem_mb, total_mem_mb = get_memory_usage()

            start_time = time.perf_counter()
            bytes_processed = 0
            frames_processed = 0

            with compute_range(f"ProcessBatches_{test_mode}"):
                if test_mode == 'data_size':
                    for batch_idx in range(n_batches):
                        with nvtx_range(f"Batch_{batch_idx}", color=ProfileColor.PURPLE, payload=batch_idx):
                            _ = self.engine.process(self.test_data)
                            bytes_processed += bytes_per_batch
                            frames_processed += 1
                            if self.config.monitor_gpu_utilization and frames_processed % 100 == 0:
                                with nvtx_range("SampleResources", color=ProfileColor.ORANGE):
                                    self._sample_resources()
                else:
                    while (time.perf_counter() - start_time) < duration_s:
                        with nvtx_range(f"Frame_{frames_processed}", color=ProfileColor.PURPLE):
                            _ = self.engine.process(self.test_data)
                            bytes_processed += bytes_per_batch
                            frames_processed += 1
                            if self.config.monitor_gpu_utilization and frames_processed % 100 == 0:
                                with nvtx_range("SampleResources", color=ProfileColor.ORANGE):
                                    self._sample_resources()

            end_time = time.perf_counter()
            elapsed_seconds = end_time - start_time

            with nvtx_range("CalculateMetrics", color=ProfileColor.YELLOW):
                gb_processed = bytes_processed / (1024**3)
                metrics['frames_processed'] = frames_processed
                metrics['gb_processed'] = gb_processed
                metrics['elapsed_seconds'] = elapsed_seconds
                metrics['frames_per_second'] = frames_processed / elapsed_seconds if elapsed_seconds > 0 else 0
                metrics['gb_per_second'] = gb_processed / elapsed_seconds if elapsed_seconds > 0 else 0
                metrics['samples_per_second'] = (frames_processed * samples_per_batch) / elapsed_seconds if elapsed_seconds > 0 else 0

                if self.config.measure_memory_bandwidth:
                    metrics.update(self._calculate_memory_bandwidth(bytes_processed, elapsed_seconds, initial_mem_mb))
                if self.config.measure_pcie_bandwidth:
                    metrics.update(self._calculate_pcie_bandwidth(bytes_processed, elapsed_seconds))
                if self.resource_samples:
                    metrics.update(self._summarize_resource_usage())

            return metrics

    def teardown(self) -> None:
        """Clean up resources (NVTX-instrumented)."""
        with teardown_range("ThroughputBenchmark.teardown"):
            if self.engine:
                self.engine.close()
                self.engine = None
            self.test_data = None
            self.resource_samples = []
            gc.collect()

    def _sample_resources(self) -> None:
        """Sample current resource usage."""
        # Skip resource sampling if all monitoring is disabled
        if not (self.config.monitor_gpu_utilization or
                self.config.monitor_temperature or
                self.config.monitor_power):
            return

        try:
            from sigtekx.utils import device_info
            info = device_info()

            sample: dict[str, Any] = {
                'timestamp': time.perf_counter(),
                'memory_used_mb': float(info.get('memory_total_mb', 0) or 0) - float(info.get('memory_free_mb', 0) or 0),
                'gpu_utilization': float(info.get('utilization_gpu', 0) or 0),
                'memory_utilization': float(info.get('utilization_memory', 0) or 0),
                'temperature_c': float(info.get('temperature_c', 0) or 0),
                'power_w': float(info.get('power_w', 0) or 0)
            }
            self.resource_samples.append(sample)
        except Exception as e:
            logger.debug(f"Resource sampling failed: {e}")

    def _calculate_memory_bandwidth(
        self,
        bytes_processed: int,
        elapsed_seconds: float,
        initial_mem_mb: int
    ) -> dict[str, float]:
        """Calculate memory bandwidth utilization."""
        current_mem_mb, total_mem_mb = get_memory_usage()

        # Theoretical peak bandwidth (estimate based on GPU)
        # This would ideally come from device properties
        theoretical_bandwidth_gbs = 500  # Example: 500 GB/s for modern GPU

        # Calculate actual bandwidth
        # Factor of 2 for read + write
        actual_bandwidth_gbs = (bytes_processed * 2) / (elapsed_seconds * 1024**3)

        return {
            'memory_bandwidth_gbs': actual_bandwidth_gbs,
            'memory_bandwidth_utilization': actual_bandwidth_gbs / theoretical_bandwidth_gbs,
            'memory_allocated_mb': current_mem_mb - initial_mem_mb,
            'memory_total_mb': total_mem_mb
        }

    def _calculate_pcie_bandwidth(
        self,
        bytes_processed: int,
        elapsed_seconds: float
    ) -> dict[str, float]:
        """Calculate PCIe bandwidth utilization."""
        # PCIe bandwidth for H2D + D2H transfers
        # Assuming PCIe 3.0 x16: ~16 GB/s theoretical
        theoretical_pcie_bandwidth_gbs = 16.0

        # Actual transfer (input + output)
        pcie_bytes = bytes_processed * 2  # Approximate
        actual_pcie_bandwidth_gbs = pcie_bytes / (elapsed_seconds * 1024**3)

        return {
            'pcie_bandwidth_gbs': actual_pcie_bandwidth_gbs,
            'pcie_bandwidth_utilization': actual_pcie_bandwidth_gbs / theoretical_pcie_bandwidth_gbs
        }

    def _summarize_resource_usage(self) -> dict[str, float]:
        """Summarize resource usage statistics."""
        if not self.resource_samples:
            return {}

        gpu_utils = [s['gpu_utilization'] for s in self.resource_samples if s['gpu_utilization'] is not None]
        mem_utils = [s['memory_utilization'] for s in self.resource_samples if s['memory_utilization'] is not None]
        temps = [s['temperature_c'] for s in self.resource_samples if s['temperature_c'] is not None]
        powers = [s['power_w'] for s in self.resource_samples if s['power_w'] is not None]

        summary = {}

        if gpu_utils:
            summary['gpu_utilization_mean'] = np.mean(gpu_utils)
            summary['gpu_utilization_max'] = np.max(gpu_utils)

        if mem_utils:
            summary['memory_utilization_mean'] = np.mean(mem_utils)
            summary['memory_utilization_max'] = np.max(mem_utils)

        if temps:
            summary['temperature_mean_c'] = np.mean(temps)
            summary['temperature_max_c'] = np.max(temps)

        if powers:
            summary['power_mean_w'] = np.mean(powers)
            summary['power_max_w'] = np.max(powers)
            t_end = float(self.resource_samples[-1]['timestamp'])
            t_start = float(self.resource_samples[0]['timestamp'])
            summary['energy_consumed_wh'] = (np.mean(powers) * (t_end - t_start)) / 3600

        return summary


class ScalingBenchmark(ThroughputBenchmark):
    """
    Benchmark for analyzing throughput scaling characteristics.

    Tests how throughput scales with batch size, FFT size, and other parameters
    to identify optimal configurations and bottlenecks.
    """

    def __init__(self, config: ThroughputBenchmarkConfig | None = None):
        super().__init__(config)
        self.scaling_results: list[dict[str, Any]] = []

    def run_scaling_analysis(self) -> dict[str, Any]:
        """Run comprehensive scaling analysis."""
        results = {
            'batch_scaling': self._test_batch_scaling(),
            'nfft_scaling': self._test_nfft_scaling(),
            'combined_scaling': self._test_combined_scaling()
        }

        # Identify optimal configuration
        results['optimal_config'] = self._find_optimal_configuration()

        return results

    def _test_batch_scaling(self) -> dict[str, Any]:
        """Test throughput scaling with batch size."""
        logger.info("Testing channel count scaling...")

        channel_results = []
        base_nfft = 2048  # Fixed FFT size

        for num_channels in self.config.test_channel_counts:
            # Create config for this channel count
            test_config = EngineConfig(
                nfft=base_nfft,
                channels=num_channels,
                warmup_iters=5
            )

            # Run throughput test
            engine = Engine(config=test_config)

            test_data = make_test_batch(
                'noise',
                test_config,
                rng=np.random.default_rng(self.config.seed),
            )

            # Measure throughput
            start = time.perf_counter()
            n_iterations = 100
            for _ in range(n_iterations):
                engine.process(test_data)
            elapsed = time.perf_counter() - start

            samples_per_second = (n_iterations * base_nfft * num_channels) / elapsed

            channel_results.append({
                'channels': num_channels,
                'throughput_msps': samples_per_second / 1e6,
                'time_per_batch_ms': (elapsed / n_iterations) * 1000
            })

            engine.close()

            logger.info(f"  Channels {num_channels}: {samples_per_second/1e6:.2f} MS/s")

        return {
            'results': channel_results,
            'optimal_channels': max(channel_results, key=lambda x: x['throughput_msps'])['channels']
        }

    def _test_nfft_scaling(self) -> dict[str, Any]:
        """Test throughput scaling with FFT size."""
        logger.info("Testing FFT size scaling...")

        nfft_results = []
        base_batch = 8  # Fixed batch size

        for nfft_size in self.config.test_nfft_sizes:
            # Create config for this FFT size
            test_config = EngineConfig(
                nfft=nfft_size,
                channels=base_batch,
                warmup_iters=5
            )

            # Run throughput test
            engine = Engine(config=test_config)

            test_data = make_test_batch(
                'noise',
                test_config,
                rng=np.random.default_rng(self.config.seed),
            )

            # Measure throughput
            start = time.perf_counter()
            n_iterations = 100
            for _ in range(n_iterations):
                engine.process(test_data)
            elapsed = time.perf_counter() - start

            samples_per_second = (n_iterations * nfft_size * base_batch) / elapsed

            nfft_results.append({
                'nfft_size': nfft_size,
                'throughput_msps': samples_per_second / 1e6,
                'time_per_frame_ms': (elapsed / n_iterations) * 1000
            })

            engine.close()

            logger.info(f"  NFFT {nfft_size}: {samples_per_second/1e6:.2f} MS/s")

        return {
            'results': nfft_results,
            'optimal_nfft': max(nfft_results, key=lambda x: x['throughput_msps'])['nfft_size']
        }

    def _test_combined_scaling(self) -> dict[str, Any]:
        """Test combined parameter scaling."""
        logger.info("Testing combined parameter scaling...")

        # Test subset of combinations
        test_combinations = [
            (256, 1), (256, 8), (256, 32),
            (1024, 1), (1024, 8), (1024, 32),
            (4096, 1), (4096, 8), (4096, 32)
        ]

        combined_results = []

        for nfft, batch in test_combinations:
            test_config = EngineConfig(
                nfft=nfft,
                channels=batch,
                warmup_iters=5
            )

            engine = Engine(config=test_config)

            test_data = make_test_batch(
                'noise',
                test_config,
                rng=np.random.default_rng(self.config.seed),
            )

            # Measure
            start = time.perf_counter()
            n_iterations = 100
            for _ in range(n_iterations):
                engine.process(test_data)
            elapsed = time.perf_counter() - start

            throughput = (n_iterations * nfft * batch) / elapsed / 1e6

            combined_results.append({
                'nfft': nfft,
                'channels': batch,
                'throughput_msps': throughput
            })

            engine.close()

            logger.info(f"  NFFT={nfft}, Batch={batch}: {throughput:.2f} MS/s")

        return {
            'results': combined_results,
            'optimal': max(combined_results, key=lambda x: x['throughput_msps'])
        }

    def _find_optimal_configuration(self) -> dict[str, Any]:
        """Find optimal configuration based on all tests."""
        # This would analyze all scaling results to find the best config
        return {
            'recommended_nfft': 2048,
            'recommended_batch': 16,
            'expected_throughput_msps': 1000.0
        }


class MemoryStressBenchmark(ThroughputBenchmark):
    """
    Benchmark for stress-testing memory subsystem.

    Tests maximum achievable memory bandwidth and identifies memory bottlenecks.
    """

    def execute_iteration(self) -> dict[str, float]:
        """Execute memory stress test."""
        metrics = super().execute_iteration()

        # Additional memory stress metrics
        metrics.update(self._test_memory_patterns())

        return metrics

    def _test_memory_patterns(self) -> dict[str, float]:
        """Test different memory access patterns."""
        results = {}

        # Sequential access pattern (already tested in base)

        # Random access pattern simulation
        # This would require custom kernels to truly test
        results['random_access_penalty'] = 1.0  # Placeholder

        # Strided access pattern
        results['strided_access_penalty'] = 1.0  # Placeholder

        return results


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Throughput benchmark')
    parser.add_argument('--mode', choices=['throughput', 'scaling', 'memory'],
                       default='throughput', help='Benchmark mode')
    parser.add_argument('--duration', type=float, default=10.0,
                       help='Test duration in seconds')
    parser.add_argument('--output', default=None,
                       help='Output file (defaults under benchmark_results/throughput)')

    args = parser.parse_args()

    config = ThroughputBenchmarkConfig(
        name=f'throughput_{args.mode}',
        test_duration_s=args.duration,
        iterations=1  # Single sustained test
    )

    if args.mode == 'throughput':
        benchmark = ThroughputBenchmark(config)
        result = benchmark.run()
    elif args.mode == 'scaling':
        benchmark = ScalingBenchmark(config)
        result = benchmark.run()
        scaling_analysis = benchmark.run_scaling_analysis()
        result.metadata['scaling_analysis'] = scaling_analysis
    else:  # memory
        benchmark = MemoryStressBenchmark(config)
        result = benchmark.run()

    # Save results
    from sigtekx.benchmarks.base import save_benchmark_results
    if args.output:
        save_benchmark_results(result, args.output)
    else:
        from datetime import datetime

        base_dir = get_benchmark_run_dir('throughput')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        mode_label = 'throughput' if args.mode == 'throughput' else f"throughput_{args.mode}"
        filename = f"{normalize_benchmark_name(mode_label)}_{timestamp}.json"
        save_benchmark_results(result, base_dir / filename)

    # Print summary
    def _mean_of(stats: dict, key: str, default: float = 0.0) -> float:
        val = stats.get(key, default)
        if isinstance(val, dict):
            return float(val.get('mean', default))
        try:
            return float(val)
        except Exception:
            return float(default)

    print("\nThroughput Results:")
    fps = _mean_of(result.statistics, 'frames_per_second', 0.0)
    gbs = _mean_of(result.statistics, 'gb_per_second', 0.0)
    sps = _mean_of(result.statistics, 'samples_per_second', 0.0)
    print(f"  Frames/second: {fps:.1f}")
    print(f"  GB/second: {gbs:.2f}")
    print(f"  MS/second: {sps/1e6:.2f}")
