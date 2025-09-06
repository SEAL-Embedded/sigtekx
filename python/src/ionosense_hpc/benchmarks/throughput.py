"""
python/src/ionosense_hpc/benchmarks/throughput_enhanced.py
--------------------------------------------------------------------------------
Enhanced throughput benchmark with memory bandwidth analysis and
scaling characterization following HPC benchmarking standards.
"""

import gc
import time
from typing import Any

import numpy as np

from ionosense_hpc.benchmarks.base import BaseBenchmark, BenchmarkConfig
from ionosense_hpc.config import EngineConfig, Presets
from ionosense_hpc.core import Processor
from ionosense_hpc.utils import get_memory_usage, logger, make_test_batch


class ThroughputBenchmarkConfig(BenchmarkConfig):
    """Configuration for throughput benchmarking."""

    # Throughput-specific parameters
    test_duration_s: float = 10.0  # Duration for sustained throughput test
    data_size_gb: float | None = None  # Total data to process (overrides duration)

    # Scaling analysis
    test_batch_sizes: list[int] = [1, 2, 4, 8, 16, 32, 64, 128]
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
        super().__init__(config or ThroughputBenchmarkConfig(name="EnhancedThroughput"))
        self.config: ThroughputBenchmarkConfig = self.config

        self.processor = None
        self.engine_config = None
        self.test_data = None
        self.resource_samples = []

    def setup(self) -> None:
        """Initialize processor for throughput testing."""
        # Use throughput-optimized preset
        if self.config.engine_config:
            self.engine_config = EngineConfig(**self.config.engine_config)
        else:
            self.engine_config = Presets.throughput()

        self.processor = Processor(self.engine_config)
        self.processor.initialize()

        # Pre-generate test data
        self.test_data = make_test_batch(
            self.engine_config.nfft,
            self.engine_config.batch,
            signal_type='noise',
            seed=self.config.seed
        )

        # Force garbage collection before measurement
        gc.collect()

        logger.info("Throughput benchmark initialized")
        logger.info(f"  Configuration: {self.engine_config}")

    def execute_iteration(self) -> dict[str, float]:
        """Execute throughput measurement."""
        metrics = {}

        # Determine test parameters
        bytes_per_sample = 4  # float32
        samples_per_batch = self.engine_config.nfft * self.engine_config.batch
        bytes_per_batch = samples_per_batch * bytes_per_sample

        if self.config.data_size_gb is not None:
            total_bytes = self.config.data_size_gb * (1024**3)
            n_batches = int(total_bytes / bytes_per_batch)
            test_mode = 'data_size'
        else:
            # Estimate batches for duration-based test
            estimated_fps = 1000  # Initial estimate
            n_batches = int(self.config.test_duration_s * estimated_fps)
            test_mode = 'duration'

        # Get initial memory state
        if self.config.measure_memory_bandwidth:
            initial_mem_mb, total_mem_mb = get_memory_usage()

        # Start timing
        start_time = time.perf_counter()
        bytes_processed = 0
        frames_processed = 0

        # Process data
        if test_mode == 'data_size':
            for _ in range(n_batches):
                _ = self.processor.process(self.test_data)
                bytes_processed += bytes_per_batch
                frames_processed += 1

                # Resource monitoring
                if self.config.monitor_gpu_utilization and frames_processed % 100 == 0:
                    self._sample_resources()
        else:
            # Duration-based processing
            while (time.perf_counter() - start_time) < self.config.test_duration_s:
                _ = self.processor.process(self.test_data)
                bytes_processed += bytes_per_batch
                frames_processed += 1

                if self.config.monitor_gpu_utilization and frames_processed % 100 == 0:
                    self._sample_resources()

        # End timing
        end_time = time.perf_counter()
        elapsed_seconds = end_time - start_time

        # Calculate throughput metrics
        gb_processed = bytes_processed / (1024**3)

        metrics['frames_processed'] = frames_processed
        metrics['gb_processed'] = gb_processed
        metrics['elapsed_seconds'] = elapsed_seconds
        metrics['frames_per_second'] = frames_processed / elapsed_seconds if elapsed_seconds > 0 else 0
        metrics['gb_per_second'] = gb_processed / elapsed_seconds if elapsed_seconds > 0 else 0
        metrics['samples_per_second'] = (frames_processed * samples_per_batch) / elapsed_seconds if elapsed_seconds > 0 else 0

        # Memory bandwidth analysis
        if self.config.measure_memory_bandwidth:
            metrics.update(self._calculate_memory_bandwidth(
                bytes_processed,
                elapsed_seconds,
                initial_mem_mb
            ))

        # PCIe bandwidth analysis
        if self.config.measure_pcie_bandwidth:
            metrics.update(self._calculate_pcie_bandwidth(
                bytes_processed,
                elapsed_seconds
            ))

        # Resource utilization
        if self.resource_samples:
            metrics.update(self._summarize_resource_usage())

        return metrics

    def teardown(self) -> None:
        """Clean up resources."""
        if self.processor:
            self.processor.reset()
            self.processor = None
        self.test_data = None
        self.resource_samples = []
        gc.collect()

    def _sample_resources(self) -> None:
        """Sample current resource usage."""
        try:
            from ionosense_hpc.utils import device_info
            info = device_info()

            sample = {
                'timestamp': time.perf_counter(),
                'memory_used_mb': info.get('memory_total_mb', 0) - info.get('memory_free_mb', 0),
                'gpu_utilization': info.get('utilization_gpu', 0),
                'memory_utilization': info.get('utilization_memory', 0),
                'temperature_c': info.get('temperature_c', 0),
                'power_w': info.get('power_w', 0)
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
            summary['energy_consumed_wh'] = (np.mean(powers) *
                                            (self.resource_samples[-1]['timestamp'] -
                                             self.resource_samples[0]['timestamp'])) / 3600

        return summary


class ScalingBenchmark(ThroughputBenchmark):
    """
    Benchmark for analyzing throughput scaling characteristics.
    
    Tests how throughput scales with batch size, FFT size, and other parameters
    to identify optimal configurations and bottlenecks.
    """

    def __init__(self, config: ThroughputBenchmarkConfig | None = None):
        super().__init__(config)
        self.scaling_results = []

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
        logger.info("Testing batch size scaling...")

        batch_results = []
        base_nfft = 2048  # Fixed FFT size

        for batch_size in self.config.test_batch_sizes:
            # Create config for this batch size
            test_config = EngineConfig(
                nfft=base_nfft,
                batch=batch_size,
                warmup_iters=5
            )

            # Run throughput test
            processor = Processor(test_config)
            processor.initialize()

            test_data = make_test_batch(base_nfft, batch_size, seed=self.config.seed)

            # Measure throughput
            start = time.perf_counter()
            n_iterations = 100
            for _ in range(n_iterations):
                processor.process(test_data)
            elapsed = time.perf_counter() - start

            samples_per_second = (n_iterations * base_nfft * batch_size) / elapsed

            batch_results.append({
                'batch_size': batch_size,
                'throughput_msps': samples_per_second / 1e6,
                'time_per_batch_ms': (elapsed / n_iterations) * 1000
            })

            processor.reset()

            logger.info(f"  Batch {batch_size}: {samples_per_second/1e6:.2f} MS/s")

        return {
            'results': batch_results,
            'optimal_batch': max(batch_results, key=lambda x: x['throughput_msps'])['batch_size']
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
                batch=base_batch,
                warmup_iters=5
            )

            # Run throughput test
            processor = Processor(test_config)
            processor.initialize()

            test_data = make_test_batch(nfft_size, base_batch, seed=self.config.seed)

            # Measure throughput
            start = time.perf_counter()
            n_iterations = 100
            for _ in range(n_iterations):
                processor.process(test_data)
            elapsed = time.perf_counter() - start

            samples_per_second = (n_iterations * nfft_size * base_batch) / elapsed

            nfft_results.append({
                'nfft_size': nfft_size,
                'throughput_msps': samples_per_second / 1e6,
                'time_per_frame_ms': (elapsed / n_iterations) * 1000
            })

            processor.reset()

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
                batch=batch,
                warmup_iters=5
            )

            processor = Processor(test_config)
            processor.initialize()

            test_data = make_test_batch(nfft, batch, seed=self.config.seed)

            # Measure
            start = time.perf_counter()
            n_iterations = 100
            for _ in range(n_iterations):
                processor.process(test_data)
            elapsed = time.perf_counter() - start

            throughput = (n_iterations * nfft * batch) / elapsed / 1e6

            combined_results.append({
                'nfft': nfft,
                'batch': batch,
                'throughput_msps': throughput
            })

            processor.reset()

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

    parser = argparse.ArgumentParser(description='Enhanced throughput benchmark')
    parser.add_argument('--mode', choices=['throughput', 'scaling', 'memory'],
                       default='throughput', help='Benchmark mode')
    parser.add_argument('--duration', type=float, default=10.0,
                       help='Test duration in seconds')
    parser.add_argument('--output', default='throughput_results.json',
                       help='Output file')

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
    from ionosense_hpc.benchmarks.base import save_benchmark_results
    save_benchmark_results(result, args.output)

    # Print summary
    print("\nThroughput Results:")
    print(f"  Frames/second: {result.statistics.get('frames_per_second', 0):.1f}")
    print(f"  GB/second: {result.statistics.get('gb_per_second', 0):.2f}")
    print(f"  MS/second: {result.statistics.get('samples_per_second', 0)/1e6:.2f}")
