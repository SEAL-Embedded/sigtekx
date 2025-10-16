"""Tests for the unified Engine API.

This module tests the v2.0 unified Engine class, ensuring it maintains
all functionality from the previous three-layer architecture while
providing a simpler, more obvious interface.
"""

import warnings
from collections.abc import Generator

import numpy as np
import pytest
from numpy.testing import assert_array_equal

from ionosense_hpc import (
    Engine,
    EngineConfig,
    benchmark_latency,
    process_signal,
)
from ionosense_hpc.exceptions import (
    EngineStateError,
    ValidationError,
)

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def test_config() -> EngineConfig:
    """Small configuration for fast testing."""
    return EngineConfig(
        nfft=256,
        batch=1,
        overlap=0.0,
        sample_rate_hz=1000,
        warmup_iters=0,
        enable_profiling=True
    )


@pytest.fixture
def test_data() -> np.ndarray:
    """Generate test signal data."""
    return np.random.randn(256).astype(np.float32)


@pytest.fixture
def dual_channel_data() -> np.ndarray:
    """Generate dual-channel test data."""
    return np.random.randn(512).astype(np.float32)  # 256 * 2


# -----------------------------------------------------------------------------
# Basic Functionality Tests
# -----------------------------------------------------------------------------

class TestEngineBasics:
    """Test basic Engine functionality."""

    def test_creation_with_preset(self):
        """Test engine creation with string preset."""
        engine = Engine(preset='default')
        assert engine.config.nfft == 1024
        assert engine.config.batch == 2
        assert engine.is_initialized
        engine.close()

    def test_creation_with_config(self, test_config: EngineConfig):
        """Test engine creation with EngineConfig object."""
        engine = Engine(config=test_config)
        assert engine.config == test_config
        assert engine.is_initialized
        engine.close()

    def test_creation_with_none(self):
        """Test engine creation with default config."""
        engine = Engine(None)
        assert engine.config.nfft == 1024  # Default realtime preset
        assert engine.is_initialized
        engine.close()

    def test_invalid_preset(self):
        """Test error on invalid preset name."""
        with pytest.raises(ValueError, match="Unknown preset"):
            Engine("invalid_preset")

    def test_process(self, test_config: EngineConfig, test_data: np.ndarray):
        """Test basic processing."""
        engine = Engine(config=test_config)
        output = engine.process(test_data)

        assert output.shape == (1, 129)  # (batch, nfft//2 + 1)
        assert output.dtype == np.float32
        assert np.all(output >= 0)  # Magnitude is non-negative

        engine.close()

    def test_multiple_process_calls(
        self,
        test_config: EngineConfig,
        test_data: np.ndarray
    ):
        """Test multiple process calls maintain consistency."""
        engine = Engine(config=test_config)

        outputs = []
        for _ in range(3):
            output = engine.process(test_data)
            outputs.append(output)

        # All outputs should be identical for same input
        assert_array_equal(outputs[0], outputs[1])
        assert_array_equal(outputs[1], outputs[2])

        engine.close()


# -----------------------------------------------------------------------------
# Context Manager Tests
# -----------------------------------------------------------------------------

class TestEngineContextManager:
    """Test Engine as context manager."""

    def test_context_manager(self, test_config: EngineConfig, test_data: np.ndarray):
        """Test basic context manager usage."""
        with Engine(config=test_config) as engine:
            assert engine.is_initialized
            output = engine.process(test_data)
            assert output.shape == (1, 129)

        # Engine should be closed after context
        assert not engine.is_initialized

    def test_context_manager_exception(
        self,
        test_config: EngineConfig,
        test_data: np.ndarray
    ):
        """Test context manager with exception."""
        try:
            with Engine(config=test_config) as engine:
                engine.process(test_data)
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Engine should still be closed
        assert not engine.is_initialized

    def test_nested_context_error(self, test_config: EngineConfig):
        """Test that closed engine cannot be re-entered."""
        engine = Engine(config=test_config)
        engine.close()

        with pytest.raises(EngineStateError, match="closed"):
            with engine:
                pass


# -----------------------------------------------------------------------------
# Advanced Options Tests
# -----------------------------------------------------------------------------

class TestEngineAdvancedOptions:
    """Test advanced Engine options for research workflows."""

    def test_validate_inputs_false(self, test_config: EngineConfig):
        """Test that validation still occurs (validate_inputs removed in v0.9.3)."""
        engine = Engine(config=test_config)

        # Should validate and raise ValidationError
        bad_data = np.array([1, 2, 3], dtype=np.float32)  # Wrong size

        with pytest.raises((ValidationError, RuntimeError)):
            engine.process(bad_data)

        engine.close()

    def test_stream_count_override(self, test_config: EngineConfig):
        """Test overriding stream count via config."""
        test_config.stream_count = 5
        engine = Engine(config=test_config)
        assert engine.config.stream_count == 5
        engine.close()


