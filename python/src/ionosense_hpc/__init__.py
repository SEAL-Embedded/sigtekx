# python/src/ionosense_hpc/__init__.py
"""
Ionosense HPC Library

A high-performance CUDA FFT engine for dual-channel ULF/VLF antenna signal processing.
"""
import sys
import os
import platform
from pathlib import Path
from importlib.resources import files

__version__ = "0.1.0"

def _setup_dll_search_path():
    """
    Adds the bundled DLLs to the search path on Windows.
    """
    if sys.platform != "win32":
        return "Not on Windows, no action needed."

    try:
        libs_dir = files("ionosense_hpc") / ".libs" / "windows"
    except ImportError:
        libs_dir = Path(__file__).parent / ".libs" / "windows"

    if libs_dir.exists() and libs_dir.is_dir():
        os.add_dll_directory(str(libs_dir))
        return f"Successfully added {libs_dir} to DLL search path."
    else:
        dev_dir = Path(__file__).parent / "core"
        if dev_dir.exists() and dev_dir.is_dir():
            os.add_dll_directory(str(dev_dir))
            return f"Added dev directory {dev_dir} to DLL search path."
        return f"Warning: Bundled library directory not found at {libs_dir}."

_dll_setup_message = _setup_dll_search_path()

try:
    # C++ Core Bindings
    from .core.engine import RtFftEngine, RtFftConfig

    # CORRECTED IMPORT PATH: Now points to .utils.config
    from .utils.config import ProcessingConfig

except ImportError as e:
    raise ImportError(
        f"\n{'='*80}\n"
        f"Failed to import the C++ core or Python modules of `ionosense_hpc`.\n"
        f"This is likely a build or environment issue.\n"
        f"{'='*80}\n"
        f"Platform: {platform.platform()}\n"
        f"Python: {sys.version}\n"
        f"DLL Setup: {_dll_setup_message}\n"
        f"Original Error: {e}\n\n"
        f"Troubleshooting Steps:\n"
        f"1. Rebuild the project: `.\\scripts\\cli.ps1 rebuild`.\n"
        f"2. Check for the extension: `_engine...pyd` must exist in `python/src/ionosense_hpc/core/`.\n"
        f"3. Check for `__init__.py`: Ensure empty `__init__.py` files exist in `core/` and `utils/`.\n"
        f"{'='*80}\n"
    ) from e

__all__ = [
    "RtFftEngine",
    "RtFftConfig",
    "ProcessingConfig",
]

