"""Comprehensive tests for the centralized logging module.

This suite validates the functionality of `setup_logging` under various
conditions, including environment variable controls, argument overrides,
and fallbacks. It also tests the output of logging helper functions
and the correctness of the custom color formatter.
"""

import logging
import re
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

from ionosense_hpc.config.schemas import EngineConfig
from ionosense_hpc.utils.logging import (
    _ColorFormatter,
    _env_truthy,
    _is_running_under_profiler,
    _should_color,
    log_config,
    log_device_info,
    log_performance,
    setup_logging,
)

# ANSI escape code for color
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

# Handle optional rich import for handler type checking
try:
    from rich.logging import RichHandler
    HANDLER_TYPES = (logging.StreamHandler, RichHandler)
except ImportError:
    HANDLER_TYPES = (logging.StreamHandler,)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def clean_logger() -> Generator[logging.Logger, None, None]:
    """Provides a clean logger instance for each test, restoring state afterward."""
    logger = logging.getLogger('ionosense_hpc')
    original_level = logger.level
    original_handlers = logger.handlers[:]
    original_propagate = logger.propagate
    try:
        yield logger
    finally:
        logger.setLevel(original_level)
        logger.handlers = original_handlers
        logger.propagate = original_propagate


@pytest.fixture
def mock_engine_config(validation_config: EngineConfig) -> EngineConfig:
    """Provides a reusable EngineConfig fixture for testing log helpers."""
    return validation_config


@pytest.fixture
def mock_stats_data() -> dict:
    """Provides sample performance statistics for testing."""
    return {
        'latency_us': 123.45,
        'throughput_gbps': 67.89,
        'frames_processed': 1000,
    }


# -----------------------------------------------------------------------------
# Tests for setup_logging
# -----------------------------------------------------------------------------

class TestSetupLogging:
    """Tests the main `setup_logging` function."""

    def test_default_setup(self, clean_logger: logging.Logger):
        """Test logger setup with default parameters."""
        logger = setup_logging()
        assert logger.name == 'ionosense_hpc'
        assert logger.level == logging.INFO
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], HANDLER_TYPES)
        assert not logger.propagate

    @pytest.mark.parametrize(
        "level_str, expected_level",
        [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
            ("INVALID_LEVEL", logging.INFO),  # Should default to INFO
        ],
    )
    def test_level_setting(
        self,
        clean_logger: logging.Logger,
        level_str: str,
        expected_level: int
    ):
        """Test setting log level via argument and environment variable."""
        # Test with argument
        logger = setup_logging(level=level_str)
        assert logger.level == expected_level

        # Test with environment variable
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("IONO_LOG_LEVEL", level_str)
            logger = setup_logging()
            assert logger.level == expected_level

    def test_file_logging(
        self,
        clean_logger: logging.Logger,
        temp_data_dir: Path
    ):
        """Test that file logging works correctly when a path is provided."""
        log_file = temp_data_dir / "test.log"
        logger = setup_logging(log_file=str(log_file))

        assert len(logger.handlers) == 2
        assert any(isinstance(h, logging.FileHandler) for h in logger.handlers)

        # Write to log and check file content
        test_message = "This is a test message for the file log."
        logger.info(test_message)

        # Manually close handler to ensure flush
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler):
                handler.close()

        assert log_file.exists()
        content = log_file.read_text()
        assert test_message in content
        assert "INFO" in content

    def test_no_rich_fallback(
        self,
        clean_logger: logging.Logger,
        monkeypatch
    ):
        """Test that setup falls back to _ColorFormatter if rich is not found."""
        monkeypatch.setitem(sys.modules, "rich", None)
        monkeypatch.setitem(sys.modules, "rich.console", None)
        monkeypatch.setitem(sys.modules, "rich.logging", None)

        logger = setup_logging(color=True)
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0].formatter, _ColorFormatter)

    def test_profiler_detection_disables_color(
        self,
        clean_logger: logging.Logger,
        monkeypatch,
        capsys
    ):
        """Test that profiler detection disables color and logs a message."""
        # HACK: Temporarily remove root handlers so that the `basicConfig` call
        # inside the tested function has an effect.
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        root_logger.handlers.clear()

        try:
            monkeypatch.setenv("NSYS_PROFILING_SESSION_ID", "12345")
            logger = setup_logging()

            # Check that color is disabled (formatter will not be _ColorFormatter with use_color=True)
            is_color_formatter = isinstance(logger.handlers[0].formatter, _ColorFormatter)
            if is_color_formatter:
                assert not logger.handlers[0].formatter.use_color  # type: ignore

            # Check for the info message
            captured = capsys.readouterr()
            assert "Profiler detected, falling back to simple logging" in captured.err
        finally:
            # Restore the original handlers to avoid side effects
            root_logger.handlers = original_handlers


# -----------------------------------------------------------------------------
# Tests for Logging Helpers
# -----------------------------------------------------------------------------

