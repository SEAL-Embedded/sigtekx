"""Utility functions for ionosense-hpc."""

from .device import (
    check_cuda_available,
    current_device,
    device_info,
    get_compute_capability,
    get_memory_usage,
    gpu_count,
    monitor_device,
)
from .logging import log_config, log_device_info, log_performance, logger, setup_logging
from .profiling import nvtx_range
from .signals import make_chirp, make_multitone, make_noise, make_sine, make_test_batch

__all__ = [
    # Device utilities
    'gpu_count',
    'current_device',
    'device_info',
    'get_memory_usage',
    'check_cuda_available',
    'get_compute_capability',
    'monitor_device',
    # Logging utilities
    'logger',
    'setup_logging',
    'log_config',
    'log_performance',
    'log_device_info',
    # Signal generators
    'make_sine',
    'make_chirp',
    'make_noise',
    'make_multitone',
    'make_test_batch',
    # Profiling
    'nvtx_range',
    # Reporting (import from ionosense_hpc.benchmarks.reporting when needed)
]
