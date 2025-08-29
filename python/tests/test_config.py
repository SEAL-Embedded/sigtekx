# python/tests/test_config.py
"""
Unit tests for the ProcessingConfig class.
"""
import pytest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

# CORRECTED IMPORT PATH: Now points to ionosense_hpc.utils.config
from ionosense_hpc.utils.config import ProcessingConfig, PYNVML_AVAILABLE

pytestmark = pytest.mark.config


def test_valid_config_creation():
    """Tests that a ProcessingConfig can be created with valid, explicit parameters."""
    config = ProcessingConfig(
        fft_size=2048,
        batch_size=16,
        window='hamming',
        output_type='power'
    )
    assert config.fft_size == 2048
    assert config.batch_size == 16
    assert config.window == 'hamming'
    assert config.output_type == 'power'
    assert config.use_graphs is True


def test_fft_size_validation():
    """Tests that non-power-of-2 FFT sizes raise a ValueError."""
    with pytest.raises(ValueError, match="must be a positive power of 2"):
        ProcessingConfig(fft_size=1000)
    with pytest.raises(ValueError, match="must be a positive power of 2"):
        ProcessingConfig(fft_size=-4096)


def test_batch_size_validation():
    """Tests that invalid batch sizes (odd, zero, negative) raise a ValueError."""
    with pytest.raises(ValueError, match="must be a positive, even number"):
        ProcessingConfig(batch_size=7)
    with pytest.raises(ValueError, match="must be a positive, even number"):
        ProcessingConfig(batch_size=0)
    with pytest.raises(ValueError, match="must be a positive, even number"):
        ProcessingConfig(batch_size=-8)


def test_string_option_validation():
    """Tests that invalid string options for window/output raise a ValueError."""
    with pytest.raises(ValueError, match="Unsupported window function"):
        ProcessingConfig(window='invalid_window')
    with pytest.raises(ValueError, match="Unsupported output type"):
        ProcessingConfig(output_type='invalid_output')


def test_immutability():
    """Tests that the config object is frozen and cannot be modified after creation."""
    config = ProcessingConfig()
    with pytest.raises(FrozenInstanceError):
        config.fft_size = 1024


def test_get_engine_params():
    """Tests the conversion to a dictionary for the C++ engine."""
    config = ProcessingConfig(fft_size=8192, batch_size=8, use_graphs=False)
    params = config.get_engine_params()
    expected_params = {
        'nfft': 8192,
        'batch': 8,
        'use_graphs': False,
    }
    assert params == expected_params


@patch('ionosense_hpc.utils.config.PYNVML_AVAILABLE', False)
def test_auto_tune_batch_size_fallback():
    """
    Tests the fallback auto-tuning logic when pynvml is not available.
    """
    config_medium = ProcessingConfig(fft_size=4096, batch_size=None)
    assert config_medium.batch_size == 32


@pytest.mark.skipif(not PYNVML_AVAILABLE, reason="pynvml is not installed, cannot run GPU memory test")
def test_auto_tune_with_pynvml():
    """
    Tests that auto-tuning runs without error when pynvml is available.
    """
    config = ProcessingConfig(fft_size=4096, batch_size=None)
    assert config.batch_size is not None
    assert config.batch_size > 0
    assert config.batch_size % 2 == 0
    print(f"\n(PYNVML) Auto-tuned batch size to: {config.batch_size}")

