"""Ionosense-HPC: High-performance CUDA FFT engine and benchmarking suite.

This package provides a Python interface to a high-performance CUDA-based
signal processing engine, optimized for real-time signal analysis.

It also includes a professional, research-grade benchmarking infrastructure
for reproducible performance evaluation.
"""

import contextlib
import os
import platform
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

# ============================================================================
# Version Info & Metadata
# ============================================================================
# Version info (single source of truth)
from .__version__ import __version__, __version_info__

__author__ = "Kevin Rahsaz"
__standards__ = ["RSE", "RE", "IEEE-1057", "IEEE-754"]


# ============================================================================
# DLL Bootstrap for Windows (MUST RUN BEFORE CORE IMPORTS)
# ============================================================================

def _bootstrap_windows_dlls():
    """Load required Windows DLLs before importing the extension module.

    This function must run before any attempt to import _engine.
    It adds the DLL directory to the search path on Windows.
    """
    if platform.system() != 'Windows':
        return

    # Get the package directory
    package_dir = Path(__file__).parent

    # Check for DLL directory
    dll_dir = package_dir / '.libs' / 'windows'
    if not dll_dir.exists():
        # Try alternative location
        dll_dir = package_dir / 'core'

    if dll_dir.exists():
        # Add to DLL search path
        try:
            # Python 3.8+ method
            os.add_dll_directory(str(dll_dir))
        except AttributeError:
            # Fallback for older Python
            if str(dll_dir) not in os.environ.get('PATH', ''):
                os.environ['PATH'] = str(dll_dir) + os.pathsep + os.environ.get('PATH', '')

    # Also check for CUDA toolkit in PATH
    cuda_paths = [
        r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin',
        r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.0\bin',
        r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin',
        r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.7\bin',
    ]

    for cuda_path in cuda_paths:
        if Path(cuda_path).exists():
            with contextlib.suppress(AttributeError, OSError):
                os.add_dll_directory(cuda_path)
            break

# Run DLL bootstrap immediately
_bootstrap_windows_dlls()


# ============================================================================
# Core Engine Imports
# ============================================================================

# Import exceptions first (no dependencies)
# Import configuration (minimal dependencies)
from .config import EngineConfig, Presets
from .core.engine import benchmark_latency, process_signal
from .exceptions import (
    ConfigError,
    DeviceNotFoundError,
    DllLoadError,
    EngineRuntimeError,
    EngineStateError,
    IonosenseError,
    ValidationError,
)

# Import utilities (may use pynvml)
from .utils.device import current_device, device_info, gpu_count

# Import core engine classes (requires _engine module)
# Provide type-only imports for mypy and graceful runtime fallback.
_ENGINE_AVAILABLE = False
_ENGINE_ERROR = ""

Engine: Any
if TYPE_CHECKING:
    from .core import Engine as EngineType

try:
    from .core import Engine as _Engine
    Engine = _Engine
    _ENGINE_AVAILABLE = True
except (ImportError, DllLoadError) as e:
    _ENGINE_ERROR = str(e)

    class _UnavailableEngineProxy:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(
                f"Engine not available: {_ENGINE_ERROR}\n"
                "Please ensure the package was built correctly:\n"
                "  Linux/WSL: ./scripts/cli.sh build\n"
                "  Windows: .\\scripts\\cli.ps1 build"
            )

    Engine = _UnavailableEngineProxy
    warnings.warn(
        f"C++ engine module could not be loaded: {_ENGINE_ERROR}",
        UserWarning,
        stacklevel=2,
    )



"""
Benchmark and report modules live under the `ionosense_hpc.benchmarks` package.
To keep imports light and avoid optional heavy dependencies at import time,
they are not re-exported at the top level. Import from submodules instead, e.g.:

  from ionosense_hpc.benchmarks import BenchmarkSuite
  from ionosense_hpc.benchmarks.throughput import ThroughputBenchmark
"""

# ============================================================================
# Public API
# ============================================================================

__all__ = [
    # -- Metadata --
    "__version__",
    "__version_info__",
    "__author__",
    "__standards__",

    # -- Core Engine --
    "Engine",

    # -- Convenience --
    "process_signal",
    "benchmark_latency",

    # -- Config --
    "EngineConfig",
    "Presets",

    # -- Core Exceptions --
    "IonosenseError",
    "ConfigError",
    "DeviceNotFoundError",
    "DllLoadError",
    "EngineStateError",
    "EngineRuntimeError",
    "ValidationError",

    # -- Utilities (lightweight) --
    "gpu_count",
    "current_device",
    "device_info",

    # -- Diagnostics --
    "show_versions",
    "self_test",
]


# ============================================================================
# Helper Functions
# ============================================================================

