"""Numerical validation helpers for testing."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def assert_allclose(
    actual: np.ndarray,
    expected: np.ndarray,
    rtol: float = 1e-5,
    atol: float = 1e-8,
    err_msg: str = ""
) -> None:
    """Assert that two arrays are element-wise equal within tolerance.
    
    Args:
        actual: Actual output array
        expected: Expected output array
        rtol: Relative tolerance
        atol: Absolute tolerance
        err_msg: Optional error message
        
    Raises:
        AssertionError: If arrays are not close
    """
    np.testing.assert_allclose(actual, expected, rtol=rtol, atol=atol, err_msg=err_msg)


def assert_spectral_peak(
    spectrum: np.ndarray,
    expected_frequency: float,
    sample_rate: int,
    nfft: int,
    tolerance_hz: float = 10.0
) -> None:
    """Assert that spectrum has peak at expected frequency.
    
    Args:
        spectrum: Magnitude spectrum array
        expected_frequency: Expected peak frequency in Hz
        sample_rate: Sample rate in Hz
        nfft: FFT size
        tolerance_hz: Frequency tolerance in Hz
        
    Raises:
        AssertionError: If peak is not at expected frequency
    """
    # Calculate frequency bins
    freqs = np.fft.rfftfreq(nfft, 1/sample_rate)

    # Find peak
    peak_idx = np.argmax(spectrum)
    peak_freq = freqs[peak_idx]

    # Check if within tolerance
    error_hz = abs(peak_freq - expected_frequency)
    assert error_hz <= tolerance_hz, \
        f"Peak at {peak_freq:.1f} Hz, expected {expected_frequency:.1f} Hz " \
        f"(error: {error_hz:.1f} Hz)"


def assert_parseval(
    time_signal: np.ndarray,
    freq_spectrum: np.ndarray,
    tolerance: float = 1e-12
) -> None:
    """Verify Parseval's theorem (energy conservation).
    
    Args:
        time_signal: Time-domain signal
        freq_spectrum: Unscaled frequency-domain magnitude spectrum from rfft.
        tolerance: Relative tolerance for energy comparison.
        
    Raises:
        AssertionError: If energy is not conserved
    """
    # Time-domain energy
    time_energy = np.sum(np.abs(time_signal) ** 2)

    # FIX: Correctly calculate frequency-domain energy from rfft output
    # According to Parseval's theorem for DFTs, the energy is the sum
    # of squared magnitudes of the spectrum, normalized by the signal length.
    # For a real-valued signal, rfft returns a one-sided spectrum. To get the
    # full energy, we must double the power of all frequencies except for
    # DC (index 0) and the Nyquist frequency (last element, if N is even).
    n = len(time_signal)
    freq_energy_components = freq_spectrum ** 2

    if n % 2 == 0:  # Even-length signal, Nyquist frequency is present
        freq_energy = freq_energy_components[0] + 2 * np.sum(freq_energy_components[1:-1]) + freq_energy_components[-1]
    else:  # Odd-length signal, no Nyquist frequency
        freq_energy = freq_energy_components[0] + 2 * np.sum(freq_energy_components[1:])

    freq_energy /= n

    # Check relative error, handle division by zero
    if time_energy == 0:
        rel_error = 0 if freq_energy == 0 else float('inf')
    else:
        rel_error = abs(time_energy - freq_energy) / time_energy

    assert rel_error <= tolerance, \
        f"Energy not conserved: time={time_energy:.4f}, freq={freq_energy:.4f} " \
        f"(error: {rel_error:.2%})"


def assert_snr(
    signal: np.ndarray,
    noise: np.ndarray,
    min_snr_db: float
) -> float:
    """Assert that signal-to-noise ratio meets minimum requirement.
    
    Args:
        signal: Clean signal
        noise: Noise or error signal
        min_snr_db: Minimum required SNR in dB
        
    Returns:
        Actual SNR in dB
        
    Raises:
        AssertionError: If SNR is below minimum
    """
    signal_power = np.mean(signal ** 2)
    noise_power = np.mean(noise ** 2)

    if noise_power == 0:
        return float('inf')

    snr_db = 10 * np.log10(signal_power / noise_power)
    assert snr_db >= min_snr_db, \
        f"SNR {snr_db:.1f} dB is below minimum {min_snr_db:.1f} dB"

    return snr_db


def validate_fft_symmetry(
    complex_spectrum: np.ndarray,
    tolerance: float = 1e-10
) -> bool:
    """Check if FFT output has expected symmetry properties.
    
    Args:
        complex_spectrum: Complex FFT output
        tolerance: Tolerance for symmetry check
        
    Returns:
        True if symmetry is valid
    """
    # For real input, FFT should have Hermitian symmetry
    # This is automatically satisfied for rfft, but can check DC/Nyquist

    # DC component should be real
    if abs(complex_spectrum[0].imag) > tolerance:
        return False

    # Nyquist component (if present) should be real
    if len(complex_spectrum) % 2 == 0:
        if abs(complex_spectrum[-1].imag) > tolerance:
            return False

    return True


def calculate_thd(
    spectrum: np.ndarray,
    fundamental_idx: int,
    num_harmonics: int = 5
) -> float:
    """Calculate Total Harmonic Distortion.
    
    Args:
        spectrum: Magnitude spectrum
        fundamental_idx: Index of fundamental frequency
        num_harmonics: Number of harmonics to include
        
    Returns:
        THD as a percentage
    """
    fundamental_power = spectrum[fundamental_idx] ** 2

    harmonic_power = 0
    for n in range(2, num_harmonics + 1):
        harmonic_idx = fundamental_idx * n
        if harmonic_idx < len(spectrum):
            harmonic_power += spectrum[harmonic_idx] ** 2

    if fundamental_power == 0:
        return 0.0

    thd = np.sqrt(harmonic_power / fundamental_power) * 100
    return thd

def compare_with_reference(
    actual: np.ndarray,
    reference: np.ndarray,
    *,
    metric: str = "rmse",
    thresholds: dict[str, float] | None = None
) -> tuple[float, bool]:
    """
    Compare `actual` vs `reference` and decide pass/fail.

    Supported metrics:
      - "rmse"        : root-mean-square error
      - "mae"         : mean absolute error
      - "max"         : max absolute error
      - "correlation" : cosine similarity (no mean-centering)

    Returns
    -------
    Tuple[float, bool]
        (value, passes) where `passes` is a native Python bool.

    Notes
    -----
    - We use cosine similarity for 'correlation' so a DC offset (e.g., +0.5)
      *reduces* similarity and can fail — matching the test's expectation.
    """
    actual = np.asarray(actual)
    reference = np.asarray(reference)

    if actual.shape != reference.shape:
        raise ValueError(f"Shape mismatch: actual.shape={actual.shape} vs reference.shape={reference.shape}")

    # Default thresholds that are sane for fp64/fp32 and align with tests:
    # small diffs should pass; big offsets should fail.
    if thresholds is None:
        # Pick a base tolerance by dtype (fp32 noisier than fp64)
        if np.issubdtype(actual.dtype, np.floating):
            eps = np.finfo(actual.dtype).eps
        else:
            eps = 1e-12
        base_err = 1e-6 if eps < 1e-12 else 1e-5   # rmse/mae/max thresholds
        corr_min = 0.99                             # cosine similarity floor
        thresholds = {"rmse": base_err, "mae": base_err, "max": base_err, "correlation": corr_min}

    thr: dict[str, float] = dict(thresholds)

    if metric == "rmse":
        value = float(np.sqrt(np.mean((actual - reference) ** 2)))
        passes = value <= thr["rmse"]

    elif metric == "mae":
        value = float(np.mean(np.abs(actual - reference)))
        passes = value <= thr["mae"]

    elif metric == "max":
        value = float(np.max(np.abs(actual - reference)))
        passes = value <= thr["max"]

    elif metric == "correlation":
        # Cosine similarity (no mean-centering) so DC offsets lower the score.
        denom = float(np.linalg.norm(actual) * np.linalg.norm(reference))
        if denom == 0.0:
            # if either vector is all zeros, define similarity 1.0 if both are zero; else 0.0
            both_zero = bool(np.all(actual == 0) and np.all(reference == 0))
            value = 1.0 if both_zero else 0.0
        else:
            value = float(np.dot(actual, reference) / denom)
        passes = value >= thr["correlation"]

    else:
        raise ValueError(f"Unsupported metric: {metric!r}. Use 'rmse'|'mae'|'max'|'correlation'.")

    return value, bool(passes)

def validate_output_range(
    output: np.ndarray,
    min_val: float | None = None,
    max_val: float | None = None
) -> bool:
    """Validate that output values are within expected range.
    
    Args:
        output: Output array to validate
        min_val: Minimum expected value
        max_val: Maximum expected value
        
    Returns:
        True if all values are within range
    """
    if min_val is not None and np.min(output) < min_val:
        return False
    if max_val is not None and np.max(output) > max_val:
        return False
    return True


def check_numerical_stability(
    outputs: Sequence[np.ndarray],
    *,
    max_variance: float = 1e-12
) -> bool:
    """
    Given multiple runs' outputs, check stability by measuring variance
    across runs for each element and taking the max variance.

    Returns:
        bool: True if max per-element variance <= max_variance, else False.
              Guaranteed to be a native Python bool.
    """
    if not outputs:
        raise ValueError("`outputs` must contain at least one array.")

    arrays = [np.asarray(o) for o in outputs]
    first_shape = arrays[0].shape
    if any(a.shape != first_shape for a in arrays):
        raise ValueError("All arrays in `outputs` must have the same shape.")

    # Single run is vacuously stable
    if len(arrays) == 1:
        return True

    stacked = np.stack(arrays, axis=0)  # (runs, ...)
    var_across_runs = np.var(stacked, axis=0)  # elementwise variance
    max_var = float(np.max(var_across_runs))
    return bool(max_var <= float(max_variance))

