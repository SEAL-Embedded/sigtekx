"""Tests for spectrogram generation and visualization utilities."""

import numpy as np
import pytest
from pathlib import Path
import tempfile
import sys

# Add experiments to path for analysis module imports
_experiments_path = Path(__file__).parent.parent / "experiments"
if str(_experiments_path) not in sys.path:
    sys.path.insert(0, str(_experiments_path))

from ionosense_hpc.config import EngineConfig
from analysis.spectrogram import (
    SpectrogramGenerator,
    SpectrogramData,
    generate_spectrogram,
    save_spectrogram,
    load_spectrogram,
)


class TestSpectrogramGeneration:
    """Test spectrogram generation from time-series data."""

    def test_basic_spectrogram_generation(self):
        """Test basic spectrogram generation with synthetic signal."""
        # Create config
        config = EngineConfig(
            nfft=1024,
            channels=1,
            overlap=0.5,
            sample_rate_hz=48000
        )

        # Generate test signal (1 second)
        duration_sec = 1.0
        num_samples = int(config.sample_rate_hz * duration_sec)
        signal = np.random.randn(num_samples).astype(np.float32)

        # Generate spectrogram
        with SpectrogramGenerator(config) as generator:
            spec_data = generator.generate(signal)

        # Validate output
        assert isinstance(spec_data, SpectrogramData)
        assert spec_data.spectrogram.shape[1] == config.nfft // 2 + 1  # freq bins
        assert spec_data.spectrogram.shape[0] > 0  # time steps
        assert len(spec_data.times) == spec_data.spectrogram.shape[0]
        assert len(spec_data.frequencies) == spec_data.spectrogram.shape[1]
        assert spec_data.config == config
        assert spec_data.channel == 0

    def test_multi_channel_signal(self):
        """Test spectrogram generation with multi-channel input."""
        config = EngineConfig(
            nfft=512,
            channels=2,
            overlap=0.75,
            sample_rate_hz=44100
        )

        # Generate 2-channel signal (0.5 seconds)
        num_samples = config.sample_rate_hz // 2
        signal = np.random.randn(2, num_samples).astype(np.float32)

        # Generate spectrograms for both channels
        with SpectrogramGenerator(config) as generator:
            spec_ch0 = generator.generate(signal, channel=0)
            spec_ch1 = generator.generate(signal, channel=1)

        # Validate both outputs
        assert spec_ch0.channel == 0
        assert spec_ch1.channel == 1
        assert spec_ch0.spectrogram.shape == spec_ch1.spectrogram.shape

    def test_different_overlaps(self):
        """Test that different overlaps produce different time resolutions."""
        config_low = EngineConfig(nfft=1024, channels=1, overlap=0.0)
        config_high = EngineConfig(nfft=1024, channels=1, overlap=0.875)

        signal = np.random.randn(48000).astype(np.float32)

        with SpectrogramGenerator(config_low) as gen_low:
            spec_low = gen_low.generate(signal)

        with SpectrogramGenerator(config_high) as gen_high:
            spec_high = gen_high.generate(signal)

        # High overlap should produce more time steps
        assert spec_high.spectrogram.shape[0] > spec_low.spectrogram.shape[0]

    def test_known_sine_wave(self):
        """Test spectrogram with known sine wave signal."""
        # Generate 1 kHz sine wave
        config = EngineConfig(
            nfft=2048,
            channels=1,
            overlap=0.5,
            sample_rate_hz=48000
        )

        freq_hz = 1000.0
        duration_sec = 1.0
        num_samples = int(config.sample_rate_hz * duration_sec)
        t = np.arange(num_samples) / config.sample_rate_hz
        signal = np.sin(2 * np.pi * freq_hz * t).astype(np.float32)

        # Generate spectrogram
        with SpectrogramGenerator(config) as generator:
            spec_data = generator.generate(signal)

        # Find peak frequency in spectrogram
        mean_spectrum = np.mean(spec_data.spectrogram, axis=0)
        peak_freq_idx = np.argmax(mean_spectrum)
        peak_freq = spec_data.frequencies[peak_freq_idx]

        # Peak should be near 1000 Hz (within frequency resolution)
        freq_resolution = config.sample_rate_hz / config.nfft
        assert abs(peak_freq - freq_hz) < 2 * freq_resolution

    def test_short_signal_error(self):
        """Test that short signals (< NFFT) raise ValueError."""
        config = EngineConfig(nfft=2048, channels=1)

        # Signal shorter than NFFT
        signal = np.random.randn(1000).astype(np.float32)

        with pytest.raises(ValueError, match="Input data too short"):
            with SpectrogramGenerator(config) as generator:
                generator.generate(signal)

    def test_invalid_channel_error(self):
        """Test that invalid channel index raises ValueError."""
        config = EngineConfig(nfft=1024, channels=2)
        signal = np.random.randn(2, 10000).astype(np.float32)

        with pytest.raises(ValueError, match="Channel .* requested"):
            with SpectrogramGenerator(config) as generator:
                generator.generate(signal, channel=2)  # Only channels 0, 1 exist


