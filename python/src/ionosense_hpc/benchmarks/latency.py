"""
ionosense_hpc.benchmarks.latency
--------------------------------
Benchmark for measuring processing latency.

Measures the wall-clock time for individual FFT operations to complete,
focusing on worst-case and percentile latencies, which are critical for
real-time system design.
"""
from __future__ import annotations

import time
import numpy as np

from .base import BenchmarkBase
from ..core.fft_processor import FFTProcessor
from ..utils.console import safe_print

class LatencyBenchmark(BenchmarkBase):
    """
    Measures per-operation latency using high-resolution timers.
    """

    def run_single(self, fft_size: int, batch_size: int) -> dict:
        """
        Runs a latency test for a single configuration.

        Args:
            fft_size: The FFT length to test.
            batch_size: The number of simultaneous signals to test.

        Returns:
            A dictionary containing latency statistics in microseconds.
        """
        if self.config.verbose:
            safe_print(f"  Measuring latency: FFT Size={fft_size}, Batch Size={batch_size}")

        processor = FFTProcessor(
            fft_size=fft_size,
            batch_size=batch_size,
            use_graphs=self.config.use_graphs,
            num_streams=1 # Use 1 stream for clearest latency measurement
        )

        # Prepare a consistent set of input data
        input_signals = [
            np.random.randn(fft_size).astype(np.float32)
            for _ in range(batch_size)
        ]

        # Warmup iterations to ensure caches are hot and GPU is clocked up
        for _ in range(self.config.warmup_iterations):
            processor.process(*input_signals)

        # Measurement loop
        timings_us = np.zeros(self.config.num_iterations)
        for i in range(self.config.num_iterations):
            start_time = time.perf_counter()
            processor.process(*input_signals)
            end_time = time.perf_counter()
            timings_us[i] = (end_time - start_time) * 1_000_000 # microseconds

        # Calculate and return statistics
        return {
            "mean_us": np.mean(timings_us),
            "median_us": np.median(timings_us),
            "std_us": np.std(timings_us),
            "min_us": np.min(timings_us),
            "max_us": np.max(timings_us),
            "p90_us": np.percentile(timings_us, 90),
            "p95_us": np.percentile(timings_us, 95),
            "p99_us": np.percentile(timings_us, 99),
        }
