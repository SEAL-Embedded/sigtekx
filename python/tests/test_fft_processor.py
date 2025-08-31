"""
Tests for the high-level FFTProcessor API.
"""
import pytest
import numpy as np
from ionosense_hpc import FFTProcessor

def test_processor_initialization(fft_processor_instance: FFTProcessor):
    """Tests that the FFTProcessor initializes correctly."""
    assert fft_processor_instance.fft_size == 2048
    assert fft_processor_instance.batch_size == 2
    assert fft_processor_instance.num_streams == 3

def test_processor_simple_process(fft_processor_instance: FFTProcessor):
    """Tests a single, synchronous processing call."""
    fft_size = fft_processor_instance.fft_size
    ch1 = np.random.randn(fft_size).astype(np.float32)
    ch2 = np.random.randn(fft_size).astype(np.float32)

    result = fft_processor_instance.process(ch1, ch2)

    assert result.shape == (2, fft_size // 2 + 1)
    assert result.dtype == np.float32

def test_processor_wrong_input_count(fft_processor_instance: FFTProcessor):
    """Tests that providing the wrong number of inputs raises an error."""
    fft_size = fft_processor_instance.fft_size
    ch1 = np.random.randn(fft_size).astype(np.float32)
    with pytest.raises(ValueError, match="Expected 2 inputs, got 1"):
        fft_processor_instance.process(ch1)

def test_processor_wrong_input_shape(fft_processor_instance: FFTProcessor):
    """Tests that providing inputs with the wrong shape raises an error."""
    fft_size = fft_processor_instance.fft_size
    ch1 = np.random.randn(fft_size).astype(np.float32)
    ch2_wrong = np.random.randn(1024).astype(np.float32)
    with pytest.raises(ValueError, match="Input 1 has shape"):
        fft_processor_instance.process(ch1, ch2_wrong)

def test_processor_batch_process(fft_processor_instance: FFTProcessor):
    """Tests processing a pre-constructed batch of data."""
    fft_size = fft_processor_instance.fft_size
    batch_size = fft_processor_instance.batch_size
    batch_data = np.random.randn(batch_size, fft_size).astype(np.float32)

    result = fft_processor_instance.process_batch(batch_data)
    assert result.shape == (batch_size, fft_size // 2 + 1)

def test_processor_with_window(fft_processor_instance: FFTProcessor):
    """Verifies that setting a window works."""
    fft_processor_instance.set_window('hann')
    # This just tests the mechanism, not the numerical result (which is in integration)
    assert fft_processor_instance._window_data is not None
    assert fft_processor_instance._window_data.shape == (fft_processor_instance.fft_size,)
