"""Pydantic v2 configuration schemas for the engine."""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing_extensions import Self


class EngineConfig(BaseModel):
    """Configuration for the signal processing engine.
    
    This class validates all parameters and provides sensible defaults
    for real-time dual-channel ULF/VLF signal processing.
    """
    
    # Signal parameters
    nfft: int = Field(
        default=1024,
        gt=0,
        description="FFT size (must be power of 2)"
    )
    batch: int = Field(
        default=2,
        gt=0,
        description="Number of channels (2 for dual-antenna)"
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
        description="Input sample rate in Hz"
    )
    
    # Execution parameters
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
        description="Number of pinned buffers for double-buffering"
    )
    warmup_iters: int = Field(
        default=1,
        ge=0,
        description="Warmup iterations to stabilize GPU clocks"
    )
    timeout_ms: int = Field(
        default=1000,
        gt=0,
        description="Timeout for async operations in milliseconds"
    )
    
    # Performance tuning
    use_cuda_graphs: bool = Field(
        default=False,
        description="Enable CUDA Graphs (future feature)"
    )
    enable_profiling: bool = Field(
        default=False,
        description="Enable internal profiling metrics"
    )

    # --- Model Configuration (Pydantic V2+ Standard) ---
    model_config = ConfigDict(
        validate_assignment=True,
        use_enum_values=True
    )
    
    @field_validator('nfft')
    @classmethod
    def validate_power_of_two(cls, v: int) -> int:
        """Ensure nfft is a power of 2."""
        if v & (v - 1) != 0:
            raise ValueError(f"nfft must be a power of 2, got {v}")
        return v
    
    @model_validator(mode='after')
    def validate_memory_requirements(self) -> Self:
        """Check that configuration won't exceed reasonable memory limits."""
        bytes_per_buffer = self.nfft * self.batch * 4  # float32
        total_bytes = bytes_per_buffer * self.pinned_buffer_count * 3  # input, output, intermediate
        
        # Lowered threshold to align with test case expectations
        if total_bytes > 256 * 1024**2:  # 256MB warning threshold
            import warnings
            warnings.warn(
                f"Configuration requires ~{total_bytes/(1024**2):.1f}MB device memory",
                ResourceWarning
            )
        return self
    
    @property
    def hop_size(self) -> int:
        """Calculate hop size between frames."""
        return int(self.nfft * (1.0 - self.overlap))
    
    @property
    def num_output_bins(self) -> int:
        """Number of frequency bins in R2C FFT output."""
        return self.nfft // 2 + 1
    
    @property
    def frame_duration_ms(self) -> float:
        """Duration of one FFT frame in milliseconds."""
        return (self.nfft / self.sample_rate_hz) * 1000
    
    @property
    def hop_duration_ms(self) -> float:
        """Duration between frame starts in milliseconds."""
        return (self.hop_size / self.sample_rate_hz) * 1000
    
    def __repr__(self) -> str:
        return (
            f"<EngineConfig nfft={self.nfft} batch={self.batch} "
            f"overlap={self.overlap:.1%} fs={self.sample_rate_hz}Hz>"
        )