class TestSpectrogramSaveLoad:
    """Test spectrogram saving and loading."""

    def test_save_and_load_roundtrip(self):
        """Test that save/load preserves spectrogram data."""
        config = EngineConfig(
            nfft=512,
            channels=1,
            overlap=0.625,
            sample_rate_hz=22050
        )

        signal = np.random.randn(22050).astype(np.float32)  # 1 second

        # Generate spectrogram
        with SpectrogramGenerator(config) as generator:
            original = generator.generate(signal)

        # Save to temporary file
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "test_spec.npz"
            save_spectrogram(original, save_path)

            # Load back
            loaded = load_spectrogram(save_path)

        # Validate loaded data matches original
        assert np.allclose(loaded.spectrogram, original.spectrogram)
        assert np.allclose(loaded.times, original.times)
        assert np.allclose(loaded.frequencies, original.frequencies)
        assert loaded.config.nfft == original.config.nfft
        assert loaded.config.channels == original.config.channels
        assert loaded.config.overlap == original.config.overlap
        assert loaded.config.sample_rate_hz == original.config.sample_rate_hz
        assert loaded.channel == original.channel

    def test_save_creates_directory(self):
        """Test that save creates parent directories if needed."""
        config = EngineConfig(nfft=256, channels=1)
        signal = np.random.randn(10000).astype(np.float32)

        with SpectrogramGenerator(config) as generator:
            spec_data = generator.generate(signal)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Deep nested path
            save_path = Path(tmpdir) / "deep" / "nested" / "path" / "spec.npz"
            save_spectrogram(spec_data, save_path)

            # Verify file exists
            assert save_path.exists()

    def test_load_nonexistent_file(self):
        """Test that loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_spectrogram("nonexistent_file.npz")


class TestConvenienceFunctions:
    """Test convenience wrapper functions."""

    def test_generate_spectrogram_function(self):
        """Test generate_spectrogram convenience function."""
        config = EngineConfig(nfft=1024, channels=1, overlap=0.5)
        signal = np.random.randn(10000).astype(np.float32)

        # Use convenience function
        spec_data = generate_spectrogram(signal, config)

        # Validate result
        assert isinstance(spec_data, SpectrogramData)
        assert spec_data.spectrogram.shape[1] == config.nfft // 2 + 1


class TestSpectrogramMetadata:
    """Test spectrogram metadata and axes calculations."""

    def test_time_axis_calculation(self):
        """Test that time axis is calculated correctly."""
        config = EngineConfig(
            nfft=1024,
            channels=1,
            overlap=0.5,
            sample_rate_hz=48000
        )

        signal = np.random.randn(48000).astype(np.float32)  # 1 second

        with SpectrogramGenerator(config) as generator:
            spec_data = generator.generate(signal)

        # Time values should be in seconds
        assert spec_data.times[0] >= 0
        assert spec_data.times[-1] <= 1.0  # Signal is 1 second

        # Time values should increase monotonically
        assert np.all(np.diff(spec_data.times) > 0)

    def test_frequency_axis_calculation(self):
        """Test that frequency axis is calculated correctly."""
        config = EngineConfig(
            nfft=2048,
            channels=1,
            sample_rate_hz=48000
        )

        signal = np.random.randn(48000).astype(np.float32)

        with SpectrogramGenerator(config) as generator:
            spec_data = generator.generate(signal)

        # Frequency should start at 0 Hz
        assert spec_data.frequencies[0] == 0.0

        # Frequency should end at Nyquist (sample_rate / 2)
        nyquist = config.sample_rate_hz / 2
        assert spec_data.frequencies[-1] == pytest.approx(nyquist)

        # Frequency resolution should match nfft
        freq_res = config.sample_rate_hz / config.nfft
        freq_diffs = np.diff(spec_data.frequencies)
        assert np.all(np.isclose(freq_diffs, freq_res))

    def test_spectrogram_dimensions(self):
        """Test that spectrogram dimensions are correct."""
        config = EngineConfig(
            nfft=512,
            channels=1,
            overlap=0.75,
            sample_rate_hz=16000
        )

        duration_sec = 2.0
        num_samples = int(config.sample_rate_hz * duration_sec)
        signal = np.random.randn(num_samples).astype(np.float32)

        with SpectrogramGenerator(config) as generator:
            spec_data = generator.generate(signal)

        # Number of frequency bins
        expected_freq_bins = config.nfft // 2 + 1
        assert spec_data.spectrogram.shape[1] == expected_freq_bins

        # Number of time steps
        hop_size = int(config.nfft * (1 - config.overlap))
        expected_time_steps = 1 + (num_samples - config.nfft) // hop_size
        assert spec_data.spectrogram.shape[0] == expected_time_steps