# -----------------------------------------------------------------------------
# Property Tests
# -----------------------------------------------------------------------------

class TestEngineProperties:
    """Test Engine properties."""

    def test_config_property(self, test_config: EngineConfig):
        """Test config property is read-only."""
        engine = Engine(config=test_config)

        assert engine.config == test_config

        # Should not be able to modify
        with pytest.raises(AttributeError):
            engine.config = EngineConfig()  # type: ignore[misc]

        engine.close()

    def test_is_initialized_property(self, test_config: EngineConfig):
        """Test is_initialized property."""
        engine = Engine(config=test_config)
        assert engine.is_initialized is True

        engine.close()
        assert engine.is_initialized is False

    def test_stats_property(
        self,
        test_config: EngineConfig,
        test_data: np.ndarray
    ):
        """Test stats property."""
        engine = Engine(config=test_config)

        # Initial stats
        stats = engine.stats
        assert stats["frames_processed"] == 0

        # After processing
        engine.process(test_data)
        stats = engine.stats
        assert stats["frames_processed"] > 0
        assert stats["latency_us"] > 0

        engine.close()

    def test_device_info_property(self, test_config: EngineConfig):
        """Test device_info property."""
        engine = Engine(config=test_config)

        info = engine.device_info
        assert "device_name" in info
        assert "cuda_version" in info
        assert "device_memory_mb" in info

        engine.close()


# -----------------------------------------------------------------------------
# Error Handling Tests
# -----------------------------------------------------------------------------

class TestEngineErrorHandling:
    """Test Engine error handling."""

    def test_process_wrong_size(self, test_config: EngineConfig):
        """Test error on wrong input size."""
        engine = Engine(config=test_config)
        wrong_size_data = np.zeros(100, dtype=np.float32)

        with pytest.raises(ValidationError, match="size mismatch"):
            engine.process(wrong_size_data)

        engine.close()

    def test_process_wrong_dtype(self, test_config: EngineConfig):
        """Test automatic dtype conversion."""
        engine = Engine(config=test_config)

        # Should convert these
        int_data = np.zeros(256, dtype=np.int32)
        output = engine.process(int_data)
        assert output is not None

        # Should fail on these
        complex_data = np.zeros(256, dtype=np.complex64)
        with pytest.raises(ValidationError, match="Unsupported data type"):
            engine.process(complex_data)

        engine.close()

    def test_process_with_nan(self, test_config: EngineConfig):
        """Test warning on NaN values."""
        engine = Engine(config=test_config)

        nan_data = np.full(256, np.nan, dtype=np.float32)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            engine.process(nan_data)
            assert len(w) == 1
            assert "NaN or Inf" in str(w[0].message)

        engine.close()

    def test_closed_engine_error(self, test_config: EngineConfig):
        """Test error when using closed engine."""
        engine = Engine(config=test_config)
        engine.close()

        with pytest.raises(EngineStateError, match="closed"):
            engine.process(np.zeros(256, dtype=np.float32))

        with pytest.raises(EngineStateError, match="closed"):
            engine.reset()


# -----------------------------------------------------------------------------
# Research Features Tests
# -----------------------------------------------------------------------------

class TestEngineResearchFeatures:
    """Test research-specific features."""

    def test_detailed_metrics(
        self,
        test_config: EngineConfig,
        test_data: np.ndarray
    ):
        """Test detailed metrics with profiling enabled."""
        config = test_config
        config.enable_profiling = True

        engine = Engine(config=config)

        # Process multiple frames
        for _ in range(10):
            engine.process(test_data)

        # Check stats (detailed_metrics may not exist)
        stats = engine.stats
        assert "frames_processed" in stats
        assert stats["frames_processed"] == 10

        engine.close()

    def test_experimental_features(self, test_config: EngineConfig):
        """Test enabling experimental features."""
        engine = Engine(config=test_config)

        # Enable unsafe mode
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            engine.enable_experimental_feature("unsafe_mode")
            assert len(w) == 1
            assert "Unsafe mode" in str(w[0].message)

        # Unknown feature
        with pytest.raises(ValueError, match="Unknown experimental feature"):
            engine.enable_experimental_feature("unknown_feature")

        engine.close()

    def test_cuda_stream_access(self, test_config: EngineConfig):
        """Test CUDA stream access (currently not implemented)."""
        engine = Engine(config=test_config)

        with pytest.raises(NotImplementedError):
            engine.get_cuda_stream(0)

        engine.close()

    def test_device_ptr_access(self, test_config: EngineConfig):
        """Test device pointer access (currently not implemented)."""
        engine = Engine(config=test_config)

        with pytest.raises(NotImplementedError):
            engine.get_device_ptr()

        engine.close()


