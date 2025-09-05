"""Tests for signal generation utilities."""

import numpy as np
import pytest
from scipy import signal as sp_signal
from scipy import stats

from ionosense_hpc.utils.signals import (
    make_chirp,
    make_multitone,
    make_noise,
    make_sine,
    make_test_batch,
)


@pytest.fixture(scope="module")
def signal_params():
    """Provides common parameters for signal generation tests."""
    return {"duration": 1.0, "sample_rate": 48000}


class TestSignalGenerators:
    """Test individual signal generation functions."""

    def test_make_sine(self, signal_params):
        """Test sine wave generation for correctness."""
        params = {
            "frequency": 1000,
            "amplitude": 2.0,
            "phase": np.pi / 2,
            **signal_params,
        }
        signal = make_sine(**params)

        expected_length = int(params["duration"] * params["sample_rate"])
        assert len(signal) == expected_length, "Signal length is incorrect."
        assert np.isclose(
            np.max(signal), params["amplitude"], atol=1e-5
        ), "Amplitude does not match expected peak."
        assert signal.dtype == np.float32, "Data type should be float32."

        # Verify frequency content
        fft_vals = np.fft.rfft(signal)
        freqs = np.fft.rfftfreq(len(signal), 1 / params["sample_rate"])
        peak_freq = freqs[np.argmax(np.abs(fft_vals))]
        assert np.isclose(
            peak_freq, params["frequency"], atol=1.0
        ), "Peak frequency does not match."

    @pytest.mark.parametrize("method", ["linear", "quadratic", "logarithmic"])
    def test_make_chirp(self, method, signal_params):
        """Test chirp generation for correctness."""
        params = {
            "f_start": 100,
            "f_end": 5000,
            "method": method,
            **signal_params,
        }
        signal = make_chirp(**params)
        expected_length = int(params["duration"] * params["sample_rate"])
        assert len(signal) == expected_length, "Signal length is incorrect."
        assert signal.dtype == np.float32, "Data type should be float32."

    @pytest.mark.parametrize(
        "noise_type, expected_slope",
        [("white", 0.0), ("pink", -1.0), ("brown", -2.0)],
    )
    def test_noise_spectrum(self, noise_type, expected_slope, signal_params):
        """Test that generated noise has the correct spectral slope."""
        # Use a longer duration for more reliable spectral analysis
        noise = make_noise(
            duration=5.0,
            sample_rate=signal_params["sample_rate"],
            noise_type=noise_type,
            seed=42,
        )

        # Calculate Power Spectral Density using Welch's method
        freqs, psd = sp_signal.welch(
            noise, fs=signal_params["sample_rate"], nperseg=4096
        )

        # Fit a line to the log-log plot of the PSD
        # We skip the DC component (freqs[0]) and very high frequencies
        valid_indices = np.where((freqs > 1) & (psd > 1e-10))
        log_freqs = np.log10(freqs[valid_indices])
        log_psd = np.log10(psd[valid_indices])

        # Power is proportional to 1/f^beta, so log(P) is proportional to -beta*log(f).
        # We expect the slope of the log-log plot to be -beta.
        # White noise (beta=0), Pink (beta=1), Brown (beta=2).
        # Our `expected_slope` is -beta.
        res = stats.linregress(log_freqs, log_psd)
        measured_slope = res.slope

        assert np.isclose(
            measured_slope, expected_slope, atol=0.3
        ), f"{noise_type} noise should have a spectral slope near {expected_slope}."

    def test_make_multitone(self, signal_params):
        """Test multitone signal generation."""
        frequencies = [100.0, 500.0, 2000.0]
        amplitudes = [0.5, 0.8, 0.3]
        signal = make_multitone(
            frequencies=frequencies, amplitudes=amplitudes, **signal_params
        )

        expected_length = int(signal_params["duration"] * signal_params["sample_rate"])
        assert len(signal) == expected_length, "Signal length is incorrect."

        # Check that the spectral peaks exist at the right frequencies
        fft_vals = np.fft.rfft(signal)
        freqs = np.fft.rfftfreq(len(signal), 1 / signal_params["sample_rate"])
        for freq in frequencies:
            idx = np.argmin(np.abs(freqs - freq))
            # Check for a significant magnitude at the expected frequency bin
            assert (
                np.abs(fft_vals[idx]) > 100
            ), f"Did not find a peak for {freq} Hz."


class TestBatchGenerator:
    """Test the make_test_batch function."""

    @pytest.mark.parametrize("batch_size", [1, 2, 8])
    @pytest.mark.parametrize("signal_type", ["sine", "noise", "zeros", "multitone"])
    def test_batch_creation(self, batch_size, signal_type):
        """Test that batches are created with the correct shape and properties."""
        nfft = 1024
        batch_data = make_test_batch(
            nfft=nfft, batch=batch_size, signal_type=signal_type, seed=123
        )

        assert (
            batch_data.shape == (nfft * batch_size,)
        ), "Batch data has incorrect shape."
        assert batch_data.dtype == np.float32, "Batch data has incorrect dtype."

    def test_batch_channels_are_different(self):
        """Test that channels in a batch are not identical (except for 'zeros')."""
        nfft = 1024
        batch_size = 4

        # For sine, channels should differ due to added noise
        sine_batch = make_test_batch(
            nfft=nfft, batch=batch_size, signal_type="sine", seed=42
        )
        ch1 = sine_batch[0:nfft]
        ch2 = sine_batch[nfft : 2 * nfft]
        assert not np.array_equal(
            ch1, ch2
        ), "Sine batch channels should be different."

        # For noise, channels should be statistically independent
        noise_batch = make_test_batch(
            nfft=nfft, batch=batch_size, signal_type="noise", seed=43
        )
        ch1_noise = noise_batch[0:nfft]
        ch2_noise = noise_batch[nfft : 2 * nfft]
        assert not np.array_equal(
            ch1_noise, ch2_noise
        ), "Noise batch channels should be different."

    def test_batch_zeros_are_identical(self):
        """Test that channels in a 'zeros' batch are identical."""
        nfft = 1024
        batch_size = 4
        zeros_batch = make_test_batch(
            nfft=nfft, batch=batch_size, signal_type="zeros"
        )
        ch1 = zeros_batch[0:nfft]
        ch2 = zeros_batch[nfft : 2 * nfft]
        assert np.array_equal(ch1, ch2), "Zeros batch channels should be identical."

