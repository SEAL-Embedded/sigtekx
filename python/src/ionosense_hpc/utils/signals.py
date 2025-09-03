"""Signal generation utilities for testing and validation."""


import numpy as np


def make_sine(
    frequency: float,
    duration: float,
    sample_rate: int = 48000,
    amplitude: float = 1.0,
    phase: float = 0.0,
    dtype: np.dtype = np.float32
) -> np.ndarray:
    """Generate a sine wave signal.

    Args:
        frequency: Frequency in Hz
        duration: Duration in seconds
        sample_rate: Sample rate in Hz
        amplitude: Peak amplitude
        phase: Initial phase in radians
        dtype: Output data type

    Returns:
        1D array containing the sine wave
    """
    t = np.arange(0, duration, 1.0 / sample_rate, dtype=np.float64)
    signal = amplitude * np.sin(2 * np.pi * frequency * t + phase)
    return signal.astype(dtype)


def make_chirp(
    f_start: float,
    f_end: float,
    duration: float,
    sample_rate: int = 48000,
    method: str = 'linear',
    amplitude: float = 1.0,
    dtype: np.dtype = np.float32
) -> np.ndarray:
    """Generate a chirp (frequency sweep) signal.

    Args:
        f_start: Starting frequency in Hz
        f_end: Ending frequency in Hz
        duration: Duration in seconds
        sample_rate: Sample rate in Hz
        method: Sweep method ('linear' or 'logarithmic')
        amplitude: Peak amplitude
        dtype: Output data type

    Returns:
        1D array containing the chirp signal
    """
    t = np.arange(0, duration, 1.0 / sample_rate, dtype=np.float64)

    if method == 'linear':
        # Linear frequency sweep
        phase = 2 * np.pi * (f_start * t + (f_end - f_start) * t**2 / (2 * duration))
    elif method == 'logarithmic':
        # Logarithmic frequency sweep
        if f_start <= 0 or f_end <= 0:
            raise ValueError("Logarithmic chirp requires positive frequencies")
        beta = duration / np.log(f_end / f_start)
        phase = 2 * np.pi * beta * f_start * (np.exp(t / beta) - 1)
    else:
        raise ValueError(f"Unknown method: {method}")

    signal = amplitude * np.sin(phase)
    return signal.astype(dtype)


def make_noise(
    duration: float,
    sample_rate: int = 48000,
    noise_type: str = 'white',
    amplitude: float = 1.0,
    seed: int | None = None,
    dtype: np.dtype = np.float32
) -> np.ndarray:
    """Generate noise signal.

    Args:
        duration: Duration in seconds
        sample_rate: Sample rate in Hz
        noise_type: Type of noise ('white', 'pink', 'brown')
        amplitude: RMS amplitude
        seed: Random seed for reproducibility
        dtype: Output data type

    Returns:
        1D array containing the noise signal
    """
    if seed is not None:
        np.random.seed(seed)

    n_samples = int(duration * sample_rate)

    if noise_type == 'white':
        # White noise: flat spectrum
        signal = np.random.randn(n_samples)

    elif noise_type == 'pink':
        # Pink noise: 1/f spectrum
        # Simple approximation using filtering
        white = np.random.randn(n_samples)
        # Apply simple IIR filter for 1/f rolloff
        b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
        a = [1, -2.494956002, 2.017265875, -0.522189400]
        signal = np.zeros(n_samples)
        for i in range(len(b), n_samples):
            signal[i] = sum(b[j] * white[i-j] for j in range(len(b)))
            if i >= len(a):
                signal[i] -= sum(a[j] * signal[i-j] for j in range(1, len(a)))

    elif noise_type == 'brown':
        # Brown noise: 1/f² spectrum (integrated white noise)
        white = np.random.randn(n_samples)
        signal = np.cumsum(white) / np.sqrt(n_samples)

    else:
        raise ValueError(f"Unknown noise type: {noise_type}")

    # Normalize to desired amplitude
    signal = amplitude * signal / np.std(signal)
    return signal.astype(dtype)


