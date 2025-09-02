"""Custom exception hierarchy for ionosense-hpc."""

from typing import Any


class IonosenseError(Exception):
    """Base exception for all ionosense-hpc errors."""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint

    def __str__(self) -> str:
        msg = super().__str__()
        if self.hint:
            msg += f"\nHint: {self.hint}"
        return msg


class ConfigError(IonosenseError):
    """Configuration validation or compatibility error."""

    def __init__(self, message: str, field: str | None = None, value: Any = None):
        hint = None
        if field:
            hint = f"Check the '{field}' field"
            if value is not None:
                hint += f" (current value: {value})"
        super().__init__(message, hint)
        self.field = field
        self.value = value


class DeviceNotFoundError(IonosenseError):
    """No CUDA-capable devices found."""

    def __init__(self, message: str = "No CUDA-capable devices found"):
        hint = "Ensure NVIDIA drivers are installed and a GPU is present"
        super().__init__(message, hint)


class DllLoadError(IonosenseError):
    """Failed to load required DLL/shared library."""

    def __init__(self, dll_name: str, original_error: Exception | None = None):
        message = f"Failed to load {dll_name}"
        if original_error:
            message += f": {original_error}"
        hint = "Check that CUDA toolkit is installed and on PATH"
        super().__init__(message, hint)
        self.dll_name = dll_name
        self.original_error = original_error


class EngineStateError(IonosenseError):
    """Engine is in an invalid state for the requested operation."""

    def __init__(self, message: str, current_state: str | None = None):
        hint = None
        if current_state == "uninitialized":
            hint = "Call initialize() or use the Processor context manager"
        elif current_state == "processing":
            hint = "Wait for current operation to complete"
        super().__init__(message, hint)
        self.current_state = current_state


class EngineRuntimeError(IonosenseError):
    """Runtime error during engine processing."""

    def __init__(self, message: str, cuda_error: str | None = None):
        hint = None
        if cuda_error:
            if "out of memory" in cuda_error.lower():
                hint = "Reduce batch size or nfft, or use a GPU with more memory"
            elif "invalid configuration" in cuda_error.lower():
                hint = "Check that nfft is a power of 2 and batch > 0"
        super().__init__(message, hint)
        self.cuda_error = cuda_error


class ValidationError(IonosenseError):
    """Input data validation error."""

    def __init__(self, message: str, expected: str | None = None, got: str | None = None):
        hint = None
        if expected and got:
            hint = f"Expected {expected}, got {got}"
        super().__init__(message, hint)
        self.expected = expected
        self.got = got
