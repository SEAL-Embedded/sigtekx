"""
Unified configuration schema for the Ionosense HPC engine.

This module defines a single, cohesive EngineConfig that covers all aspects
of signal processing configuration: signal parameters, pipeline parameters,
execution parameters, and performance tuning.

Following API design best practices:
- Single configuration class (no multiple competing config types)
- Sensible defaults for common use cases
- Explicit configuration over implicit behavior
- Validation at construction time
"""

from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ============================================================================
# Enumerations (matching C++ enums)
# ============================================================================

class WindowType(str, Enum):
    """Window function types for spectral analysis."""
    RECTANGULAR = 'rectangular'
    HANN = 'hann'
    BLACKMAN = 'blackman'


class WindowSymmetry(str, Enum):
    """Window symmetry modes controlling endpoint behavior."""
    PERIODIC = 'periodic'    # For FFT processing (denominator N)
    SYMMETRIC = 'symmetric'  # For time-domain analysis (denominator N-1)


class WindowNorm(str, Enum):
    """Window normalization schemes."""
    UNITY = 'unity'  # Normalize to unity power/energy gain
    SQRT = 'sqrt'    # Apply square root normalization


class ScalePolicy(str, Enum):
    """FFT output scaling policies."""
    NONE = 'none'
    ONE_OVER_N = '1/N'
    ONE_OVER_SQRT_N = '1/sqrt(N)'


class OutputMode(str, Enum):
    """Pipeline output format."""
    MAGNITUDE = 'magnitude'
    COMPLEX = 'complex'


class ExecutionMode(str, Enum):
    """Execution strategy for the engine."""
    BATCH = 'batch'         # Maximum throughput batch processing
    STREAMING = 'streaming'  # Low-latency streaming with ring buffer


# ============================================================================
# Unified Engine Configuration
# ============================================================================

