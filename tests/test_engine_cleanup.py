"""Tests for Engine cleanup error handling.

This module tests the robust exception handling in Engine.close(), __del__(),
and __exit__() methods, including GPU memory leak detection, error classification,
and build-mode-aware behavior.
"""

import os
import warnings
from unittest import mock

import pytest

from sigtekx import Engine, EngineConfig
from sigtekx.exceptions import EngineCleanupError

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def test_config() -> EngineConfig:
    """Small configuration for fast testing."""
    return EngineConfig(
        nfft=256,
        channels=1,
        overlap=0.0,
        sample_rate_hz=1000,
        warmup_iters=0,
        enable_profiling=False  # Disable profiling for cleanup tests
    )


@pytest.fixture
def mock_cpp_engine():
    """Mock C++ engine for testing cleanup behavior."""
    mock_engine = mock.Mock()
    mock_engine.synchronize = mock.Mock()
    mock_engine.reset = mock.Mock()
    mock_engine.get_stats = mock.Mock(return_value=mock.Mock(
        latency_us=10.0,
        throughput_gbps=5.0,
        frames_processed=1
    ))
    return mock_engine


# -----------------------------------------------------------------------------
# Basic Behavior Tests
# -----------------------------------------------------------------------------

def test_close_is_idempotent(test_config):
    """Test that multiple close() calls are safe."""
    engine = Engine(config=test_config)
    engine.close()

    # Second close should not raise
    engine.close()
    engine.close()

    assert engine._closed


def test_close_marks_engine_closed(test_config):
    """Test that close() properly marks engine as closed."""
    engine = Engine(config=test_config)
    assert not engine._closed

    engine.close()

    assert engine._closed
    assert engine._cpp_engine is None
    assert not engine._initialized


def test_close_clears_cpp_engine(test_config, mock_cpp_engine):
    """Test that close() clears C++ engine reference."""
    engine = Engine(config=test_config)
    engine._cpp_engine = mock_cpp_engine
    engine._initialized = True

    engine.close()

    # Should have called reset on C++ engine
    mock_cpp_engine.reset.assert_called_once()

    # Should clear reference
    assert engine._cpp_engine is None


# -----------------------------------------------------------------------------
# Error Classification Tests
# -----------------------------------------------------------------------------

def test_cuda_device_error_logged_as_info(test_config, mock_cpp_engine, caplog):
    """Test that CUDA device errors during cleanup are logged as INFO."""
    # Mock C++ engine to raise CUDA device error
    mock_cpp_engine.reset.side_effect = RuntimeError("CUDA device error during shutdown")

    engine = Engine(config=test_config)
    engine._cpp_engine = mock_cpp_engine
    engine._initialized = True

    # Should not raise (even in debug mode), just log as INFO
    with caplog.at_level("INFO"):
        engine.close()

    assert engine._closed
    assert "CUDA device error during reset (expected)" in caplog.text


def test_memory_error_logged_as_error(test_config, mock_cpp_engine, caplog):
    """Test that memory errors during cleanup are logged as ERROR."""
    # Mock C++ engine to raise memory error
    mock_cpp_engine.reset.side_effect = RuntimeError("out of memory during cleanup")

    engine = Engine(config=test_config)
    engine._cpp_engine = mock_cpp_engine
    engine._initialized = True

    with caplog.at_level("ERROR"):
        if __debug__:
            # In debug mode, should raise EngineCleanupError
            with pytest.raises(EngineCleanupError) as exc_info:
                engine.close()
            assert "reset_memory" in exc_info.value.cleanup_step
        else:
            # In release mode, should log but not raise
            engine.close()
            assert "Memory error during reset" in caplog.text


# -----------------------------------------------------------------------------
# GPU Memory Tracking Tests
# -----------------------------------------------------------------------------

def test_memory_tracking_disabled_by_default_in_release(test_config):
    """Test that memory tracking is disabled by default in release builds."""
    # In release mode (python -O), __debug__ == False
    if not __debug__:
        engine = Engine(config=test_config)
        assert not engine._should_track_cleanup_memory()
        engine.close()


def test_memory_tracking_enabled_by_default_in_debug(test_config):
    """Test that memory tracking is enabled by default in debug builds."""
    # In debug mode (normal python), __debug__ == True
    if __debug__:
        engine = Engine(config=test_config)
        assert engine._should_track_cleanup_memory()
        engine.close()


def test_memory_tracking_can_be_force_enabled(test_config):
    """Test that memory tracking can be force-enabled via env var."""
    original_env = os.environ.get('SIGX_TRACK_CLEANUP_MEMORY')

    try:
        os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = '1'
        engine = Engine(config=test_config)
        assert engine._should_track_cleanup_memory()
        engine.close()
    finally:
        if original_env is None:
            os.environ.pop('SIGX_TRACK_CLEANUP_MEMORY', None)
        else:
            os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = original_env


def test_memory_tracking_can_be_force_disabled(test_config):
    """Test that memory tracking can be force-disabled via env var."""
    original_env = os.environ.get('SIGX_TRACK_CLEANUP_MEMORY')

    try:
        os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = '0'
        engine = Engine(config=test_config)
        assert not engine._should_track_cleanup_memory()
        engine.close()
    finally:
        if original_env is None:
            os.environ.pop('SIGX_TRACK_CLEANUP_MEMORY', None)
        else:
            os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = original_env


