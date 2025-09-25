# tests/test_fixtures.py

from pathlib import Path

import numpy as np
import pytest

from ionosense_hpc import Engine
from ionosense_hpc.config import EngineConfig


def test_temp_data_dir(temp_data_dir):
    """Test the temp_data_dir fixture."""
    assert isinstance(temp_data_dir, Path)
    assert temp_data_dir.is_dir()
    assert temp_data_dir.name == "test_data"

def test_config_fixtures(validation_config, realtime_config, benchmark_config):
    """Test the config-related fixtures."""
    assert isinstance(validation_config, EngineConfig)
    assert validation_config.nfft == 256

    assert isinstance(realtime_config, EngineConfig)
    assert realtime_config.nfft == 1024

    assert isinstance(benchmark_config, EngineConfig)
    assert benchmark_config.enable_profiling is True

@pytest.mark.gpu
def test_test_engine(test_engine):
    """Test the test_engine fixture."""
    assert isinstance(test_engine, Engine)
    assert test_engine.is_initialized is True

def test_seeded_rng(seeded_rng):
    """Test the seeded_rng fixture."""
    assert isinstance(seeded_rng, np.random.Generator)
    assert seeded_rng.random() == np.random.default_rng(seed=42).random()

def test_data_generation_fixtures(test_sine_data, test_batch_data, test_noise_data, reference_fft_output):
    """Test the data generation fixtures."""
    assert isinstance(test_sine_data, np.ndarray)
    assert test_sine_data.dtype == np.float32

    assert test_batch_data.shape == (2048,)

    assert isinstance(test_noise_data, np.ndarray)

    assert isinstance(reference_fft_output, np.ndarray)
    assert len(reference_fft_output) == 256 // 2 + 1

def test_mock_device_info(mock_device_info):
    """Test the mock_device_info fixture."""
    assert isinstance(mock_device_info, dict)
    assert mock_device_info['name'] == 'Mock GPU'
    assert 'memory_total_mb' in mock_device_info

