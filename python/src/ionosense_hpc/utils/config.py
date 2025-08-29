# ionosense_hpc/core/config.py
"""
Configuration management for the Ionosense HPC pipeline.

This module defines dataclasses for managing processing and runtime
configurations, including validation and auto-tuning of parameters.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
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

    This is an immutable dataclass that validates all parameters upon
    creation to ensure a valid state before it reaches the C++ engine.
    If `batch_size` is not provided, it will be auto-tuned based on
    GPU memory and FFT size.

    Attributes:
        fft_size: The size of the FFT (e.g., 4096). Must be a power of 2.
        batch_size: The number of FFTs to process in a single batch.
                    Must be a positive, even number. Auto-tuned if None.
        window: The window function to apply to the time-domain signal.
        output_type: The desired format for the output data.
        use_graphs: If True, enables CUDA Graphs for lower launch overhead.
        num_streams: The number of concurrent CUDA streams to use.
                     This should match the C++ engine's implementation.
    """
    fft_size: int = 4096
    batch_size: Optional[int] = None
    window: WindowFunction = 'hann'
    output_type: OutputType = 'magnitude'
    use_graphs: bool = True
    num_streams: int = 3  # Matches C++ engine's triple-buffer design

    def __post_init__(self):
        """Perform validation and auto-tuning after initialization."""
        self._validate()

        # If batch_size is None, auto-tune it.
        # We use object.__setattr__ because the dataclass is frozen.
        if self.batch_size is None:
            tuned_batch_size = self._auto_tune_batch_size()
            object.__setattr__(self, 'batch_size', tuned_batch_size)
            logging.info(f"Auto-tuned batch size to {tuned_batch_size}")

    def _validate(self) -> None:
        """Ensures all configuration parameters are valid."""
        # FFT size must be a positive power of 2
        if self.fft_size <= 0 or (self.fft_size & (self.fft_size - 1)) != 0:
            raise ValueError(f"fft_size must be a positive power of 2, but got {self.fft_size}")

        # Batch size, if specified, must be a positive even number
        if self.batch_size is not None:
            if self.batch_size <= 0 or self.batch_size % 2 != 0:
                raise ValueError(
                    "batch_size must be a positive, even number for dual-channel processing, "
                    f"but got {self.batch_size}"
                )

        # Type hints with Literal handle window and output_type validation for static analysis,
        # but a runtime check is still good practice.
        if self.window not in WindowFunction.__args__:
             raise ValueError(f"Unsupported window function: '{self.window}'")
        if self.output_type not in OutputType.__args__:
             raise ValueError(f"Unsupported output type: '{self.output_type}'")

    def get_engine_params(self) -> Dict[str, Any]:
        """
        Formats the configuration into a dictionary suitable for the C++ engine.

        Returns:
            A dictionary with keys 'nfft', 'batch', and 'use_graphs'.
        """
        return {
            'nfft': self.fft_size,
            'batch': self.batch_size,
            'use_graphs': self.use_graphs,
        }

    def _auto_tune_batch_size(self) -> int:
        """
        Selects an optimal batch size based on GPU memory and FFT size.

        Uses pynvml for direct queries if available, otherwise falls back to a
        heuristic based on FFT size.
        """
        if PYNVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                # Assuming device 0, can be made configurable via RuntimeConfig
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                gpu_memory_bytes = mem_info.free
                pynvml.nvmlShutdown()

                # Heuristic: Aim to use ~10% of free GPU memory for FFT buffers.
                # Memory per FFT (approx): input(N*4) + output_complex((N/2+1)*8)
                bytes_per_fft = self.fft_size * 4 + (self.fft_size // 2 + 1) * 8
                max_batch = int((gpu_memory_bytes * 0.1) / bytes_per_fft)

                # Round down to the nearest power of 2, ensuring it's at least 2
                if max_batch > 1:
                    batch = 1 << (max_batch.bit_length() - 1)
                    return min(batch, 256) # Clamp to a reasonable maximum
                return 2 # Minimum valid batch size
            except Exception as e:
                logging.warning(f"Failed to query GPU memory with pynvml: {e}. "
                                "Falling back to heuristic.")

        # Fallback heuristic if pynvml is not available or fails
        if self.fft_size <= 2048:
            return 64
        elif self.fft_size <= 4096:
            return 32
        elif self.fft_size <= 8192:
            return 16
        else:
            return 8

