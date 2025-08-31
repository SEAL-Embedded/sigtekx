"""
ionosense_hpc: High-performance CUDA FFT engine for ULF/VLF signal processing.

This package provides GPU-accelerated signal processing capabilities optimized
for real-time dual-channel antenna data analysis, achieving <200μs latency per
FFT pair with IEEE 754 float32 numerical accuracy.

Copyright (c) 2025 University of Washington SEAL Lab
"""

# __init__.py (top-level) — lightweight & lazy
from importlib import metadata as _md, import_module as _imp

# Windows DLL bootstrap stays fine
def _bootstrap_dlls() -> None:
    import os, pathlib
    if os.name == "nt":
        dll_dir = pathlib.Path(__file__).parent / ".libs" / "windows"
        if dll_dir.is_dir():
            try: os.add_dll_directory(str(dll_dir))
            except Exception: pass
_bootstrap_dlls(); del _bootstrap_dlls

try:
    __version__ = _md.version("ionosense-hpc")
except _md.PackageNotFoundError:
    __version__ = "0.0.0-dev"
del _md

# Public API names we’ll expose on demand
__all__ = [
    "FFTProcessor", "Pipeline", "PipelineBuilder",
    "FFTConfig", "PipelineConfig",
    "IonosphereError", "ConfigurationError", "CudaError", "StateError",
    "generate_test_signal", "SignalParameters",
    "ensure_cuda_available", "get_device_info",
]

# Lazy attribute loader so we don’t import core/utils until actually used
def __getattr__(name: str):
    if name in {"FFTProcessor", "Pipeline", "PipelineBuilder", "FFTConfig", "PipelineConfig",
                "IonosphereError", "ConfigurationError", "CudaError", "StateError"}:
        mod = _imp(".core", __name__)
        return getattr(mod, name)
    if name in {"generate_test_signal", "SignalParameters", "ensure_cuda_available", "get_device_info"}:
        mod = _imp(".utils", __name__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name}")

def __dir__():
    return sorted(list(globals().keys()) + __all__)
