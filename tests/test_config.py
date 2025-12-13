"""Tests for configuration module."""

import numpy as np
import pytest
from pydantic import ValidationError

from sigtekx.config import EngineConfig, get_preset, list_presets, validate_input_array
from sigtekx.exceptions import ValidationError as SigTekXValidationError


class TestEngineConfig:
    """Test EngineConfig validation and properties."""

    def test_default_config(self):
        """Test default configuration values."""
        config = EngineConfig()
        assert config.nfft == 1024
        assert config.channels == 2
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
            EngineConfig(nfft=65536, channels=256)


class TestPresets:
    """Test configuration presets."""

    def test_default_preset(self):
        """Test default preset configuration (batch)."""
        config = get_preset('default')
        assert config.nfft == 1024
        assert config.channels == 2
        assert config.overlap == 0.5
        assert config.warmup_iters == 1

    def test_default_preset_streaming(self):
        """Test default preset configuration (streaming)."""
        config = get_preset('default', executor='streaming')
        assert config.nfft == 1024
        assert config.channels == 2
        assert config.overlap == 0.5
        assert config.stream_count == 4  # More streams for streaming

    def test_iono_preset_batch(self):
        """Test ionosphere preset configuration (batch - throughput)."""
        config = get_preset('iono', executor='batch')
        assert config.nfft == 16384  # Higher resolution for throughput
        assert config.channels == 32    # More channels
        assert config.overlap == 0.75
        assert config.pinned_buffer_count == 4

    def test_iono_preset_streaming(self):
        """Test ionosphere preset configuration (streaming - latency)."""
        config = get_preset('iono', executor='streaming')
        assert config.nfft == 4096  # Lower resolution for latency
        assert config.channels == 2    # Fewer channels
        assert config.overlap == 0.75
        assert config.stream_count == 6  # More streams for pipelining

    def test_ionox_preset_batch(self):
        """Test extreme ionosphere preset configuration (batch)."""
        config = get_preset('ionox', executor='batch')
        assert config.nfft == 32768  # Maximum resolution
        assert config.channels == 32    # Many channels
        assert config.overlap == 0.9375
        assert config.warmup_iters == 10

    def test_ionox_preset_streaming(self):
        """Test extreme ionosphere preset configuration (streaming)."""
        config = get_preset('ionox', executor='streaming')
        assert config.nfft == 8192   # Balanced for quality and latency
        assert config.channels == 2
        assert config.overlap == 0.9
        assert config.warmup_iters == 10

    def test_custom_preset(self):
        """Test custom preset creation with overrides."""
        config = EngineConfig.from_preset('default', nfft=2048, channels=4)
        assert config.nfft == 2048
        assert config.channels == 4

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
        with pytest.raises(SigTekXValidationError):
            validate_input_array([1, 2, 3])

        # Shape mismatch
        data = np.array([1, 2, 3])
        with pytest.raises(SigTekXValidationError):
            validate_input_array(data, expected_shape=(4,))

    def test_nan_warning(self):
        """Test warning for NaN values."""
        data = np.array([1.0, np.nan, 3.0], dtype=np.float32)
        with pytest.warns(RuntimeWarning):
            validate_input_array(data)


@pytest.mark.parametrize("nfft,channels,expected_mb", [
    (1024, 2, 0),     # Small config: 0.04 MB buffers + 0.03 MB workspace ≈ 0 MB
    (4096, 32, 4),    # Medium config: 2.50 MB buffers + 2.00 MB workspace ≈ 4 MB
    (16384, 128, 72)  # Large config: 40.00 MB buffers + 32.00 MB workspace ≈ 72 MB
])
def test_memory_estimation(nfft, channels, expected_mb):
    """Test memory usage estimation.

    Validates GPU memory estimates using precise cuFFT workspace calculation
    from cufftEstimate1d() API (introduced in commit 5297b0c).
    """
    from sigtekx.config import estimate_memory_usage_mb

    config = EngineConfig(nfft=nfft, channels=channels)
    estimated = estimate_memory_usage_mb(config)

    # Should be within a reasonable range or both be small.
    assert np.isclose(estimated, expected_mb, atol=3) or (estimated < 1 and expected_mb < 1)


class TestCuFFTWorkspaceEstimation:
    """Test precise cuFFT workspace estimation integration."""

    def test_binding_available(self):
        """Verify C++ binding is accessible."""
        from sigtekx.core import _native
        assert hasattr(_native, 'estimate_cufft_workspace_bytes')

    def test_basic_estimation(self):
        """Test basic cuFFT workspace estimation."""
        from sigtekx.core import _native

        workspace = _native.estimate_cufft_workspace_bytes(4096, 8)
        assert isinstance(workspace, int)
        assert workspace >= 0  # May be 0 or heuristic value

    @pytest.mark.parametrize("nfft,channels", [
        (1024, 1),
        (4096, 8),
        (8192, 8),
        (16384, 4),
    ])
    def test_ionosphere_configs(self, nfft, channels):
        """Test memory estimation for ionosphere configurations."""
        from sigtekx.config import estimate_memory_usage_mb

        config = EngineConfig(nfft=nfft, channels=channels, overlap=0.75)
        memory_mb = estimate_memory_usage_mb(config)

        # Should return a non-negative estimate
        assert memory_mb >= 0

    def test_fallback_on_binding_failure(self):
        """Test graceful fallback when binding is unavailable."""
        from sigtekx.config import estimate_memory_usage_mb

        config = EngineConfig(nfft=4096, channels=8)

        # Should not crash even if binding fails
        memory_mb = estimate_memory_usage_mb(config)
        assert memory_mb >= 0

    def test_r2c_vs_c2c(self):
        """Test R2C vs C2C transform estimation."""
        from sigtekx.core import _native

        nfft, channels = 4096, 8

        workspace_r2c = _native.estimate_cufft_workspace_bytes(nfft, channels, True)
        workspace_c2c = _native.estimate_cufft_workspace_bytes(nfft, channels, False)

        # Both should be non-negative
        assert workspace_r2c >= 0
        assert workspace_c2c >= 0

    def test_experiments_validation_reuse(self):
        """Test that experiments validation reuses core logic."""
        import sys
        from pathlib import Path

        # Add experiments to path
        experiments_path = Path(__file__).parent.parent / 'experiments'
        if str(experiments_path) not in sys.path:
            sys.path.insert(0, str(experiments_path))

        from conf.validation import ConfigValidator

        validator = ConfigValidator()

        # Test memory estimation method exists and works
        mem_mb = validator._estimate_memory_usage(nfft=4096, channels=8)
        assert isinstance(mem_mb, (int, float))
        assert mem_mb >= 0

