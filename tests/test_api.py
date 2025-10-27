"""Integration tests for the unified v0.9.3 API.

This module tests the new unified API with:
- Single EngineConfig class with all parameters
- Three core presets (default, iono, ionox)
- PipelineBuilder for custom pipelines
- Engine initialization patterns (preset, config, pipeline)
- All enums (WindowType, WindowSymmetry, WindowNorm, etc.)
"""

import numpy as np
import pytest

from ionosense_hpc import (
    Engine,
    EngineConfig,
    ExecutionMode,
    OutputMode,
    PipelineBuilder,
    ScalePolicy,
    WindowNorm,
    WindowSymmetry,
    WindowType,
    compare_presets,
    describe_preset,
    get_preset,
    list_presets,
)

# =============================================================================
# Preset Tests
# =============================================================================

class TestPresets:
    """Test built-in preset functionality."""

    def test_list_presets(self):
        """Test listing available presets."""
        presets = list_presets()
        assert isinstance(presets, list)
        assert 'default' in presets
        assert 'iono' in presets
        assert 'ionox' in presets
        assert len(presets) == 3

    def test_get_preset_default(self):
        """Test getting default preset."""
        config = get_preset('default')
        assert isinstance(config, EngineConfig)
        assert config.nfft == 1024
        assert config.channels == 2
        assert config.overlap == 0.5
        assert config.window == WindowType.HANN
        assert config.mode == ExecutionMode.BATCH

    def test_get_preset_iono(self):
        """Test getting iono preset (defaults to batch)."""
        config = get_preset('iono')
        assert config.nfft == 16384  # Batch: higher resolution
        assert config.channels == 32
        assert config.overlap == 0.75
        assert config.window == WindowType.BLACKMAN
        assert config.mode == ExecutionMode.BATCH

    def test_get_preset_iono_streaming(self):
        """Test getting iono preset with streaming executor."""
        config = get_preset('iono', executor='streaming')
        assert config.nfft == 4096  # Streaming: lower latency
        assert config.channels == 2
        assert config.overlap == 0.75
        assert config.mode == ExecutionMode.STREAMING

    def test_get_preset_ionox(self):
        """Test getting ionox preset (defaults to batch)."""
        config = get_preset('ionox')
        assert config.nfft == 32768  # Batch: maximum resolution
        assert config.channels == 32
        assert config.overlap == 0.9375
        assert config.window == WindowType.BLACKMAN
        assert config.mode == ExecutionMode.BATCH

    def test_get_preset_ionox_streaming(self):
        """Test getting ionox preset with streaming executor."""
        config = get_preset('ionox', executor='streaming')
        assert config.nfft == 8192  # Streaming: balanced
        assert config.channels == 2
        assert config.overlap == 0.9
        assert config.mode == ExecutionMode.STREAMING

    def test_get_preset_unknown(self):
        """Test error on unknown preset."""
        with pytest.raises(ValueError, match="Unknown preset"):
            get_preset('nonexistent')

    def test_describe_preset(self):
        """Test preset description (shows both variants)."""
        desc = describe_preset('iono')
        assert 'Ionosphere' in desc
        assert 'batch' in desc
        assert 'streaming' in desc
        # Contains NFFFTs for both variants
        assert '16384' in desc  # BATCH mode variant
        assert '4096' in desc  # STREAMING mode variant

    def test_compare_presets(self):
        """Test preset comparison table."""
        comparison = compare_presets()
        assert 'default' in comparison
        assert 'iono' in comparison
        assert 'ionox' in comparison
        assert 'NFFT' in comparison

    def test_preset_returns_copy(self):
        """Test that presets return independent copies."""
        config1 = get_preset('default')
        config2 = get_preset('default')

        # Modify one
        config1.nfft = 2048

        # Should not affect the other
        assert config2.nfft == 1024


# =============================================================================
# EngineConfig Tests
# =============================================================================

