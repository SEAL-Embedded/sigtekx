"""
Thin Python wrapper that re-exports the CUDA engine from the compiled module.
Keeps both new (RtFft*) and legacy (CudaFft*) names working.
"""
from __future__ import annotations

try:
    from ._engine import RtFftEngine, RtFftConfig
except ImportError:
    try:
        from ._engine import CudaFftEngine as RtFftEngine, CudaFftConfig as RtFftConfig
    except ImportError as e:
        raise ImportError(
            "\nFailed to import Ionosense CUDA engine symbols from _engine.pyd."
            "\nThis typically means the C++ module has not been compiled."
            "\nRun './scripts/cli.ps1 build' and try again."
            f"\nOriginal error: {e}"
        )

__all__ = ['RtFftEngine', 'RtFftConfig']