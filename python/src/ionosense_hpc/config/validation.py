"""Configuration validation utilities."""

import warnings
from typing import Optional, Tuple

import numpy as np

from ..exceptions import ConfigError, ValidationError


def validate_config_device_compatibility(
    config: 'EngineConfig',
    device_memory_mb: int,
    compute_capability: Tuple[int, int]
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
    if estimated_mb > device_memory_mb * 0.9:  # Leave 10% headroom
        raise ConfigError(
            f"Configuration requires ~{estimated_mb}MB but device has {device_memory_mb}MB",
            hint="Reduce batch size or nfft"
        )
    
    # Compute capability check
    major, minor = compute_capability
    if major < 6:
        warnings.warn(
            f"GPU compute capability {major}.{minor} is below recommended 6.0",
            PerformanceWarning
        )
    
    # Large FFT warning
    if config.nfft > 16384:
        warnings.warn(
            f"Large FFT size ({config.nfft}) may impact real-time performance",
            PerformanceWarning
        )


def estimate_memory_usage_mb(config: 'EngineConfig') -> int:
    """Estimate GPU memory usage for a configuration.
    
    Args:
        config: Engine configuration
        
    Returns:
        Estimated memory usage in megabytes
    """
    # Calculate buffer sizes
    input_size = config.nfft * config.batch * 4  # float32
    output_size = config.num_output_bins * config.batch * 4
    complex_size = output_size * 2  # complex float
    
    # Account for all buffers
    per_buffer = input_size + output_size + complex_size
    total_bytes = per_buffer * config.pinned_buffer_count
    
    # Add workspace estimates
    cufft_workspace = config.nfft * config.batch * 8  # Rough estimate
    total_bytes += cufft_workspace
    
    # Window coefficients
    total_bytes += config.nfft * 4
    
    return total_bytes // (1024 * 1024)


def validate_input_array(
    data: np.ndarray,
    expected_shape: Optional[Tuple[int, ...]] = None,
    expected_dtype: Optional[np.dtype] = None,
    name: str = "input"
) -> np.ndarray:
    """Validate and prepare a NumPy array for processing.
    
    Args:
        data: Input array to validate
        expected_shape: Expected shape (None to skip)
        expected_dtype: Expected dtype (None to skip)
        name: Name for error messages
        
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
    if expected_shape is not None:
        if data.shape != expected_shape:
            raise ValidationError(
                f"{name} shape mismatch",
                expected=str(expected_shape),
                got=str(data.shape)
            )
    
    # Dtype validation/conversion
    if expected_dtype is not None:
        if data.dtype != expected_dtype:
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
    
    # Check for NaN/Inf
    if np.issubdtype(data.dtype, np.floating):
        if not np.isfinite(data).all():
            warnings.warn(f"{name} contains NaN or Inf values", RuntimeWarning)
    
    return data


def validate_batch_size(data: np.ndarray, config: 'EngineConfig') -> None:
    """Validate that data matches the configured batch size.
    
    Args:
        data: Input data array
        config: Engine configuration
        
    Raises:
        ValidationError: If batch size doesn't match
    """
    expected_samples = config.nfft * config.batch
    if data.size != expected_samples:
        raise ValidationError(
            f"Data size mismatch for batch processing",
            expected=f"{expected_samples} samples ({config.batch} x {config.nfft})",
            got=f"{data.size} samples"
        )