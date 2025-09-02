"""Profiling utilities, including NVTX shims for NVIDIA Nsight."""
import warnings
from contextlib import contextmanager

try:
    import nvtx
    NVTX_AVAILABLE = True
except ImportError:
    NVTX_AVAILABLE = False
    warnings.warn("`nvtx` not installed. NVTX markers will be disabled. "
                  "Install with: pip install nvtx", ImportWarning)


@contextmanager
def nvtx_range(name: str, color: str = "blue"):
    """
    A context manager for NVIDIA Tools Extension (NVTX) ranges.
    These ranges are visible in NVIDIA Nsight Systems, making it easy
    to identify specific sections of code in the profiler timeline.

    If the `nvtx-plugins` package is not installed, this context manager
    acts as a no-op, allowing the code to run without modification.

    Args:
        name (str): The name of the range to be displayed in the profiler.
        color (str): The color of the range. Can be a color name like "blue",
                     "green", "red", or a hex code like "#FF0000".
    """
    if NVTX_AVAILABLE:
        with nvtx.annotate(message=name, color=color):
            yield
    else:
        yield

