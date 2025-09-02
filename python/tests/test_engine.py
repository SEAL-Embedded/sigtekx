"""
Tests for the mid-level Engine wrapper.
"""
import gc
from unittest.mock import ANY, MagicMock, patch

import numpy as np
import pytest

from ionosense_hpc.config import EngineConfig
from ionosense_hpc.core.engine import Engine
from ionosense_hpc.core.raw_engine import RawEngine  # Import RawEngine for spec
from ionosense_hpc.exceptions import EngineStateError, ValidationError


@pytest.fixture
def mock_raw_engine_instance():
    """Provides a mocked instance of RawEngine."""
    # Use RawEngine as the spec for an accurate mock
    mock_instance = MagicMock(spec=RawEngine)
    mock_instance.is_initialized = False

    mock_instance.get_stats.return_value = {
        'latency_us': 10.0,
        'throughput_gbps': 1.0,
        'frames_processed': 1
    }
    # Add the missing get_runtime_info method to the mock's spec
    mock_instance.get_runtime_info.return_value = {
        'device_name': 'MockDevice',
        'cuda_version': '12.0',
        'device_memory_mb': 8192,
        'device_memory_free_mb': 4096
    }
    return mock_instance


@pytest.fixture
def engine_config():
    """Provides a basic EngineConfig instance."""
    return EngineConfig(nfft=1024, batch=2, overlap=0, warmup_iters=0)


@pytest.fixture
def engine(mock_raw_engine_instance):
    """Provides an uninitialized Engine instance with a mocked RawEngine."""
    with patch('ionosense_hpc.core.engine.RawEngine', return_value=mock_raw_engine_instance):
        e = Engine()
        yield e
        # Ensure cleanup for __del__ testing
        if 'e' in locals():
            del e
        gc.collect()


@pytest.fixture
def initialized_engine(engine, engine_config):
    """Provides an initialized Engine instance."""
    def side_effect(*args, **kwargs):
        engine._raw_engine.is_initialized = True

    engine._raw_engine.initialize.side_effect = side_effect

    output_shape = (engine_config.batch, engine_config.num_output_bins)
    engine._raw_engine.process.return_value = np.zeros(output_shape, dtype=np.float32)

    engine.initialize(engine_config)
    return engine


class TestEngineLifecycle:
    """Tests for the lifecycle and properties of the Engine."""

    def test_init_with_config(self, engine_config):
        """Test that __init__ with a config calls initialize."""
        with patch('ionosense_hpc.core.engine.RawEngine') as mock_raw_cls:
            e = Engine(config=engine_config)
            e._raw_engine.initialize.assert_called_once_with(engine_config.model_dump())

    def test_repr_uninitialized(self, engine):
        """Test the __repr__ string for an uninitialized engine."""
        assert "uninitialized" in repr(engine)

    def test_repr_initialized(self, initialized_engine):
        """Test the __repr__ string for an initialized engine."""
        assert "initialized" in repr(initialized_engine)
        # Check for config content, which is more robust than a class name
        assert "nfft=1024" in repr(initialized_engine)

    def test_del_calls_reset(self, engine_config):
        """Test that the destructor calls reset on an initialized engine."""
        with patch('ionosense_hpc.core.engine.RawEngine') as mock_cls:
            mock_cls.return_value.is_initialized = True
            e = Engine(config=engine_config)
            mock_reset = e._raw_engine.reset

            del e
            gc.collect()

            mock_reset.assert_called_once()

    def test_del_suppresses_errors(self, engine_config):
        """Test that __del__ does not raise exceptions if reset fails."""
        with patch('ionosense_hpc.core.engine.RawEngine') as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.is_initialized = True
            mock_instance.reset.side_effect = RuntimeError("Cleanup failed")

            try:
                # This scope is to ensure __del__ is called
                e = Engine(config=engine_config)
                del e
                gc.collect()
            except Exception as e:
                pytest.fail(f"__del__ raised an unexpected exception: {e}")

    def test_properties_uninitialized(self, engine):
        """Test properties on an uninitialized engine."""
        assert not engine.is_initialized
        assert engine.config is None

    def test_properties_initialized(self, initialized_engine, engine_config):
        """Test properties on an initialized engine."""
        assert initialized_engine.is_initialized
        assert initialized_engine.config == engine_config
        initialized_engine.device_info
        initialized_engine._raw_engine.get_runtime_info.assert_called_once()