class TestLogHelpers:
    """Tests the helper functions for logging structured data."""

    def test_log_config(
        self,
        clean_logger: logging.Logger,
        mock_engine_config: EngineConfig,
        capsys
    ):
        """Test that engine configuration is logged correctly."""
        setup_logging(level="INFO")
        log_config(mock_engine_config)
        captured = capsys.readouterr()
        output = captured.err

        assert "Engine Configuration" in output
        assert f"FFT Size: {mock_engine_config.nfft}" in output
        assert f"Sample Rate: {mock_engine_config.sample_rate_hz} Hz" in output
        assert f"Overlap: {mock_engine_config.overlap:.1%}" in output

    def test_log_performance(
        self,
        clean_logger: logging.Logger,
        mock_stats_data: dict,
        capsys
    ):
        """Test that performance statistics are logged correctly."""
        setup_logging(level="INFO")
        log_performance(mock_stats_data)
        captured = capsys.readouterr()
        output = captured.err

        assert "Performance Statistics" in output
        assert f"Latency: {mock_stats_data['latency_us']:.1f} μs" in output
        assert f"Throughput: {mock_stats_data['throughput_gbps']:.2f} GB/s" in output
        assert f"Frames Processed: {mock_stats_data['frames_processed']}" in output

    def test_log_device_info(
        self,
        clean_logger: logging.Logger,
        mock_device_info: dict,
        capsys
    ):
        """Test that device information is logged correctly."""
        setup_logging(level="INFO")
        log_device_info(mock_device_info)
        captured = capsys.readouterr()
        output = captured.err

        assert "CUDA Device Information" in output
        assert f"Device: {mock_device_info['name']}" in output
        assert f"Memory: {mock_device_info['memory_free_mb']}" in output
        cc = mock_device_info['compute_capability']
        assert f"Compute Capability: {cc[0]}.{cc[1]}" in output
        assert f"Temperature: {mock_device_info['temperature_c']}°C" in output


# -----------------------------------------------------------------------------
# Tests for Private Helpers
# -----------------------------------------------------------------------------

class TestPrivateHelpers:
    """Tests private helper functions within the logging module."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("1", True), ("true", True), ("yes", True), ("on", True),
            ("0", False), ("false", False), ("no", False), ("off", False),
            ("TRUE", True), ("FaLsE", False),
            (None, None), ("", None), ("invalid", None),
        ],
    )
    def test_env_truthy(self, monkeypatch, value, expected):
        """Test _env_truthy with various inputs."""
        env_var = "TEST_TRUTHY_VAR"
        if value is not None:
            monkeypatch.setenv(env_var, value)
        else:
            monkeypatch.delenv(env_var, raising=False)

        assert _env_truthy(env_var) is expected

    @pytest.mark.parametrize("is_profiling", [True, False])
    def test_is_running_under_profiler(self, monkeypatch, is_profiling):
        """Test profiler detection logic."""
        monkeypatch.delenv("NSYS_PROFILING_SESSION_ID", raising=False)
        if is_profiling:
            monkeypatch.setenv("NSYS_PROFILING_SESSION_ID", "1")
        assert _is_running_under_profiler() is is_profiling

    @pytest.mark.parametrize("is_tty, expected", [(True, True), (False, False)])
    def test_should_color(self, monkeypatch, is_tty, expected):
        """Test color detection based on TTY status."""
        monkeypatch.setattr(sys.stderr, "isatty", lambda: is_tty)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: is_tty)
        monkeypatch.delenv("CI", raising=False)
        assert _should_color() is expected

    def test_should_color_in_ci(self, monkeypatch):
        """Test that color is disabled in CI environments."""
        monkeypatch.setenv("CI", "true")
        assert not _should_color()


# -----------------------------------------------------------------------------
# Tests for _ColorFormatter
# -----------------------------------------------------------------------------

class TestColorFormatter:
    """Tests the custom _ColorFormatter class."""

    @pytest.mark.parametrize(
        "level, color_present",
        [
            (logging.DEBUG, True),
            (logging.INFO, True),
            (logging.WARNING, True),
            (logging.ERROR, True),
            (logging.CRITICAL, True),
        ],
    )
    def test_color_formatting(self, level: int, color_present: bool):
        """Test that color codes are applied correctly for each level."""
        formatter = _ColorFormatter("%(levelname)s %(message)s", use_color=True)
        record = logging.LogRecord(
            "test", level, "/path", 1, "test message", None, None
        )
        formatted = formatter.format(record)

        if color_present:
            assert ANSI_RE.search(formatted)
            # Check that the level name is correctly padded and colored
            assert f"{logging.getLevelName(level):<8}" in ANSI_RE.sub('', formatted)
        else:
            assert not ANSI_RE.search(formatted)

    def test_no_color_formatting(self):
        """Test that no color is applied when use_color is False."""
        formatter = _ColorFormatter("%(levelname)s %(message)s", use_color=False)
        record = logging.LogRecord(
            "test", logging.INFO, "/path", 1, "test message", None, None
        )
        formatted = formatter.format(record)
        assert not ANSI_RE.search(formatted)
        assert "INFO    " in formatted  # Check for padding without color


