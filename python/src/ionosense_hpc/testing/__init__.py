"""Testing utilities for ionosense-hpc."""

from .fixtures import (
    benchmark_config,
    gpu_available,
    mock_device_info,
    realtime_config,
    reference_fft_output,
    seeded_rng,
    skip_without_gpu,
    temp_data_dir,
    test_batch_data,
    test_batch_size,
    test_nfft_size,
    test_noise_data,
    test_processor,
    test_signal_type,
    test_sine_data,
    validation_config,
)
from .validators import (
    assert_allclose,
    assert_parseval,
    assert_snr,
    assert_spectral_peak,
    calculate_thd,
    check_numerical_stability,
    compare_with_reference,
    validate_fft_symmetry,
    validate_output_range,
)

# These are not part of the public API
__all__ = []
