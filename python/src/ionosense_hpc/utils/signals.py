"""
ionosense_hpc.utils.signals: Signal generation and windowing utilities.

Provides functions for generating test signals and window functions
for validation and benchmarking.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Literal, Optional, Tuple
import numpy as np
from numpy.typing import NDArray

WindowFunction = Literal['hann', 'hamming', 'blackman', 'bartlett', 'kaiser', 'rectangular']


@dataclass(frozen=True)
class SignalParameters:
    """
    Parameters for synthetic signal generation.
    
    Attributes:
        sample_rate: Sampling rate in Hz.
        duration: Signal duration in seconds.
        frequencies: (ch1_freq, ch2_freq) in Hz.
        amplitudes: (ch1_amp, ch2_amp).
        noise_level: Gaussian noise standard deviation.
        phase_offset: Phase offset between channels in radians.
        dtype: NumPy data type (must be float32 for GPU).
    """
    sample_rate: int = 100_000
    duration: float = 1.0
    frequencies: Tuple[float, float] = (7000.0, 1000.0)
    amplitudes: Tuple[float, float] = (1.0, 1.0)
    noise_level: float = 0.01
    phase_offset: float = 0.0
    dtype: np.dtype = np.float32


def generate_test_signal(
    params: Optional[SignalParameters] = None,
    seed: Optional[int] = None
) -> Dict[str, NDArray[np.float32]]:
    """
    Generate dual-channel test signals.
    
    Args:
        params: Signal parameters. Uses defaults if None.
        seed: Random seed for reproducibility.
    
    Returns:
        Dictionary with 'ch1' and 'ch2' arrays.
    
    Example:
        >>> signals = generate_test_signal(seed=42)
        >>> print(f"Generated {len(signals['ch1'])} samples")
    """
    if params is None:
        params = SignalParameters()
    
    n_samples = int(params.sample_rate * params.duration)
    t = np.arange(n_samples, dtype=params.dtype) / params.sample_rate
    
    # Generate pure tones
    ch1 = params.amplitudes[0] * np.sin(2 * np.pi * params.frequencies[0] * t)
    ch2 = params.amplitudes[1] * np.sin(
        2 * np.pi * params.frequencies[1] * t + params.phase_offset
    )
    
    # Add noise if specified
    if params.noise_level > 0:
        rng = np.random.default_rng(seed)
        ch1 += rng.normal(0, params.noise_level, n_samples).astype(params.dtype)
        ch2 += rng.normal(0, params.noise_level, n_samples).astype(params.dtype)
    
    return {
        "ch1": ch1.astype(params.dtype),
        "ch2": ch2.astype(params.dtype)
    }


def create_window(
    window_type: WindowFunction,
    size: int,
    **kwargs
) -> NDArray[np.float32]:
    """
    Create a window function array.
    
    Args:
        window_type: Type of window function.
        size: Window size.
        **kwargs: Additional parameters (e.g., beta for Kaiser).
    
    Returns:
        Window array of shape (size,).
    
    Raises:
        ValueError: If window type is unknown.
    
    Example:
        >>> window = create_window('hann', 4096)
        >>> assert window.shape == (4096,)
    """
    window_funcs = {
        'hann': np.hanning,
        'hamming': np.hamming,
        'blackman': np.blackman,
        'bartlett': np.bartlett,
        'kaiser': lambda n: np.kaiser(n, kwargs.get('beta', 14.0)),
        'rectangular': np.ones,
    }
    
    if window_type not in window_funcs:
        raise ValueError(
            f"Unknown window '{window_type}'. "
            f"Choose from: {list(window_funcs.keys())}"
        )
    
    return window_funcs[window_type](size).astype(np.float32)


def compute_snr(
    signal: NDArray[np.float32],
    noise: NDArray[np.float32]
) -> float:
    """
    Compute signal-to-noise ratio in dB.
    
    Args:
        signal: Clean signal array.
        noise: Noise array.
    
    Returns:
        SNR in decibels.
    """
    signal_power = np.mean(signal ** 2)
    noise_power = np.mean(noise ** 2)
    
    if noise_power == 0:
        return float('inf')
    
    return 10 * np.log10(signal_power / noise_power)


def generate_chirp(
    f0: float,
    f1: float,
    duration: float,
    sample_rate: int = 100_000,
    method: Literal['linear', 'quadratic', 'logarithmic'] = 'linear'
) -> NDArray[np.float32]:
    """
    Generate a frequency sweep signal.
    
    Args:
        f0: Starting frequency in Hz.
        f1: Ending frequency in Hz.
        duration: Sweep duration in seconds.
        sample_rate: Sampling rate in Hz.
        method: Sweep method.
    
    Returns:
        Chirp signal array.
    """
    from scipy.signal import chirp
    
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return chirp(t, f0, duration, f1, method=method).astype(np.float32)