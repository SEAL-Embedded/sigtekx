"""Utility functions for ionosense-hpc.

This package re-exports selected helpers and provides lazy wrappers for
signal generators to avoid importing heavy optional deps at module import time.
"""

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


# --- Lazy signal wrappers (import scipy-dependent code only on use) ---
def make_sine(*args, **kwargs):
    from .signals import make_sine as _impl
    return _impl(*args, **kwargs)


def make_chirp(*args, **kwargs):
    from .signals import make_chirp as _impl
    return _impl(*args, **kwargs)


def make_noise(*args, **kwargs):
    from .signals import make_noise as _impl
    return _impl(*args, **kwargs)


def make_multitone(*args, **kwargs):
    from .signals import make_multitone as _impl
    return _impl(*args, **kwargs)


def make_test_batch(*args, **kwargs):
    from .signals import make_test_batch as _impl
    return _impl(*args, **kwargs)


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
    # Signal generators (lazy wrappers)
    'make_sine',
    'make_chirp',
    'make_noise',
    'make_multitone',
    'make_test_batch',
    # Profiling
    'nvtx_range',
    # Reporting (import from ionosense_hpc.benchmarks.reporting when needed)
]
