"""Pydantic v2 configuration schemas for the engine.

This module defines `EngineConfig`, the core data structure for all engine
parameters. It uses Pydantic for robust validation, type safety, and
serialization, which is essential for research reproducibility.
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EngineConfig(BaseModel):
    """Configuration schema for the CUDA FFT signal processing engine.

    This class defines and validates all engine parameters, providing type safety,
    constraint checking, and computed properties for derived values. EngineConfig
    objects are immutable after creation and can be safely shared across threads.
    """

    # =====================================================================
    # SIGNAL PARAMETERS
    # =====================================================================
    nfft: int = Field(
        default=1024,
        gt=0,
        description="FFT size (must be a power of 2)."
    )

    batch: int = Field(
        default=2,
        gt=0,
        description="Number of parallel FFT channels to process simultaneously."
    )

    overlap: float = Field(
        default=0.5,
        ge=0.0,
        lt=1.0,
        description="Frame overlap factor [0.0, 1.0)."
    )

    sample_rate_hz: int = Field(
        default=48000,
        gt=0,
        description="Input signal sample rate in Hz."
    )

    # =====================================================================
    # EXECUTION PARAMETERS
    # =====================================================================
    stream_count: int = Field(
        default=3,
        gt=0,
        le=32,
        description="Number of CUDA streams for pipeline parallelism."
    )

    pinned_buffer_count: int = Field(
        default=2,
        ge=2,
        le=8,
        description="Number of pinned memory buffers (min 2 for double buffering)."
    )

    warmup_iters: int = Field(
        default=1,
        ge=0,
        description="Number of warmup iterations to stabilize GPU performance."
    )

    timeout_ms: int = Field(
        default=1000,
        gt=0,
        description="Timeout for asynchronous operations in milliseconds."
    )

    # =====================================================================
    # PERFORMANCE PARAMETERS
    # =====================================================================
    use_cuda_graphs: bool = Field(
        default=False,
        description="Enable CUDA Graphs optimization (future feature)."
    )

    enable_profiling: bool = Field(
        default=False,
        description="Enable internal profiling and performance metrics collection."
    )

    # =====================================================================
    # PYDANTIC V2 MODEL CONFIGURATION
    # =====================================================================
    model_config = ConfigDict(
        validate_assignment=True,
        use_enum_values=True
    )

    @field_validator('nfft')
    @classmethod
    def validate_power_of_two(cls, v: int) -> int:
        """Ensures nfft is a power of 2."""
        if v & (v - 1) != 0:
            raise ValueError(f"nfft must be a power of 2, got {v}")
        return v

    @model_validator(mode='after')
    def validate_memory_requirements(self) -> Self:
        """Warns if the configuration is likely to exceed memory constraints."""
        bytes_per_input_buffer = self.nfft * self.batch * 4
        bytes_per_output_buffer = self.num_output_bins * self.batch * 4
        total_bytes = (bytes_per_input_buffer + bytes_per_output_buffer) * self.pinned_buffer_count * 3

        if total_bytes > 256 * 1024**2:  # 256MB warning threshold
            import warnings
            warnings.warn(
                f"Configuration requires ~{total_bytes / (1024**2):.1f}MB device memory",
                ResourceWarning,
                stacklevel=2
            )
        return self

    # =====================================================================
    # COMPUTED PROPERTIES
    # =====================================================================
    @property
    def hop_size(self) -> int:
        """The number of samples between consecutive frame starts."""
        return int(self.nfft * (1.0 - self.overlap))

    @property
    def num_output_bins(self) -> int:
        """The number of frequency bins in the one-sided (real) FFT output."""
        return self.nfft // 2 + 1

    @property
    def frame_duration_ms(self) -> float:
        """The duration of one FFT frame in milliseconds."""
        return (self.nfft / self.sample_rate_hz) * 1000

    @property
    def hop_duration_ms(self) -> float:
        """The time between the start of consecutive frames in milliseconds."""
        return (self.hop_size / self.sample_rate_hz) * 1000

    def __repr__(self) -> str:
        """Returns a concise string representation of the configuration."""
        return (
            f"<EngineConfig nfft={self.nfft} batch={self.batch} "
            f"overlap={self.overlap:.1%} fs={self.sample_rate_hz}Hz>"
        )
