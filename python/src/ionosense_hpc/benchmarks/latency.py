"""Latency benchmarking for the signal processing pipeline."""

import time
import json
import argparse
from typing import Dict, Any, Optional

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
    """Benchmark per-frame processing latency."""
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
        
        # This direct access is for benchmarking only; avoid in production
        if hasattr(proc, '_engine'):
            proc._engine._frame_count = 0
            proc._engine._total_latency_us = 0.0
        
        latencies = []
        logger.info("Starting timed iterations...")
        
        for i in range(n_iterations):
            _ = proc.process(test_data)
            # In a real scenario, latency would be measured end-to-end
            # Here we use the engine's internal stat for simplicity
            stats = proc._engine.get_stats()
            latencies.append(stats['latency_us'])
    
    latencies = np.array(latencies)
    results = {
        'config': { 'nfft': config.nfft, 'batch': config.batch, 'overlap': config.overlap },
        'n_iterations': n_iterations,
        'mean_us': float(np.mean(latencies)),
        'std_us': float(np.std(latencies)),
        'min_us': float(np.min(latencies)),
        'max_us': float(np.max(latencies)),
    }
    
    if report_percentiles:
        results.update({
            'p50_us': float(np.percentile(latencies, 50)),
            'p90_us': float(np.percentile(latencies, 90)),
            'p99_us': float(np.percentile(latencies, 99)),
        })
    
    return results


def benchmark_jitter(
    config: Optional[EngineConfig] = None,
    duration_seconds: float = 10.0,
    target_fps: Optional[float] = None
) -> Dict[str, Any]:
    """Benchmark timing jitter for real-time processing."""
    # (Implementation remains the same)
    if config is None:
        config = Presets.realtime()
    
    if target_fps is None:
        samples_per_second = config.sample_rate_hz
        samples_per_frame = config.hop_size * config.batch
        target_fps = samples_per_second / samples_per_frame if samples_per_frame > 0 else 0
    
    target_interval_ms = 1000.0 / target_fps if target_fps > 0 else 0
    
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
            
            if target_fps and target_interval_ms > 0:
                elapsed = (frame_end - frame_start) * 1000
                sleep_time = max(0, target_interval_ms - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time / 1000)

    frame_times = np.array(frame_times)
    interval_times = np.array(interval_times) if interval_times else np.array([0])
    
    results = {
        'duration_s': duration_seconds,
        'target_fps': target_fps,
        'n_frames': len(frame_times),
        'frame_time': {
            'mean_ms': float(np.mean(frame_times)),
            'std_ms': float(np.std(frame_times)),
        },
        'interval': {
            'mean_ms': float(np.mean(interval_times)),
            'jitter_ms': float(np.std(interval_times)),
        }
    }
    return results

# --- SCRIPT ENTRY POINT ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run latency and jitter benchmarks.")
    parser.add_argument("-n", "--iterations", type=int, default=1000, help="Number of iterations for latency test.")
    parser.add_argument("-d", "--duration", type=float, default=5.0, help="Duration in seconds for jitter test.")
    parser.add_argument("--preset", type=str, default="realtime", help="Configuration preset to use.")
    args = parser.parse_args()

    try:
        config = getattr(Presets, args.preset)()
    except AttributeError:
        print(f"Error: Preset '{args.preset}' not found.")
        exit(1)

    print("--- Running Latency Benchmark ---")
    latency_results = benchmark_latency(config, n_iterations=args.iterations)
    print(json.dumps(latency_results, indent=2))

    print("\n--- Running Jitter Benchmark ---")
    jitter_results = benchmark_jitter(config, duration_seconds=args.duration)
    print(json.dumps(jitter_results, indent=2))
