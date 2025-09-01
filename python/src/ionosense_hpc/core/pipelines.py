"""
ionosense_hpc.core.pipelines: Direct wrapper for C++ PipelineEngine.

Provides Python access to the high-performance pipeline with multi-stream
execution and profiling capabilities. This version does not use CUDA graphs.
"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING
import numpy as np
from numpy.typing import NDArray

from .config import PipelineConfig, FFTConfig
from .exceptions import translate_cpp_exception, StateError, ConfigurationError

if TYPE_CHECKING:
    from .profiling import PipelineStats

try:
    from . import _engine
except ImportError as e:
    raise ImportError(
        "Failed to import compiled _engine module. "
        "Ensure the library was built with: ./scripts/cli.sh build"
    ) from e


class Pipeline:
    """
    High-performance asynchronous FFT pipeline with multi-stream execution.
    
    This class wraps the C++ PipelineEngine, providing zero-copy buffer access
    and full control over async execution.
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        Initialize the pipeline with the given configuration.
        
        Args:
            config: Pipeline configuration. If None, uses defaults.
        """
        if config is None:
            config = PipelineConfig()
        
        # Build the C++ engine
        builder = _engine.PipelineBuilder()
        builder.with_streams(config.num_streams)
        builder.with_profiling(config.enable_profiling)
        
        # Configure the stage (currently only FFT supported)
        if isinstance(config.stage_config, FFTConfig):
            builder.with_fft(config.stage_config.nfft, config.stage_config.batch_size)
        else:
            raise ConfigurationError("Only FFT processing stage currently supported")
        
        try:
            self._engine = builder.build()
            self._config = config
        except Exception as e:
            raise translate_cpp_exception(e)
    
    def set_window(self, window_coeffs: NDArray[np.float32]) -> None:
        self._engine.set_window(np.ascontiguousarray(window_coeffs, dtype=np.float32))

    
    def prepare(self) -> None:
        """
        Prepare the pipeline for execution.
        
        This performs warm-up runs. Must be called before any execute operations.
        
        Raises:
            StateError: If already prepared.
        """
        try:
            self._engine.prepare()
        except Exception as e:
            raise translate_cpp_exception(e)
    
    def execute_async(self, stream_idx: Optional[int] = None) -> int:
        """
        Execute the pipeline asynchronously on the specified stream.
        
        Args:
            stream_idx: Stream index (0 to num_streams-1). If None, 
                       uses round-robin scheduling.
        
        Returns:
            The stream index that was used.
        
        Raises:
            StateError: If pipeline not prepared.
            ValueError: If stream_idx is out of range.
        """
        try:
            if stream_idx is None:
                return self._engine.execute_async()
            else:
                self._engine.execute_async(stream_idx)
                return stream_idx
        except Exception as e:
            raise translate_cpp_exception(e)
    
    def sync_stream(self, stream_idx: int) -> None:
        """
        Wait for a specific stream to complete execution.
        
        Args:
            stream_idx: The stream index to synchronize.
        
        Raises:
            ValueError: If stream_idx is out of range.
        """
        try:
            self._engine.sync_stream(stream_idx)
        except Exception as e:
            raise translate_cpp_exception(e)
    
    def synchronize_all(self) -> None:
        """Wait for all streams to complete."""
        try:
            self._engine.synchronize_all()
        except Exception as e:
            raise translate_cpp_exception(e)
    
    def get_input_buffer(self, stream_idx: int) -> NDArray[np.float32]:
        """
        Get a zero-copy view of the pinned input buffer for a stream.
        
        Args:
            stream_idx: The stream index.
        
        Returns:
            A NumPy array view of shape (batch_size, nfft).
        """
        try:
            return self._engine.get_input_buffer(stream_idx)
        except Exception as e:
            raise translate_cpp_exception(e)
    
    def get_output_buffer(self, stream_idx: int) -> NDArray[np.float32]:
        """
        Get a zero-copy view of the pinned output buffer for a stream.
        
        Args:
            stream_idx: The stream index.
        
        Returns:
            A NumPy array view of shape (batch_size, nfft/2+1).
        """
        try:
            return self._engine.get_output_buffer(stream_idx)
        except Exception as e:
            raise translate_cpp_exception(e)
    
    @property
    def stats(self) -> PipelineStats:
        """Get performance statistics."""
        from .profiling import PipelineStats
        return PipelineStats._from_cpp(self._engine.stats)
    
    def reset_stats(self) -> None:
        """Reset performance statistics."""
        self._engine.reset_stats()
    
    @property
    def is_prepared(self) -> bool:
        """Check if the pipeline is prepared for execution."""
        return self._engine.is_prepared
    
    @property
    def num_streams(self) -> int:
        """Get the number of streams."""
        return self._config.num_streams


class PipelineBuilder:
    """
    Builder pattern for constructing Pipeline instances.
    
    Provides a fluent interface for configuring pipelines.
    """
    
    def __init__(self):
        """Initialize with default configuration."""
        self._config = PipelineConfig()
    
    def with_streams(self, num_streams: int) -> PipelineBuilder:
        """Set the number of CUDA streams."""
        if not 1 <= num_streams <= 16:
            raise ConfigurationError(f"Number of streams must be 1-16, got {num_streams}")
        self._config.num_streams = num_streams
        return self
    
    def with_profiling(self, enable: bool) -> PipelineBuilder:
        """Enable or disable profiling."""
        self._config.enable_profiling = bool(enable)
        return self
    
    def with_fft(self, size: int, batch: int) -> PipelineBuilder:
        """Configure for FFT processing."""
        self._config.stage_config = FFTConfig(nfft=size, batch_size=batch)
        return self
    
    def verbose(self, enable: bool = True) -> PipelineBuilder:
        """Enable verbose output."""
        self._config.verbose = bool(enable)
        return self
    
    def build(self) -> Pipeline:
        """
        Build the configured pipeline.
        
        Returns:
            A new Pipeline instance.
        
        Raises:
            ConfigurationError: If configuration is invalid.
        """
        return Pipeline(self._config)
