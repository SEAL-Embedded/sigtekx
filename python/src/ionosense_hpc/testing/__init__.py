"""Testing utilities for ionosense-hpc."""

from .fixtures import (
    temp_data_dir,
    validation_config,
    realtime_config,
    test_processor,
    seeded_rng,
    test_sine_data,
    test_batch_data,
    test_noise_data,
    mock_device_info,
    test_signal_type,
    test_nfft_size,
    test_batch_size,
    gpu_available,
    skip_without_gpu,
    benchmark_config,
    reference_fft_output
)

from .validators import (
    assert_allclose,
    assert_spectral_peak,
    assert_parseval,
    assert_snr,
    validate_fft_symmetry,
    calculate_thd,
    compare_with_reference,
    validate_output_range,
    check_numerical_stability
)

# These are not part of the public API
__all__ = []