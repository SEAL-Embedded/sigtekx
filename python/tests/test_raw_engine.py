"""
Tests for the low-level RawEngine wrapper to improve test coverage.
"""

import gc
import sys
import warnings
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

# Assuming the module structure from the coverage report
from ionosense_hpc.core.raw_engine import RawEngine, import_engine
from ionosense_hpc.exceptions import (
    DllLoadError,
    EngineRuntimeError,
)


@pytest.fixture
def mock_engine_module():
    """Fixture to provide a mock of the C++ _engine extension module."""
    mock_module = MagicMock()
    mock_module.ResearchEngine.return_value = MagicMock()
    mock_module.EngineConfig.return_value = MagicMock()
    return mock_module


@pytest.fixture
def raw_engine(mock_engine_module):
    """Fixture to get an instance of an uninitialized RawEngine with a mocked backend."""
    with patch("ionosense_hpc.core.raw_engine.import_engine", return_value=mock_engine_module):
        engine = RawEngine()
        yield engine
        # Ensure cleanup for __del__ testing
        if 'engine' in locals():
            del engine
        gc.collect()


@pytest.fixture
def initialized_raw_engine(raw_engine):
    """Fixture for an initialized RawEngine instance."""
    config = {"nfft": 1024, "batch_size": 2, "overlap": 0, "device_id": 0}
    raw_engine.initialize(config)
    return raw_engine


class TestRawEngineLifecycle:
    """Tests for the lifecycle and properties of RawEngine."""

    def test_repr_uninitialized(self, raw_engine):
        """Test the __repr__ string for an uninitialized engine."""
        assert "uninitialized" in repr(raw_engine)

    def test_repr_initialized(self, initialized_raw_engine):
        """Test the __repr__ string for an initialized engine."""
        assert "initialized" in repr(initialized_raw_engine)

    def test_config_property_uninitialized(self, raw_engine):
        """Test the config property on an uninitialized engine."""
        assert raw_engine.config is None

    def test_config_property_initialized(self, initialized_raw_engine):
        """Test the config property on an initialized engine."""
        config = initialized_raw_engine.config
        assert isinstance(config, dict)
        assert config["nfft"] == 1024
        # Ensure it's a copy
        config["nfft"] = 999
        assert initialized_raw_engine.config["nfft"] == 1024

    def test_del_suppresses_errors(self, mock_engine_module):
        """Test that __del__ does not raise exceptions if reset fails."""
        mock_engine_instance = mock_engine_module.ResearchEngine.return_value
        mock_engine_instance.reset.side_effect = RuntimeError("Cleanup failed")

        with patch("ionosense_hpc.core.raw_engine.import_engine", return_value=mock_engine_module):
            engine = RawEngine()
            config = {"nfft": 1024, "batch_size": 2, "overlap": 0, "device_id": 0}
            engine.initialize(config)

            # Deleting the object should not raise an exception
            try:
                del engine
                gc.collect()
            except Exception as e:
                pytest.fail(f"__del__ raised an unexpected exception: {e}")


class TestRawEngineProcessing:
    """Tests for the data processing methods."""

    def test_process_with_float64_input(self, initialized_raw_engine):
        """Test that non-float32 input is correctly cast."""
        input_data = np.random.randn(1024 * 2).astype(np.float64)
        initialized_raw_engine.process(input_data)
        # Check if the mock was called with a float32 array
        called_with_arg = initialized_raw_engine._engine.process.call_args[0][0]
        assert called_with_arg.dtype == np.float32

    def test_process_with_non_contiguous_input(self, initialized_raw_engine):
        """Test that non-contiguous input is made contiguous."""
        input_data = np.random.randn(1024 * 4).astype(np.float32)[::2]
        assert not input_data.flags['C_CONTIGUOUS']
        initialized_raw_engine.process(input_data)
        called_with_arg = initialized_raw_engine._engine.process.call_args[0][0]
        assert called_with_arg.flags['C_CONTIGUOUS']

    def test_synchronize_uninitialized(self, raw_engine):
        """Test that synchronize returns early if not initialized."""
        raw_engine.synchronize()
        raw_engine._engine.synchronize.assert_not_called()

    def test_get_stats_uninitialized(self, raw_engine):
        """Test get_stats returns zero-dict if not initialized."""
        stats = raw_engine.get_stats()
        assert stats == {
            'latency_us': 0.0,
            'throughput_gbps': 0.0,
            'frames_processed': 0
        }
        raw_engine._engine.get_stats.assert_not_called()


