"""
ionosense_hpc.core: Core processing engine and pipeline components.
"""

# Import order matters for C++ dependencies
from .exceptions import (
    IonosphereError,
    ConfigurationError,
    CudaError,
    StateError,
    NumericalError,
    translate_cpp_exception
)

from .config import (
    FFTConfig,
    PipelineConfig,
    BenchmarkConfig
)

from .profiling import (
    PipelineStats,
    nvtx_range,
    time_section,
    PerformanceMonitor
)

from .pipelines import (
    Pipeline,
    PipelineBuilder
)

from .fft_processor import FFTProcessor

__all__ = [
    # Exceptions
    'IonosphereError',
    'ConfigurationError',
    'CudaError',
    'StateError',
    'NumericalError',
    'translate_cpp_exception',
    # Config
    'FFTConfig',
    'PipelineConfig',
    'BenchmarkConfig',
    # Profiling
    'PipelineStats',
    'nvtx_range',
    'time_section',
    'PerformanceMonitor',
    # Pipeline
    'Pipeline',
    'PipelineBuilder',
    # Processor
    'FFTProcessor',
]