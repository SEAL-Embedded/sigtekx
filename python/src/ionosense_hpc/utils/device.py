"""CUDA device query and management utilities."""

import contextlib
import warnings
from typing import Any

from ionosense_hpc.core.engine import _import_cpp_engine

try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    # Optional dependency: silently degrade without emitting import-time warnings.
    # Tests treat ImportWarning as errors; runtime gracefully falls back to C++ queries.
    NVML_AVAILABLE = False


def gpu_count() -> int:
    """Get the number of available CUDA devices.

    Returns:
        Number of CUDA-capable GPU's
    """
    if NVML_AVAILABLE:
        try:
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            pynvml.nvmlShutdown()
            return int(count)
        except Exception:
            pass

    # Fallback to C++ module
    try:
        cpp_module = _import_cpp_engine()
    except Exception:
        return 0

    try:
        devices = cpp_module.get_available_devices()
        return len(list(devices))
    except Exception:
        return 0


def current_device() -> int:
    """Get the currently selected CUDA device ID.

    Returns:
        Current device ID (0-based)
    """
    try:
        cpp_module = _import_cpp_engine()
        return int(cpp_module.select_best_device())
    except Exception:
        return 0


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
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(device_id)

            # Basic info
            info['name'] = pynvml.nvmlDeviceGetName(handle)

            # Memory info
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            info['memory_total_mb'] = mem_info.total // (1024 * 1024)
            info['memory_free_mb'] = mem_info.free // (1024 * 1024)

            # Compute capability
            major = pynvml.nvmlDeviceGetCudaComputeCapability(handle)[0]
            minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)[1]
            info['compute_capability'] = (major, minor)

            # Optional monitoring (may fail on some GPUs)
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

            pynvml.nvmlShutdown()
        except Exception as e:
            warnings.warn(f"NVML query failed: {e}", stacklevel=2)

    # Try to get basic info from C++ module as fallback
    if info['name'] == 'Unknown':
        try:
            cpp_module = _import_cpp_engine()
            devices = list(cpp_module.get_available_devices())
            if device_id < len(devices):
                device_str = devices[device_id]
                name_part = device_str.split('] ', 1)[1] if '] ' in device_str else device_str
                if ' (CC ' in name_part:
                    name, cc_part = name_part.split(' (CC ', 1)
                    info['name'] = name
                    cc_tokens = cc_part.split(')', 1)[0].split('.')
                    if len(cc_tokens) == 2:
                        try:
                            info['compute_capability'] = (int(cc_tokens[0]), int(cc_tokens[1]))
                        except ValueError:
                            pass
                else:
                    info['name'] = name_part
        except Exception:
            pass

    return info


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
    return gpu_count() > 0


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
        try:
            return int(cc[0]), int(cc[1])
        except Exception:
            return (0, 0)
    return (0, 0)


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
