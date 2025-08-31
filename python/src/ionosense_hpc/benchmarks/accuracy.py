"""
ionosense_hpc.benchmarks.accuracy
---------------------------------
Benchmark for verifying the numerical accuracy of the CUDA FFT engine
against a trusted reference implementation (NumPy).

This is a critical component for ensuring IEEE-level scientific validity
and reproducibility.
"""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .base import BenchmarkBase, BenchmarkResult
from ..core.fft_processor import FFTProcessor
from ..utils.signals import generate_test_signal, apply_window
from ..utils.console import print_header, print_separator, safe_print

def mean_squared_error(y_true: NDArray, y_pred: NDArray) -> float:
    """Calculates the Mean Squared Error."""
    return np.mean(np.square(y_true.astype(np.float64) - y_pred.astype(np.float64)))

class AccuracyBenchmark(BenchmarkBase):
    """
    Compares GPU FFT results against a NumPy reference to ensure correctness.
    """

    def run_single(self, fft_size: int, batch_size: int) -> dict:
        """
        Runs a single accuracy test for a given configuration.

        Args:
            fft_size: The FFT length to test.
            batch_size: The number of simultaneous signals to test.

        Returns:
            A dictionary containing accuracy metrics.
        """
        if self.config.verbose:
            safe_print(f"  Verifying: FFT Size={fft_size}, Batch Size={batch_size}")

        # 1. Initialize the GPU processor
        processor = FFTProcessor(
            fft_size=fft_size,
            batch_size=batch_size,
            window='hann',
            use_graphs=self.config.use_graphs
        )

        # 2. Generate a reproducible test signal
        signals = generate_test_signal(
            sample_rate=100_000,
            duration=(fft_size / 100_000) * 2, # Ensure enough samples
            frequencies=[1337.0, 7331.0],
            noise_level=0.1,
            seed=42 # for reproducibility
        )
        input_signals = [signals[f'ch{i+1}'][:fft_size] for i in range(batch_size)]

        # 3. Run GPU implementation
        gpu_results = processor.process(*input_signals)

        # 4. Run CPU reference implementation
        cpu_results = []
        for signal_chunk in input_signals:
            windowed_signal = apply_window(signal_chunk, window_type='hann')
            spectrum = np.fft.rfft(windowed_signal)
            magnitude = np.abs(spectrum)
            cpu_results.append(magnitude)
        cpu_results = np.array(cpu_results, dtype=np.float32)

        # 5. Calculate and return accuracy metrics
        max_abs_error = np.max(np.abs(cpu_results - gpu_results))
        mse = mean_squared_error(cpu_results, gpu_results)
        rms_error = np.sqrt(mse)

        return {
            "max_absolute_error": float(max_abs_error),
            "mean_squared_error": mse,
            "root_mean_squared_error": rms_error,
            "passed": bool(max_abs_error < 1e-4) # IEEE float32 precision tolerance
        }
