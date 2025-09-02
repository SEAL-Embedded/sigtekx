"""Centralized logging configuration for ionosense-hpc."""

import logging
import os
import sys

# Module logger
logger = logging.getLogger('ionosense_hpc')


def setup_logging(
    level: str | None = None,
    format_string: str | None = None,
    log_file: str | None = None
) -> logging.Logger:
    """Configure logging for the ionosense_hpc package.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        format_string: Custom format string
        log_file: Optional file to write logs to
        
    Returns:
        Configured logger instance
    """
    # Check environment variable for log level
    if level is None:
        level = os.environ.get('IONO_LOG_LEVEL', 'INFO')

    # Default format
    if format_string is None:
        format_string = '[%(asctime)s] %(name)s %(levelname)s: %(message)s'

    # Configure logger
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(format_string))
    logger.addHandler(console_handler)

    # File handler if requested
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(format_string))
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def log_config(config: 'EngineConfig', level: int = logging.INFO) -> None:
    """Log engine configuration details.
    
    Args:
        config: Engine configuration to log
        level: Logging level to use
    """
    logger.log(level, "Engine Configuration:")
    logger.log(level, f"  FFT Size: {config.nfft}")
    logger.log(level, f"  Batch Size: {config.batch}")
    logger.log(level, f"  Sample Rate: {config.sample_rate_hz} Hz")
    logger.log(level, f"  Overlap: {config.overlap:.1%}")
    logger.log(level, f"  Output Bins: {config.num_output_bins}")
    logger.log(level, f"  Frame Duration: {config.frame_duration_ms:.2f} ms")
    logger.log(level, f"  Hop Duration: {config.hop_duration_ms:.2f} ms")


def log_performance(stats: dict, level: int = logging.INFO) -> None:
    """Log performance statistics.
    
    Args:
        stats: Performance statistics dictionary
        level: Logging level to use
    """
    logger.log(level, "Performance Statistics:")
    logger.log(level, f"  Latency: {stats.get('latency_us', 0):.1f} μs")
    logger.log(level, f"  Throughput: {stats.get('throughput_gbps', 0):.2f} GB/s")
    logger.log(level, f"  Frames Processed: {stats.get('frames_processed', 0)}")


def log_device_info(info: dict, level: int = logging.INFO) -> None:
    """Log CUDA device information.
    
    Args:
        info: Device info dictionary
        level: Logging level to use
    """
    logger.log(level, "CUDA Device Information:")
    logger.log(level, f"  Device: {info.get('name', 'Unknown')}")
    logger.log(level, f"  Memory: {info.get('memory_free_mb', 0)}/{info.get('memory_total_mb', 0)} MB free")
    if info.get('compute_capability'):
        cc = info['compute_capability']
        logger.log(level, f"  Compute Capability: {cc[0]}.{cc[1]}")
    if info.get('temperature_c'):
        logger.log(level, f"  Temperature: {info['temperature_c']}°C")


# Initialize with defaults on import
setup_logging()
