"""
The core processing pipeline that orchestrates the C++ FFT engine.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from ._engine import RtFftEngine
from .buffers import BufferPool
from .config import ProcessingConfig

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    """
    Structured output from a single pipeline execution.

    Attributes:
        output: A NumPy array containing the processed data (e.g., magnitude spectra).
        latency_ms: The end-to-end execution time in milliseconds for this batch.
        stream_id: The CUDA stream ID used for this execution.
        metadata: A dictionary of configuration parameters used for this run.
    """
    output: NDArray[np.float32]
    latency_ms: float
    stream_id: int
    metadata: dict[str, Any]


class FFTPipeline:
    """
    Manages the full, high-performance FFT processing pipeline.

    This class is the primary orchestrator. It initializes the C++ engine,
    manages the zero-copy buffer pool, and handles the flow of data to and
    from the GPU.
    """
    def __init__(self, config: ProcessingConfig):
        """
        Initializes the FFT pipeline.

        Args:
            config: A validated ProcessingConfig object.
        """
        self.config = config
        log.info("Initializing FFTPipeline with FFT size %d and batch size %d",
                 config.fft_size, config.batch_size)

        # 1) Initialize the C++ engine
        self.engine = RtFftEngine(**config.get_engine_params())
        log.info("RtFftEngine created with %d streams.", self.engine.num_streams)

        # 2) CRITICAL: Disable CUDA graphs before any further setup
        #    Graphs capture memory state at capture time, incompatible with
        #    Python's runtime modification of pinned memory
        self.engine.use_graphs = False
        log.info("CUDA graphs disabled for Python pipeline compatibility")

        # 3) Window function
        window_map = {
            'hann': np.hanning,
            'hamming': np.hamming,
            'blackman': np.blackman,
            'bartlett': np.bartlett,
            'rectangular': np.ones,
        }
        window_func = window_map[self.config.window]
        window_array = window_func(self.config.fft_size).astype(np.float32)
        self.engine.set_window(window_array)
        log.info("Window function '%s' set on the GPU.", self.config.window)

        # 4) Buffer pool registration (row-major: (batch, fft_size) / (batch, bins))
        self.buffer_pool = BufferPool(self.config.num_streams)
        for i in range(self.config.num_streams):
            self.buffer_pool.register_input_buffer(i, self.engine.pinned_input(i))
            self.buffer_pool.register_output_buffer(i, self.engine.pinned_output(i))

        # 5) Call prepare_for_execution as required by the C++ API
        #    This warms up the streams and performs necessary initialization
        log.info("Preparing engine for execution...")
        self.engine.prepare_for_execution()
        log.info("Engine prepared and ready for processing.")

        self._current_stream = 0

    def process_batch(self, batch_data: NDArray[np.float32]) -> "PipelineResult":
        """
        Process one batch through the GPU pipeline.

        Args:
            batch_data: shape (batch_size, fft_size), dtype float32.

        Returns:
            PipelineResult with output shape (batch_size, fft_size//2 + 1).
        """
        B, N = self.config.batch_size, self.config.fft_size

        # shape + dtype sanity
        if batch_data.shape != (B, N):
            raise ValueError(
                f"Input data has shape {batch_data.shape}, expected {(B, N)}"
            )
        if batch_data.dtype != np.float32:
            batch_data = batch_data.astype(np.float32, copy=False)
        if not batch_data.flags["C_CONTIGUOUS"]:
            batch_data = np.ascontiguousarray(batch_data)

        # round-robin stream
        stream_id = getattr(self, "_current_stream", 0)
        self._current_stream = (stream_id + 1) % self.engine.num_streams

        t0 = time.perf_counter()

        # ---- H->Pinned copy (row-major: (batch, N)) ----
        in_buf = self.buffer_pool.get_input_buffer(stream_id)
        with in_buf.use() as h_in:
            np.copyto(h_in, batch_data)

        # ---- Launch GPU pipeline on this stream ----
        self.engine.execute_async(stream_id)

        # ---- Ensure D2H finished before reading pinned output ----
        self.engine.sync_stream(stream_id)

        # ---- Read pinned output into a fresh NumPy array ----
        out_buf = self.buffer_pool.get_output_buffer(stream_id)
        with out_buf.use() as h_out:
            output_data = h_out.copy()  # (B, N//2 + 1)

        t1 = time.perf_counter()

        return PipelineResult(
            output=output_data,
            latency_ms=(t1 - t0) * 1000.0,
            stream_id=stream_id,
            metadata={
                "fft_size": N,
                "batch_size": B,
                "window": self.config.window,
            },
        )