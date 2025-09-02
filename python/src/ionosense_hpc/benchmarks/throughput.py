"""Throughput benchmarking for sustained processing performance."""

import json
import time
from typing import Any

import numpy as np

from ..config import EngineConfig, Presets
from ..core import Processor
from ..utils import get_memory_usage, logger, make_test_batch


def benchmark_throughput(
    config: EngineConfig | None = None,
    duration_seconds: float = 10.0,
    data_size_mb: float | None = None,
    report_memory: bool = True
) -> dict[str, Any]:
    """Benchmark sustained throughput performance.
    
    Args:
        config: Engine configuration (None for throughput preset)
        duration_seconds: Test duration if data_size_mb not specified
        data_size_mb: Total data to process in MB (overrides duration)
        report_memory: Include memory usage statistics
        
    Returns:
        Dictionary with throughput metrics
    """
    if config is None:
        config = Presets.throughput()

    bytes_per_sample = 4  # float32
    samples_per_batch = config.nfft * config.batch
    bytes_per_batch = samples_per_batch * bytes_per_sample
    mb_per_batch = bytes_per_batch / (1024 * 1024)

    if data_size_mb is not None:
        n_batches = int(data_size_mb / mb_per_batch)
        test_mode = f"{data_size_mb:.1f} MB data"
    else:
        # A rough estimate for progress, the loop condition is time-based
        est_fps = 1000
        n_batches = int(duration_seconds * est_fps)
        test_mode = f"{duration_seconds:.1f} seconds"

    logger.info(f"Starting throughput benchmark: {test_mode}")
    logger.info(f"  Batch size: {samples_per_batch} samples ({mb_per_batch:.2f} MB)")

    test_data = make_test_batch(config.nfft, config.batch, signal_type='noise', seed=42)

    if report_memory:
        initial_mem_mb, total_mem_mb = get_memory_usage()

    with Processor(config) as proc:
        start_time = time.perf_counter()
        bytes_processed = 0
        frames_processed = 0

        if data_size_mb is not None:
            for _ in range(n_batches):
                _ = proc.process(test_data)
                bytes_processed += bytes_per_batch
                frames_processed += 1
        else:
            while (time.perf_counter() - start_time) < duration_seconds:
                _ = proc.process(test_data)
                bytes_processed += bytes_per_batch
                frames_processed += 1

        end_time = time.perf_counter()
        elapsed_seconds = end_time - start_time

        if report_memory:
            final_mem_mb, _ = get_memory_usage()

    mb_processed = bytes_processed / (1024 * 1024)
    gb_processed = bytes_processed / (1024 ** 3)

    results = {
        'config': config.model_dump(),
        'runtime': {
            'elapsed_seconds': elapsed_seconds,
            'frames_processed': frames_processed,
            'gb_processed': gb_processed
        },
        'throughput': {
            'frames_per_second': frames_processed / elapsed_seconds,
            'gb_per_second': gb_processed / elapsed_seconds,
            'samples_per_second': (frames_processed * samples_per_batch) / elapsed_seconds
        }
    }

    if report_memory:
        results['memory'] = {
            'initial_mb': initial_mem_mb,
            'final_mb': final_mem_mb,
            'delta_mb': final_mem_mb - initial_mem_mb,
            'total_available_mb': total_mem_mb
        }

    return results


def benchmark_batch_scaling(
    nfft: int = 2048,
    batch_sizes: list | None = None,
    n_iterations: int = 100
) -> dict[str, Any]:
    """Benchmark performance scaling with batch size.
    
    Args:
        nfft: FFT size to test
        batch_sizes: List of batch sizes to test
        n_iterations: Iterations per batch size
        
    Returns:
        Dictionary with scaling analysis
    """
    if batch_sizes is None:
        batch_sizes = [1, 2, 4, 8, 16, 32, 64]

    logger.info(f"Starting batch scaling benchmark: nfft={nfft}")

    results = {
        'nfft': nfft,
        'batch_sizes': batch_sizes,
        'throughput_msps': [],
        'latency_us': [],
        'efficiency_percent': []
    }

    base_throughput_per_channel = None

    for batch in batch_sizes:
        logger.info(f"  Testing batch={batch}...")

        config = EngineConfig(nfft=nfft, batch=batch, warmup_iters=10)
        test_data = make_test_batch(nfft, batch, seed=42)

        with Processor(config) as proc:
            latencies = []
            # Warmup is handled by Processor, run benchmark iterations
            for _ in range(n_iterations):
                proc.process(test_data)
                latencies.append(proc.get_stats()['latency_us'])
            avg_latency_us = np.mean(latencies)

        total_samples = nfft * batch * n_iterations
        total_time_s = sum(latencies) / 1e6
        throughput_sps = total_samples / total_time_s if total_time_s > 0 else 0

        results['throughput_msps'].append(throughput_sps / 1e6)
        results['latency_us'].append(avg_latency_us)

        if base_throughput_per_channel is None and batch > 0:
            base_throughput_per_channel = throughput_sps / batch
            efficiency = 100.0
        elif base_throughput_per_channel is not None:
            expected_throughput = base_throughput_per_channel * batch
            efficiency = (throughput_sps / expected_throughput) * 100 if expected_throughput > 0 else 0
        else:
            efficiency = 0.0

        results['efficiency_percent'].append(efficiency)

        logger.info(f"    Throughput: {throughput_sps/1e6:.2f} MS/s, Latency: {avg_latency_us:.1f} us, Efficiency: {efficiency:.1f}%")

    return results

if __name__ == '__main__':
    print("Running Throughput Benchmark...")
    throughput_results = benchmark_throughput()
    print(json.dumps(throughput_results, indent=2, default=str))

    print("\nRunning Batch Scaling Benchmark...")
    scaling_results = benchmark_batch_scaling()
    print(json.dumps(scaling_results, indent=2, default=str))