def make_multitone(
    frequencies: list | np.ndarray,
    duration: float,
    sample_rate: int = 48000,
    amplitudes: list | np.ndarray | None = None,
    phases: list | np.ndarray | None = None,
    dtype: np.dtype = np.float32
) -> np.ndarray:
    """Generate a multi-tone signal.

    Args:
        frequencies: List of frequencies in Hz
        duration: Duration in seconds
        sample_rate: Sample rate in Hz
        amplitudes: Amplitude for each frequency (None for equal)
        phases: Phase for each frequency in radians (None for zero)
        dtype: Output data type

    Returns:
        1D array containing the multi-tone signal
    """
    frequencies = np.asarray(frequencies)
    n_tones = len(frequencies)

    amplitudes = np.ones(n_tones) / n_tones if amplitudes is None else np.asarray(amplitudes)
    phases = np.zeros(n_tones) if phases is None else np.asarray(phases)

    t = np.arange(0, duration, 1.0 / sample_rate, dtype=np.float64)
    signal = np.zeros_like(t)

    for freq, amp, phase in zip(frequencies, amplitudes, phases, strict=False):
        signal += amp * np.sin(2 * np.pi * freq * t + phase)

    return signal.astype(dtype)


def make_test_batch(
    nfft: int,
    batch: int,
    signal_type: str = 'sine',
    seed: int | None = None,
    **kwargs
) -> np.ndarray:
    """Generate a batch of test signals for engine processing.

    Args:
        nfft: FFT size (number of samples per channel)
        batch: Number of channels
        signal_type: Type of signal ('sine', 'chirp', 'noise', 'zeros')
        seed: Random seed for reproducibility
        **kwargs: Additional arguments for signal generators

    Returns:
        1D array of size nfft * batch
    """
    if seed is not None:
        np.random.seed(seed)

    # Generate base signal
    duration = nfft / kwargs.get('sample_rate', 48000)

    if signal_type == 'sine':
        frequency = kwargs.get('frequency', 1000.0)
        base_signal = make_sine(frequency, duration, **{k: v for k, v in kwargs.items()
                                                        if k not in ['frequency']})
    elif signal_type == 'chirp':
        f_start = kwargs.get('f_start', 100.0)
        f_end = kwargs.get('f_end', 5000.0)
        base_signal = make_chirp(f_start, f_end, duration,
                                 **{k: v for k, v in kwargs.items()
                                    if k not in ['f_start', 'f_end']})
    elif signal_type == 'noise':
        base_signal = make_noise(duration, **kwargs)
    elif signal_type == 'zeros':
        base_signal = np.zeros(nfft, dtype=np.float32)
    else:
        raise ValueError(f"Unknown signal type: {signal_type}")

    # Ensure correct length
    if len(base_signal) > nfft:
        base_signal = base_signal[:nfft]
    elif len(base_signal) < nfft:
        base_signal = np.pad(base_signal, (0, nfft - len(base_signal)))

    # Create batch
    if batch == 1:
        return base_signal
    else:
        # Add slight variations for each channel
        batch_data = np.zeros(nfft * batch, dtype=base_signal.dtype)
        for i in range(batch):
            if signal_type == 'noise':
                # Different noise for each channel
                channel_signal = make_noise(duration, seed=(seed + i) if seed else None, **kwargs)
                if len(channel_signal) > nfft:
                    channel_signal = channel_signal[:nfft]
            elif signal_type == 'zeros':
                channel_signal = base_signal
            else:
                # Add small frequency/phase variation
                noise = make_noise(duration, amplitude=0.01, seed=(seed + i) if seed else None)
                channel_signal = base_signal + noise[:len(base_signal)]

            batch_data[i * nfft:(i + 1) * nfft] = channel_signal

        return batch_data
