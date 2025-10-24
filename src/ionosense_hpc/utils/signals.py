"""
Signal generation utilities for testing and validation.

This module centralizes signal generation routines used throughout the
benchmarking and testing stack. Implementations favour pure NumPy/SciPy
vectorization where possible and require callers to provide NumPy
Generators for any stochastic behaviour to keep reproducibility under
caller control.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, cast

import numpy as np
from numpy.typing import DTypeLike
from scipy import signal as sp_signal

from ionosense_hpc.config import EngineConfig

NoiseKind = Literal["white", "pink", "brown"]


def _time_vector(sample_rate: int, n_samples: int) -> np.ndarray:
    """Return a float64 time base with bounds checking."""
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    return np.arange(n_samples, dtype=np.float64) / float(sample_rate)


def _cast_dtype(array: np.ndarray, dtype: DTypeLike) -> np.ndarray:
    """Convert to requested dtype without unnecessary copies."""
    return cast(np.ndarray, array.astype(dtype, copy=False))


def _scale_to_rms(signal: np.ndarray, target_rms: float) -> np.ndarray:
    """Scale signal to the requested RMS amplitude."""
    if target_rms < 0:
        raise ValueError("amplitude must be non-negative")
    if target_rms == 0:
        return np.zeros_like(signal)

    rms = float(np.sqrt(np.mean(np.square(signal))))
    if rms == 0:
        return np.zeros_like(signal)
    return signal * (target_rms / rms)


def _resolve_sample_count(
    sample_rate: int,
    samples: int | None,
    seconds: float | None,
    name: str,
) -> int:
    """Resolve sample counts from either explicit samples or seconds."""
    if samples is not None and seconds is not None:
        raise ValueError(f"Specify either {name}_samples or {name}_seconds, not both")

    if samples is not None:
        value = int(samples)
    elif seconds is not None:
        if seconds <= 0:
            raise ValueError(f"{name}_seconds must be positive")
        value = int(round(seconds * sample_rate))
    else:
        raise ValueError(f"Provide {name}_samples or {name}_seconds")

    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


# --- Core Signal Functions -------------------------------------------------

def make_sine(
    sample_rate: int,
    n_samples: int,
    frequency: float,
    *,
    amplitude: float = 1.0,
    phase: float = 0.0,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """Generate a sine wave with the requested parameters."""
    if frequency < 0:
        raise ValueError("frequency must be non-negative")
    t = _time_vector(sample_rate, n_samples)
    waveform = amplitude * np.sin(2.0 * np.pi * frequency * t + phase)
    return _cast_dtype(waveform, dtype)


def make_chirp(
    sample_rate: int,
    n_samples: int,
    f_start: float,
    f_end: float,
    *,
    method: str = "linear",
    amplitude: float = 1.0,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """Generate a frequency sweep using scipy.signal.chirp."""
    if f_start < 0 or f_end < 0:
        raise ValueError("chirp frequencies must be non-negative")
    duration = n_samples / float(sample_rate)
    t = np.linspace(0.0, duration, n_samples, endpoint=False, dtype=np.float64)
    chirp = amplitude * sp_signal.chirp(t, f0=f_start, f1=f_end, t1=duration, method=method)
    return _cast_dtype(np.asarray(chirp), dtype)


def make_multitone(
    sample_rate: int,
    n_samples: int,
    frequencies: Sequence[float],
    *,
    amplitudes: Sequence[float] | None = None,
    phases: Sequence[float] | None = None,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """Generate a multitone waveform from frequency, amplitude, and phase sets."""
    freq_arr = np.asarray(frequencies, dtype=np.float64)
    if freq_arr.ndim != 1 or freq_arr.size == 0:
        raise ValueError("frequencies must be a 1D sequence with at least one entry")
    if np.any(freq_arr < 0):
        raise ValueError("frequencies must be non-negative")

    if amplitudes is None:
        amp_arr = np.ones_like(freq_arr)
    else:
        amp_arr = np.asarray(amplitudes, dtype=np.float64)

    phase_arr = np.zeros_like(freq_arr) if phases is None else np.asarray(phases, dtype=np.float64)

    if not (len(freq_arr) == len(amp_arr) == len(phase_arr)):
        raise ValueError("frequencies, amplitudes, and phases must have matching lengths")

    t = _time_vector(sample_rate, n_samples)
    angular = 2.0 * np.pi * freq_arr[:, None] * t
    waveform = np.sum(amp_arr[:, None] * np.sin(angular + phase_arr[:, None]), axis=0)
    return _cast_dtype(waveform, dtype)


# --- Noise Generators ------------------------------------------------------

def make_white_noise(
    n_samples: int,
    *,
    amplitude: float = 1.0,
    rng: np.random.Generator,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """Generate white noise scaled to the requested RMS amplitude."""
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    white = rng.standard_normal(n_samples)
    scaled = _scale_to_rms(white, amplitude)
    return _cast_dtype(scaled, dtype)


def make_pink_noise(
    n_samples: int,
    *,
    amplitude: float = 1.0,
    rng: np.random.Generator,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """Generate pink (1/f) noise via frequency domain filtering."""
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    white = rng.standard_normal(n_samples)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n_samples)
    freqs[0] = 1.0
    spectrum /= np.sqrt(freqs)
    spectrum[0] = 0.0
    pink = np.fft.irfft(spectrum, n_samples)
    scaled = _scale_to_rms(pink, amplitude)
    return _cast_dtype(scaled, dtype)


def make_brown_noise(
    n_samples: int,
    *,
    amplitude: float = 1.0,
    rng: np.random.Generator,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """Generate brown (1/f²) noise by integrating white noise."""
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    white = rng.standard_normal(n_samples)
    brown = np.cumsum(white)
    brown -= np.mean(brown)
    scaled = _scale_to_rms(brown, amplitude)
    return _cast_dtype(scaled, dtype)


def make_noise(
    n_samples: int,
    *,
    noise_type: NoiseKind = "white",
    amplitude: float = 1.0,
    rng: np.random.Generator,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """Convenience wrapper for noise generation by type."""
    noise_key = noise_type.lower()
    if noise_key == "white":
        return make_white_noise(n_samples, amplitude=amplitude, rng=rng, dtype=dtype)
    if noise_key == "pink":
        return make_pink_noise(n_samples, amplitude=amplitude, rng=rng, dtype=dtype)
    if noise_key == "brown":
        return make_brown_noise(n_samples, amplitude=amplitude, rng=rng, dtype=dtype)
    raise ValueError(f"Unsupported noise_type: {noise_type}")


# --- Deterministic Waveforms -----------------------------------------------

def make_pulse_train(
    sample_rate: int,
    n_samples: int,
    *,
    period_samples: int | None = None,
    period_seconds: float | None = None,
    pulse_width_samples: int | None = None,
    pulse_width_seconds: float | None = None,
    amplitude: float = 1.0,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """Generate a periodic pulse train using vectorized tiling."""
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")

    if period_samples is None and period_seconds is None:
        period_samples = max(1, n_samples // 10)

    period = _resolve_sample_count(sample_rate, period_samples, period_seconds, "period")

    if pulse_width_samples is None and pulse_width_seconds is None:
        pulse_width_samples = min(5, period)

    width = _resolve_sample_count(sample_rate, pulse_width_samples, pulse_width_seconds, "pulse_width")
    if width > period:
        raise ValueError("pulse width cannot exceed the period")

    on_segment = np.full(width, amplitude, dtype=np.float64)
    off_segment = np.zeros(period - width, dtype=np.float64)
    pattern = np.concatenate((on_segment, off_segment))
    repeats = int(np.ceil(n_samples / period))
    train = np.tile(pattern, repeats)[:n_samples]
    return _cast_dtype(train, dtype)


def make_impulse(
    n_samples: int,
    *,
    amplitude: float = 1.0,
    index: int = 0,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """Generate an impulse with a single non-zero sample."""
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    if not 0 <= index < n_samples:
        raise ValueError("index must be within the signal length")
    impulse = np.zeros(n_samples, dtype=np.float64)
    impulse[index] = amplitude
    return _cast_dtype(impulse, dtype)


def make_dc_signal(
    n_samples: int,
    *,
    value: float = 1.0,
    dtype: DTypeLike = np.float32,
) -> np.ndarray:
    """Generate a constant (DC) signal."""
    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    dc = np.full(n_samples, value, dtype=np.float64)
    return _cast_dtype(dc, dtype)


# --- High-Level Batch Creation --------------------------------------------

def make_test_batch(
    signal_type: str,
    config: EngineConfig,
    *,
    rng: np.random.Generator,
    n_samples: int | None = None,
    channels: int | None = None,
    dtype: DTypeLike = np.float32,
    channel_variation: float = 0.01,
    **kwargs,
) -> np.ndarray:
    """Create a batched signal array tailored to the engine configuration."""
    n_samples = int(n_samples or config.nfft)
    batch = int(batch or config.channels)
    sample_rate = int(kwargs.pop("sample_rate", config.sample_rate_hz))

    if n_samples <= 0:
        raise ValueError("n_samples must be positive")
    if batch <= 0:
        raise ValueError("batch must be positive")

    signal_key = signal_type.lower()
    base_signal: np.ndarray | None = None

    if signal_key == "sine":
        base_signal = make_sine(
            sample_rate=sample_rate,
            n_samples=n_samples,
            frequency=float(kwargs.pop("frequency", 1000.0)),
            amplitude=float(kwargs.pop("amplitude", 1.0)),
            phase=float(kwargs.pop("phase", 0.0)),
            dtype=np.float64,
        )
    elif signal_key == "chirp":
        base_signal = make_chirp(
            sample_rate=sample_rate,
            n_samples=n_samples,
            f_start=float(kwargs.pop("f_start", 100.0)),
            f_end=float(kwargs.pop("f_end", sample_rate / 3.0)),
            method=str(kwargs.pop("method", "linear")),
            amplitude=float(kwargs.pop("amplitude", 1.0)),
            dtype=np.float64,
        )
    elif signal_key == "multitone":
        base_signal = make_multitone(
            sample_rate=sample_rate,
            n_samples=n_samples,
            frequencies=kwargs.pop("frequencies", (1000.0, 2000.0, 5000.0)),
            amplitudes=kwargs.pop("amplitudes", None),
            phases=kwargs.pop("phases", None),
            dtype=np.float64,
        )
    elif signal_key == "pulse_train":
        period_samples = kwargs.pop("period_samples", None)
        period_seconds = kwargs.pop("period_seconds", None)
        width_samples = kwargs.pop("pulse_width_samples", None)
        width_seconds = kwargs.pop("pulse_width_seconds", None)
        base_signal = make_pulse_train(
            sample_rate=sample_rate,
            n_samples=n_samples,
            period_samples=period_samples,
            period_seconds=period_seconds,
            pulse_width_samples=width_samples,
            pulse_width_seconds=width_seconds,
            amplitude=float(kwargs.pop("amplitude", 1.0)),
            dtype=np.float64,
        )
    elif signal_key == "impulse":
        base_signal = make_impulse(
            n_samples=n_samples,
            amplitude=float(kwargs.pop("amplitude", 1.0)),
            index=int(kwargs.pop("index", 0)),
            dtype=np.float64,
        )
    elif signal_key == "dc":
        base_signal = make_dc_signal(
            n_samples=n_samples,
            value=float(kwargs.pop("value", 1.0)),
            dtype=np.float64,
        )
    elif signal_key == "nyquist":
        t = np.arange(n_samples, dtype=np.float64)
        base_signal = np.cos(np.pi * t)
    elif signal_key == "zeros":
        base_signal = np.zeros(n_samples, dtype=np.float64)

    batch_data: np.ndarray
    if base_signal is not None:
        base_signal = np.asarray(base_signal, dtype=np.float64)
        batch_data = np.empty((channels, n_samples), dtype=np.float64)
        variation_scale = float(max(channel_variation, 0.0))
        for idx in range(batch):
            channel = base_signal.copy()
            if variation_scale > 0 and not np.allclose(base_signal, 0.0):
                ref_level = float(np.mean(np.abs(base_signal)))
                if ref_level > 0:
                    jitter_rms = variation_scale * ref_level
                    channel += make_white_noise(
                        n_samples,
                        amplitude=jitter_rms,
                        rng=rng,
                        dtype=np.float64,
                    )
            batch_data[idx] = channel
    else:
        noise_kind: NoiseKind
        if signal_key == "noise":
            noise_kind = cast(NoiseKind, kwargs.pop("noise_type", "white"))
        else:
            noise_kind = cast(NoiseKind, signal_key.replace("_noise", ""))
        amplitude = float(kwargs.pop("amplitude", 1.0))
        batch_data = np.empty((channels, n_samples), dtype=np.float64)
        for idx in range(batch):
            batch_data[idx] = make_noise(
                n_samples,
                noise_type=noise_kind,
                amplitude=amplitude,
                rng=rng,
                dtype=np.float64,
            )

    array = _cast_dtype(batch_data.reshape(-1), dtype)
    return array


__all__ = [
    "make_sine",
    "make_chirp",
    "make_multitone",
    "make_white_noise",
    "make_pink_noise",
    "make_brown_noise",
    "make_noise",
    "make_pulse_train",
    "make_impulse",
    "make_dc_signal",
    "make_test_batch",
]