class TestEngineProcessing:
    """Tests for the data processing methods."""

    def test_process_list_input(self, initialized_engine, engine_config):
        """Test processing a plain list of floats."""
        input_data = [0.0] * (engine_config.nfft * engine_config.batch)
        initialized_engine.process(input_data)
        initialized_engine._raw_engine.process.assert_called_once()
        call_args = initialized_engine._raw_engine.process.call_args[0]
        assert isinstance(call_args[0], np.ndarray)

    def test_process_with_output_buffer(self, initialized_engine, engine_config):
        """Test processing with a pre-allocated output buffer."""
        input_data = np.zeros(engine_config.nfft * engine_config.batch, dtype=np.float32)
        output_buffer = np.zeros((engine_config.batch, engine_config.num_output_bins), dtype=np.float32)

        mock_result = np.ones_like(output_buffer)
        initialized_engine._raw_engine.process.return_value = mock_result

        result = initialized_engine.process(input_data, output=output_buffer)

        assert np.array_equal(result, mock_result)
        assert result is output_buffer
        assert np.all(output_buffer == 1.0)

    def test_process_frames_basic(self, initialized_engine, engine_config):
        """Test basic frame processing functionality."""
        frame_size = engine_config.nfft * engine_config.batch
        hop_size = engine_config.hop_size
        num_frames = 3

        input_data = np.zeros((num_frames - 1) * hop_size * engine_config.batch + frame_size, dtype=np.float32)

        result = initialized_engine.process_frames(input_data)

        assert result.shape == (num_frames, engine_config.batch, engine_config.num_output_bins)
        assert initialized_engine._raw_engine.process.call_count == num_frames

    def test_initialize_runs_warmup(self):
        """Test that warmup iterations are run during initialization."""
        config = EngineConfig(warmup_iters=5)
        with patch('ionosense_hpc.core.engine.RawEngine') as mock_raw_cls:
            mock_raw_cls.return_value.get_stats.return_value = {'latency_us': 1.0}
            engine = Engine(config=config)
            assert engine._raw_engine.process.call_count == config.warmup_iters


class TestEngineErrorHandling:
    """Tests for various error conditions."""

    def test_process_not_initialized(self, engine):
        """Test that calling process before init raises an error."""
        with pytest.raises(EngineStateError, match="not initialized"):
            engine.process(np.zeros(10))

    def test_process_frames_not_initialized(self, engine):
        """Test that calling process_frames before init raises an error."""
        with pytest.raises(EngineStateError, match="not initialized"):
            engine.process_frames(np.zeros(10))

    def test_process_invalid_output_buffer_shape(self, initialized_engine):
        """Test providing an output buffer with the wrong shape."""
        input_data = np.zeros(1024 * 2, dtype=np.float32)
        bad_output_buffer = np.zeros((1, 1))
        with pytest.raises(ValidationError, match="Output buffer shape mismatch"):
            initialized_engine.process(input_data, output=bad_output_buffer)

    def test_process_frames_input_too_short(self, initialized_engine, engine_config):
        """Test process_frames with an input signal that is too short."""
        short_input = np.zeros(engine_config.nfft - 1, dtype=np.float32)
        with pytest.raises(ValidationError, match="Input too short"):
            initialized_engine.process_frames(short_input)


class TestEngineStats:
    """Tests for statistics and logging."""

    def test_get_stats_averaging(self, initialized_engine):
        """Test that get_stats correctly calculates average latency."""
        latencies = [100.0, 150.0, 200.0, 200.0]
        stats_list = [{'latency_us': l} for l in latencies]

        initialized_engine._raw_engine.get_stats.side_effect = stats_list

        input_data = np.zeros(1024 * 2, dtype=np.float32)
        for _ in range(3):
            initialized_engine.process(input_data)

        stats = initialized_engine.get_stats()

        assert stats['total_frames'] == 3
        assert stats['avg_latency_us'] == pytest.approx(150.0)

    def test_log_performance(self, initialized_engine):
        """Test that log_performance calls get_stats and the logger."""
        with patch('ionosense_hpc.core.engine.log_performance') as mock_log:
            initialized_engine.log_performance()
            mock_log.assert_called_once_with(ANY)
            assert initialized_engine._raw_engine.get_stats.called

