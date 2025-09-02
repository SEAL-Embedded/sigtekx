"""Utility functions for ionosense-hpc."""

from .device import (
    gpu_count,
    current_device,
    device_info,
    get_memory_usage,
    check_cuda_available,
    get_compute_capability,
    monitor_device
)

from .logging import (
    logger,
    setup_logging,
    log_config,
    log_performance,
    log_device_info
)

from .signals import (
    make_sine,
    make_chirp,
    make_noise,
    make_multitone,
    make_test_batch
)

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
    'make_test_batch'
]