"""Test complete StageConfig Python bindings (Phase 0 foundation)."""

from sigtekx.core import _native

# Use C++ types from _native module
StageConfig = _native.StageConfig
WindowType = _native.WindowType
WindowSymmetry = _native.WindowSymmetry
WindowNorm = _native.WindowNorm
ScalePolicy = _native.ScalePolicy
OutputMode = _native.OutputMode


def test_stage_config_all_fields_accessible():
    """Verify all 12 StageConfig fields are bound and writable."""
    config = StageConfig()

    # FFT parameters
    assert hasattr(config, 'nfft')
    assert hasattr(config, 'channels')
    assert hasattr(config, 'overlap')
    assert hasattr(config, 'sample_rate_hz')

    # Windowing parameters
    assert hasattr(config, 'window_type')
    assert hasattr(config, 'window_norm')
    assert hasattr(config, 'window_symmetry')
    assert hasattr(config, 'preload_window')

    # Scaling and output
    assert hasattr(config, 'scale_policy')
    assert hasattr(config, 'output_mode')

    # Execution parameters
    assert hasattr(config, 'inplace')
    assert hasattr(config, 'warmup_iters')

    # Computed property
    assert hasattr(config, 'hop_size')


def test_stage_config_default_values():
    """Verify default values match C++ struct (processing_stage.hpp:38-112)."""
    config = StageConfig()

    assert config.nfft == 1024
    assert config.channels == 2
    assert config.overlap == 0.5
    assert config.sample_rate_hz == 48000
    assert config.window_type == WindowType.HANN
    assert config.window_norm == WindowNorm.UNITY
    assert config.window_symmetry == WindowSymmetry.PERIODIC
    assert config.preload_window is True
    assert config.scale_policy == ScalePolicy.ONE_OVER_N
    assert config.output_mode == OutputMode.MAGNITUDE
    assert config.inplace is True
    assert config.warmup_iters == 1


def test_stage_config_field_assignment():
    """Test that all fields accept valid values."""
    config = StageConfig()

    # FFT parameters
    config.nfft = 4096
    assert config.nfft == 4096

    config.channels = 8
    assert config.channels == 8

    config.overlap = 0.75
    assert config.overlap == 0.75

    config.sample_rate_hz = 100000
    assert config.sample_rate_hz == 100000

    # Windowing parameters
    config.window_type = WindowType.BLACKMAN
    assert config.window_type == WindowType.BLACKMAN

    config.window_norm = WindowNorm.SQRT
    assert config.window_norm == WindowNorm.SQRT

    config.window_symmetry = WindowSymmetry.SYMMETRIC
    assert config.window_symmetry == WindowSymmetry.SYMMETRIC

    config.preload_window = False
    assert config.preload_window is False

    # Scaling and output
    config.scale_policy = ScalePolicy.ONE_OVER_SQRT_N
    assert config.scale_policy == ScalePolicy.ONE_OVER_SQRT_N

    config.output_mode = OutputMode.COMPLEX_PASSTHROUGH
    assert config.output_mode == OutputMode.COMPLEX_PASSTHROUGH

    # Execution parameters
    config.inplace = False
    assert config.inplace is False

    config.warmup_iters = 10
    assert config.warmup_iters == 10


def test_stage_config_hop_size_calculation():
    """Test hop_size() computed property."""
    config = StageConfig()
    config.nfft = 1024
    config.overlap = 0.5

    assert config.hop_size() == 512  # 1024 * (1 - 0.5)

    config.overlap = 0.75
    assert config.hop_size() == 256  # 1024 * (1 - 0.75)

    config.nfft = 2048
    config.overlap = 0.875
    assert config.hop_size() == 256  # 2048 * (1 - 0.875)


def test_stage_config_enum_values():
    """Test that enum values are exported and usable without qualification."""
    config = StageConfig()

    # Should work without StageConfig.WindowType prefix
    config.window_type = WindowType.RECTANGULAR
    config.window_type = WindowType.HANN
    config.window_type = WindowType.BLACKMAN

    config.window_symmetry = WindowSymmetry.PERIODIC
    config.window_symmetry = WindowSymmetry.SYMMETRIC

    config.window_norm = WindowNorm.UNITY
    config.window_norm = WindowNorm.SQRT

    config.scale_policy = ScalePolicy.NONE
    config.scale_policy = ScalePolicy.ONE_OVER_N
    config.scale_policy = ScalePolicy.ONE_OVER_SQRT_N

    config.output_mode = OutputMode.MAGNITUDE
    config.output_mode = OutputMode.COMPLEX_PASSTHROUGH


def test_stage_config_repr():
    """Test __repr__ includes key fields."""
    config = StageConfig()
    config.nfft = 4096
    config.channels = 4
    config.overlap = 0.875

    repr_str = repr(config)

    assert "4096" in repr_str
    assert "4" in repr_str  # channels
    assert "0.875" in repr_str
    assert "StageConfig" in repr_str


def test_stage_config_ionosphere_use_case():
    """Example: Configure for ionosphere VLF/ULF detection (Phase 0 foundation)."""
    config = StageConfig()

    # High-resolution ionosphere analysis
    config.nfft = 8192
    config.overlap = 0.75
    config.channels = 2
    config.sample_rate_hz = 100000

    # Spectral analysis settings
    config.window_type = WindowType.BLACKMAN
    config.window_symmetry = WindowSymmetry.PERIODIC  # FFT-optimized
    config.window_norm = WindowNorm.UNITY

    # Energy-preserving scaling
    config.scale_policy = ScalePolicy.ONE_OVER_N
    config.output_mode = OutputMode.MAGNITUDE

    # Optimizations
    config.preload_window = True
    config.inplace = True

    # Verify configuration
    assert config.hop_size() == 2048  # 8192 * (1 - 0.75)
    assert config.window_symmetry == WindowSymmetry.PERIODIC
    assert config.scale_policy == ScalePolicy.ONE_OVER_N
