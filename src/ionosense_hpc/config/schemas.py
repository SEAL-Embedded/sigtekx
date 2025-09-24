"""
Pydantic v2 configuration schemas for the engine with research metadata support.

This module defines configuration structures for both the core engine and
research experiments, providing type safety, validation, and serialization
for reproducible research following RSE/RE standards.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ============================================================================
# Core Engine Configuration
# ============================================================================

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
    # RESEARCH METADATA (NEW)
    # =====================================================================
    experiment_id: str | None = Field(
        default=None,
        description="Unique identifier for research experiment."
    )

    tags: list[str] = Field(
        default_factory=list,
        description="Tags for categorizing configurations."
    )

    notes: str | None = Field(
        default=None,
        description="Free-form notes about this configuration."
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

    @property
    def effective_fps(self) -> float:
        """Effective frames per second based on hop size."""
        return self.sample_rate_hz / self.hop_size if self.hop_size > 0 else 0

    @property
    def memory_estimate_mb(self) -> float:
        """Estimated GPU memory usage in MB."""
        bytes_per_input = self.nfft * self.batch * 4
        bytes_per_output = self.num_output_bins * self.batch * 4
        total_bytes = (bytes_per_input + bytes_per_output) * self.pinned_buffer_count * 3
        return total_bytes / (1024 * 1024)

    def to_experiment_dict(self) -> dict[str, Any]:
        """Export configuration with experiment metadata."""
        base_dict = self.model_dump()
        base_dict['_metadata'] = {
            'exported_at': datetime.now().isoformat(),
            'computed_properties': {
                'hop_size': self.hop_size,
                'num_output_bins': self.num_output_bins,
                'frame_duration_ms': self.frame_duration_ms,
                'hop_duration_ms': self.hop_duration_ms,
                'effective_fps': self.effective_fps,
                'memory_estimate_mb': self.memory_estimate_mb
            }
        }
        return base_dict

    def __repr__(self) -> str:
        """Returns a concise string representation of the configuration."""
        exp_str = f" exp={self.experiment_id}" if self.experiment_id else ""
        return (
            f"<EngineConfig nfft={self.nfft} batch={self.batch} "
            f"overlap={self.overlap:.1%} fs={self.sample_rate_hz}Hz{exp_str}>"
        )


# ============================================================================
# Research Experiment Configuration (NEW)
# ============================================================================

class ExperimentMetadata(BaseModel):
    """Metadata for research experiments ensuring reproducibility."""

    experiment_id: str = Field(
        description="Unique identifier for the experiment."
    )

    name: str = Field(
        description="Human-readable experiment name."
    )

    description: str | None = Field(
        default=None,
        description="Detailed experiment description."
    )

    researcher: str | None = Field(
        default=None,
        description="Name or ID of the researcher."
    )

    project: str | None = Field(
        default=None,
        description="Associated project or grant."
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Experiment creation timestamp."
    )

    tags: list[str] = Field(
        default_factory=list,
        description="Tags for categorization and search."
    )

    standards: list[str] = Field(
        default_factory=lambda: ["RSE", "RE", "IEEE"],
        description="Compliance standards followed."
    )

    version: str = Field(
        default="2.0.0",
        description="Experiment schema version."
    )

    dependencies: dict[str, str] = Field(
        default_factory=dict,
        description="Software dependencies and versions."
    )

    hardware_requirements: dict[str, Any] = Field(
        default_factory=dict,
        description="Required hardware specifications."
    )

    related_experiments: list[str] = Field(
        default_factory=list,
        description="IDs of related experiments."
    )

    publications: list[str] = Field(
        default_factory=list,
        description="Related publications or reports."
    )

    data_sources: list[str] = Field(
        default_factory=list,
        description="Input data sources or datasets."
    )

    model_config = ConfigDict(
        validate_assignment=True
    )


class ResearchConfig(BaseModel):
    """Complete configuration for research experiments."""

    metadata: ExperimentMetadata = Field(
        description="Experiment metadata for reproducibility."
    )

    engine_configs: dict[str, EngineConfig] = Field(
        default_factory=dict,
        description="Named engine configurations for the experiment."
    )

    benchmark_configs: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Benchmark-specific configurations."
    )

    parameter_sweeps: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Parameter sweep specifications."
    )

    output_settings: dict[str, Any] = Field(
        default_factory=lambda: {
            "save_raw_data": True,
            "save_intermediate": True,
            "compression": "gzip",
            "format": "json"
        },
        description="Output and storage settings."
    )

    reproducibility: dict[str, Any] = Field(
        default_factory=lambda: {
            "seed": 42,
            "deterministic": True,
            "capture_environment": True,
            "verify_checksums": True
        },
        description="Reproducibility settings."
    )

    analysis_settings: dict[str, Any] = Field(
        default_factory=lambda: {
            "confidence_level": 0.95,
            "outlier_threshold": 3.0,
            "min_samples": 30,
            "statistical_tests": ["shapiro", "kruskal"]
        },
        description="Statistical analysis settings."
    )

    reporting: dict[str, Any] = Field(
        default_factory=lambda: {
            "generate_report": True,
            "format": "pdf",
            "include_plots": True,
            "include_raw_data": False
        },
        description="Report generation settings."
    )

    model_config = ConfigDict(
        validate_assignment=True
    )

    @model_validator(mode='after')
    def validate_experiment_consistency(self) -> Self:
        """Validate experiment configuration consistency."""
        # Ensure all referenced configs exist
        for sweep in self.parameter_sweeps:
            if 'base_config' in sweep:
                base_name = sweep['base_config']
                if base_name not in self.engine_configs and base_name not in self.benchmark_configs:
                    raise ValueError(f"Referenced base config '{base_name}' not found")
        return self

    def to_file(self, path: str) -> None:
        """Save configuration to file with checksums."""
        import hashlib
        import json

        data = self.model_dump()

        # Add checksum for integrity
        # Use default=str to handle datetime and other non-JSON-native types
        content = json.dumps(data, sort_keys=True, indent=2, default=str)
        checksum = hashlib.sha256(content.encode()).hexdigest()

        data['_integrity'] = {
            'checksum': checksum,
            'algorithm': 'sha256',
            'timestamp': datetime.now().isoformat()
        }

        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    @classmethod
    def from_file(cls, path: str, verify: bool = True) -> 'ResearchConfig':
        """Load configuration from file with optional verification."""
        import hashlib
        import json

        with open(path) as f:
            data = json.load(f)

        if verify and '_integrity' in data:
            integrity = data.pop('_integrity')

            # Verify checksum
            content = json.dumps(data, sort_keys=True, indent=2)
            checksum = hashlib.sha256(content.encode()).hexdigest()

            if checksum != integrity['checksum']:
                from ionosense_hpc.exceptions import DataIntegrityError
                raise DataIntegrityError(
                    "Configuration file integrity check failed",
                    expected_hash=integrity['checksum'],
                    actual_hash=checksum
                )

        return cls(**data)


# ============================================================================
# Processing Stage Configuration (Future Extensibility)
# ============================================================================

class StageType(str, Enum):
    """Types of processing stages."""
    WINDOW = "window"
    FFT = "fft"
    MAGNITUDE = "magnitude"
    PHASE = "phase"
    FILTER = "filter"
    RESAMPLE = "resample"


class StageConfig(BaseModel):
    """Configuration for a processing stage in the pipeline."""

    stage_type: StageType = Field(
        description="Type of processing stage."
    )

    enabled: bool = Field(
        default=True,
        description="Whether this stage is enabled."
    )

    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Stage-specific parameters."
    )

    input_validation: bool = Field(
        default=True,
        description="Validate input data."
    )

    output_validation: bool = Field(
        default=True,
        description="Validate output data."
    )

    profiling: bool = Field(
        default=False,
        description="Enable stage-level profiling."
    )

    model_config = ConfigDict(
        validate_assignment=True,
        use_enum_values=True
    )


class PipelineConfig(BaseModel):
    """Configuration for the complete processing pipeline."""

    name: str = Field(
        default="default_pipeline",
        description="Pipeline name."
    )

    stages: list[StageConfig] = Field(
        default_factory=lambda: [
            StageConfig(stage_type=StageType.WINDOW),
            StageConfig(stage_type=StageType.FFT),
            StageConfig(stage_type=StageType.MAGNITUDE)
        ],
        description="Ordered list of processing stages."
    )

    parallel_stages: bool = Field(
        default=False,
        description="Enable parallel stage execution where possible."
    )

    error_handling: str = Field(
        default="stop",
        description="Error handling strategy: 'stop', 'skip', or 'continue'."
    )

    model_config = ConfigDict(
        validate_assignment=True
    )

    @field_validator('stages')
    @classmethod
    def validate_stage_order(cls, v: list[StageConfig]) -> list[StageConfig]:
        """Validate that stages are in a valid order."""
        # FFT must come before MAGNITUDE or PHASE
        fft_index = next((i for i, s in enumerate(v) if s.stage_type == StageType.FFT), -1)
        mag_index = next((i for i, s in enumerate(v) if s.stage_type == StageType.MAGNITUDE), -1)
        phase_index = next((i for i, s in enumerate(v) if s.stage_type == StageType.PHASE), -1)

        if mag_index >= 0 and fft_index >= 0 and mag_index < fft_index:
            raise ValueError("MAGNITUDE stage must come after FFT stage")
        if phase_index >= 0 and fft_index >= 0 and phase_index < fft_index:
            raise ValueError("PHASE stage must come after FFT stage")

        return v
