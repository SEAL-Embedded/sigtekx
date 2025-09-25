"""Tests for signal generation utilities."""

import numpy as np
import pytest
from scipy import signal as sp_signal
from scipy import stats

from ionosense_hpc.config import EngineConfig
from ionosense_hpc.utils.signals import (
    make_chirp,
    make_multitone,
    make_noise,
    make_sine,
    make_test_batch,
)


@pytest.fixture(scope="module")
def signal_params() -> dict[str, int]:
    """Provides common parameters for signal generation tests."""
    sample_rate = 48_000
    n_samples = sample_rate  # 1 second worth of samples
    return {"sample_rate": sample_rate, "n_samples": n_samples}


class TestSignalGenerators:
    """Test individual signal generation functions."""

    def test_make_sine(self, signal_params: dict[str, int]) -> None:
        """Test sine wave generation for correctness."""
        signal = make_sine(
            sample_rate=signal_params["sample_rate"],
            n_samples=signal_params["n_samples"],
            frequency=1000.0,
            amplitude=2.0,
            phase=np.pi / 2,
            dtype=np.float32,
        )

        expected_length = signal_params["n_samples"]
        assert len(signal) == expected_length, "Signal length is incorrect."
        assert np.isclose(np.max(signal), 2.0, atol=1e-5), "Amplitude mismatch."
        assert signal.dtype == np.float32, "Data type should be float32."

        fft_vals = np.fft.rfft(signal)
        freqs = np.fft.rfftfreq(len(signal), 1 / signal_params["sample_rate"])
        peak_freq = freqs[np.argmax(np.abs(fft_vals))]
        assert np.isclose(peak_freq, 1000.0, atol=1.0), "Peak frequency mismatch."

    @pytest.mark.parametrize("method", ["linear", "quadratic", "logarithmic"])
    def test_make_chirp(self, method: str, signal_params: dict[str, int]) -> None:
        """Test chirp generation for correctness."""
        signal = make_chirp(
            sample_rate=signal_params["sample_rate"],
            n_samples=signal_params["n_samples"],
            f_start=100.0,
            f_end=5000.0,
            method=method,
            dtype=np.float32,
        )

        expected_length = signal_params["n_samples"]
        assert len(signal) == expected_length, "Signal length is incorrect."
        assert signal.dtype == np.float32, "Data type should be float32."

    @pytest.mark.parametrize(
        "noise_type, expected_slope",
        [("white", 0.0), ("pink", -1.0), ("brown", -2.0)],
    )
    def test_noise_spectrum(
        self,
        noise_type: str,
        expected_slope: float,
        signal_params: dict[str, int],
    ) -> None:
        """Test that generated noise has the correct spectral slope."""
        n_samples = int(5.0 * signal_params["sample_rate"])
        rng = np.random.default_rng(42)
        noise = make_noise(
            n_samples=n_samples,
            noise_type=noise_type,
            rng=rng,
            dtype=np.float32,
        )

        freqs, psd = sp_signal.welch(
            noise, fs=signal_params["sample_rate"], nperseg=4096
        )

        valid_indices = np.where((freqs > 1) & (psd > 1e-10))
        log_freqs = np.log10(freqs[valid_indices])
        log_psd = np.log10(psd[valid_indices])

        res = stats.linregress(log_freqs, log_psd)
        measured_slope = res.slope

        assert np.isclose(
            measured_slope, expected_slope, atol=0.3
        ), f"{noise_type} noise should have spectral slope near {expected_slope}."

    def test_make_multitone(self, signal_params: dict[str, int]) -> None:
        """Test multitone signal generation."""
        frequencies = [100.0, 500.0, 2000.0]
        amplitudes = [0.5, 0.8, 0.3]
        signal = make_multitone(
            sample_rate=signal_params["sample_rate"],
            n_samples=signal_params["n_samples"],
            frequencies=frequencies,
            amplitudes=amplitudes,
            dtype=np.float32,
        )

        expected_length = signal_params["n_samples"]
        assert len(signal) == expected_length, "Signal length is incorrect."

        fft_vals = np.fft.rfft(signal)
        freqs = np.fft.rfftfreq(len(signal), 1 / signal_params["sample_rate"])
        for freq in frequencies:
            idx = np.argmin(np.abs(freqs - freq))
            assert np.abs(fft_vals[idx]) > 100, f"No peak detected for {freq} Hz."


class TestBatchGenerator:
    """Test the make_test_batch function."""

    SAMPLE_RATE = 48_000

    @pytest.mark.parametrize("batch_size", [1, 2, 8])
    @pytest.mark.parametrize("signal_type", ["sine", "noise", "zeros", "multitone"])
    def test_batch_creation(self, batch_size: int, signal_type: str) -> None:
        """Test that batches are created with the correct shape and properties."""
        nfft = 1024
        config = EngineConfig(nfft=nfft, batch=batch_size, sample_rate_hz=self.SAMPLE_RATE)
        rng = np.random.default_rng(123)
        batch_data = make_test_batch(signal_type, config, rng=rng)

        assert batch_data.shape == (nfft * batch_size,), "Batch data has incorrect shape."
        assert batch_data.dtype == np.float32, "Batch data has incorrect dtype."

    def test_batch_channels_are_different(self) -> None:
        """Channels in a batch should differ when expected."""
        nfft = 1024
        batch_size = 4
        config = EngineConfig(nfft=nfft, batch=batch_size, sample_rate_hz=self.SAMPLE_RATE)

        sine_batch = make_test_batch(
            "sine",
            config,
            rng=np.random.default_rng(42),
            frequency=1000.0,
        )
        ch1 = sine_batch[0:nfft]
        ch2 = sine_batch[nfft : 2 * nfft]
        assert not np.array_equal(ch1, ch2), "Sine batch channels should be different."

        noise_batch = make_test_batch(
            "noise",
            config,
            rng=np.random.default_rng(43),
        )
        ch1_noise = noise_batch[0:nfft]
        ch2_noise = noise_batch[nfft : 2 * nfft]
        assert not np.array_equal(ch1_noise, ch2_noise), "Noise channels should be different."

    def test_batch_zeros_are_identical(self) -> None:
        """Channels in a 'zeros' batch should be identical."""
        nfft = 1024
        batch_size = 4
        config = EngineConfig(nfft=nfft, batch=batch_size, sample_rate_hz=self.SAMPLE_RATE)
        zeros_batch = make_test_batch(
            "zeros",
            config,
            rng=np.random.default_rng(0),
        )
        ch1 = zeros_batch[0:nfft]
        ch2 = zeros_batch[nfft : 2 * nfft]
        assert np.array_equal(ch1, ch2), "Zeros batch channels should be identical."

