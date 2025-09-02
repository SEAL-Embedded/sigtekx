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

from .profiling import (
    nvtx_range
)

from .reporting import (
    print_header,
    print_latency_report,
    print_throughput_report,
    print_accuracy_report
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
    'make_test_batch',
    # Profiling
    'nvtx_range',
    # Reporting
    'print_header',
    'print_latency_report',
    'print_throughput_report',
    'print_accuracy_report'
]
