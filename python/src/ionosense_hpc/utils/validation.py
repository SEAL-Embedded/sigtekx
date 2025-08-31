"""
ionosense_hpc.utils.validation: Input validation utilities.

Provides functions for validating parameters and data to ensure
correctness and prevent errors in the processing pipeline.
"""

from typing import Any, List, Tuple
import numpy as np
from numpy.typing import NDArray


def validate_fft_size(size: int) -> bool:
    """
    Check if a value is a valid FFT size (positive power of 2).
    
    Args:
        size: The size to validate.
    
    Returns:
        True if valid, False otherwise.
    
    Example:
        >>> validate_fft_size(4096)
        True
        >>> validate_fft_size(4000)
        False
    """
    if not isinstance(size, int) or size <= 0:
        return False
    # Check if power of 2: only one bit should be set
    return (size & (size - 1)) == 0


def get_optimal_fft_size(min_size: int) -> int:
    """
    Find the next power of 2 >= min_size.
    
    Args:
        min_size: Minimum required size.
    
    Returns:
        Next power of 2.
    
    Example:
        >>> get_optimal_fft_size(3000)
        4096
    """
    if min_size <= 0:
        raise ValueError("min_size must be positive")
    
    # Find position of highest bit, then shift
    return 1 << (min_size - 1).bit_length()


def validate_signal_data(
    data: Any,
    expected_shape: Tuple[int, ...],
    dtype: np.dtype = np.float32
) -> NDArray:
    """
    Validate and convert signal data.
    
    Args:
        data: Input data to validate.
        expected_shape: Expected array shape.
        dtype: Expected data type.
    
    Returns:
        Validated NumPy array.
    
    Raises:
        ValueError: If validation fails.
    """
    arr = np.asarray(data, dtype=dtype)
    
    if arr.shape != expected_shape:
        raise ValueError(
            f"Expected shape {expected_shape}, got {arr.shape}"
        )
    
    if not np.isfinite(arr).all():
        raise ValueError("Signal contains NaN or Inf values")
    
    return arr


def validate_batch_consistency(arrays: List[NDArray]) -> bool:
    """
    Check if arrays have consistent shapes for batch processing.
    
    Args:
        arrays: List of arrays to check.
    
    Returns:
        True if consistent, False otherwise.
    """
    if not arrays:
        return True
    
    first_shape = arrays[0].shape
    return all(arr.shape == first_shape for arr in arrays)


def check_cuda_compute_capability(
    required_major: int = 7,
    required_minor: int = 0
) -> Tuple[bool, str]:
    """
    Check if GPU meets minimum compute capability.
    
    Args:
        required_major: Minimum major version.
        required_minor: Minimum minor version.
    
    Returns:
        (is_sufficient, description_string)
    """
    try:
        from ..utils.device import get_device_info
        info = get_device_info(0)
        
        major, minor = info.compute_capability
        is_sufficient = (major > required_major or 
                        (major == required_major and minor >= required_minor))
        
        desc = f"GPU: {info.name} (CC {major}.{minor})"
        if not is_sufficient:
            desc += f" - Requires CC {required_major}.{required_minor}+"
        
        return is_sufficient, desc
        
    except Exception as e:
        return False, f"Could not check GPU: {e}"