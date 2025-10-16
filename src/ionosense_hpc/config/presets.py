"""Built-in engine configuration presets.

This module defines the three core presets:
- default: General-purpose configuration
- iono: Standard ionosphere monitoring (4096 FFT, 0.75 overlap, Blackman window)
- ionox: Extreme ionosphere (8192 FFT, 0.9 overlap, Blackman window)

Following API design principles:
- Simple, memorable names
- Clear purpose for each preset
- No magic - explicit configuration values
"""

from .schemas import (
    EngineConfig,
    ExecutionMode,
    ScalePolicy,
    WindowNorm,
    WindowSymmetry,
    WindowType,
)

# ============================================================================
# Built-in Presets
# ============================================================================

_PRESETS = {
    'default': EngineConfig(
        # Signal parameters
        nfft=1024,
        batch=2,
        overlap=0.5,
        sample_rate_hz=48000,

        # Pipeline parameters
        window=WindowType.HANN,
        window_symmetry=WindowSymmetry.PERIODIC,
        window_norm=WindowNorm.UNITY,
        scale=ScalePolicy.ONE_OVER_N,

        # Execution parameters
        mode=ExecutionMode.BATCH,
        stream_count=3,
        pinned_buffer_count=2,

        # Performance
        warmup_iters=1,
        enable_profiling=False
    ),

    'iono': EngineConfig(
        # Signal parameters - Ionosphere monitoring
        nfft=4096,  # Good frequency resolution for HF/VLF
        batch=8,    # Process multiple channels
        overlap=0.75,  # High overlap for temporal resolution
        sample_rate_hz=48000,

        # Pipeline parameters - Optimized for ionosphere
        window=WindowType.BLACKMAN,  # Better sidelobe suppression
        window_symmetry=WindowSymmetry.PERIODIC,
        window_norm=WindowNorm.UNITY,
        scale=ScalePolicy.ONE_OVER_N,

        # Execution parameters
        mode=ExecutionMode.BATCH,
        stream_count=4,
        pinned_buffer_count=4,

        # Performance
        warmup_iters=5,
        enable_profiling=False
    ),

    'ionox': EngineConfig(
        # Signal parameters - Extreme ionosphere (missile detection, etc.)
        nfft=8192,  # Ultra-high frequency resolution
        batch=16,   # Large batch for throughput
        overlap=0.9,  # Very high overlap for detailed temporal analysis
        sample_rate_hz=48000,

        # Pipeline parameters - Maximum quality
        window=WindowType.BLACKMAN,
        window_symmetry=WindowSymmetry.PERIODIC,
        window_norm=WindowNorm.UNITY,
        scale=ScalePolicy.ONE_OVER_N,

        # Execution parameters - High throughput
        mode=ExecutionMode.BATCH,
        stream_count=4,
        pinned_buffer_count=4,

        # Performance
        warmup_iters=10,
        enable_profiling=False
    ),
}


# ============================================================================
# Public API
# ============================================================================

def get_preset(name: str) -> EngineConfig:
    """Get a preset configuration by name.

    Args:
        name: Preset name ('default', 'iono', 'ionox')

    Returns:
        Deep copy of the preset EngineConfig

    Raises:
        ValueError: If preset name is unknown

    Examples:
        >>> config = get_preset('iono')
        >>> config = get_preset('ionox')
    """
    if name not in _PRESETS:
        available = ', '.join(_PRESETS.keys())
        raise ValueError(
            f"Unknown preset '{name}'. Available presets: {available}"
        )

    # Return a deep copy so modifications don't affect the original
    return _PRESETS[name].model_copy(deep=True)


def list_presets() -> list[str]:
    """Get list of available preset names.

    Returns:
        List of preset names

    Examples:
        >>> presets = list_presets()
        >>> print(presets)
        ['default', 'iono', 'ionox']
    """
    return list(_PRESETS.keys())


def describe_preset(name: str) -> str:
    """Get a description of a preset.

    Args:
        name: Preset name

    Returns:
        Human-readable description

    Examples:
        >>> print(describe_preset('iono'))
        Ionosphere Monitoring Preset:
          FFT: 4096, Batch: 8, Overlap: 75.0%
          Window: BLACKMAN (PERIODIC)
          Mode: BATCH
    """
    if name not in _PRESETS:
        available = ', '.join(_PRESETS.keys())
        raise ValueError(f"Unknown preset '{name}'. Available: {available}")

    config = _PRESETS[name]

    descriptions = {
        'default': 'General Purpose',
        'iono': 'Ionosphere Monitoring',
        'ionox': 'Extreme Ionosphere (High Resolution)'
    }

    title = descriptions.get(name, name.capitalize())

    return f"""{title} Preset:
  FFT: {config.nfft}, Batch: {config.batch}, Overlap: {config.overlap:.1%}
  Window: {config.window.value.upper()} ({config.window_symmetry.value.upper()})
  Mode: {config.mode.value.upper()}
  Sample Rate: {config.sample_rate_hz} Hz"""


# ============================================================================
# Preset Comparison
# ============================================================================

def compare_presets() -> str:
    """Generate a comparison table of all presets.

    Returns:
        Formatted comparison table

    Examples:
        >>> print(compare_presets())
    """
    header = f"{'Preset':<10} | {'NFFT':<6} | {'Batch':<6} | {'Overlap':<8} | {'Window':<10}"
    separator = "-" * len(header)

    lines = [header, separator]

    for name in _PRESETS:
        cfg = _PRESETS[name]
        line = (
            f"{name:<10} | "
            f"{cfg.nfft:<6} | "
            f"{cfg.batch:<6} | "
            f"{cfg.overlap:<8.1%} | "
            f"{cfg.window.value:<10}"
        )
        lines.append(line)

    return "\n".join(lines)
