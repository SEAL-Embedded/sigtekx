"""Profiling utilities with NVIDIA Nsight (NVTX) integration.

This module provides NVTX markers for detailed performance analysis with
NVIDIA's profiling tools. When the `nvtx` package is not installed, these
utilities become no-ops with zero overhead.
"""

import warnings
from contextlib import contextmanager

try:
    import nvtx
    NVTX_AVAILABLE = True
except ImportError:
    NVTX_AVAILABLE = False
    warnings.warn(
        "`nvtx` not installed. NVTX markers will be disabled. "
        "Install with: pip install nvtx",
        ImportWarning, stacklevel=2
    )


@contextmanager
def nvtx_range(name: str, color: str = "blue"):
    """Creates a context-managed NVTX range for profiling.

    This range will appear in the NVIDIA Nsight Systems timeline viewer,
    allowing for easy identification of code sections.

    Args:
        name: A descriptive name for the profiling range.
        color: A color for the range in the profiler (e.g., 'blue', 'red').
    """
    if NVTX_AVAILABLE:
        with nvtx.annotate(message=name, color=color):
            yield
    else:
        yield
