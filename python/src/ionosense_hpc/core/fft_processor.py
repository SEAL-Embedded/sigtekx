from __future__ import annotations
from typing import Optional, Union
import threading
import numpy as np
from numpy.typing import NDArray

from .pipelines import Pipeline, PipelineBuilder
from .config import FFTConfig
from .exceptions import ConfigurationError, StateError
from ..utils.signals import create_window


# Type alias for readability
FFTArray = NDArray[np.float32]


class FFTProcessor:
    """
    Synchronous FFT processor with automatic stream management.

    This class provides the simplest API for GPU-accelerated FFT processing,
    handling all buffer management and synchronization internally.
    """

    __slots__ = (
        "fft_size",
        "batch_size",
        "_current_stream",
        "_lock",
        "_window_data",
        "_pipeline",
    )

    def __init__(
        self,
        fft_size: int = 4096,
        batch_size: int = 2,
        window: Optional[Union[str, FFTArray]] = None,
        num_streams: int = 3,
        enable_profiling: bool = True,
    ):
        """
        Initialize the FFT processor.
        """
        self.fft_size = int(fft_size)
        self.batch_size = int(batch_size)
        self._current_stream = 0
        self._lock = threading.Lock()
        self._window_data: Optional[FFTArray] = None

        self._pipeline: Pipeline = (
            PipelineBuilder()
            .with_fft(self.fft_size, self.batch_size)
            .with_streams(num_streams)
            .with_profiling(enable_profiling)
            .build()
        )
        
        if isinstance(window, str):
            self._window_data = create_window(window, self.fft_size)
            self._pipeline.set_window(self._window_data)
        elif isinstance(window, np.ndarray):
            self._window_data = window.astype(np.float32)
            self._pipeline.set_window(self._window_data)
        
        self._pipeline.prepare()

    def process(self, *inputs: FFTArray) -> FFTArray:
        """
        Process time-domain signals by validating them and delegating to process_batch.
        """
        if len(inputs) != self.batch_size:
            raise ValueError(f"Expected {self.batch_size} inputs, got {len(inputs)}")

        for i, arr in enumerate(inputs):
            if arr.shape != (self.fft_size,):
                raise ValueError(
                    f"Input {i} has shape {arr.shape}, expected ({self.fft_size},)"
                )

        input_batch = np.stack(inputs)
        return self.process_batch(input_batch)

    def process_batch(self, data: FFTArray) -> FFTArray:
        """
        Process a pre-made batch of signals. This is the primary processing method.
        """
        if data.shape != (self.batch_size, self.fft_size):
            raise ValueError(
                f"Expected shape ({self.batch_size}, {self.fft_size}), got {data.shape}"
            )

        processed_data = np.ascontiguousarray(data, dtype=np.float32)

        with self._lock:
            stream_idx = self._current_stream
            self._current_stream = (self._current_stream + 1) % self._pipeline.num_streams

        input_buffer = self._pipeline.get_input_buffer(stream_idx)
        
        # --- THE FINAL, DEFINITIVE FIX ---
        # The previous slice-based copy was causing memory corruption due to
        # broadcasting issues with the pybind11 buffer view. A manual, row-by-row
        # copy is safer and guarantees correctness.
        for i in range(self.batch_size):
            input_buffer[i, :self.fft_size] = processed_data[i]
        # ---------------------------------

        self._pipeline.execute_async(stream_idx)
        self._pipeline.sync_stream(stream_idx)

        return self._pipeline.get_output_buffer(stream_idx).copy()

    def set_window(self, window: Union[str, FFTArray]) -> None:
        """
        Set or change the window function used for processing.
        """
        if isinstance(window, str):
            self._window_data = create_window(window, self.fft_size)
        else:
            window_array = np.asarray(window, dtype=np.float32)
            if window_array.shape != (self.fft_size,):
                raise ValueError(f"Window shape {window_array.shape} != ({self.fft_size},)")
            self._window_data = np.ascontiguousarray(window_array)
        
        if self._window_data is not None:
            self._pipeline.set_window(self._window_data)

    @property
    def stats(self):
        """Performance statistics object exposed by the underlying pipeline."""
        return self._pipeline.stats

    def reset_stats(self) -> None:
        """Reset performance statistics."""
        self._pipeline.reset_stats()

    @property
    def num_streams(self) -> int:
        """Number of processing streams."""
        return self._pipeline.num_streams

    @property
    def bins(self) -> int:
        """Number of frequency bins in the output."""
        return self.fft_size // 2 + 1

    def __repr__(self) -> str:
        return (
            f"FFTProcessor(fft_size={self.fft_size}, "
            f"batch_size={self.batch_size}, "
            f"num_streams={self.num_streams})"
        )