# -----------------------------------------------------------------------------
# Class Method Tests
# -----------------------------------------------------------------------------

class TestEngineClassMethods:
    """Test Engine class methods."""

    def test_get_available_devices(self):
        """Test getting available CUDA devices."""
        devices = Engine.get_available_devices()
        assert isinstance(devices, list)
        # Should have at least one device in test environment
        # (or empty list if no CUDA)

    def test_select_best_device(self):
        """Test selecting best device."""
        device_id = Engine.select_best_device()
        assert isinstance(device_id, int)
        assert device_id >= 0


# -----------------------------------------------------------------------------
# Convenience Function Tests
# -----------------------------------------------------------------------------

class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_process_signal(self, test_data: np.ndarray):
        """Test one-shot processing function."""
        # With config
        config = EngineConfig(nfft=256, batch=1, overlap=0.0)
        output = process_signal(test_data, config)
        assert output.shape == (1, 129)

        # With preset
        output = process_signal(test_data, preset='default')
        assert output.shape == (1, 513)  # default is 1024 FFT = 513 bins

    def test_benchmark_latency(self):
        """Test benchmarking function."""
        config = EngineConfig(nfft=256, batch=1, overlap=0.0, warmup_iters=0)
        results = benchmark_latency(
            config=config,
            iterations=10,
            data_size=256
        )

        assert "mean" in results
        assert "min" in results
        assert "max" in results
        assert "p99" in results
        assert results["mean"] > 0


# -----------------------------------------------------------------------------
# Lifecycle Tests
# -----------------------------------------------------------------------------

class TestEngineLifecycle:
    """Test Engine lifecycle management."""

    def test_reset(
        self,
        test_config: EngineConfig,
        test_data: np.ndarray
    ):
        """Test engine reset."""
        engine = Engine(config=test_config)

        # Process some data
        engine.process(test_data)

        # Reset
        engine.reset()
        assert engine.is_initialized  # Should auto-reinitialize

        # Stats should be reset
        stats2 = engine.stats
        assert stats2["frames_processed"] == 0

        # Should still work
        output = engine.process(test_data)
        assert output is not None

        engine.close()

    def test_close_idempotent(self, test_config: EngineConfig):
        """Test that close() can be called multiple times."""
        engine = Engine(config=test_config)

        engine.close()
        engine.close()  # Should not error
        engine.close()  # Still safe

        assert not engine.is_initialized

    def test_del_warning(self, test_config: EngineConfig):
        """Test warning on __del__ without close."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            engine = Engine(config=test_config)
            # Simulate deletion without close
            del engine

            # Should have warned about not closing
            assert any("not properly closed" in str(warning.message) for warning in w)


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------

class TestEngineIntegration:
    """Integration tests for complete workflows."""

    def test_full_research_workflow(self):
        """Test complete research workflow."""
        # Custom config for research
        config = EngineConfig(
            nfft=2048,
            batch=4,
            overlap=0.5,
            sample_rate_hz=48000,
            enable_profiling=True
        )

        # Create research engine
        engine = Engine(config=config)

        # Generate test signals
        test_size = config.nfft * config.batch
        signals = [
            np.random.randn(test_size).astype(np.float32)
            for _ in range(10)
        ]

        # Process signals
        outputs = []
        for signal in signals:
            output = engine.process(signal)
            outputs.append(output)

        # Verify outputs
        assert len(outputs) == 10
        assert all(o.shape == (4, 1025) for o in outputs)

        # Check stats
        stats = engine.stats
        assert stats["frames_processed"] == 10

        engine.close()

    def test_streaming_workflow(
        self,
        test_config: EngineConfig
    ):
        """Test streaming data processing."""
        def data_generator() -> Generator[np.ndarray, None, None]:
            """Generate stream of data."""
            for i in range(5):
                yield np.random.randn(256).astype(np.float32)

        with Engine(config=test_config) as engine:
            results = []
            for data in data_generator():
                output = engine.process(data)
                results.append(output)

            assert len(results) == 5
            assert all(r.shape == (1, 129) for r in results)

