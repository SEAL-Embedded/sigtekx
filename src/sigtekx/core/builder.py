"""Pipeline builder for custom processing pipelines.

This module provides a fluent interface for constructing custom signal processing
pipelines from individual stages (window, FFT, magnitude, etc.).

Following API design principles:
- Fluent interface (method chaining)
- Clear, explicit stage configuration
- Type-safe with validation
- Composable - build complex from simple

Example:
    >>> from ionosense_hpc import PipelineBuilder
    >>>
    >>> pipeline = (
    ...     PipelineBuilder()
    ...     .add_window('blackman', symmetry='periodic')
    ...     .add_fft(scale='1/N')
    ...     .add_magnitude()
    ...     .configure(nfft=4096, channels=8, overlap=0.75)
    ...     .build()
    ... )
"""

from __future__ import annotations

from typing import Any

from ionosense_hpc.config import EngineConfig, ScalePolicy, WindowNorm, WindowSymmetry, WindowType


class PipelineBuilder:
    """Fluent builder for custom processing pipelines.

    Provides a step-by-step interface for constructing signal processing pipelines
    with full control over each stage's configuration.

    The builder follows a simple pattern:
    1. Add stages (window, FFT, magnitude) in order
    2. Configure engine parameters
    3. Build the pipeline

    All methods return self for method chaining.

    Examples:
        # Basic pipeline
        >>> builder = PipelineBuilder()
        >>> builder.add_window('hann')
        >>> builder.add_fft()
        >>> builder.add_magnitude()
        >>> builder.configure(nfft=2048, channels=4)
        >>> pipeline = builder.build()

        # Fluent interface (recommended)
        >>> pipeline = (PipelineBuilder()
        ...     .add_window('hann')
        ...     .add_fft('1/N')
        ...     .add_magnitude()
        ...     .configure(nfft=2048, channels=4)
        ...     .build())

        # Custom window configuration
        >>> pipeline = (PipelineBuilder()
        ...     .add_window(
        ...         type='blackman',
        ...         symmetry='periodic',
        ...         norm='unity'
        ...     )
        ...     .add_fft(scale='1/sqrt(N)')
        ...     .add_magnitude()
        ...     .configure(nfft=4096, channels=8, overlap=0.75)
        ...     .build())
    """

    def __init__(self):
        """Initialize an empty pipeline builder."""
        self._stages = []
        self._config = None

    def add_window(
        self,
        type: str | WindowType = 'hann',
        symmetry: str | WindowSymmetry = 'periodic',
        norm: str | WindowNorm = 'unity'
    ) -> PipelineBuilder:
        """Add a window stage to the pipeline.

        Args:
            type: Window function type ('rectangular', 'hann', 'blackman')
            symmetry: Window symmetry mode ('periodic', 'symmetric')
            norm: Normalization scheme ('unity', 'sqrt')

        Returns:
            Self for method chaining

        Examples:
            >>> builder.add_window('hann')
            >>> builder.add_window('blackman', symmetry='periodic', norm='unity')
        """
        # Normalize string inputs to enums
        if isinstance(type, str):
            type = WindowType(type)
        if isinstance(symmetry, str):
            symmetry = WindowSymmetry(symmetry)
        if isinstance(norm, str):
            norm = WindowNorm(norm)

        self._stages.append({
            'type': 'window',
            'params': {
                'window_type': type,
                'symmetry': symmetry,
                'norm': norm
            }
        })
        return self

    def add_fft(self, scale: str | ScalePolicy = '1/N') -> PipelineBuilder:
        """Add an FFT stage to the pipeline.

        Args:
            scale: FFT output scaling ('none', '1/N', '1/sqrt(N)')

        Returns:
            Self for method chaining

        Examples:
            >>> builder.add_fft()
            >>> builder.add_fft('1/N')
            >>> builder.add_fft('1/sqrt(N)')
        """
        # Normalize string input to enum
        if isinstance(scale, str):
            scale = ScalePolicy(scale)

        self._stages.append({
            'type': 'fft',
            'params': {
                'scale': scale
            }
        })
        return self

    def add_magnitude(self) -> PipelineBuilder:
        """Add a magnitude computation stage.

        Converts complex FFT output to real magnitude values.

        Returns:
            Self for method chaining

        Examples:
            >>> builder.add_magnitude()
        """
        self._stages.append({
            'type': 'magnitude',
            'params': {}
        })
        return self

    def configure(
        self,
        config: EngineConfig | None = None,
        **kwargs: Any
    ) -> PipelineBuilder:
        """Set engine configuration for the pipeline.

        Args:
            config: Complete EngineConfig object, OR
            **kwargs: Individual configuration parameters

        Returns:
            Self for method chaining

        Examples:
            # Using kwargs
            >>> builder.configure(nfft=4096, channels=8, overlap=0.75)

            # Using config object
            >>> config = EngineConfig(nfft=4096, channels=8, overlap=0.75)
            >>> builder.configure(config=config)

            # Mix preset with overrides
            >>> base_config = EngineConfig.from_preset('iono')
            >>> builder.configure(config=base_config)
        """
        if config is not None:
            self._config = config
        elif kwargs:
            self._config = EngineConfig(**kwargs)
        else:
            raise ValueError("Must provide either config object or kwargs")

        return self

    def build(self) -> Pipeline:
        """Build and validate the pipeline.

        Creates an immutable Pipeline object with all configured stages and settings.

        Returns:
            Validated Pipeline ready for use with Engine

        Raises:
            ValueError: If pipeline is empty or configuration is missing
            ValidationError: If stage configuration is invalid

        Examples:
            >>> pipeline = builder.build()
        """
        if not self._stages:
            raise ValueError("Pipeline must have at least one stage")

        if self._config is None:
            raise ValueError(
                "Pipeline configuration not set. Call configure() before build()."
            )

        # Update config with pipeline-specific parameters from stages
        config = self._config.model_copy(deep=True)

        # Extract window/scale parameters from stages and apply to config
        for stage in self._stages:
            if stage['type'] == 'window':
                params = stage['params']
                config.window = params['window_type']
                config.window_symmetry = params['symmetry']
                config.window_norm = params['norm']
            elif stage['type'] == 'fft':
                config.scale = stage['params']['scale']
            elif stage['type'] == 'magnitude':
                config.output = 'magnitude'

        # Validate final configuration
        config.model_validate(config)

        return Pipeline(
            stages=self._stages.copy(),
            config=config
        )

    def clear(self) -> PipelineBuilder:
        """Clear all stages and configuration.

        Resets the builder to empty state.

        Returns:
            Self for method chaining

        Examples:
            >>> builder.clear()
        """
        self._stages = []
        self._config = None
        return self

    def __repr__(self) -> str:
        """String representation for debugging."""
        n_stages = len(self._stages)
        has_config = self._config is not None
        return f"<PipelineBuilder stages={n_stages} configured={has_config}>"


