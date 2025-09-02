"""Tests for signal generation utilities."""

import pytest
import numpy as np

from ionosense_hpc.utils import (
    make_sine,
    make_chirp,
    make_noise,
    make_multitone,
    make_test_batch
)


class TestSignalGenerators:
    """Test signal generation functions."""
    
    def test_make_sine(self):
        """Test sine wave generation."""
        signal = make_sine(
            frequency=1000,
            duration=0.1,
            sample_rate=48000,
            amplitude=2.0,
            phase=np.pi/2
        )
        
        # Check length
        expected_length = int(0.1 * 48000)
        assert len(signal) == expected_length
        
        # Check amplitude (approximate)
        assert np.max(np.abs(signal)) <= 2.0
        
        # Check dtype
        assert signal.dtype == np.float32
    
    def test_make_chirp_linear(self):
        """Test linear chirp generation."""
        signal = make_chirp(
            f_start=100,
            f_end=1000,
            duration=1.0,
            sample_rate=48000,
            method='linear'
        )
        
        assert len(signal) == 48000
        assert signal.dtype == np.float32
        
        # Frequency should increase over time
        # (This is a simple check, not a rigorous validation)
        first_quarter = signal[:12000]
        last_quarter = signal[-12000:]
        
        # Later part should have more zero crossings (higher frequency)
        first_crossings = np.sum(np.diff(np.sign(first_quarter)) != 0)
        last_crossings = np.sum(np.diff(np.sign(last_quarter)) != 0)
        assert last_crossings > first_crossings
    
    def test_make_chirp_logarithmic(self):
        """Test logarithmic chirp generation."""
        signal = make_chirp(
            f_start=100,
            f_end=10000,
            duration=1.0,
            sample_rate=48000,
            method='logarithmic'
        )
        
        assert len(signal) == 48000
        assert signal.dtype == np.float32
    
    def test_make_chirp_invalid(self):
        """Test chirp with invalid parameters."""
        # Negative frequency for log chirp
        with pytest.raises(ValueError):
            make_chirp(
                f_start=-100,
                f_end=1000,
                duration=1.0,
                method='logarithmic'
            )
        
        # Unknown method
        with pytest.raises(ValueError):
            make_chirp(
                f_start=100,
                f_end=1000,
                duration=1.0,
                method='unknown'
            )
    
    def test_make_noise_white(self):
        """Test white noise generation."""
        signal = make_noise(
            duration=1.0,
            sample_rate=48000,
            noise_type='white',
            amplitude=1.0,
            seed=42
        )
        
        assert len(signal) == 48000
        assert signal.dtype == np.float32
        
        # Check amplitude scaling
        assert np.abs(np.std(signal) - 1.0) < 0.1
        
        # Reproducibility with seed
        signal2 = make_noise(
            duration=1.0,
            sample_rate=48000,
            noise_type='white',
            seed=42
        )
        np.testing.assert_array_equal(signal, signal2)
    
    def test_make_noise_types(self):
        """Test different noise types."""
        for noise_type in ['white', 'pink', 'brown']:
            signal = make_noise(
                duration=0.1,
                sample_rate=48000,
                noise_type=noise_type,
                seed=42
            )
            
            assert len(signal) == 4800
            assert not np.any(np.isnan(signal))
            assert not np.any(np.isinf(signal))
    
    def test_make_multitone(self):
        """Test multi-tone signal generation."""
        frequencies = [1000, 2000, 3000]
        amplitudes = [1.0, 0.5, 0.25]
        
        signal = make_multitone(
            frequencies=frequencies,
            duration=0.1,
            sample_rate=48000,
            amplitudes=amplitudes
        )
        
        assert len(signal) == 4800
        assert signal.dtype == np.float32
        
        # FFT should show peaks at specified frequencies
        fft = np.fft.rfft(signal)
        freqs = np.fft.rfftfreq(len(signal), 1/48000)
        
        # Find peaks (simple method)
        magnitude = np.abs(fft)
        peaks = []
        for f in frequencies:
            idx = np.argmin(np.abs(freqs - f))
            if magnitude[idx] > np.mean(magnitude) * 5:  # Simple threshold
                peaks.append(freqs[idx])
        
        # Should find peaks near the specified frequencies
        assert len(peaks) >= 2  # At least 2 of 3 should be detectable
    
    def test_make_test_batch(self):
        """Test batch signal generation."""
        batch_data = make_test_batch(
            nfft=1024,
            batch=4,
            signal_type='sine',
            frequency=1000,
            seed=42
        )
        
        # Check total size
        assert len(batch_data) == 1024 * 4
        assert batch_data.dtype == np.float32
        
        # Each channel should be slightly different
        channels = batch_data.reshape(4, 1024)
        
        # Channels should be similar but not identical
        for i in range(1, 4):
            correlation = np.corrcoef(channels[0], channels[i])[0, 1]
            assert 0.9 < correlation < 1.0  # High correlation but not 1.0
    
    def test_make_test_batch_types(self):
        """Test different batch signal types."""
        for signal_type in ['sine', 'chirp', 'noise', 'zeros']:
            batch_data = make_test_batch(
                nfft=256,
                batch=2,
                signal_type=signal_type,
                seed=42
            )
            
            assert len(batch_data) == 512
            assert not np.any(np.isnan(batch_data))
            
            if signal_type == 'zeros':
                assert np.all(batch_data == 0)


class TestSignalProperties:
    """Test signal properties and characteristics."""
    
    def test_sine_frequency_accuracy(self):
        """Test that generated sine has correct frequency."""
        frequency = 1000  # Hz
        sample_rate = 48000
        duration = 1.0
        
        signal = make_sine(frequency, duration, sample_rate)
        
        # Use FFT to verify frequency
        fft = np.fft.rfft(signal)
        freqs = np.fft.rfftfreq(len(signal), 1/sample_rate)
        
        # Find peak
        peak_idx = np.argmax(np.abs(fft))
        peak_freq = freqs[peak_idx]
        
        # Should be within 1 Hz (resolution limited by FFT size)
        assert abs(peak_freq - frequency) < 1.0
    
    def test_noise_spectrum(self):
        """Test noise spectral characteristics."""
        # White noise should have flat spectrum
        white = make_noise(
            duration=10.0,  # Long duration for better statistics
            sample_rate=48000,
            noise_type='white',
            seed=42
        )
        
        # Compute spectrum
        fft = np.fft.rfft(white)
        magnitude = np.abs(fft)
        
        # Divide into bands and check flatness
        n_bands = 10
        band_size = len(magnitude) // n_bands
        band_powers = []
        
        for i in range(n_bands):
            start = i * band_size
            end = (i + 1) * band_size
            band_powers.append(np.mean(magnitude[start:end] ** 2))
        
        # All bands should have similar power (within 50%)
        mean_power = np.mean(band_powers)
        for power in band_powers:
            assert 0.5 * mean_power < power < 1.5 * mean_power