def show_versions(verbose: bool = True) -> dict:
    """Show version information for ionosense-hpc and dependencies.

    Args:
        verbose: If True, print to console

    Returns:
        Dictionary with version information
    """
    import numpy as np

    versions = {
        'ionosense_hpc': __version__,
        'python': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'numpy': np.__version__,
        'platform': platform.platform(),
        'engine_available': _ENGINE_AVAILABLE
    }

    # Try to get CUDA version
    if _ENGINE_AVAILABLE:
        try:
            engine = Engine(Presets.validation())
            try:
                info = engine.device_info
                versions['cuda'] = info.get('cuda_version', 'Unknown')
                versions['device'] = info.get('device_name', 'Unknown')
            finally:
                engine.close()
        except Exception:
            versions['cuda'] = 'Error detecting'
            versions['device'] = 'Error detecting'
    else:
        versions['cuda'] = 'N/A (engine not loaded)'
        versions['device'] = 'N/A'

    # Try to get pynvml version
    try:
        import pynvml
        versions['pynvml'] = pynvml.__version__ if hasattr(pynvml, '__version__') else 'installed'
    except ImportError:
        versions['pynvml'] = 'not installed'

    if verbose:
        print("Ionosense-HPC Environment")
        print("=" * 40)
        for key, value in versions.items():
            print(f"{key:20s}: {value}")

    return versions


def self_test(verbose: bool = True) -> bool:
    """Run a quick self-test to verify installation.

    Args:
        verbose: If True, print progress

    Returns:
        True if all tests pass
    """
    if verbose:
        print("Running ionosense-hpc self-test...")
        print("-" * 40)

    all_passed = True

    # Test 1: Check engine availability
    if verbose:
        print("1. Checking engine availability...")
    if not _ENGINE_AVAILABLE:
        if verbose:
            print(f"   FAIL: {_ENGINE_ERROR}")
        return False
    else:
        if verbose:
            print("   OK: Engine module loaded")

    # Test 2: Check GPU availability
    if verbose:
        print("2. Checking GPU availability...")
    try:
        n_gpus = gpu_count()
        if n_gpus == 0:
            if verbose:
                print("   WARNING: No GPUs found")
            all_passed = False
        else:
            if verbose:
                print(f"   OK: {n_gpus} GPU(s) found")
    except Exception as e:
        if verbose:
            print(f"   FAIL: {e}")
        all_passed = False

    # Test 3: Try to create and initialize engine
    if verbose:
        print("3. Testing engine initialization...")
    engine = None
    try:
        engine = Engine(Presets.validation())
        if verbose:
            print("   OK: Engine initialized")
    except Exception as e:
        if verbose:
            print(f"   FAIL: {e}")
        all_passed = False
        return False

    # Test 4: Run a simple processing test
    if verbose:
        print("4. Testing signal processing...")
    try:
        import numpy as np
        test_data = np.zeros(engine.config.nfft * engine.config.batch, dtype=np.float32)
        output = engine.process(test_data)

        expected_shape = (engine.config.batch, engine.config.num_output_bins)
        if output.shape != expected_shape:
            if verbose:
                print(f"   FAIL: Unexpected output shape {output.shape}")
            all_passed = False
        else:
            if verbose:
                print(f"   OK: Processing successful, output shape {output.shape}")
    except Exception as e:
        if verbose:
            print(f"   FAIL: {e}")
        all_passed = False
    finally:
        if engine is not None:
            engine.close()

    # Test 5: Check for NaN/Inf in output
    if 'output' in locals():
        if verbose:
            print("5. Checking numerical stability...")
        if np.any(np.isnan(output)) or np.any(np.isinf(output)):
            if verbose:
                print("   FAIL: Output contains NaN or Inf")
            all_passed = False
        else:
            if verbose:
                print("   OK: Output is numerically stable")

    if verbose:
        print("-" * 40)
        if all_passed and _ENGINE_AVAILABLE and gpu_count() > 0:
            print("Self-test PASSED ✓")
        else:
            print("Self-test completed with warnings or errors.")

    return all_passed


# ============================================================================
# Package Initialization
# ============================================================================

# Set up logging on import
from .utils.logging import setup_logging

setup_logging()

# Warn if running in an environment without GPU
try:
    if _ENGINE_AVAILABLE and gpu_count() == 0:
        warnings.warn(
            "No CUDA-capable GPU detected. The engine may not function correctly.",
            RuntimeWarning,
            stacklevel=2,
        )
except DeviceNotFoundError as exc:
    warnings.warn(
        f"CUDA device query failed during module import: {exc}",
        RuntimeWarning,
        stacklevel=2,
    )
    raise

# Print brief info when imported interactively
if hasattr(sys, 'ps1'):  # Interactive mode
    print(f"Ionosense-HPC v{__version__} ready.")
    if not _ENGINE_AVAILABLE:
        print(f"Warning: C++ engine module not available ({_ENGINE_ERROR}). Run build first.")
