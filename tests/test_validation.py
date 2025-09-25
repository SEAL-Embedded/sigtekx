# tests/test_validation.py

import numpy as np
import pytest

from ionosense_hpc.testing.validators import (
    assert_allclose,
    assert_parseval,
    assert_snr,
    assert_spectral_peak,
    calculate_thd,
    check_numerical_stability,
    compare_with_reference,
    validate_fft_symmetry,
    validate_output_range,
)


def test_assert_allclose():
    """Test the assert_allclose validator."""
    a = np.array([1.0, 2.0, 3.0])
    b_pass = np.array([1.0, 2.000001, 3.0])
    b_fail = np.array([1.0, 2.001, 3.0])

    assert_allclose(a, b_pass, atol=1e-5)
    with pytest.raises(AssertionError):
        assert_allclose(a, b_fail, atol=1e-5)

def test_assert_spectral_peak():
    """Test the assert_spectral_peak validator."""
    sample_rate = 48000
    nfft = 1024
    freqs = np.fft.rfftfreq(nfft, 1 / sample_rate)
    spectrum = np.zeros_like(freqs)

    peak_freq_hz = 1000
    peak_idx = np.abs(freqs - peak_freq_hz).argmin()
    spectrum[peak_idx] = 1.0
    actual_peak_freq = freqs[peak_idx]

    assert_spectral_peak(spectrum, peak_freq_hz, sample_rate, nfft, tolerance_hz=50)

    expected_fail_freq = peak_freq_hz + 100
    with pytest.raises(AssertionError, match=f"Peak at {actual_peak_freq:.1f} Hz, expected {expected_fail_freq:.1f} Hz"):
        assert_spectral_peak(spectrum, expected_fail_freq, sample_rate, nfft, tolerance_hz=50)

def test_assert_parseval():
    """Test the assert_parseval validator."""
    n = 1024
    time_signal = np.sin(2 * np.pi * 10 * np.linspace(0, 1, n, endpoint=False))
    # FIX: Pass the UN-SCALED magnitude spectrum to the validator
    freq_spectrum = np.abs(np.fft.rfft(time_signal))

    # Test passing case. Tolerance should be tight for a mathematical identity.
    assert_parseval(time_signal, freq_spectrum, tolerance=1e-12)

    # Test failing case (by altering spectrum energy)
    with pytest.raises(AssertionError):
        assert_parseval(time_signal, freq_spectrum * 1.1, tolerance=1e-12)

def test_assert_snr():
    """Test the assert_snr validator."""
    signal = np.ones(100)
    noise = np.random.randn(100) * 0.1

    snr = assert_snr(signal, noise, min_snr_db=15)
    assert snr > 15

    with pytest.raises(AssertionError):
        assert_snr(signal, noise, min_snr_db=30)

    assert assert_snr(signal, np.zeros_like(signal), min_snr_db=100) == float('inf')

def test_validate_fft_symmetry():
    """Test the validate_fft_symmetry validator."""
    # Passing case: DC and Nyquist are real
    good_spectrum = np.array([1.0, 1+2j, -1+3j, 2.0], dtype=np.complex64)
    assert validate_fft_symmetry(good_spectrum)

    # Failing case: DC has imaginary part
    bad_dc = good_spectrum.copy()
    bad_dc[0] = 1.0 + 1e-9j
    assert not validate_fft_symmetry(bad_dc)

    # Failing case: Nyquist has imaginary part
    bad_nyquist = good_spectrum.copy()
    bad_nyquist[-1] = 2.0 - 1e-9j
    assert not validate_fft_symmetry(bad_nyquist)


def test_calculate_thd():
    """Test the calculate_thd validator."""
    spectrum = np.zeros(1024)
    fundamental_idx = 10

    spectrum[fundamental_idx] = 1.0
    spectrum[fundamental_idx * 2] = 0.5
    spectrum[fundamental_idx * 3] = 0.2

    thd = calculate_thd(spectrum, fundamental_idx, num_harmonics=5)
    assert thd == pytest.approx(53.85, rel=1e-2)

    spectrum[fundamental_idx] = 0
    assert calculate_thd(spectrum, fundamental_idx) == 0.0

def test_compare_with_reference():
    """Test the compare_with_reference validator."""
    actual = np.linspace(0, 1, 100)
    reference_pass = actual.copy()
    reference_fail = actual + 0.5

    # Test passing cases
    for metric in ['rmse', 'mae', 'max', 'correlation']:
        _, passes = compare_with_reference(actual, reference_pass, metric=metric)
        assert passes is True, f"Passing case failed for metric: {metric}"

    # Test failing cases
    for metric in ['rmse', 'mae', 'max', 'correlation']:
        _, passes = compare_with_reference(actual, reference_fail, metric=metric)
        assert passes is False, f"Failing case passed for metric: {metric}"

    # Test error handling for invalid metric
    with pytest.raises(ValueError, match="Unsupported metric"):
        compare_with_reference(actual, reference_pass, metric='invalid')

    # Test error handling for shape mismatch
    with pytest.raises(ValueError, match="Shape mismatch"):
        compare_with_reference(actual, actual[:-1])

    # Test correlation with zero vectors
    val, passes = compare_with_reference(np.zeros(5), np.zeros(5), metric='correlation')
    assert passes is True and val == 1.0
    val, passes = compare_with_reference(np.zeros(5), np.ones(5), metric='correlation')
    assert passes is False and val == 0.0

    # Test integer dtype branch to improve coverage
    actual_int = np.array([1, 2, 3])
    reference_int = np.array([1, 2, 4])
    _, passes_int = compare_with_reference(actual_int, reference_int, metric='rmse')
    assert passes_int is False


def test_validate_output_range():
    """Test the validate_output_range validator."""
    data = np.array([-0.5, 0.0, 0.5])
    assert validate_output_range(data, min_val=-1.0, max_val=1.0)
    assert not validate_output_range(data, min_val=0.0)
    assert not validate_output_range(data, max_val=0.4)

def test_check_numerical_stability():
    """Test the check_numerical_stability validator."""
    stable_outputs = [np.ones(10) + 1e-12, np.ones(10) - 1e-12]
    unstable_outputs = [np.ones(10), np.ones(10) * 2]

    assert check_numerical_stability(stable_outputs, max_variance=1e-10) is True
    assert check_numerical_stability(unstable_outputs, max_variance=0.1) is False
    assert check_numerical_stability([np.ones(10)]) is True

    # Test error handling for empty list and shape mismatch
    with pytest.raises(ValueError, match="must contain at least one array"):
        check_numerical_stability([])
    with pytest.raises(ValueError, match="must have the same shape"):
        check_numerical_stability([np.ones(2), np.ones(3)])


