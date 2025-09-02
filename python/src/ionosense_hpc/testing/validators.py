"""Numerical validation helpers for testing."""

from typing import Tuple, Optional

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
    tolerance: float = 0.01
) -> None:
    """Verify Parseval's theorem (energy conservation).
    
    Args:
        time_signal: Time-domain signal
        freq_spectrum: Frequency-domain magnitude spectrum
        tolerance: Relative tolerance for energy comparison
        
    Raises:
        AssertionError: If energy is not conserved
    """
    # Time-domain energy
    time_energy = np.sum(time_signal ** 2)
    
    # Frequency-domain energy (accounting for one-sided spectrum)
    freq_energy = np.sum(freq_spectrum ** 2)
    freq_energy = freq_energy * 2  # One-sided spectrum correction
    freq_energy = freq_energy / len(time_signal)  # Normalization
    
    # Check relative error
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
    metric: str = 'rmse'
) -> Tuple[float, bool]:
    """Compare actual output with reference using specified metric.
    
    Args:
        actual: Actual output
        reference: Reference output
        metric: Comparison metric ('rmse', 'mae', 'max', 'correlation')
        
    Returns:
        Tuple of (metric_value, passes_threshold)
    """
    thresholds = {
        'rmse': 1e-4,
        'mae': 1e-5,
        'max': 1e-3,
        'correlation': 0.999
    }
    
    if metric == 'rmse':
        value = np.sqrt(np.mean((actual - reference) ** 2))
        passes = value < thresholds['rmse']
    elif metric == 'mae':
        value = np.mean(np.abs(actual - reference))
        passes = value < thresholds['mae']
    elif metric == 'max':
        value = np.max(np.abs(actual - reference))
        passes = value < thresholds['max']
    elif metric == 'correlation':
        value = np.corrcoef(actual.flatten(), reference.flatten())[0, 1]
        passes = value > thresholds['correlation']
    else:
        raise ValueError(f"Unknown metric: {metric}")
    
    return value, passes


def validate_output_range(
    output: np.ndarray,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None
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
    outputs: list,
    max_variance: float = 1e-10
) -> bool:
    """Check numerical stability across multiple runs.
    
    Args:
        outputs: List of output arrays from multiple runs
        max_variance: Maximum allowed variance
        
    Returns:
        True if outputs are numerically stable
    """
    if len(outputs) < 2:
        return True
    
    # Stack outputs and compute variance
    stacked = np.stack(outputs)
    variance = np.var(stacked, axis=0)
    
    return np.max(variance) < max_variance