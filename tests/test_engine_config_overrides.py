"""Tests for Engine configuration override mechanism using model_copy()."""

import pytest

from sigtekx import Engine
from sigtekx.exceptions import ConfigError


class TestEngineConfigOverrides:
    """Test Engine configuration override validation."""

    def test_valid_overrides(self):
        """Test that valid overrides work correctly."""
        with Engine(preset='default', nfft=2048, overlap=0.75) as engine:
            assert engine.config.nfft == 2048
            assert engine.config.overlap == 0.75

    def test_invalid_type_override(self):
        """Test that invalid type raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            Engine(preset='default', nfft="invalid")

        err = exc_info.value
        assert err.field == 'nfft'
        assert err.value == 'invalid'
        assert 'Invalid configuration override' in str(err)

    def test_out_of_range_override(self):
        """Test that out-of-range value raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            Engine(preset='default', overlap=1.5)

        err = exc_info.value
        assert err.field == 'overlap'
        assert err.value == 1.5
        assert 'Invalid configuration override' in str(err)

    def test_unknown_parameter_override(self):
        """Test that unknown parameter raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            Engine(preset='default', unknown_param=123)

        err = exc_info.value
        assert 'unknown_param' in str(err).lower()
        assert 'Invalid configuration override' in str(err)

    def test_type_coercion_works(self):
        """Test that Pydantic type coercion works (string to int)."""
        with Engine(preset='default', nfft="4096") as engine:
            assert engine.config.nfft == 4096
            assert isinstance(engine.config.nfft, int)

    def test_power_of_two_validation(self):
        """Test that nfft power-of-two validation works."""
        with pytest.raises(ConfigError) as exc_info:
            Engine(preset='default', nfft=1000)

        err = exc_info.value
        assert err.field == 'nfft'
        assert 'power of 2' in str(err).lower()

    def test_multiple_overrides(self):
        """Test multiple overrides applied together."""
        with Engine(
            preset='default',
            nfft=8192,
            overlap=0.875,
            channels=4,
            sample_rate_hz=96000
        ) as engine:
            assert engine.config.nfft == 8192
            assert engine.config.overlap == 0.875
            assert engine.config.channels == 4
            assert engine.config.sample_rate_hz == 96000

    def test_negative_overlap_raises_error(self):
        """Test that negative overlap raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            Engine(preset='default', overlap=-0.1)

        err = exc_info.value
        assert err.field == 'overlap'
        assert err.value == -0.1

    def test_zero_channels_raises_error(self):
        """Test that zero channels raises ConfigError."""
        with pytest.raises(ConfigError) as exc_info:
            Engine(preset='default', channels=0)

        err = exc_info.value
        assert err.field == 'channels'
        assert err.value == 0

    def test_error_includes_hint(self):
        """Test that ConfigError includes helpful hint."""
        with pytest.raises(ConfigError) as exc_info:
            Engine(preset='default', nfft="not_a_number")

        err = exc_info.value
        assert err.hint is not None
        assert 'nfft' in err.hint

    def test_override_after_mode_application(self):
        """Test that overrides work after mode is applied."""
        with Engine(preset='default', mode='streaming', nfft=8192) as engine:
            assert engine.config.nfft == 8192
            assert engine.config.mode.value == 'streaming'

    def test_config_error_has_error_code(self):
        """Test that ConfigError includes error code E1010."""
        with pytest.raises(ConfigError) as exc_info:
            Engine(preset='default', nfft="invalid")

        err = exc_info.value
        assert err.error_code == "E1010"

    def test_chained_exception_preserved(self):
        """Test that original Pydantic error is preserved."""
        with pytest.raises(ConfigError) as exc_info:
            Engine(preset='default', nfft="invalid")

        # Check that Pydantic ValidationError is in the chain
        assert exc_info.value.__cause__ is not None
        import pydantic
        assert isinstance(exc_info.value.__cause__, pydantic.ValidationError)
