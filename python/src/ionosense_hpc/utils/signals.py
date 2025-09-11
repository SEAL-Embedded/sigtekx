"""
Signal generation utilities for testing and validation.

This module provides functions for creating various test signals. It leverages
the robust, industry-standard implementations from NumPy and SciPy to ensure
the generated signals are reliable and suitable for validating the signal
processing engine.
"""

from typing import cast

import numpy as np
from numpy.typing import DTypeLike
from scipy import signal as sp_signal


def make_sine(
    frequency: float,
    duration: float,
    sample_rate: int = 48000,
    amplitude: float = 1.0,
    phase: float = 0.0,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """
    Generate a sine wave signal.

    Args:
        frequency: Frequency in Hz.
        duration: Duration in seconds.
        sample_rate: Sample rate in Hz.
        amplitude: Peak amplitude.
        phase: Initial phase in radians.
        dtype: Output data type.

    Returns:
        A 1D array containing the sine wave.
    """
    num_samples = int(duration * sample_rate)
    t = np.linspace(0.0, duration, num_samples, endpoint=False, dtype=np.float64)
    signal = amplitude * np.sin(2 * np.pi * frequency * t + phase)
    return cast(np.ndarray, signal.astype(dtype))


def make_chirp(
    f_start: float,
    f_end: float,
    duration: float,
    sample_rate: int = 48000,
    method: str = "linear",
    amplitude: float = 1.0,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """
    Generate a chirp (frequency sweep) signal using SciPy.

    Args:
        f_start: Starting frequency in Hz.
        f_end: Ending frequency in Hz.
        duration: Duration in seconds.
        sample_rate: Sample rate in Hz.
        method: Sweep method ('linear', 'quadratic', 'logarithmic', 'hyperbolic').
        amplitude: Peak amplitude.
        dtype: Output data type.

    Returns:
        A 1D array containing the chirp signal.
    """
    num_samples = int(duration * sample_rate)
    t = np.linspace(0.0, duration, num_samples, endpoint=False, dtype=np.float64)
    # SciPy's chirp is defined from -1 to 1, so we scale it by amplitude
    sig = amplitude * sp_signal.chirp(
        t, f0=f_start, f1=f_end, t1=duration, method=method
    )
    # Ensure concrete ndarray type for typing
    arr = np.asarray(sig)
    return cast(np.ndarray, arr.astype(dtype))


def make_noise(
    duration: float,
    sample_rate: int = 48000,
    noise_type: str = "white",
    amplitude: float = 1.0,
    seed: int | None = None,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """
    Generate a noise signal.

    Args:
        duration: Duration in seconds.
        sample_rate: Sample rate in Hz.
        noise_type: Type of noise ('white', 'pink', 'brown').
        amplitude: RMS amplitude.
        seed: Random seed for reproducibility.
        dtype: Output data type.

    Returns:
        A 1D array containing the noise signal.
    """
    num_samples = int(duration * sample_rate)
    rng = np.random.default_rng(seed)

    if noise_type == "white":
        # White noise has a flat power spectrum.
        signal = rng.standard_normal(num_samples)
    elif noise_type in ("pink", "brown"):
        # Generate white noise and color it in the frequency domain.
        white_noise = rng.standard_normal(num_samples)
        fft_white = np.fft.rfft(white_noise)

        # Calculate frequencies for the FFT bins.
        frequencies = np.fft.rfftfreq(num_samples, d=1.0 / sample_rate)
        # Avoid division by zero at the DC component.
        frequencies[0] = 1.0

        if noise_type == "pink":
            # Pink noise power is proportional to 1/f. Amplitude is 1/sqrt(f).
            fft_colored = fft_white / np.sqrt(frequencies)
        else:  # brown
            # Brown noise power is proportional to 1/f^2. Amplitude is 1/f.
            fft_colored = fft_white / frequencies

        # The DC component should not be scaled.
        fft_colored[0] = 0
        signal = np.fft.irfft(fft_colored, n=num_samples)
    else:
        raise ValueError(f"Unknown noise type: {noise_type}")

    # Normalize to the desired RMS amplitude and convert type.
    signal_rms = np.sqrt(np.mean(signal**2))
    if signal_rms > 1e-9:
        signal = (signal / signal_rms) * amplitude

    return cast(np.ndarray, signal.astype(dtype))


def make_multitone(
    frequencies: list[float] | np.ndarray,
    duration: float,
    sample_rate: int = 48000,
    amplitudes: list[float] | np.ndarray | None = None,
    phases: list[float] | np.ndarray | None = None,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """
    Generate a multi-tone signal.

    Args:
        frequencies: A list or array of frequencies in Hz.
        duration: Duration in seconds.
        sample_rate: Sample rate in Hz.
        amplitudes: Amplitude for each frequency. If None, equal amplitudes
                    are used.
        phases: Phase for each frequency in radians. If None, all phases are 0.
        dtype: Output data type.

    Returns:
        A 1D array containing the multi-tone signal.
    """
    frequencies = np.asarray(frequencies)
    num_tones = len(frequencies)

    if amplitudes is None:
        amplitudes = np.ones(num_tones)
    amplitudes = np.asarray(amplitudes)

    if phases is None:
        phases = np.zeros(num_tones)
    phases = np.asarray(phases)

    if not (len(frequencies) == len(amplitudes) == len(phases)):
        msg = "Frequencies, amplitudes, and phases must have the same length."
        raise ValueError(msg)

    num_samples = int(duration * sample_rate)
    t = np.linspace(0.0, duration, num_samples, endpoint=False, dtype=np.float64)
    signal = np.zeros_like(t)

    for freq, amp, phase in zip(frequencies, amplitudes, phases, strict=True):
        signal += amp * np.sin(2 * np.pi * freq * t + phase)

    return cast(np.ndarray, signal.astype(dtype))


def make_test_batch(
    nfft: int,
    batch: int,
    signal_type: str = "sine",
    sample_rate: int = 48000,
    seed: int | None = None,
    **kwargs,
) -> np.ndarray:
    """
    Generate a batch of test signals for engine processing.

    Args:
        nfft: FFT size (number of samples per channel).
        batch: Number of channels.
        signal_type: Type of signal ('sine', 'chirp', 'noise', 'zeros', 'multitone').
        sample_rate: Sample rate in Hz.
        seed: Random seed for reproducibility.
        **kwargs: Additional arguments for the underlying signal generators.

    Returns:
        A 1D array of size (nfft * batch) containing the batched signals.
    """
    rng = np.random.default_rng(seed)
    duration = nfft / sample_rate

    # Generate the base signal which might be used by multiple channels.
    if signal_type == "sine":
        kwargs.setdefault("frequency", 1000.0)
        base_signal = make_sine(duration=duration, sample_rate=sample_rate, **kwargs)
    elif signal_type == "chirp":
        kwargs.setdefault("f_start", 100.0)
        kwargs.setdefault("f_end", 5000.0)
        base_signal = make_chirp(duration=duration, sample_rate=sample_rate, **kwargs)
    elif signal_type == "noise":
        # Noise will be generated per-channel to ensure channels are uncorrelated.
        base_signal = None
    elif signal_type == "multitone":
        kwargs.setdefault("frequencies", [1000.0, 2000.0, 5000.0])
        base_signal = make_multitone(duration=duration, sample_rate=sample_rate, **kwargs)
    elif signal_type == "zeros":
        base_signal = np.zeros(nfft, dtype=np.float32)
    else:
        raise ValueError(f"Unknown signal type: {signal_type}")

    # For signals that aren't noise, ensure they have the correct length.
    if base_signal is not None:
        if len(base_signal) > nfft:
            base_signal = base_signal[:nfft]
        elif len(base_signal) < nfft:
            base_signal = np.pad(base_signal, (0, nfft - len(base_signal)))

    if batch == 1 and base_signal is not None:
        return cast(np.ndarray, base_signal)
    if batch == 1 and signal_type == "noise":
        return make_noise(
            duration=duration, sample_rate=sample_rate, seed=seed, **kwargs
        )

    # Create batch with variations for each channel.
    batch_data = np.zeros(nfft * batch, dtype=np.float32)
    for i in range(batch):
        channel_seed = rng.integers(2**32)  # Get a new seed for each channel
        if signal_type == "noise":
            channel_signal = make_noise(
                duration=duration, sample_rate=sample_rate, seed=channel_seed, **kwargs
            )
        elif signal_type == "zeros":
            assert base_signal is not None
            channel_signal = base_signal.copy()
        else:
            # Add a small amount of noise to each channel to make them unique.
            assert base_signal is not None
            noise_amp = float(0.01 * np.mean(np.abs(base_signal)))
            noise = make_noise(
                duration=duration,
                sample_rate=sample_rate,
                amplitude=noise_amp,
                seed=channel_seed,
            )
            channel_signal = base_signal + noise

        # Final length check for the generated channel signal
        if len(channel_signal) > nfft:
            channel_signal = channel_signal[:nfft]

        batch_data[i * nfft : (i + 1) * nfft] = channel_signal

    return batch_data
