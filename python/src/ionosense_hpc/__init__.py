# python/src/ionosense_hpc/__init__.py
from importlib import metadata as _md

__version__ = _md.version("ionosense-hpc")

def _bootstrap_dlls() -> None:
    # On Windows, make staged CUDA DLLs available at import time (Py ≥3.8)
    import os, pathlib
    if os.name == "nt":
        dll_dir = pathlib.Path(__file__).with_name(".libs") / "windows"
        if dll_dir.is_dir():
            try:
                os.add_dll_directory(str(dll_dir))
            except Exception:
                pass  # best-effort

_bootstrap_dlls()
del _bootstrap_dlls, _md
