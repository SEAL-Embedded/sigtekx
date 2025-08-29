# python/src/ionosense_hpc/utils/signals.py
"""
Signal generation and I/O utilities for testing and validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, Literal, Optional, Tuple

import numpy as np
from numpy.typing import NDArray

# Define literal types for valid window functions
WindowFunction = Literal['hann', 'hamming', 'blackman', 'bartlett', 'kaiser', 'rectangular']


@dataclass(frozen=True)
class SignalParameters:
    """
    Immutable parameters for generating synthetic dual-channel signals.

    Attributes:
        sample_rate: The sampling rate in Hz.
        duration: The signal duration in seconds.
        frequencies: A tuple of (channel_1_freq_hz, channel_2_freq_hz).
        amplitudes: A tuple of (channel_1_amplitude, channel_2_amplitude).
        noise_level: Standard deviation of Gaussian noise to add to the signal.
        dtype: The numpy data type for the signal (e.g., np.float32).
    """
    sample_rate: int = 100_000
    duration: float = 1.0
    frequencies: Tuple[float, float] = (7000.0, 1000.0)
    amplitudes: Tuple[float, float] = (1.0, 1.0)
    noise_level: float = 0.01
    dtype: np.dtype = np.float32


def generate_test_signal(
    params: SignalParameters | None = None,
) -> Dict[str, NDArray[np.float32]]:
    """
    Generates a dual-channel test signal based on the provided parameters.

    Args:
        params: A SignalParameters object. If None, default parameters are used.

    Returns:
        A dictionary with 'ch1' and 'ch2' keys, each containing a NumPy array
        representing the time-domain signal.
    """
    if params is None:
        params = SignalParameters()

    n_samples = int(params.sample_rate * params.duration)
    t = np.arange(n_samples, dtype=params.dtype) / params.sample_rate

    # Generate pure tones for each channel
    ch1 = params.amplitudes[0] * np.sin(2 * np.pi * params.frequencies[0] * t)
    ch2 = params.amplitudes[1] * np.sin(2 * np.pi * params.frequencies[1] * t)

    # Add Gaussian noise if requested
    if params.noise_level > 0:
        noise_gen = np.random.default_rng()
        ch1 += noise_gen.normal(scale=params.noise_level, size=n_samples)
        ch2 += noise_gen.normal(scale=params.noise_level, size=n_samples)

    return {"ch1": ch1.astype(params.dtype), "ch2": ch2.astype(params.dtype)}


def apply_window(
    signal: NDArray[np.float32],
    window_type: WindowFunction = 'hann',
) -> NDArray[np.float32]:
    """
    Applies a window function to a signal.

    This is a CPU-based operation, typically used for pre-processing or
    validation. The main HPC pipeline applies the window on the GPU.

    Args:
        signal: The input signal as a 1D NumPy array.
        window_type: The type of window function to apply.

    Returns:
        The windowed signal.
    """
    n_samples = len(signal)
    
    # Using a dictionary lookup is a clean way to handle multiple cases
    window_funcs = {
        'hann': np.hanning,
        'hamming': np.hamming,
        'blackman': np.blackman,
        'bartlett': np.bartlett,
        'kaiser': lambda size: np.kaiser(size, beta=14), # beta=14 is a common choice
        'rectangular': np.ones,
    }

    if window_type not in window_funcs:
        raise ValueError(f"Unknown window type: '{window_type}'. "
                         f"Valid options are: {list(window_funcs.keys())}")

    window = window_funcs[window_type](n_samples).astype(signal.dtype)
    return signal * window