# -----------------------------------------------------------------------------
# Profiler Detection Tests
# -----------------------------------------------------------------------------

def test_verbose_logging_disabled_under_profiler(test_config, monkeypatch):
    """Test that verbose logging is disabled when running under profiler."""
    # Mock profiler detection to return True
    monkeypatch.setenv('NSYS_PROFILING_SESSION_ID', 'test_session')

    engine = Engine(config=test_config)

    # In debug mode, verbose should be False under profiler
    if __debug__:
        from sigtekx.utils.logging import _is_running_under_profiler
        assert _is_running_under_profiler()

    engine.close()


def test_verbose_logging_enabled_in_debug_mode(test_config, monkeypatch):
    """Test that verbose logging is enabled in debug mode (no profiler)."""
    # Ensure no profiler env vars are set
    for var in ['NSYS_PROFILING_SESSION_ID', 'NSIGHT_SYSTEMS_PROFILING_SESSION_ID', 'CUDA_INJECTION64_PATH']:
        monkeypatch.delenv(var, raising=False)

    engine = Engine(config=test_config)

    # In debug mode without profiler, verbose should be True
    if __debug__:
        from sigtekx.utils.logging import _is_running_under_profiler
        assert not _is_running_under_profiler()

    engine.close()


# -----------------------------------------------------------------------------
# __del__ Method Tests
# -----------------------------------------------------------------------------

def test_del_issues_resource_warning(test_config):
    """Test that __del__ issues ResourceWarning when engine not closed."""
    engine = Engine(config=test_config)

    # Trigger __del__ without closing
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", ResourceWarning)
        del engine

        # Should have issued ResourceWarning
        assert len(w) > 0
        assert issubclass(w[0].category, ResourceWarning)
        assert "not properly closed" in str(w[0].message).lower()


def test_del_disables_memory_tracking(test_config):
    """Test that __del__ disables memory tracking during cleanup."""
    original_env = os.environ.get('SIGX_TRACK_CLEANUP_MEMORY')

    try:
        # Enable memory tracking
        os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = '1'

        engine = Engine(config=test_config)

        # __del__ should temporarily disable it
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            del engine

        # Environment should be restored
        assert os.environ.get('SIGX_TRACK_CLEANUP_MEMORY') == '1'
    finally:
        if original_env is None:
            os.environ.pop('SIGX_TRACK_CLEANUP_MEMORY', None)
        else:
            os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = original_env


def test_del_suppresses_all_exceptions(test_config, mock_cpp_engine):
    """Test that __del__ suppresses all exceptions (finalizer contract)."""
    # Mock C++ engine to raise exception
    mock_cpp_engine.reset.side_effect = Exception("Unexpected error")

    engine = Engine(config=test_config)
    engine._cpp_engine = mock_cpp_engine
    engine._initialized = True

    # __del__ should not raise, even with exception
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        del engine


# -----------------------------------------------------------------------------
# Context Manager Tests
# -----------------------------------------------------------------------------

def test_context_manager_propagates_user_exception(test_config):
    """Test that context manager propagates user exceptions."""
    with pytest.raises(ValueError, match="test error"):
        with Engine(config=test_config) as engine:
            raise ValueError("test error")


def test_context_manager_closes_on_exception(test_config):
    """Test that context manager closes engine even on exception."""
    engine = None

    try:
        with Engine(config=test_config) as eng:
            engine = eng
            raise ValueError("test error")
    except ValueError:
        pass

    # Engine should be closed despite exception
    assert engine._closed


def test_context_manager_logs_user_exception(test_config, caplog):
    """Test that context manager logs user exceptions."""
    with caplog.at_level("WARNING"):
        try:
            with Engine(config=test_config) as engine:
                raise ValueError("test error")
        except ValueError:
            pass

    assert "Engine context exited due to exception" in caplog.text


# -----------------------------------------------------------------------------
# Edge Cases
# -----------------------------------------------------------------------------

def test_close_with_none_cpp_engine(test_config):
    """Test that close() handles None C++ engine gracefully."""
    engine = Engine(config=test_config)
    engine._cpp_engine = None
    engine._initialized = False

    # Should not raise
    engine.close()
    assert engine._closed


def test_close_synchronize_failure_continues_cleanup(test_config, mock_cpp_engine, caplog):
    """Test that synchronize failure doesn't prevent rest of cleanup."""
    # Mock synchronize to fail
    mock_cpp_engine.synchronize.side_effect = RuntimeError("Synchronize failed")

    engine = Engine(config=test_config)
    engine._cpp_engine = mock_cpp_engine
    engine._initialized = True

    with caplog.at_level("WARNING"):
        if __debug__:
            # In debug mode, may raise if other serious errors
            try:
                engine.close()
            except EngineCleanupError:
                pass
        else:
            engine.close()

    # Should have attempted reset despite synchronize failure
    mock_cpp_engine.reset.assert_called_once()
    assert engine._closed
