"""
Thin Python wrapper that re-exports the CUDA engine from the compiled module.
Keeps both new (RtFft*) and legacy (CudaFft*) names working.
"""
from __future__ import annotations

try:
    from cuda_lib import RtFftEngine, RtFftConfig  # preferred modern names
except Exception as e1:
    # fallback to legacy names if the module only exposes those
    try:
        from cuda_lib import CudaFftEngine as RtFftEngine, CudaFftConfig as RtFftConfig
    except Exception as e2:
        raise ImportError(
            f"Failed to import Ionosense CUDA engine symbols.\n"
            f"Primary error: {e1}\nSecondary error: {e2}"
        )

__all__ = ["RtFftEngine", "RtFftConfig"]
