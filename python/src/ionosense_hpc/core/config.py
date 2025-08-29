# python/src/ionosense_hpc/core/config.py
"""
Configuration management for the Ionosense HPC pipeline.

This module defines dataclasses for managing processing and runtime
configurations, including validation and auto-tuning of parameters.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

# pynvml is a more robust way to query GPU info than nvidia-smi
try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False
    logging.warning("pynvml not found. GPU memory auto-tuning will be disabled. "
                    "Install with: pip install pynvml")

# Define literal types for valid configuration options for better static analysis
WindowFunction = Literal['hann', 'hamming', 'blackman', 'bartlett', 'rectangular']
OutputType = Literal['magnitude', 'power', 'db']


@dataclass(frozen=True)
class ProcessingConfig:
    """
    Validated configuration for an FFT processing pipeline.
    ... (omitted docstring for brevity) ...
    """
    fft_size: int = 4096
    batch_size: Optional[int] = None
    window: WindowFunction = 'hann'
    output_type: OutputType = 'magnitude'
    use_graphs: bool = True
    num_streams: int = 3
    verbose: bool = False  # Add verbose flag to match C++

    def __post_init__(self):
        """Perform validation and auto-tuning after initialization."""
        self._validate()

        if self.batch_size is None:
            tuned_batch_size = self._auto_tune_batch_size()
            object.__setattr__(self, 'batch_size', tuned_batch_size)
            logging.info(f"Auto-tuned batch size to {tuned_batch_size}")

    def _validate(self) -> None:
        """Ensures all configuration parameters are valid."""
        if self.fft_size <= 0 or (self.fft_size & (self.fft_size - 1)) != 0:
            raise ValueError(f"fft_size must be a positive power of 2, but got {self.fft_size}")

        if self.batch_size is not None:
            if self.batch_size <= 0 or self.batch_size % 2 != 0:
                raise ValueError(
                    "batch_size must be a positive, even number for dual-channel processing, "
                    f"but got {self.batch_size}"
                )

        if self.window not in WindowFunction.__args__:
             raise ValueError(f"Unsupported window function: '{self.window}'")
        if self.output_type not in OutputType.__args__:
             raise ValueError(f"Unsupported output type: '{self.output_type}'")

    def get_engine_params(self) -> Dict[str, Any]:
        """
        Formats the configuration into a dictionary suitable for the C++ engine.
        """
        return {
            'nfft': self.fft_size,
            'batch': self.batch_size,
            'use_graphs': self.use_graphs,
            'verbose': self.verbose, # Add verbose to the dictionary
        }

    def _auto_tune_batch_size(self) -> int:
        """
        Selects an optimal batch size based on GPU memory and FFT size.
        """
        if PYNVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                gpu_memory_bytes = mem_info.free
                pynvml.nvmlShutdown()

                bytes_per_fft = self.fft_size * 4 + (self.fft_size // 2 + 1) * 8
                max_batch = int((gpu_memory_bytes * 0.1) / bytes_per_fft)

                if max_batch > 1:
                    batch = 1 << (max_batch.bit_length() - 1)
                    return min(batch, 256)
                return 2
            except Exception as e:
                logging.warning(f"Failed to query GPU memory with pynvml: {e}. "
                                "Falling back to heuristic.")

        # Fallback heuristic
        if self.fft_size <= 2048: return 64
        elif self.fft_size <= 4096: return 32
        elif self.fft_size <= 8192: return 16
        else: return 8