class EngineConfig(BaseModel):
    """Unified configuration for the Ionosense HPC signal processing engine.

    This single configuration class handles all aspects of engine behavior:
    - Signal parameters (nfft, channels, overlap, sample rate)
    - Pipeline parameters (window type, FFT scaling, output mode)
    - Execution parameters (mode, streams, buffers, device)
    - Performance tuning (warmup, profiling)

    Design Philosophy:
    - Sensible defaults for common cases
    - Explicit over implicit
    - One configuration to rule them all

    Examples:
        # Default configuration (works immediately)
        >>> config = EngineConfig()

        # Quick parameter overrides
        >>> config = EngineConfig(nfft=4096, channels=8, overlap=0.75)

        # Full custom configuration
        >>> config = EngineConfig(
        ...     nfft=8192,
        ...     channels=16,
        ...     overlap=0.9,
        ...     window=WindowType.BLACKMAN,
        ...     window_symmetry=WindowSymmetry.PERIODIC,
        ...     mode=ExecutionMode.BATCH
        ... )

        # From preset (using class method)
        >>> config = EngineConfig.from_preset('iono')
    """

    # ========================================================================
    # Signal Parameters
    # ========================================================================

    nfft: int = Field(
        default=1024,
        gt=0,
        description="FFT size (must be a power of 2)"
    )

    channels: int = Field(
        default=2, gt=0, description="Number of independent signal channels to process"
    )

    overlap: float = Field(
        default=0.5,
        ge=0.0,
        lt=1.0,
        description="Frame overlap factor [0.0, 1.0)"
    )

    sample_rate_hz: int = Field(
        default=48000,
        gt=0,
        description="Input signal sample rate in Hz"
    )

    # ========================================================================
    # Pipeline Parameters
    # ========================================================================

    window: WindowType = Field(
        default=WindowType.HANN,
        description="Window function type"
    )

    window_symmetry: WindowSymmetry = Field(
        default=WindowSymmetry.PERIODIC,
        description="Window symmetry mode (PERIODIC for FFT)"
    )

    window_norm: WindowNorm = Field(
        default=WindowNorm.UNITY,
        description="Window normalization scheme"
    )

    scale: ScalePolicy = Field(
        default=ScalePolicy.ONE_OVER_N,
        description="FFT output scaling policy"
    )

    output: OutputMode = Field(
        default=OutputMode.MAGNITUDE,
        description="Pipeline output format"
    )

    # ========================================================================
    # Execution Parameters
    # ========================================================================

    mode: ExecutionMode = Field(
        default=ExecutionMode.BATCH,
        description="Execution strategy"
    )

    stream_count: int = Field(
        default=3,
        gt=0,
        le=32,
        description="Number of CUDA streams for pipelining"
    )

    pinned_buffer_count: int = Field(
        default=2,
        ge=2,
        le=8,
        description="Number of pinned memory buffers (min 2 for double buffering)"
    )

    device_id: int = Field(
        default=-1,
        description="CUDA device ID (-1 for auto-select)"
    )

    # ========================================================================
    # Performance Parameters
    # ========================================================================

    warmup_iters: int = Field(
        default=1,
        ge=0,
        description="Number of warmup iterations to stabilize performance"
    )

    timeout_ms: int = Field(
        default=1000,
        gt=0,
        description="Timeout for operations in milliseconds"
    )

    use_cuda_graphs: bool = Field(
        default=False,
        description="Enable CUDA graphs for optimized execution"
    )

    enable_profiling: bool = Field(
        default=False,
        description="Enable internal profiling and metrics collection"
    )

    # ========================================================================
    # Pydantic Configuration
    # ========================================================================

    model_config = ConfigDict(
        validate_assignment=True,
        use_enum_values=False,  # Keep enum objects, not string values
        extra='forbid'  # Catch typos in parameter names
    )

    # ========================================================================
    # Validation
    # ========================================================================

    @field_validator('nfft')
    @classmethod
    def validate_power_of_two(cls, v: int) -> int:
        """Ensures nfft is a power of 2."""
        if v & (v - 1) != 0:
            raise ValueError(f"nfft must be a power of 2, got {v}")
        return v

    @model_validator(mode='after')
    def validate_memory_requirements(self) -> Self:
        """Warns if configuration may exceed typical memory constraints."""
        import warnings

        bytes_per_input_buffer = self.nfft * self.channels * 4  # float32
        bytes_per_output_buffer = self.num_output_bins * self.channels * 4
        total_bytes = (bytes_per_input_buffer + bytes_per_output_buffer) * self.pinned_buffer_count * 3

        if total_bytes > 256 * 1024**2:  # 256MB warning threshold
            warnings.warn(
                f"Configuration requires ~{total_bytes / (1024**2):.1f}MB device memory",
                ResourceWarning,
                stacklevel=3
            )
        return self

    # ========================================================================
    # Computed Properties
    # ========================================================================

    @property
    def hop_size(self) -> int:
        """Number of samples between consecutive frame starts."""
        return int(self.nfft * (1.0 - self.overlap))

    @property
    def num_output_bins(self) -> int:
        """Number of frequency bins in one-sided (real) FFT output."""
        return self.nfft // 2 + 1

    @property
    def frame_duration_ms(self) -> float:
        """Duration of one FFT frame in milliseconds."""
        return (self.nfft / self.sample_rate_hz) * 1000

    @property
    def hop_duration_ms(self) -> float:
        """Time between consecutive frames in milliseconds."""
        return (self.hop_size / self.sample_rate_hz) * 1000

    @property
    def effective_fps(self) -> float:
        """Effective frames per second based on hop size."""
        return self.sample_rate_hz / self.hop_size if self.hop_size > 0 else 0

    @property
    def memory_estimate_mb(self) -> float:
        """Estimated GPU memory usage in MB (rough estimate)."""
        bytes_per_input = self.nfft * self.channels * 4
        bytes_per_output = self.num_output_bins * self.channels * 4
        total_bytes = (bytes_per_input + bytes_per_output) * self.pinned_buffer_count * 4
        return total_bytes / (1024 * 1024)

    # ========================================================================
    # Preset Factory
    # ========================================================================

    @classmethod
    def from_preset(cls, name: str, mode: ExecutionMode | str | None = None, **overrides: Any) -> 'EngineConfig':
        """Create configuration from a named preset.

        Args:
            name: Preset name ('default', 'iono', 'ionox')
            mode: Optional execution mode override
            **overrides: Additional parameter overrides

        Returns:
            EngineConfig with preset parameters applied

        Examples:
            >>> config = EngineConfig.from_preset('iono')
            >>> config = EngineConfig.from_preset('iono', mode='streaming')
            >>> config = EngineConfig.from_preset('iono', nfft=8192, overlap=0.875)
        """
        from .config_presets import get_preset

        # Determine executor variant based on mode
        executor = 'batch'  # default
        if mode is not None:
            if isinstance(mode, str):
                mode = ExecutionMode(mode)
            # Map ExecutionMode to executor string for get_preset
            executor = 'streaming' if mode == ExecutionMode.STREAMING else 'batch'

        config = get_preset(name, executor=executor)

        # Apply mode override (to ensure mode field is set correctly)
        if mode is not None:
            config = _apply_mode_overrides(config, mode)

        # Apply additional overrides
        if overrides:
            config = config.model_copy(update=overrides)

        return config

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Export configuration as dictionary."""
        return self.model_dump()

    def __repr__(self) -> str:
        """Concise string representation."""
        return (
            f"<EngineConfig nfft={self.nfft} channels={self.channels} "
            f"overlap={self.overlap:.1%} mode={self.mode.value}>"
        )


# ============================================================================
# Mode Override Logic (Internal)
# ============================================================================

def _apply_mode_overrides(config: EngineConfig, mode: ExecutionMode) -> EngineConfig:
    """Apply mode-specific configuration overrides.

    Different execution modes have different optimal buffer/stream configurations.
    """
    overrides = {}

    if mode == ExecutionMode.STREAMING:
        # Streaming: Minimize latency, reduce channels, more streams
        overrides['stream_count'] = 6
        overrides['pinned_buffer_count'] = 4
        overrides['channels'] = max(2, config.channels // 2)  # Reduce channels for lower latency
    elif mode == ExecutionMode.BATCH:
        # Batch: Maximize throughput, use more buffers
        overrides['stream_count'] = 4
        overrides['pinned_buffer_count'] = 4

    overrides['mode'] = mode  # type: ignore[assignment]
    return config.model_copy(update=overrides)

