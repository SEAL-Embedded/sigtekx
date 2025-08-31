"""
ionosense_hpc.core.config: Configuration dataclasses with validation.

Provides type-safe configuration objects that map directly to the C++
configuration structures, with Python-side validation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from ..utils.validation import validate_fft_size
from .exceptions import ConfigurationError

# Import C++ config classes
try:
    from . import _engine
except ImportError:
    _engine = None  # Allow module to load for docs


@dataclass
class FFTConfig:
    """
    Configuration for FFT processing stage.
    
    Attributes:
        nfft: FFT size, must be power of 2 (e.g., 4096).
        batch_size: Number of signals to process in parallel.
        verbose: Enable verbose output.
    """
    nfft: int = 4096
    batch_size: int = 2
    verbose: bool = False
    
    def __post_init__(self):
        """Validate configuration on creation."""
        if not validate_fft_size(self.nfft):
            raise ConfigurationError(
                f"FFT size must be a positive power of 2, got {self.nfft}"
            )
        if self.batch_size < 1:
            raise ConfigurationError(
                f"Batch size must be at least 1, got {self.batch_size}"
            )
    
    def to_cpp_config(self):
        """Convert to C++ ProcessingConfig."""
        if _engine is None:
            raise ImportError("C++ engine not available")
        
        cfg = _engine.ProcessingConfig()
        cfg.nfft = self.nfft
        cfg.batch_size = self.batch_size
        cfg.verbose = self.verbose
        return cfg


@dataclass
class PipelineConfig:
    """
    Complete pipeline configuration.
    
    Attributes:
        num_streams: Number of CUDA streams (1-16).
        use_graphs: Enable CUDA graphs for lower latency.
        enable_profiling: Enable performance profiling.
        verbose: Enable verbose output.
        stage_config: Configuration for the processing stage.
    """
    num_streams: int = 3
    use_graphs: bool = True
    enable_profiling: bool = True
    verbose: bool = False
    stage_config: FFTConfig = field(default_factory=FFTConfig)
    
    def __post_init__(self):
        """Validate configuration."""
        if not 1 <= self.num_streams <= 16:
            raise ConfigurationError(
                f"Number of streams must be 1-16, got {self.num_streams}"
            )
        
        # Ensure stage_config is valid
        if not isinstance(self.stage_config, FFTConfig):
            self.stage_config = FFTConfig(**self.stage_config)
    
    def to_cpp_config(self):
        """Convert to C++ PipelineConfig."""
        if _engine is None:
            raise ImportError("C++ engine not available")
        
        cfg = _engine.PipelineConfig()
        cfg.num_streams = self.num_streams
        cfg.use_graphs = self.use_graphs
        cfg.enable_profiling = self.enable_profiling
        cfg.verbose = self.verbose
        cfg.stage_config = self.stage_config.to_cpp_config()
        return cfg


@dataclass
class BenchmarkConfig:
    """
    Configuration for benchmarking runs.
    
    Attributes:
        warmup_iterations: Number of warmup iterations.
        measure_iterations: Number of measured iterations.
        report_percentiles: Percentiles to report (e.g., [50, 95, 99]).
        save_raw_timings: Whether to save all individual timings.
    """
    warmup_iterations: int = 100
    measure_iterations: int = 1000
    report_percentiles: list[float] = field(
        default_factory=lambda: [50.0, 95.0, 99.0, 99.9]
    )
    save_raw_timings: bool = False
    
    def __post_init__(self):
        """Validate benchmark configuration."""
        if self.warmup_iterations < 0:
            raise ConfigurationError("Warmup iterations must be non-negative")
        if self.measure_iterations < 1:
            raise ConfigurationError("Must have at least 1 measurement iteration")