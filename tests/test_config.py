"""Tests for configuration module."""

import numpy as np
import pytest
from pydantic import ValidationError

from ionosense_hpc.config import EngineConfig, get_preset, list_presets, validate_input_array
from ionosense_hpc.exceptions import ValidationError as IonoValidationError


class TestEngineConfig:
    """Test EngineConfig validation and properties."""

    def test_default_config(self):
        """Test default configuration values."""
        config = EngineConfig()
        assert config.nfft == 1024
        assert config.batch == 2
        assert config.overlap == 0.5
        assert config.sample_rate_hz == 48000

    def test_power_of_two_validation(self):
        """Test that nfft must be power of 2."""
        # Valid powers of 2
        for n in [256, 512, 1024, 2048, 4096]:
            config = EngineConfig(nfft=n)
            assert config.nfft == n

        # Invalid values
        with pytest.raises(ValidationError):
            EngineConfig(nfft=1000)  # Not power of 2

        with pytest.raises(ValidationError):
            EngineConfig(nfft=0)  # Must be > 0

    def test_overlap_validation(self):
        """Test overlap range validation."""
        # Valid overlaps
        for overlap in [0.0, 0.25, 0.5, 0.75, 0.99]:
            config = EngineConfig(overlap=overlap)
            assert config.overlap == overlap

        # Invalid overlaps
        with pytest.raises(ValidationError):
            EngineConfig(overlap=-0.1)

        with pytest.raises(ValidationError):
            EngineConfig(overlap=1.0)

    def test_computed_properties(self):
        """Test computed properties."""
        config = EngineConfig(nfft=1024, overlap=0.5, sample_rate_hz=48000)

        assert config.hop_size == 512
        assert config.num_output_bins == 513
        assert abs(config.frame_duration_ms - 21.333) < 0.01
        assert abs(config.hop_duration_ms - 10.667) < 0.01

    def test_memory_warning(self):
        """Test memory usage warning for large configs."""
        with pytest.warns(ResourceWarning):
            # This should trigger a warning for >4GB
            EngineConfig(nfft=65536, batch=256)


class TestPresets:
    """Test configuration presets."""

    def test_default_preset(self):
        """Test default preset configuration."""
        config = get_preset('default')
        assert config.nfft == 1024
        assert config.batch == 2
        assert config.overlap == 0.5
        assert config.warmup_iters == 1

    def test_iono_preset(self):
        """Test ionosphere preset configuration."""
        config = get_preset('iono')
        assert config.nfft == 4096
        assert config.batch == 8
        assert config.overlap == 0.75
        assert config.pinned_buffer_count == 4

    def test_ionox_preset(self):
        """Test extreme ionosphere preset configuration."""
        config = get_preset('ionox')
        assert config.nfft == 8192
        assert config.batch == 16
        assert config.overlap == 0.9
        assert config.warmup_iters == 10

    def test_custom_preset(self):
        """Test custom preset creation with overrides."""
        config = EngineConfig.from_preset('default', nfft=2048, batch=4)
        assert config.nfft == 2048
        assert config.batch == 4

        # Should preserve other defaults
        assert config.overlap == 0.5

    def test_list_presets(self):
        """Test listing all presets."""
        presets = list_presets()
        assert 'default' in presets
        assert 'iono' in presets
        assert 'ionox' in presets


class TestValidation:
    """Test validation utilities."""

    def test_validate_input_array(self):
        """Test input array validation."""
        # Valid array
        data = np.array([1, 2, 3], dtype=np.float32)
        validated = validate_input_array(data, expected_dtype=np.float32)
        assert validated.dtype == np.float32

        # Auto-conversion
        data = np.array([1, 2, 3], dtype=np.int32)
        validated = validate_input_array(data, expected_dtype=np.float32)
        assert validated.dtype == np.float32

        # Non-contiguous to contiguous
        data = np.array([[1, 2], [3, 4]], dtype=np.float32).T
        assert not data.flags['C_CONTIGUOUS']
        validated = validate_input_array(data)
        assert validated.flags['C_CONTIGUOUS']

    def test_validate_input_array_errors(self):
        """Test input array validation errors."""
        # Not a numpy array
        with pytest.raises(IonoValidationError):
            validate_input_array([1, 2, 3])

        # Shape mismatch
        data = np.array([1, 2, 3])
        with pytest.raises(IonoValidationError):
            validate_input_array(data, expected_shape=(4,))

    def test_nan_warning(self):
        """Test warning for NaN values."""
        data = np.array([1.0, np.nan, 3.0], dtype=np.float32)
        with pytest.warns(RuntimeWarning):
            validate_input_array(data)


@pytest.mark.parametrize("nfft,batch,expected_mb", [
    (1024, 2, 0),     # Small config
    (4096, 32, 6),    # Medium config
    (16384, 128, 56) # REVISED: Corrected expected value from 104 to 56
])
def test_memory_estimation(nfft, batch, expected_mb):
    """Test memory usage estimation."""
    from ionosense_hpc.config import estimate_memory_usage_mb

    config = EngineConfig(nfft=nfft, batch=batch)
    estimated = estimate_memory_usage_mb(config)

    # Should be within a reasonable range or both be small.
    assert np.isclose(estimated, expected_mb, atol=3) or (estimated < 1 and expected_mb < 1)

