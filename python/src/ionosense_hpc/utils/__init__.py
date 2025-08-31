"""
ionosense_hpc.utils: Utility functions for signal processing and benchmarking.
"""

from .validation import (
    validate_fft_size,
    get_optimal_fft_size,
    validate_signal_data,
    validate_batch_consistency,
    check_cuda_compute_capability
)

from .signals import (
    SignalParameters,
    generate_test_signal,
    create_window,
    compute_snr,
    generate_chirp
)

from .device import (
    DeviceInfo,
    ensure_cuda_available,
    get_device_info,
    list_devices,
    get_device_count,
    get_cuda_version,
    set_device,
    get_memory_info,
    print_device_summary
)

from .console import (
    ConsoleFormatter,
    print_header,
    print_separator,
    print_table,
    print_stats,
    format_time,
    format_bytes,
    format_number,
    timed_section,
    ProgressReporter,
    print_benchmark_summary
)

from .data_export import (
    save_to_csv,
    save_to_npz,
    load_from_npz,
    save_to_hdf5,
    load_from_hdf5,
    save_benchmark_results,
    load_benchmark_results,
    export_for_matlab,
    create_experiment_archive
)

__all__ = [
    # Validation
    'validate_fft_size',
    'get_optimal_fft_size',
    'validate_signal_data',
    'validate_batch_consistency',
    'check_cuda_compute_capability',
    # Signals
    'SignalParameters',
    'generate_test_signal',
    'create_window',
    'compute_snr',
    'generate_chirp',
    # Device
    'DeviceInfo',
    'ensure_cuda_available',
    'get_device_info',
    'list_devices',
    'get_device_count',
    'get_cuda_version',
    'set_device',
    'get_memory_info',
    'print_device_summary',
    # Console
    'ConsoleFormatter',
    'print_header',
    'print_separator',
    'print_table',
    'print_stats',
    'format_time',
    'format_bytes',
    'format_number',
    'timed_section',
    'ProgressReporter',
    'print_benchmark_summary',
    # Data Export
    'save_to_csv',
    'save_to_npz',
    'load_from_npz',
    'save_to_hdf5',
    'load_from_hdf5',
    'save_benchmark_results',
    'load_benchmark_results',
    'export_for_matlab',
    'create_experiment_archive',
]