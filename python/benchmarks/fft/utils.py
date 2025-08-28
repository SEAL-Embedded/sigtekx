#!/usr/bin/env python3
"""
benchmark_utils.py
---------------------------------------------------------------
A centralized module of utility functions shared across various
FFT benchmark scripts. This includes engine imports, NVTX shims,
signal generation, statistical calculations, and console output.
"""
from __future__ import annotations
import numpy as np
import sys
import os
from typing import Dict, List

# ─── Dependency Checks and Imports ────────────────────────────────────────────

# NVTX shim for easy profiling with NVIDIA's Nsight Systems.
try:
    import nvtx
    def nvtx_range(name: str):
        return nvtx.annotate(message=name)
except ImportError:
    from contextlib import contextmanager
    @contextmanager
    def nvtx_range(name: str):
        yield

# tqdm for progress bars, with a helpful error message if not installed.
try:
    from tqdm import tqdm
except ImportError:
    print("FATAL: 'tqdm' is not installed. Please run 'pip install tqdm'.", file=sys.stderr)
    tqdm = None # Allow script to exit gracefully

# Centralized C++ engine import with clear error messaging.
try:
    from ionosense_hpc.core.engine import RtFftEngine as CudaFftEngine
except ImportError as e:
    print("FATAL: Could not import 'CudaFftEngine' from 'cuda_lib'.", file=sys.stderr)
    print(f"  - Error: {e}", file=sys.stderr)
    print("  - Please ensure the C++ module has been compiled successfully via './cli.ps1 build'.", file=sys.stderr)
    CudaFftEngine = None

# ─── Profiler & Environment Detection ─────────────────────────────────────────

def is_profiler_attached() -> bool:
    """
    Detects if the script is running under an Nsight profiler (NCU or NSYS).
    This is used to automatically quiet verbose output during profiling.
    """
    # Nsight Systems often sets this environment variable.
    if 'NVTX_INJECTION64_PATH' in os.environ:
        return True
    # Check for other common profiler environment variables.
    for key in os.environ:
        if 'NSIGHT' in key or 'NCU' in key or 'NSYS' in key:
            return True
    return False

# ─── Safe Console Output ──────────────────────────────────────────────────────

def safe_print(text: str, file=None):
    """
    Safely prints text to console, handling Unicode encoding issues.
    This is critical when running under profilers that use basic consoles.
    """
    if file is None:
        file = sys.stdout
    
    try:
        print(text, file=file)
    except UnicodeEncodeError:
        # Fallback: encode to ASCII with replacement characters
        safe_text = text.encode('ascii', errors='replace').decode('ascii')
        print(safe_text, file=file)

# ─── Console Formatting ───────────────────────────────────────────────────────

def print_separator(char: str = "─", width: int = 80):
    # Use ASCII characters when under a profiler
    if is_profiler_attached():
        char = "-"
    print(char * width)

def print_header(title: str):
    # Use ASCII characters when under a profiler
    if is_profiler_attached():
        print("\n" + "=" * 80)
        print(f" {title}")
        print("=" * 80)
    else:
        print("\n" + "═" * 80)
        print(f" {title}")
        print("═" * 80)

def fmt_t(ms: float) -> str:
    """Formats time in ms, switching to µs for sub-millisecond values."""
    if ms == 0: return "N/A"
    # Use 'us' instead of 'µs' when under a profiler to avoid Unicode issues
    if ms >= 1:
        return f"{ms:.3f} ms"
    else:
        if is_profiler_attached():
            return f"{ms * 1000:.3f} us"  # ASCII version
        else:
            return f"{ms * 1000:.3f} µs"  # Unicode version

def print_rocket(text: str):
    """
    Prints a line with a rocket emoji, but falls back to a safe
    ASCII character if running under a profiler to avoid encoding errors.
    """
    prefix = "->" if is_profiler_attached() else "🚀"
    safe_print(f"{prefix} {text}")

# ─── Data Generation & Stats ──────────────────────────────────────────────────

def build_signal(sr: int, length_s: float, nfft: int) -> Dict[str, np.ndarray]:
    """Generates a synthetic two-channel signal."""
    num_samples = int(sr * length_s) + nfft * 2  # Add buffer
    t = np.arange(num_samples, dtype=np.float32) / sr
    
    # Simple sine waves with a bit of noise
    ch1 = np.sin(2 * np.pi * 7_000 * t, dtype=np.float32)
    ch1 += 0.01 * np.random.randn(num_samples).astype(np.float32)
    
    ch2 = np.sin(2 * np.pi * 1_000 * t, dtype=np.float32)
    ch2 += 0.01 * np.random.randn(num_samples).astype(np.float32)
          
    return {"ch1": ch1, "ch2": ch2}

def compute_stats(data: List[float]) -> Dict[str, float]:
    """Computes descriptive statistics for a list of numbers."""
    if not data:
        return {key: 0.0 for key in ['mean', 'median', 'min', 'max', 'stdev', 'p95', 'p99']}
    
    arr = np.array(data, dtype=np.float64)
    return {
        'mean': arr.mean(), 'median': np.median(arr),
        'min': arr.min(), 'max': arr.max(),
        'stdev': arr.std(), 'p95': np.percentile(arr, 95),
        'p99': np.percentile(arr, 99),
    }

# ─── Engine Initialization Helper ─────────────────────────────────────────────

def create_engine(nfft: int, 
                  batch_size: int, 
                  use_graphs: bool = True, 
                  verbose_override: bool = False) -> 'CudaFftEngine':
    """
    Helper to create a CudaFftEngine with smart defaults.
    Verbose output is automatically disabled under a profiler unless overridden.
    """
    if CudaFftEngine is None:
        raise RuntimeError("CudaFftEngine not available - module failed to import.")
    
    # Make the engine verbose only when verbose_override is True.
    is_verbose = verbose_override
    
    return CudaFftEngine(nfft, batch_size, use_graphs=use_graphs, verbose=is_verbose)