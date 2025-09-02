"""Throughput benchmarking for sustained processing performance."""

import time
import json
import argparse
from typing import Dict, Any, Optional

import numpy as np

from ..core import Processor
from ..config import EngineConfig, Presets
from ..utils import make_test_batch, logger, get_memory_usage


def benchmark_throughput(
    config: Optional[EngineConfig] = None,
    duration_seconds: float = 10.0
) -> Dict[str, Any]:
    """Benchmark sustained throughput performance."""
    if config is None:
        config = Presets.throughput()

    samples_per_batch = config.nfft * config.batch
    bytes_per_batch = samples_per_batch * 4  # float32

    logger.info(f"Starting throughput benchmark: {duration_seconds} seconds")
    
    test_batches = [make_test_batch(config.nfft, config.batch, signal_type='noise', seed=i) for i in range(10)]
    
    with Processor(config) as proc:
        start_time = time.perf_counter()
        frames_processed = 0
        while (time.perf_counter() - start_time) < duration_seconds:
            _ = proc.process(test_batches[frames_processed % 10])
            frames_processed += 1
        elapsed_seconds = time.perf_counter() - start_time

    gb_processed = (frames_processed * bytes_per_batch) / (1024 ** 3)
    
    results = {
        'config': { 'nfft': config.nfft, 'batch': config.batch },
        'runtime': { 'elapsed_seconds': elapsed_seconds, 'frames_processed': frames_processed },
        'throughput': {
            'frames_per_second': frames_processed / elapsed_seconds,
            'gb_per_second': gb_processed / elapsed_seconds,
        }
    }
    return results

def benchmark_batch_scaling(
    nfft: int = 2048,
    batch_sizes: Optional[list] = None,
) -> Dict[str, Any]:
    """Benchmark performance scaling with batch size."""
    if batch_sizes is None:
        batch_sizes = [1, 2, 4, 8, 16, 32]
    
    logger.info(f"Starting batch scaling benchmark: nfft={nfft}")
    
    results = { 'nfft': nfft, 'batch_sizes': batch_sizes, 'throughput': [], 'efficiency': [] }
    baseline_throughput = None

    for batch in batch_sizes:
        config = EngineConfig(nfft=nfft, batch=batch)
        test_data = make_test_batch(nfft, batch, seed=42)
        with Processor(config) as proc:
            start_time = time.perf_counter()
            # A fixed number of iterations for a stable measurement
            n_iter = max(10, 1000 // batch) 
            for _ in range(n_iter):
                _ = proc.process(test_data)
            elapsed = time.perf_counter() - start_time
        
        throughput = (nfft * batch * n_iter) / elapsed
        results['throughput'].append(throughput)
        
        if baseline_throughput is None:
            baseline_throughput = throughput / batch
            efficiency = 100.0
        else:
            efficiency = (throughput / (baseline_throughput * batch)) * 100
        results['efficiency'].append(efficiency)

    return results

# --- SCRIPT ENTRY POINT ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run throughput benchmarks.")
    parser.add_argument("-d", "--duration", type=float, default=10.0, help="Duration in seconds for throughput test.")
    parser.add_argument("--preset", type=str, default="throughput", help="Configuration preset to use.")
    args = parser.parse_args()

    try:
        config = getattr(Presets, args.preset)()
    except AttributeError:
        print(f"Error: Preset '{args.preset}' not found.")
        exit(1)

    print("--- Running Throughput Benchmark ---")
    throughput_results = benchmark_throughput(config, duration_seconds=args.duration)
    print(json.dumps(throughput_results, indent=2))

    print("\n--- Running Batch Scaling Benchmark ---")
    scaling_results = benchmark_batch_scaling(nfft=config.nfft)
    print(json.dumps(scaling_results, indent=2))
