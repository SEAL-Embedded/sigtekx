"""Latency benchmarking for the signal processing pipeline."""

import time
from typing import Dict, Any, Optional
import json
import numpy as np

from ..core import Processor
from ..config import EngineConfig, Presets
from ..utils import make_test_batch, logger


def benchmark_latency(
    config: Optional[EngineConfig] = None,
    n_iterations: int = 1000,
    warmup_iterations: int = 100,
    signal_type: str = 'sine',
    report_percentiles: bool = True
) -> Dict[str, Any]:
    """Benchmark per-frame processing latency.
    
    Args:
        config: Engine configuration (None for realtime preset)
        n_iterations: Number of benchmark iterations
        warmup_iterations: Additional warmup iterations
        signal_type: Type of test signal
        report_percentiles: Include percentile statistics
        
    Returns:
        Dictionary with latency statistics
    """
    if config is None:
        config = Presets.realtime()
    
    logger.info(f"Starting latency benchmark: {n_iterations} iterations")
    
    test_data = make_test_batch(
        config.nfft,
        config.batch,
        signal_type=signal_type,
        seed=42
    )
    
    with Processor(config) as proc:
        logger.info(f"Running {warmup_iterations} warmup iterations...")
        for _ in range(warmup_iterations):
            proc.process(test_data)
        
        latencies = []
        logger.info("Starting timed iterations...")
        
        for i in range(n_iterations):
            proc.process(test_data)
            stats = proc.get_stats()
            latencies.append(stats['latency_us'])
            
            if (i + 1) % (n_iterations // 10 or 1) == 0:
                logger.debug(f"  Iteration {i + 1}/{n_iterations}")
    
    latencies_np = np.array(latencies)
    results = {
        'config': config.model_dump(),
        'n_iterations': n_iterations,
        'mean_us': float(np.mean(latencies_np)),
        'std_us': float(np.std(latencies_np)),
        'min_us': float(np.min(latencies_np)),
        'max_us': float(np.max(latencies_np)),
    }
    
    if report_percentiles:
        results.update({
            'p50_us': float(np.percentile(latencies_np, 50)),
            'p90_us': float(np.percentile(latencies_np, 90)),
            'p95_us': float(np.percentile(latencies_np, 95)),
            'p99_us': float(np.percentile(latencies_np, 99)),
        })
    
    deadline_us = 200
    misses = np.sum(latencies_np > deadline_us)
    results['deadline_misses'] = int(misses)
    results['deadline_miss_rate'] = float(misses / n_iterations) if n_iterations > 0 else 0
    
    return results


def benchmark_jitter(
    config: Optional[EngineConfig] = None,
    duration_seconds: float = 10.0,
    target_fps: Optional[float] = None
) -> Dict[str, Any]:
    """Benchmark timing jitter for real-time processing."""
    if config is None:
        config = Presets.realtime()
    
    if target_fps is None:
        samples_per_second = config.sample_rate_hz
        samples_per_frame = config.hop_size
        target_fps = samples_per_second / samples_per_frame
    
    target_interval_ms = 1000.0 / target_fps
    
    logger.info(f"Starting jitter benchmark: {duration_seconds}s @ {target_fps:.1f} FPS")
    
    test_data = make_test_batch(config.nfft, config.batch, seed=42)
    
    frame_times = []
    interval_times = []
    
    with Processor(config) as proc:
        start_time = time.perf_counter()
        last_frame_time = start_time
        
        while (time.perf_counter() - start_time) < duration_seconds:
            frame_start = time.perf_counter()
            _ = proc.process(test_data)
            frame_end = time.perf_counter()
            
            frame_time_ms = (frame_end - frame_start) * 1000
            interval_ms = (frame_start - last_frame_time) * 1000
            
            frame_times.append(frame_time_ms)
            if len(frame_times) > 1:
                interval_times.append(interval_ms)
            
            last_frame_time = frame_start
            
            elapsed = (frame_end - frame_start) * 1000
            sleep_time = max(0, target_interval_ms - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time / 1000)
    
    frame_times_np = np.array(frame_times)
    interval_times_np = np.array(interval_times) if interval_times else np.array([0])
    
    results = {
        'duration_s': duration_seconds,
        'target_fps': target_fps,
        'n_frames': len(frame_times),
        'actual_fps': len(frame_times) / duration_seconds if duration_seconds > 0 else 0,
        'frame_time': {
            'mean_ms': float(np.mean(frame_times_np)),
            'std_ms': float(np.std(frame_times_np)),
            'max_ms': float(np.max(frame_times_np))
        },
        'interval': {
            'mean_ms': float(np.mean(interval_times_np)),
            'std_ms': float(np.std(interval_times_np)),
            'jitter_ms': float(np.std(interval_times_np))
        }
    }
    return results

if __name__ == '__main__':
    print("Running Latency Benchmark...")
    latency_results = benchmark_latency()
    print(json.dumps(latency_results, indent=2, default=str))

    print("\nRunning Jitter Benchmark...")
    jitter_results = benchmark_jitter()
    print(json.dumps(jitter_results, indent=2, default=str))

