"""CUDA device query and management utilities."""

import contextlib
import logging
from typing import Any, Generator

from sigtekx.core.engine import _import_cpp_engine
from sigtekx.exceptions import DeviceNotFoundError, DllLoadError

try:
    import pynvml

    NVML_AVAILABLE = True
except ImportError:
    # Optional dependency: gracefully fall back to the C++ backend queries.
    NVML_AVAILABLE = False

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def nvml_context() -> Generator[None, None, None]:
    """Context manager for safe NVML library usage.

    Ensures nvmlInit() is called on entry and nvmlShutdown() is called on exit,
    even if exceptions occur. Provides proper resource cleanup and error logging.

    Yields:
        None

    Example:
        >>> with nvml_context():
        ...     handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        ...     name = pynvml.nvmlDeviceGetName(handle)

    Note:
        If NVML_AVAILABLE is False, this context manager is a no-op.
    """
    if not NVML_AVAILABLE:
        yield
        return

    try:
        pynvml.nvmlInit()
        yield
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception as e:
            logger.debug("NVML shutdown error (expected if init failed): %s", e)


def gpu_count() -> int:
    """Get the number of available CUDA devices.

    Returns:
        Number of CUDA-capable GPU's
    """
    if NVML_AVAILABLE:
        try:
            with nvml_context():
                return int(pynvml.nvmlDeviceGetCount())
        except pynvml.NVMLError as exc:
            logger.warning("NVML query failed: %s", exc)
        except Exception as exc:  # pragma: no cover - defensive safeguard
            raise DeviceNotFoundError("Failed to query CUDA devices via NVML") from exc

    try:
        cpp_module = _import_cpp_engine()
    except Exception as exc:  # pragma: no cover - propagate load failures
        raise DllLoadError("_engine", exc) from exc

    try:
        return len(list(cpp_module.get_available_devices()))
    except Exception as exc:  # pragma: no cover - propagate enumeration errors
        raise DeviceNotFoundError("Failed to enumerate CUDA devices via C++ backend") from exc


def current_device() -> int:
    """Get the currently selected CUDA device ID.

    Returns:
        Current device ID (0-based)
    """
    try:
        cpp_module = _import_cpp_engine()
    except Exception as exc:  # pragma: no cover - propagate load failures
        raise DllLoadError("_engine", exc) from exc

    try:
        return int(cpp_module.select_best_device())
    except Exception as exc:
        raise DeviceNotFoundError("Failed to select CUDA device") from exc


def device_info(device_id: int | None = None) -> dict[str, Any]:
    """Get detailed information about a CUDA device.

    Args:
        device_id: Device to query (None for current device)

    Returns:
        Dictionary with device properties
    """
    if device_id is None:
        device_id = current_device()

    info = {
        'id': device_id,
        'name': 'Unknown',
        'memory_total_mb': 0,
        'memory_free_mb': 0,
        'compute_capability': (0, 0),
        'temperature_c': None,
        'power_w': None,
        'utilization_gpu': None,
        'utilization_memory': None
    }

    if NVML_AVAILABLE:
        try:
            with nvml_context():
                handle = pynvml.nvmlDeviceGetHandleByIndex(device_id)

                info['name'] = pynvml.nvmlDeviceGetName(handle)

                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                info['memory_total_mb'] = mem_info.total // (1024 * 1024)
                info['memory_free_mb'] = mem_info.free // (1024 * 1024)

                major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
                info['compute_capability'] = (major, minor)

                # Optional fields with individual error handling
                with contextlib.suppress(pynvml.NVMLError):
                    info['temperature_c'] = pynvml.nvmlDeviceGetTemperature(
                        handle, pynvml.NVML_TEMPERATURE_GPU
                    )

                with contextlib.suppress(pynvml.NVMLError):
                    info['power_w'] = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0

                with contextlib.suppress(pynvml.NVMLError):
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    info['utilization_gpu'] = util.gpu
                    info['utilization_memory'] = util.memory

        except pynvml.NVMLError as exc:
            logger.warning("NVML device query failed: %s", exc)
        except Exception as exc:
            logger.warning("Unexpected NVML error: %s", exc)

    # Fallback to C++ backend if name still 'Unknown'
    if info['name'] == 'Unknown':
        try:
            cpp_module = _import_cpp_engine()
        except Exception as exc:  # pragma: no cover - propagate load failures
            raise DllLoadError("_engine", exc) from exc

        try:
            devices = list(cpp_module.get_available_devices())
        except Exception as exc:
            raise DeviceNotFoundError("Failed to enumerate CUDA devices") from exc

        if not devices:
            raise DeviceNotFoundError("No CUDA-capable devices detected")

        if device_id >= len(devices) or device_id < 0:
            raise DeviceNotFoundError(
                f"Requested device index {device_id} outside available device range"
            )

        device_str = devices[device_id]
        name_part = device_str.split('] ', 1)[1] if '] ' in device_str else device_str
        if ' (CC ' in name_part:
            name, cc_part = name_part.split(' (CC ', 1)
            info['name'] = name
            cc_tokens = cc_part.split(')', 1)[0].split('.')
            if len(cc_tokens) == 2:
                with contextlib.suppress(ValueError):
                    info['compute_capability'] = (int(cc_tokens[0]), int(cc_tokens[1]))
        else:
            info['name'] = name_part

    return info


# =================================================================
#  High-level utility functions (device_info() wrappers)
# =================================================================


def get_memory_usage() -> tuple[int, int]:
    """Get current GPU memory usage.

    Returns:
        Tuple of (used_mb, total_mb)
    """
    info = device_info()
    total = int(info['memory_total_mb'])
    free = int(info['memory_free_mb'])
    used = total - free if total > 0 else 0
    return used, total


def check_cuda_available() -> bool:
    """Check if CUDA is available and functional.

    Returns:
        True if CUDA can be used
    """
    try:
        return gpu_count() > 0
    except DeviceNotFoundError:
        return False


def get_compute_capability(device_id: int | None = None) -> tuple[int, int]:
    """Get compute capability of a device.

    Args:
        device_id: Device to query (None for current)

    Returns:
        Tuple of (major, minor) compute capability
    """
    info = device_info(device_id)
    cc = info.get('compute_capability', (0, 0))
    if isinstance(cc, tuple) and len(cc) == 2:
        return int(cc[0]), int(cc[1])
    raise DeviceNotFoundError("Compute capability unavailable for requested device")


def monitor_device(device_id: int | None = None) -> str:
    """Get a formatted string with current device status.

    Args:
        device_id: Device to monitor (None for current)

    Returns:
        Formatted status string
    """
    info = device_info(device_id)

    used_mb = int(info['memory_total_mb']) - int(info['memory_free_mb'])
    lines = [
        f"Device {info['id']}: {info['name']}",
        f"  Memory: {used_mb}/{int(info['memory_total_mb'])} MB used",
        f"  Compute Capability: {info['compute_capability'][0]}.{info['compute_capability'][1]}"
    ]

    if info['temperature_c'] is not None:
        lines.append(f"  Temperature: {info['temperature_c']}°C")

    if info['power_w'] is not None:
        lines.append(f"  Power: {info['power_w']:.1f}W")

    if info['utilization_gpu'] is not None:
        lines.append(f"  GPU Utilization: {info['utilization_gpu']}%")

    return '\n'.join(lines)
