# python/tests/test_signals.py
"""
Unit tests for the signal generation and utility functions.
"""
import numpy as np
import pytest
from numpy.testing import assert_allclose

# Import the functions and classes to be tested
from ionosense_hpc.core.signals import (
    SignalParameters,
    generate_test_signal,
    apply_window,
    WindowFunction,
)

# Mark all tests in this file as belonging to the 'signals' suite
pytestmark = pytest.mark.signals


def test_signal_parameters_creation():
    """Tests that SignalParameters can be created and is immutable."""
    params = SignalParameters(sample_rate=50_000, duration=0.5)
    assert params.sample_rate == 50_000
    assert params.duration == 0.5
    # Verify it's frozen
    with pytest.raises(AttributeError):
        params.sample_rate = 100_000


def test_generate_test_signal_defaults():
    """Tests signal generation with default parameters."""
    signals = generate_test_signal()
    assert "ch1" in signals
    assert "ch2" in signals

    # Check shape and dtype
    expected_samples = 100_000 * 1.0
    assert signals["ch1"].shape == (expected_samples,)
    assert signals["ch2"].shape == (expected_samples,)
    assert signals["ch1"].dtype == np.float32
    assert signals["ch2"].dtype == np.float32


def test_generate_test_signal_custom_params():
    """Tests signal generation with custom parameters and no noise."""
    params = SignalParameters(
        sample_rate=48000,
        duration=0.1,
        noise_level=0.0,
        dtype=np.float64
    )
    signals = generate_test_signal(params)
    expected_samples = 4800
    assert signals["ch1"].shape == (expected_samples,)
    assert signals["ch1"].dtype == np.float64

    # With no noise, the signal should be a perfect sine wave
    # We can verify this by checking its standard deviation
    expected_std = np.sqrt(0.5) # std of a sine wave with amplitude 1.0
    assert_allclose(np.std(signals["ch1"]), expected_std, rtol=1e-3)


def test_generate_test_signal_with_noise():
    """Tests that noise is correctly added to the signal."""
    params_no_noise = SignalParameters(noise_level=0.0)
    params_with_noise = SignalParameters(noise_level=0.1)

    signal_clean = generate_test_signal(params_no_noise)["ch1"]
    signal_noisy = generate_test_signal(params_with_noise)["ch1"]

    # The noisy signal should have a higher standard deviation than the clean one
    assert np.std(signal_noisy) > np.std(signal_clean)


def test_apply_window_valid():
    """Tests that all valid window functions can be applied."""
    signal = np.ones(1024, dtype=np.float32)
    window_types: list[WindowFunction] = ['hann', 'hamming', 'blackman', 'bartlett', 'kaiser', 'rectangular']

    for window_type in window_types:
        windowed_signal = apply_window(signal, window_type=window_type)
        assert windowed_signal.shape == signal.shape

        if window_type == 'rectangular':
            # Rectangular shouldn't change an all-ones signal
            assert_allclose(windowed_signal, signal)
            continue

        # 1) Tapered edges: should be significantly below 1.0
        assert float(windowed_signal[0]) < 0.1
        assert float(windowed_signal[-1]) < 0.1

        # 2) Peak close to 1.0 (account for even-N sampling + float32)
        peak = float(windowed_signal.max())
        assert 0.995 <= peak <= 1.000001  # ~1e-3 slack is plenty for fp32

        # 3) Symmetry check (all these windows are symmetric)
        assert_allclose(windowed_signal, windowed_signal[::-1], atol=1e-3)

        # 4) Energy should not exceed rectangular (basic sanity)
        assert windowed_signal.sum() <= signal.sum() + 1e-3


def test_apply_window_invalid():
    """Tests that an invalid window type raises a ValueError."""
    signal = np.ones(1024, dtype=np.float32)
    with pytest.raises(ValueError, match="Unknown window type"):
        # Use a type ignore to test runtime behavior with an invalid string
        apply_window(signal, window_type="invalid_window") # type: ignore