class TestRawEngineErrorHandling:
    """Tests for exception handling and warnings."""

    def test_initialize_runtime_error(self, raw_engine):
        """Test that a C++ RuntimeError on init raises EngineRuntimeError."""
        raw_engine._engine.initialize.side_effect = RuntimeError("Init failed")
        with pytest.raises(EngineRuntimeError, match="Failed to initialize engine"):
            raw_engine.initialize({})

    def test_process_size_mismatch_error(self, initialized_raw_engine):
        """Test specific error message for size mismatch."""
        initialized_raw_engine._engine.process.side_effect = RuntimeError("Size mismatch")
        with pytest.raises(EngineRuntimeError, match="Input size error"):
            initialized_raw_engine.process(np.zeros(1, dtype=np.float32))

    def test_process_generic_runtime_error(self, initialized_raw_engine):
        """Test generic error message for other processing errors."""
        initialized_raw_engine._engine.process.side_effect = RuntimeError("Generic error")
        with pytest.raises(EngineRuntimeError, match="Processing failed"):
            initialized_raw_engine.process(np.zeros(1024 * 2, dtype=np.float32))

    def test_reset_warning(self, initialized_raw_engine):
        """Test that a C++ RuntimeError on reset issues a warning."""
        initialized_raw_engine._engine.reset.side_effect = RuntimeError("Reset failed")
        with pytest.warns(UserWarning, match="Reset warning: Reset failed"):
            initialized_raw_engine.reset()

    def test_synchronize_error(self, initialized_raw_engine):
        """Test that a C++ RuntimeError on sync raises EngineRuntimeError."""
        initialized_raw_engine._engine.synchronize.side_effect = RuntimeError("Sync failed")
        with pytest.raises(EngineRuntimeError, match="Synchronization failed"):
            initialized_raw_engine.synchronize()

    def test_get_runtime_info_missing_attrs(self, raw_engine):
        """Test get_runtime_info handles info objects without memory attributes."""
        mock_info = MagicMock()
        # Use del to ensure the attribute is missing, not just None
        del mock_info.device_memory_total_mb
        del mock_info.device_memory_free_mb

        raw_engine._engine.get_runtime_info.return_value = mock_info
        info = raw_engine.get_runtime_info()
        assert info['device_memory_mb'] == 0
        assert info['device_memory_free_mb'] == 0


class TestEngineImportAndDevice:
    """Tests for the standalone import_engine function and device classmethods."""

    def test_import_engine_dll_load_failed(self):
        """Test DllLoadError for 'DLL load failed' message."""
        module_name = 'ionosense_hpc.core._engine'
        with patch.dict('sys.modules', {module_name: None}):
            with patch('builtins.__import__', side_effect=ImportError("DLL load failed")):
                with pytest.raises(DllLoadError):
                    import_engine()

    def test_import_engine_no_module(self):
        """Test DllLoadError for 'No module named' message."""
        module_name = 'ionosense_hpc.core._engine'
        with patch.dict('sys.modules', {module_name: None}):
            with patch('builtins.__import__', side_effect=ImportError("No module named '_engine'")):
                with pytest.raises(DllLoadError, match="Extension module not found"):
                    import_engine()

    def test_import_engine_other_import_error(self):
        """Test that other ImportErrors are re-raised."""
        module_name = 'ionosense_hpc.core._engine'
        with patch.dict('sys.modules', {module_name: None}):
            with patch('builtins.__import__', side_effect=ImportError("Some other error")):
                with pytest.raises(ImportError, match="Some other error"):
                    import_engine()

    def test_get_available_devices_error(self, mock_engine_module):
        """Test that get_available_devices warns and returns empty list on error."""
        mock_engine_module.get_available_devices.side_effect = Exception("CUDA error")
        with patch("ionosense_hpc.core.raw_engine.import_engine", return_value=mock_engine_module):
            with pytest.warns(UserWarning, match="Failed to query devices"):
                devices = RawEngine.get_available_devices()
        assert devices == []

    def test_select_best_device_error(self, mock_engine_module):
        """Test that select_best_device returns 0 on error."""
        mock_engine_module.select_best_device.side_effect = Exception("Query failed")
        with patch("ionosense_hpc.core.raw_engine.import_engine", return_value=mock_engine_module):
            device_id = RawEngine.select_best_device()
        assert device_id == 0

