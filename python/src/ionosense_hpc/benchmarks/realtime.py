"""
realtime.py
-----------------------------------------------------------------------------
Simulates a real-time, dual-channel FFT processing scenario to
measure latency and deadline adherence, following RSE/RE standards.
"""
import argparse
import json
import sys
import time
from typing import Any

import numpy as np
from tqdm import tqdm

from ..config import EngineConfig, Presets
from ..core import Processor
from ..utils.logging import logger, setup_logging
from ..utils.profiling import nvtx_range
from ..utils.reporting import print_latency_report
from ..utils.signals import make_test_batch


def benchmark_realtime(config: EngineConfig, duration_seconds: float) -> dict[str, Any]:
    """
    Runs a real-time benchmark with pacing to simulate a real-world stream.
    
    Args:
        config: The engine configuration.
        duration_seconds: The duration of the simulation in seconds.
        
    Returns:
        A dictionary containing benchmark results.
    """
    # Calculate real-time parameters from the configuration
    deadline_ms = config.hop_duration_ms
    deadline_s = deadline_ms / 1000.0
    if deadline_s <= 0:
        raise ValueError("Hop duration must be positive for real-time benchmark.")

    num_frames = int(duration_seconds / deadline_s)

    logger.info(f"Simulating real-time stream for {duration_seconds}s...")
    logger.info(f"  - Frame Deadline: {deadline_ms:.3f} ms")
    logger.info(f"  - Total Frames: {num_frames}")

    latencies_ms = []
    missed_deadlines = 0

    # Use consistent test data for each frame
    test_data = make_test_batch(config.nfft, config.batch, signal_type='noise', seed=42)

    with Processor(config) as proc:
        # Warmup is handled by the Processor's initialization

        t_global_start = time.perf_counter()

        with nvtx_range("realtime_simulation_loop"):
            for i in tqdm(range(num_frames), desc="Real-time Simulation", unit="frame"):
                # Calculate when the next frame of data would be "available"
                target_time = t_global_start + (i + 1) * deadline_s

                # Pacing: Wait until the target time is reached
                # A busy-wait is used for higher timing precision than time.sleep()
                while time.perf_counter() < target_time:
                    pass

                # --- Latency Measurement ---
                with nvtx_range(f"frame_{i}"):
                    t_iter_start = time.perf_counter()

                    proc.process(test_data)

                    t_iter_end = time.perf_counter()

                latency_ms = (t_iter_end - t_iter_start) * 1000.0
                latencies_ms.append(latency_ms)

                if latency_ms > deadline_ms:
                    missed_deadlines += 1

    latencies_arr = np.array(latencies_ms)
    results = {
        'config': config.model_dump(),
        'duration_s': duration_seconds,
        'num_frames': num_frames,
        'deadline_ms': deadline_ms,
        'missed_dl': missed_deadlines,
        'miss_rate': missed_deadlines / num_frames if num_frames > 0 else 0,
        'mean_us': float(np.mean(latencies_arr) * 1000),
        'std_us': float(np.std(latencies_arr) * 1000),
        'min_us': float(np.min(latencies_arr) * 1000),
        'max_us': float(np.max(latencies_arr) * 1000),
        'p50_us': float(np.percentile(latencies_arr, 50) * 1000),
        'p90_us': float(np.percentile(latencies_arr, 90) * 1000),
        'p99_us': float(np.percentile(latencies_arr, 99) * 1000),
    }
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-time FFT Latency and Deadline Adherence Benchmark.")
    parser.add_argument("--preset", type=str, default="realtime", help="Configuration preset to use (e.g., 'realtime', 'profiling').")
    parser.add_argument("-d", "--duration", type=float, default=10.0, help="Benchmark duration in seconds.")
    parser.add_argument("-o", "--output", type=str, help="Optional JSON output file path.")

    args = parser.parse_args()

    setup_logging(level="INFO")

    try:
        # Get configuration from presets
        config_loader = getattr(Presets, args.preset, None)
        if not config_loader:
            logger.error(f"Preset '{args.preset}' not found.")
            sys.exit(1)
        config = config_loader()
    except Exception as e:
        logger.error(f"Failed to load preset '{args.preset}': {e}")
        sys.exit(1)

    # Run the benchmark
    results = benchmark_realtime(config, args.duration)

    # Print the formatted report
    print_latency_report(results, title="Real-time Performance Report")

    if args.output:
        try:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2, default=str)
            logger.info(f"Results saved to {args.output}")
        except OSError as e:
            logger.error(f"Failed to write output file: {e}")
