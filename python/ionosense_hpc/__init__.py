"""
Ionosense HPC Library

A high-performance CUDA FFT engine for dual-channel ULF/VLF antenna signal processing.
"""
import sys
import os
import platform
import warnings
from pathlib import Path
from importlib.resources import files

__version__ = "0.1.0"

def _setup_dll_search_path():
    """
    Adds the bundled DLLs to the search path on Windows.

    This is critical for finding the CUDA runtime libraries (cudart, cufft)
    that are staged by CMake into the .libs/windows directory.
    """
    if sys.platform != "win32":
        return "Not on Windows, no action needed."

    # Find the path to the bundled libraries
    try:
        # This is the standard path for an installed package
        libs_dir = files("ionosense_hpc") / ".libs" / "windows"
    except ImportError:
        # Fallback for when the package is not installed (e.g., in development)
        libs_dir = Path(__file__).parent / ".libs" / "windows"

    if libs_dir.exists():
        os.add_dll_directory(str(libs_dir))
        return f"Successfully added {libs_dir} to DLL search path."
    else:
        # If .libs doesn't exist, try the local core/ dir as a dev fallback
        dev_dir = Path(__file__).parent / "core"
        if dev_dir.exists():
            os.add_dll_directory(str(dev_dir))
            return f"Added dev directory {dev_dir} to DLL search path."
        return f"Warning: Bundled library directory not found at {libs_dir}."


# Run the setup function upon import
_dll_setup_message = _setup_dll_search_path()

# Now, attempt to import the compiled C++ extension
try:
    from .core.engine import RtFftEngine, RtFftConfig
except ImportError as e:
    # If the import fails, raise a new exception with a detailed,
    # user-friendly error message.
    raise ImportError(
        f"\n{'='*80}\n"
        f"Failed to import the C++ core of `ionosense_hpc`.\n"
        f"This is likely a build or environment issue.\n"
        f"{'='*80}\n"
        f"Platform: {platform.platform()}\n"
        f"Python: {sys.version}\n"
        f"DLL Setup: {_dll_setup_message}\n"
        f"Original Error: {e}\n\n"
        f"Troubleshooting Steps:\n"
        f"1. Rebuild the project: Ensure you have run your build script (e.g., `.\\scripts\\cli.ps1 rebuild`).\n"
        f"2. Check for the extension: Verify that `_engine...pyd` (Win) or `_engine...so` (Linux) exists in `python/ionosense_hpc/core/`.\n"
        f"3. Check CUDA Dependencies: Make sure the CUDA Toolkit DLLs (`cufft64_*.dll`, `cudart64_*.dll`) were correctly staged into `python/ionosense_hpc/.libs/windows/` by CMake.\n"
        f"{'='*80}\n"
    ) from e

# Define what gets exposed to the user with "from ionosense_hpc import *"
__all__ = ["RtFftEngine", "RtFftConfig"]