class TestEngineConfig:
    """Test unified EngineConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = EngineConfig()
        assert config.nfft == 1024
        assert config.channels == 2
        assert config.overlap == 0.5
        assert config.sample_rate_hz == 48000
        assert config.window == WindowType.HANN
        assert config.window_symmetry == WindowSymmetry.PERIODIC
        assert config.window_norm == WindowNorm.UNITY
        assert config.scale == ScalePolicy.ONE_OVER_N
        assert config.output == OutputMode.MAGNITUDE
        assert config.mode == ExecutionMode.BATCH

    def test_custom_config(self):
        """Test creating custom configuration."""
        config = EngineConfig(
            nfft=4096,
            channels=8,
            overlap=0.75,
            sample_rate_hz=96000,
            window=WindowType.BLACKMAN,
            window_symmetry=WindowSymmetry.SYMMETRIC,
            window_norm=WindowNorm.SQRT,
            scale=ScalePolicy.ONE_OVER_SQRT_N,
            mode=ExecutionMode.STREAMING
        )

        assert config.nfft == 4096
        assert config.channels == 8
        assert config.window == WindowType.BLACKMAN
        assert config.window_symmetry == WindowSymmetry.SYMMETRIC
        assert config.mode == ExecutionMode.STREAMING

    def test_from_preset_method(self):
        """Test EngineConfig.from_preset() class method."""
        config = EngineConfig.from_preset('iono')
        assert config.nfft == 16384  # Batch variant (default)
        assert config.channels == 32

    def test_from_preset_with_overrides(self):
        """Test preset with parameter overrides."""
        config = EngineConfig.from_preset('iono', nfft=32768, overlap=0.875)
        assert config.nfft == 32768  # Overridden
        assert config.overlap == 0.875  # Overridden
        assert config.channels == 32  # From preset (batch variant)

    def test_from_preset_with_mode_override(self):
        """Test preset with mode override."""
        config = EngineConfig.from_preset('iono', mode=ExecutionMode.STREAMING)
        assert config.mode == ExecutionMode.STREAMING
        # Mode override should adjust stream/buffer counts for STREAMING
        assert config.stream_count == 6  # STREAMING mode override
        assert config.pinned_buffer_count == 4  # STREAMING mode override
        assert config.channels == 2  # Minimal channels for lower latency

    def test_computed_properties(self):
        """Test computed properties."""
        config = EngineConfig(nfft=1024, overlap=0.5, sample_rate_hz=48000)

        assert config.hop_size == 512  # nfft * (1 - overlap)
        assert config.num_output_bins == 513  # nfft // 2 + 1
        assert abs(config.frame_duration_ms - 21.333) < 0.01
        assert abs(config.hop_duration_ms - 10.667) < 0.01
        assert abs(config.effective_fps - 93.75) < 0.01

    def test_validation_power_of_two(self):
        """Test nfft must be power of 2."""
        with pytest.raises(ValueError, match="power of 2"):
            EngineConfig(nfft=1000)

    def test_validation_overlap_range(self):
        """Test overlap must be in [0, 1)."""
        with pytest.raises(ValueError):
            EngineConfig(overlap=-0.1)

        with pytest.raises(ValueError):
            EngineConfig(overlap=1.0)

    def test_enum_string_conversion(self):
        """Test that string values work for enums."""
        config = EngineConfig(
            window='blackman',  # type: ignore[arg-type]
            window_symmetry='symmetric',  # type: ignore[arg-type]
            window_norm='sqrt',  # type: ignore[arg-type]
            scale='1/sqrt(N)',  # type: ignore[arg-type]
            mode='streaming'  # type: ignore[arg-type]
        )

        assert config.window == WindowType.BLACKMAN
        assert config.window_symmetry == WindowSymmetry.SYMMETRIC
        assert config.window_norm == WindowNorm.SQRT
        assert config.scale == ScalePolicy.ONE_OVER_SQRT_N
        assert config.mode == ExecutionMode.STREAMING

    def test_config_repr(self):
        """Test configuration string representation."""
        config = EngineConfig(nfft=2048, channels=4, overlap=0.75)
        repr_str = repr(config)

        assert '2048' in repr_str
        assert '4' in repr_str
        assert '75' in repr_str  # 75%

    def test_config_to_dict(self):
        """Test configuration export to dictionary."""
        config = EngineConfig(nfft=2048, channels=4)
        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert config_dict['nfft'] == 2048
        assert config_dict['channels'] == 4


# =============================================================================
# PipelineBuilder Tests
# =============================================================================

class TestPipelineBuilder:
    """Test PipelineBuilder fluent interface."""

    def test_basic_pipeline(self):
        """Test building basic pipeline."""
        pipeline = (
            PipelineBuilder()
            .add_window('hann')
            .add_fft()
            .add_magnitude()
            .configure(nfft=1024, channels=2)
            .build()
        )

        assert pipeline.num_stages == 3
        assert pipeline.config.nfft == 1024
        assert pipeline.config.channels == 2

    def test_custom_window_params(self):
        """Test pipeline with custom window parameters."""
        pipeline = (
            PipelineBuilder()
            .add_window(
                type='blackman',
                symmetry='periodic',
                norm='unity'
            )
            .add_fft(scale='1/N')
            .add_magnitude()
            .configure(nfft=4096, channels=8)
            .build()
        )

        assert pipeline.config.window == WindowType.BLACKMAN
        assert pipeline.config.window_symmetry == WindowSymmetry.PERIODIC
        assert pipeline.config.window_norm == WindowNorm.UNITY

    def test_pipeline_with_config_object(self):
        """Test pipeline with EngineConfig object."""
        config = EngineConfig(nfft=2048, channels=4, overlap=0.75)

        pipeline = (
            PipelineBuilder()
            .add_window('hann')
            .add_fft()
            .add_magnitude()
            .configure(config=config)
            .build()
        )

        assert pipeline.config.nfft == 2048
        assert pipeline.config.channels == 4

    def test_pipeline_describe(self):
        """Test pipeline description."""
        pipeline = (
            PipelineBuilder()
            .add_window('blackman')
            .add_fft('1/sqrt(N)')
            .add_magnitude()
            .configure(nfft=4096, channels=8, overlap=0.75)
            .build()
        )

        desc = pipeline.describe()
        assert 'BLACKMAN' in desc
        assert '1/sqrt(N)' in desc
        assert 'Magnitude' in desc
        assert '4096' in desc

    def test_pipeline_stages_property(self):
        """Test pipeline stages are immutable."""
        pipeline = (
            PipelineBuilder()
            .add_window()
            .add_fft()
            .add_magnitude()
            .configure(nfft=1024, channels=2)
            .build()
        )

        stages = pipeline.stages
        assert len(stages) == 3

        # Modifying returned stages should not affect pipeline
        stages.append({'type': 'invalid'})
        assert len(pipeline.stages) == 3

    def test_empty_pipeline_error(self):
        """Test error on building empty pipeline."""
        builder = PipelineBuilder()

        with pytest.raises(ValueError, match="at least one stage"):
            builder.build()

    def test_no_config_error(self):
        """Test error when building without configuration."""
        builder = (
            PipelineBuilder()
            .add_window()
            .add_fft()
            .add_magnitude()
        )

        with pytest.raises(ValueError, match="configuration not set"):
            builder.build()

    def test_builder_clear(self):
        """Test clearing pipeline builder."""
        builder = (
            PipelineBuilder()
            .add_window()
            .add_fft()
            .configure(nfft=1024, channels=2)
        )

        builder.clear()

        # Should be empty now
        with pytest.raises(ValueError):
            builder.build()

    def test_builder_repr(self):
        """Test builder string representation."""
        builder = PipelineBuilder().add_window().add_fft()
        repr_str = repr(builder)

        assert 'stages=2' in repr_str


# =============================================================================
# Engine Initialization Tests
# =============================================================================

class TestEngineInitialization:
    """Test Engine initialization with different patterns."""

    def test_init_with_preset_name(self):
        """Test initializing with preset name."""
        engine = Engine(preset='default')
        assert engine.config.nfft == 1024
        assert engine.is_initialized
        engine.close()

    def test_init_with_config_object(self):
        """Test initializing with EngineConfig object."""
        config = EngineConfig(nfft=2048, channels=4)
        engine = Engine(config=config)
        assert engine.config.nfft == 2048
        assert engine.is_initialized
        engine.close()

    def test_init_with_pipeline(self):
        """Test initializing with Pipeline object."""
        pipeline = (
            PipelineBuilder()
            .add_window('hann')
            .add_fft()
            .add_magnitude()
            .configure(nfft=4096, channels=8)
            .build()
        )

        engine = Engine(pipeline=pipeline)
        assert engine.config.nfft == 4096
        assert engine.is_initialized
        engine.close()

    def test_init_with_preset_and_overrides(self):
        """Test preset with quick parameter overrides."""
        engine = Engine(preset='iono', nfft=8192, channels=16)
        assert engine.config.nfft == 8192  # Overridden
        assert engine.config.channels == 16  # Overridden
        assert engine.config.window == WindowType.BLACKMAN  # From preset
        engine.close()

    def test_init_with_preset_and_mode_override(self):
        """Test preset with mode override."""
        engine = Engine(preset='default', mode=ExecutionMode.STREAMING)
        assert engine.config.mode == ExecutionMode.STREAMING
        engine.close()

    def test_init_with_mode_string(self):
        """Test mode override with string."""
        engine = Engine(preset='default', mode='streaming')
        assert engine.config.mode == ExecutionMode.STREAMING
        engine.close()

    def test_init_default_when_none(self):
        """Test default preset used when no arguments."""
        engine = Engine()
        assert engine.config.nfft == 1024  # default preset
        assert engine.is_initialized
        engine.close()

    def test_init_validation_error(self):
        """Test validation error during initialization."""
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            Engine(config=EngineConfig(nfft=1000))  # Not power of 2

    def test_multiple_init_sources_error(self):
        """Test error when providing multiple initialization sources."""
        config = EngineConfig()
        pipeline = (
            PipelineBuilder()
            .add_window()
            .add_fft()
            .add_magnitude()
            .configure(nfft=1024, channels=2)
            .build()
        )

        # Should prioritize pipeline over config
        engine = Engine(pipeline=pipeline, config=config)
        assert engine.config.nfft == 1024  # From pipeline
        engine.close()


# =============================================================================
# Enum Tests
# =============================================================================

class TestEnums:
    """Test all exposed enums."""

    def test_window_type_enum(self):
        """Test WindowType enum."""
        assert WindowType.RECTANGULAR.value == 'rectangular'
        assert WindowType.HANN.value == 'hann'
        assert WindowType.BLACKMAN.value == 'blackman'

        # Test enum from string
        assert WindowType('hann') == WindowType.HANN

    def test_window_symmetry_enum(self):
        """Test WindowSymmetry enum."""
        assert WindowSymmetry.PERIODIC.value == 'periodic'
        assert WindowSymmetry.SYMMETRIC.value == 'symmetric'

    def test_window_norm_enum(self):
        """Test WindowNorm enum."""
        assert WindowNorm.UNITY.value == 'unity'
        assert WindowNorm.SQRT.value == 'sqrt'

    def test_scale_policy_enum(self):
        """Test ScalePolicy enum."""
        assert ScalePolicy.NONE.value == 'none'
        assert ScalePolicy.ONE_OVER_N.value == '1/N'
        assert ScalePolicy.ONE_OVER_SQRT_N.value == '1/sqrt(N)'

    def test_output_mode_enum(self):
        """Test OutputMode enum."""
        assert OutputMode.MAGNITUDE.value == 'magnitude'
        assert OutputMode.COMPLEX.value == 'complex'

    def test_execution_mode_enum(self):
        """Test ExecutionMode enum."""
        assert ExecutionMode.BATCH.value == 'batch'
        assert ExecutionMode.STREAMING.value == 'streaming'


# =============================================================================
# End-to-End Integration Tests
# =============================================================================

class TestEndToEndIntegration:
    """End-to-end tests of complete workflows."""

    @pytest.mark.skipif(
        not pytest.importorskip("ionosense_hpc.core._engine", reason="C++ engine not available"),
        reason="Requires C++ engine"
    )
    def test_iono_preset_workflow(self):
        """Test complete workflow with iono preset."""
        # Initialize with iono preset
        engine = Engine(preset='iono')

        # Generate test data
        n_samples = engine.config.nfft * engine.config.channels
        test_data = np.random.randn(n_samples).astype(np.float32)

        # Process
        output = engine.process(test_data)

        # Verify output shape
        expected_shape = (engine.config.channels, engine.config.num_output_bins)
        assert output.shape == expected_shape
        assert output.dtype == np.float32

        engine.close()

    @pytest.mark.skipif(
        not pytest.importorskip("ionosense_hpc.core._engine", reason="C++ engine not available"),
        reason="Requires C++ engine"
    )
    def test_custom_pipeline_workflow(self):
        """Test complete workflow with custom pipeline."""
        # Build custom pipeline
        pipeline = (
            PipelineBuilder()
            .add_window('blackman', symmetry='periodic', norm='unity')
            .add_fft(scale='1/N')
            .add_magnitude()
            .configure(nfft=4096, channels=8, overlap=0.75)
            .build()
        )

        # Initialize engine
        engine = Engine(pipeline=pipeline)

        # Generate test data
        n_samples = 4096 * 8
        test_data = np.random.randn(n_samples).astype(np.float32)

        # Process
        output = engine.process(test_data)

        # Verify
        assert output.shape == (8, 2049)
        assert np.all(output >= 0)  # Magnitude is non-negative

        engine.close()

    def test_preset_modification_workflow(self):
        """Test modifying preset with quick overrides."""
        # Start with iono preset but customize
        engine = Engine(
            preset='iono',
            nfft=8192,  # Increase resolution
            overlap=0.875,  # More temporal resolution
            mode='streaming'  # Switch to realtime mode
        )

        # Verify overrides
        assert engine.config.nfft == 8192
        assert engine.config.overlap == 0.875
        assert engine.config.mode == ExecutionMode.STREAMING

        # Verify preset values maintained
        assert engine.config.window == WindowType.BLACKMAN

        engine.close()

    def test_config_factory_workflow(self):
        """Test using EngineConfig.from_preset() factory."""
        # Create config from preset with modifications
        config = EngineConfig.from_preset(
            'ionox',
            mode=ExecutionMode.STREAMING,
            nfft=16384
        )

        # Verify
        assert config.nfft == 16384
        assert config.mode == ExecutionMode.STREAMING
        assert config.window == WindowType.BLACKMAN  # From ionox preset

        # Use config
        engine = Engine(config=config)
        assert engine.config.nfft == 16384
        engine.close()


# =============================================================================
# Backward Compatibility Tests
# =============================================================================

class TestBackwardCompatibility:
    """Test that key use cases still work."""

    def test_simple_engine_creation(self):
        """Test simplest engine creation."""
        engine = Engine()
        assert engine.is_initialized
        engine.close()

    def test_config_dict_conversion(self):
        """Test config can be converted to dict."""
        config = get_preset('iono')
        config_dict = config.model_dump()

        assert isinstance(config_dict, dict)
        assert config_dict['nfft'] == 16384  # Batch variant (default)

    def test_config_modification(self):
        """Test config can be modified after creation."""
        config = get_preset('default')
        config.nfft = 2048
        config.channels = 4

        assert config.nfft == 2048
        assert config.channels == 4
