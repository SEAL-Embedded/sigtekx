"""Utility functions for ionosense-hpc with NVTX profiling support.

This package re-exports selected helpers and provides lazy wrappers for
signal generators to avoid importing heavy optional deps at module import time.
It also exposes NVTX profiling helpers if the optional `nvtx` package is
installed; otherwise, these functions are safe no-ops.
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
from .gpu_clocks import GpuClockManager, check_clock_locking_available
from .logging import log_config, log_device_info, log_performance, logger, setup_logging
from .profiling import (
    NVTX_AVAILABLE,
    ProfileCategory,
    ProfileColor,
    ProfilingContext,
    ProfilingDomain,
    benchmark_range,
    compute_range,
    initialize_profiling,
    mark_event,
    nvtx_decorate,
    nvtx_range,
    profile_iterator,
    setup_range,
    sync_range,
    teardown_range,
    transfer_range,
    warmup_range,
)


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
    # GPU clock management
    'GpuClockManager',
    'check_clock_locking_available',
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
    'nvtx_decorate',
    'benchmark_range',
    'compute_range',
    'transfer_range',
    'setup_range',
    'teardown_range',
    'sync_range',
    'warmup_range',
    'mark_event',
    'profile_iterator',
    'ProfilingContext',
    'ProfilingDomain',
    'ProfileColor',
    'ProfileCategory',
    'initialize_profiling',
    'NVTX_AVAILABLE',
    # Reporting utilities (see ionosense_hpc.utils.reporting)
]
