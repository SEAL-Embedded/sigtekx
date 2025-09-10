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
    from ionosense_hpc.config.schemas import EngineConfig

logger = logging.getLogger('ionosense_hpc')


def setup_logging(
    level: str | None = None,
    format_string: str | None = None,
    log_file: str | None = None
) -> logging.Logger:
    """Configures the package logger.

    Args:
        level: The logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR').
            Defaults to `IONO_LOG_LEVEL` env var or 'INFO'.
        format_string: A custom format string for log messages.
        log_file: An optional file path to write logs to.

    Returns:
        The configured logger instance.
    """
    # Ensure a concrete string and guard against None for mypy
    lvl_str = level or os.environ.get('IONO_LOG_LEVEL') or 'INFO'
    fmt = format_string or '[%(asctime)s] %(name)s %(levelname)s: %(message)s'

    logger.setLevel(getattr(logging, lvl_str.upper(), logging.INFO))
    logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(console_handler)

    if log_file:
        log_path = os.path.dirname(log_file)
        if log_path:
            os.makedirs(log_path, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def log_config(config: 'EngineConfig', level: int = logging.INFO) -> None:
    """Logs key engine configuration parameters."""
    logger.log(level, "Engine Configuration:")
    logger.log(level, f"  FFT Size: {config.nfft}, Batch Size: {config.batch}")
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


# Default configuration is set by the package __init__ on import.
