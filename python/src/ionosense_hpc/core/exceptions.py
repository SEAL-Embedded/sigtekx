"""
ionosense_hpc.core.exceptions: Exception hierarchy for error handling.

Maps C++ exceptions to Python exceptions and provides a clear error
taxonomy for debugging and error recovery.
"""

from typing import Optional


class IonosphereError(Exception):
    """Base exception for all ionosense_hpc errors."""
    pass


class ConfigurationError(IonosphereError, ValueError):
    """Invalid configuration parameters."""
    pass


class CudaError(IonosphereError, RuntimeError):
    """CUDA API or kernel execution error."""
    
    def __init__(self, message: str, error_code: Optional[int] = None):
        super().__init__(message)
        self.error_code = error_code


class StateError(IonosphereError, RuntimeError):
    """Operation called in invalid state."""
    pass


class NumericalError(IonosphereError, ArithmeticError):
    """Numerical computation error (NaN, Inf, convergence)."""
    pass


def translate_cpp_exception(exc: Exception) -> IonosphereError:
    """
    Translate C++ exceptions to Python exceptions.
    
    Args:
        exc: The C++ exception caught via pybind11.
    
    Returns:
        An appropriate Python exception.
    """
    exc_str = str(exc)
    
    # Parse the C++ exception message to determine type
    if "Configuration Error:" in exc_str:
        return ConfigurationError(exc_str)
    elif "State Error:" in exc_str:
        return StateError(exc_str)
    elif "CUDA Error" in exc_str:
        # Try to extract error code
        import re
        match = re.search(r"CUDA Error (\d+)", exc_str)
        error_code = int(match.group(1)) if match else None
        return CudaError(exc_str, error_code)
    elif "cuFFT Error" in exc_str:
        return CudaError(f"cuFFT operation failed: {exc_str}")
    else:
        # Generic fallback
        return IonosphereError(f"Engine error: {exc_str}")