class Pipeline:
    """Immutable pipeline representation.

    Created by PipelineBuilder.build(). Contains the validated stage configuration
    and engine settings ready for execution.

    Attributes:
        stages: List of stage specifications
        config: Engine configuration
    """

    def __init__(self, stages: list[dict[str, Any]], config: EngineConfig):
        """Initialize pipeline (called by PipelineBuilder.build()).

        Args:
            stages: List of stage dictionaries
            config: Validated engine configuration
        """
        self._stages = stages
        self._config = config

    @property
    def stages(self) -> list[dict[str, Any]]:
        """Get list of pipeline stages."""
        return self._stages.copy()  # Return copy to prevent modification

    @property
    def config(self) -> EngineConfig:
        """Get engine configuration."""
        return self._config

    @property
    def num_stages(self) -> int:
        """Get number of stages in pipeline."""
        return len(self._stages)

    def describe(self) -> str:
        """Get human-readable description of the pipeline.

        Returns:
            Formatted string describing the pipeline

        Examples:
            >>> print(pipeline.describe())
            Pipeline (3 stages):
              1. Window: HANN (PERIODIC, UNITY norm)
              2. FFT: scale=1/N
              3. Magnitude
            Config: nfft=4096 channels=8 overlap=75.0%
        """
        lines = [f"Pipeline ({self.num_stages} stages):"]

        for i, stage in enumerate(self._stages, 1):
            stage_type = stage['type']
            params = stage['params']

            if stage_type == 'window':
                wtype = params['window_type'].value.upper()
                sym = params['symmetry'].value.upper()
                norm = params['norm'].value.upper()
                lines.append(f"  {i}. Window: {wtype} ({sym}, {norm} norm)")
            elif stage_type == 'fft':
                scale = params['scale'].value
                lines.append(f"  {i}. FFT: scale={scale}")
            elif stage_type == 'magnitude':
                lines.append(f"  {i}. Magnitude")

        lines.append(
            f"Config: nfft={self._config.nfft} "
            f"channels={self._config.channels} "
            f"overlap={self._config.overlap:.1%}"
        )

        return "\n".join(lines)

    def __repr__(self) -> str:
        """Concise string representation."""
        return f"<Pipeline stages={self.num_stages} nfft={self._config.nfft}>"
