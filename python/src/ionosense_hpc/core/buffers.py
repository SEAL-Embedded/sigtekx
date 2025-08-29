# python/src/ionosense_hpc/core/buffers.py
"""
Buffer management with safety guarantees for zero-copy data transfer.
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Generator

import numpy as np
from numpy.typing import NDArray

log = logging.getLogger(__name__)


class ManagedBuffer:
    """
    A thread-safe wrapper around a NumPy view of a CUDA pinned memory buffer.

    This class ensures that only one thread can access the underlying memory
    at a time, preventing data corruption in multi-threaded scenarios. It uses a
    context manager for safe, exception-proof access.
    """
    def __init__(self,
                 view: NDArray[np.float32],
                 stream_id: int,
                 name: str):
        """
        Initializes the managed buffer.

        Args:
            view: A NumPy array that is a view onto the pinned memory.
            stream_id: The CUDA stream this buffer is associated with.
            name: A descriptive name for logging and debugging.
        """
        self._view = view
        self._stream_id = stream_id
        self._name = name
        self._lock = threading.Lock()

    @property
    def stream_id(self) -> int:
        """The CUDA stream ID associated with this buffer."""
        return self._stream_id

    @property
    def shape(self) -> tuple[int, ...]:
        """The shape of the buffer."""
        return self._view.shape

    @property
    def dtype(self) -> np.dtype:
        """The data type of the buffer."""
        return self._view.dtype

    @property
    def nbytes(self) -> int:
        """The total size of the buffer in bytes."""
        return self._view.nbytes

    @contextmanager
    def use(self) -> Generator[NDArray[np.float32], None, None]:
        """
        Provides exclusive, thread-safe access to the buffer via a context manager.

        Example:
            with managed_buffer.use() as buf:
                # `buf` is the NumPy array, guaranteed to be safe from races
                np.copyto(buf, user_data)
        """
        log.debug("Acquiring lock for buffer '%s'...", self._name)
        self._lock.acquire()
        try:
            yield self._view
        finally:
            log.debug("Releasing lock for buffer '%s'.", self._name)
            self._lock.release()


class BufferPool:
    """
    A container for managing input and output buffers for multiple CUDA streams.

    This class acts as a central registry for the memory buffers exposed by the
    C++ RtFftEngine.
    """
    def __init__(self, num_streams: int):
        """
        Initializes the buffer pool.

        Args:
            num_streams: The number of concurrent streams the pool will manage.
        """
        if num_streams <= 0:
            raise ValueError("Number of streams must be positive.")
        self.num_streams = num_streams
        self._input_buffers: dict[int, ManagedBuffer] = {}
        self._output_buffers: dict[int, ManagedBuffer] = {}

    def register_input_buffer(self, stream_id: int, view: NDArray[np.float32]):
        """Registers the pinned input buffer for a given stream."""
        if not 0 <= stream_id < self.num_streams:
            raise IndexError(f"Stream ID {stream_id} is out of valid range [0, {self.num_streams-1}]")
        self._input_buffers[stream_id] = ManagedBuffer(
            view=view,
            stream_id=stream_id,
            name=f"input_stream_{stream_id}"
        )
        log.info("Registered input buffer for stream %d with shape %s", stream_id, view.shape)

    def register_output_buffer(self, stream_id: int, view: NDArray[np.float32]):
        """Registers the pinned output buffer for a given stream."""
        if not 0 <= stream_id < self.num_streams:
            raise IndexError(f"Stream ID {stream_id} is out of valid range [0, {self.num_streams-1}]")
        self._output_buffers[stream_id] = ManagedBuffer(
            view=view,
            stream_id=stream_id,
            name=f"output_stream_{stream_id}"
        )
        log.info("Registered output buffer for stream %d with shape %s", stream_id, view.shape)

    def get_input_buffer(self, stream_id: int) -> ManagedBuffer:
        """Retrieves the managed input buffer for a given stream."""
        if stream_id not in self._input_buffers:
            raise KeyError(f"No input buffer registered for stream ID {stream_id}")
        return self._input_buffers[stream_id]

    def get_output_buffer(self, stream_id: int) -> ManagedBuffer:
        """Retrieves the managed output buffer for a given stream."""
        if stream_id not in self._output_buffers:
            raise KeyError(f"No output buffer registered for stream ID {stream_id}")
        return self._output_buffers[stream_id]
