"""Centralized logging configuration for the application.

This module provides a logging setup designed for scientific computing,
supporting reproducible research, performance monitoring, and diagnostics.
It is configurable via the `IONO_LOG_LEVEL` environment variable.
"""

import logging
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sigtekx.config.schemas import EngineConfig

PACKAGE_LOGGER_NAME = "sigtekx"
package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
if not any(isinstance(h, logging.NullHandler) for h in package_logger.handlers):
    package_logger.addHandler(logging.NullHandler())
# Compatibility alias for callers expecting a shared package logger
logger = package_logger

def _env_truthy(name: str, default: bool | None = None) -> bool | None:
    v = os.environ.get(name)
    if v is None:
        return default
    v = v.strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    return default

class _ColorFormatter(logging.Formatter):
    # ANSI color codes
    RESET = "\x1b[0m"
    COLORS = {
        logging.DEBUG: "\x1b[38;5;244m",   # gray
        logging.INFO: "\x1b[34m",          # blue
        logging.WARNING: "\x1b[33m",       # yellow
        logging.ERROR: "\x1b[31m",         # red
        logging.CRITICAL: "\x1b[1;31m",    # bold red
    }

    def __init__(self, fmt : str, datefmt : str | None = None, use_color:bool = True):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        if self.use_color and record.levelno in self.COLORS:
            # Pad levelname for alignment after adding color codes
            color, reset = self.COLORS[record.levelno], self.RESET
            record.levelname = f"{color}{record.levelname:<8}{reset}"
        else:
            record.levelname = f"{record.levelname:<8}" # No color, just pad
        return super().format(record)


def _should_color() -> bool:
    """Detects if the terminal supports color."""
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return False
    return sys.stderr.isatty() and sys.stdout.isatty()

def _is_running_under_profiler() -> bool:
    """Detects if running under a known profiler like NVIDIA Nsight."""
    profiler_vars = [
        "NSYS_PROFILING_SESSION_ID",
        "NSIGHT_SYSTEMS_PROFILING_SESSION_ID",
        "CUDA_INJECTION64_PATH",
    ]
    return any(var in os.environ for var in profiler_vars)

def setup_logging(
    level: str | None = None,
    format_string: str | None = None,
    log_file: str | None = None,
    color: bool | None = None
) -> logging.Logger:
    """Configures the package logger with rich formatting and safe fallbacks.

    Args:
        level: The logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR').
            Defaults to `IONO_LOG_LEVEL` env var or 'INFO'.
        format_string: A custom format string for log messages.
        log_file: An optional file path to write logs to.
        color: Force-enable/disable color. By default, auto-detects TTY and
               can be overridden by `IONO_LOG_COLOR` env var.

    Returns:
        The configured logger instance.
    """
    lvl_str = level or os.environ.get('IONO_LOG_LEVEL') or 'INFO'
    fmt = format_string or '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'

    # Determine if color should be used, with profiler detection taking precedence
    use_color: bool
    if _is_running_under_profiler():
        use_color = False
        # Use a temporary basic logger to inform the user
        logging.basicConfig()
        logging.getLogger('sigtekx_setup').info("Profiler detected, falling back to simple logging.")
    else:
        color_env = _env_truthy("IONO_LOG_COLOR")
        use_color = color if color is not None else (color_env if color_env is not None else _should_color())

    package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    package_logger.setLevel(getattr(logging, lvl_str.upper(), logging.INFO))
    package_logger.handlers.clear()

    # --- Console Handler ---
    console_handler: logging.Handler | None = None
    if use_color:
        try:
            from rich.console import Console
            from rich.logging import RichHandler
            stderr_console = Console(stderr=True)
            console_handler = RichHandler(
                console=stderr_console,
                show_path=False,
                rich_tracebacks=True,
                markup=True,
                log_time_format="[%Y-%m-%d %H:%M:%S]",
            )
            console_handler.setFormatter(logging.Formatter("%(message)s", datefmt=datefmt))
        except ImportError:
            pass # Fallback to custom formatter below

    if console_handler is None:
        console_handler = logging.StreamHandler(sys.stderr)
        formatter = _ColorFormatter(fmt, datefmt=datefmt, use_color=use_color)
        console_handler.setFormatter(formatter)

    package_logger.addHandler(console_handler)

    # --- File Handler ---
    if log_file:
        log_path = os.path.dirname(log_file)
        if log_path:
            os.makedirs(log_path, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        package_logger.addHandler(file_handler)


    package_logger.propagate = False
    return package_logger

def log_config(config: 'EngineConfig', level: int = logging.INFO) -> None:
    """Logs key engine configuration parameters."""
    logger.log(level, "Engine Configuration:")
    logger.log(level, f"  FFT Size: {config.nfft}, Batch Size: {config.channels}")
    logger.log(level, f"  Sample Rate: {config.sample_rate_hz} Hz, Overlap: {config.overlap:.1%}")
    logger.log(level, f"  Frame/Hop Duration: {config.frame_duration_ms:.2f}ms / {config.hop_duration_ms:.2f}ms")


def log_performance(stats: dict, level: int = logging.INFO) -> None:
    """Logs key performance metrics."""
    logger.log(level, "Performance Statistics:")
    logger.log(level, f"  Latency: {stats.get('latency_us', 0):.1f} μs")
    logger.log(level, f"  Throughput: {stats.get('throughput_gbps', 0):.2f} GB/s")
    logger.log(level, f"  Frames Processed: {stats.get('frames_processed', 0)}")


def log_device_info(info: dict, level: int = logging.INFO) -> None:
    """Logs key information about the CUDA device."""
    logger.log(level, "CUDA Device Information:")
    logger.log(level, f"  Device: {info.get('name', 'Unknown')}")
    logger.log(level, f"  Memory: {info.get('memory_free_mb', 0)}/{info.get('memory_total_mb', 0)} MB free")
    if 'compute_capability' in info:
        cc = info['compute_capability']
        logger.log(level, f"  Compute Capability: {cc[0]}.{cc[1]}")
    if 'temperature_c' in info:
        logger.log(level, f"  Temperature: {info['temperature_c']}°C")
