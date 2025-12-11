"""Configuration validation utilities."""

from typing import Final
import warnings

import numpy as np

from sigtekx.config.schemas import EngineConfig
from sigtekx.exceptions import ConfigError, ValidationError

# Memory safety thresholds
DEVICE_MEMORY_SAFETY_FACTOR: Final[float] = 0.9  # Reserve 10% GPU memory for overhead

# Hardware compatibility thresholds
MINIMUM_COMPUTE_CAPABILITY_MAJOR: Final[int] = 6  # Pascal+ architecture required
MINIMUM_COMPUTE_CAPABILITY_MINOR: Final[int] = 0

# Performance warning thresholds
LARGE_FFT_SIZE_WARNING: Final[int] = 16384  # Warn for very large FFTs


def validate_config_device_compatibility(
    config: EngineConfig,
    device_memory_mb: int,
    compute_capability: tuple[int, int]
) -> None:
    """Validate configuration against device capabilities.

    Args:
        config: Engine configuration to validate
        device_memory_mb: Available device memory in MB
        compute_capability: Device compute capability (major, minor)

    Raises:
        ConfigError: If configuration exceeds device capabilities
    """
    # Memory check
    estimated_mb = estimate_memory_usage_mb(config)
    available_memory_mb = device_memory_mb * DEVICE_MEMORY_SAFETY_FACTOR
    if estimated_mb > available_memory_mb:
        raise ConfigError(
            f"Configuration requires ~{estimated_mb}MB but device has {device_memory_mb}MB",
            hint="Reduce batch size or nfft"
        )

    # Compute capability check
    major, minor = compute_capability
    if major < MINIMUM_COMPUTE_CAPABILITY_MAJOR:
        warnings.warn(
            (
                "GPU compute capability "
                f"{major}.{minor} is below recommended "
                f"{MINIMUM_COMPUTE_CAPABILITY_MAJOR}."
                f"{MINIMUM_COMPUTE_CAPABILITY_MINOR}"
            ),
            RuntimeWarning,
            stacklevel=2
        )

    # Large FFT warning
    if config.nfft > LARGE_FFT_SIZE_WARNING:
        warnings.warn(
            f"Large FFT size ({config.nfft}) may impact real-time performance",
            RuntimeWarning,
            stacklevel=2
        )


def estimate_memory_usage_mb(config: EngineConfig,
    include_workspace: bool = True,
    safety_margin: bool = True) -> float:
    """Estimate GPU memory usage for a configuration.

    Args:
        config: Engine configuration

    Returns:
        Estimated memory usage in megabytes
    """
    # Calculate buffer sizes
    input_size = config.nfft * config.channels * 4  # float32
    output_size = config.num_output_bins * config.channels * 4
    complex_size = output_size * 2  # complex float

    # Account for all buffers
    per_buffer = input_size + output_size + complex_size
    total_bytes = per_buffer * config.pinned_buffer_count

    # Add cuFFT workspace estimate (precise query with intelligent fallback)
    try:
        # Import inside function to avoid circular import
        from sigtekx.core import _native
        cufft_workspace = _native.estimate_cufft_workspace_bytes(
            nfft=config.nfft,
            channels=config.channels,
            is_real_input=True,  # We use R2C transforms
            use_fallback_on_error=True  # Enables heuristic fallback
        )
    except Exception:
        # Conservative fallback if binding fails unexpectedly
        # Estimate: complex FFT workspace (8 bytes per sample) with 2× safety margin
        cufft_workspace = config.nfft * config.channels * 8 * 2

    total_bytes += cufft_workspace

    # Window coefficients
    total_bytes += config.nfft * 4

    return total_bytes // (1024 * 1024)


def validate_input_array(
    data: np.ndarray,
    expected_shape: tuple[int, ...] | None = None,
    expected_dtype: np.dtype | None = None,
    name: str = "input",
    skip_nan_check: bool = False
) -> np.ndarray:
    """Validate and prepare a NumPy array for processing.

    Args:
        data: Input array to validate
        expected_shape: Expected shape (None to skip)
        expected_dtype: Expected dtype (None to skip)
        name: Name for error messages
        skip_nan_check: Skip expensive NaN/Inf check (for performance)

    Returns:
        Validated array (possibly with dtype conversion)

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(data, np.ndarray):
        raise ValidationError(
            f"{name} must be a NumPy array",
            expected="numpy.ndarray",
            got=type(data).__name__
        )

    # Shape validation
    if expected_shape is not None and data.shape != expected_shape:
        raise ValidationError(
            f"{name} shape mismatch",
            expected=str(expected_shape),
            got=str(data.shape)
        )

    # Dtype validation/conversion
    if expected_dtype is not None and data.dtype != expected_dtype:
        try:
            data = data.astype(expected_dtype, copy=False)
        except (ValueError, TypeError) as e:
            raise ValidationError(
                f"Cannot convert {name} to {expected_dtype}",
                expected=str(expected_dtype),
                got=str(data.dtype)
            ) from e

    # Check for contiguous memory
    if not data.flags['C_CONTIGUOUS']:
        data = np.ascontiguousarray(data)

    # Check for NaN/Inf (can be skipped for performance in hot paths)
    if not skip_nan_check:
        if np.issubdtype(data.dtype, np.floating) and not np.isfinite(data).all():
            warnings.warn(
                f"{name} contains NaN or Inf values", RuntimeWarning, stacklevel=2
            )

    return data


def validate_input_size(data: np.ndarray, config: EngineConfig) -> None:
    """Validate that input data size matches engine configuration.

    Args:
        data: Input data array
        config: Engine configuration

    Raises:
        ValidationError: If input size doesn't match nfft * channels
    """
    expected_samples = config.nfft * config.channels
    if data.size != expected_samples:
        raise ValidationError(
            "Input data size mismatch",
            expected=f"{expected_samples} samples ({config.channels} channels × {config.nfft} samples)",
            got=f"{data.size} samples"
        )
