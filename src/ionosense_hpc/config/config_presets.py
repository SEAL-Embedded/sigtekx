"""Built-in engine configuration presets with executor-specific variants.

This module defines adaptive configuration presets that adjust parameters based
on the selected executor type (batch vs streaming).

Core presets:
- default: General-purpose configuration
- iono: Standard ionosphere monitoring (adapts NFFT for executor)
- ionox: Extreme ionosphere (adapts NFFT for executor)

Executor types:
- batch: Throughput-optimized (higher NFFT, larger batches)
- streaming: Latency-optimized (lower NFFT, smaller batches, ring buffer)

Following API design principles:
- Simple, memorable names
- Clear purpose for each preset
- Adaptive parameters based on execution strategy
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
# Adaptive Preset System - Executor-Specific Variants
# ============================================================================

_PRESET_VARIANTS = {
    'default': {
        'batch': EngineConfig(
            # Signal parameters - General-purpose batch
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
        'streaming': EngineConfig(
            # Signal parameters - Low-latency streaming
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
            mode=ExecutionMode.STREAMING,
            stream_count=4,  # More streams for pipelining
            pinned_buffer_count=3,

            # Performance
            warmup_iters=1,
            enable_profiling=False
        ),
    },

    'iono': {
        'batch': EngineConfig(
            # Signal parameters - Ionosphere batch throughput
            nfft=16384,  # Higher resolution for batch throughput
            batch=32,    # Large batch for maximum efficiency
            overlap=0.75,
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
        'streaming': EngineConfig(
            # Signal parameters - Ionosphere streaming latency
            nfft=4096,  # Lower NFFT for reduced latency
            batch=2,    # Minimal batch for lowest latency
            overlap=0.75,
            sample_rate_hz=48000,

            # Pipeline parameters
            window=WindowType.BLACKMAN,
            window_symmetry=WindowSymmetry.PERIODIC,
            window_norm=WindowNorm.UNITY,
            scale=ScalePolicy.ONE_OVER_N,

            # Execution parameters
            mode=ExecutionMode.STREAMING,
            stream_count=6,  # More streams for overlap management
            pinned_buffer_count=4,

            # Performance
            warmup_iters=5,
            enable_profiling=False
        ),
    },

    'ionox': {
        'batch': EngineConfig(
            # Signal parameters - Extreme ionosphere throughput
            nfft=32768,  # Maximum frequency resolution
            batch=32,    # Very large batch for maximum throughput
            overlap=0.9375,  # Very high overlap
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
        'streaming': EngineConfig(
            # Signal parameters - Extreme ionosphere latency
            nfft=8192,  # Balanced for quality and latency
            batch=2,    # Minimal batch for lowest latency
            overlap=0.9,
            sample_rate_hz=48000,

            # Pipeline parameters
            window=WindowType.BLACKMAN,
            window_symmetry=WindowSymmetry.PERIODIC,
            window_norm=WindowNorm.UNITY,
            scale=ScalePolicy.ONE_OVER_N,

            # Execution parameters
            mode=ExecutionMode.STREAMING,
            stream_count=8,  # Maximum streams for pipelining
            pinned_buffer_count=6,

            # Performance
            warmup_iters=10,
            enable_profiling=False
        ),
    },
}

# Legacy flat presets (deprecated - use get_preset() with executor parameter)
_PRESETS = {name: variants['batch'] for name, variants in _PRESET_VARIANTS.items()}


# ============================================================================
# Public API
# ============================================================================

def get_preset(name: str, executor: str = 'batch') -> EngineConfig:
    """Get a preset configuration adapted for the specified executor.

    Args:
        name: Preset name ('default', 'iono', 'ionox')
        executor: Executor type ('batch', 'streaming')

    Returns:
        Deep copy of the preset EngineConfig optimized for the executor

    Raises:
        ValueError: If preset name or executor type is unknown

    Examples:
        >>> # Get ionosphere config optimized for batch throughput
        >>> config = get_preset('iono', executor='batch')
        >>> # Get ionosphere config optimized for streaming latency
        >>> config = get_preset('iono', executor='streaming')
        >>> # Legacy usage (defaults to batch)
        >>> config = get_preset('iono')
    """
    if name not in _PRESET_VARIANTS:
        available = ', '.join(_PRESET_VARIANTS.keys())
        raise ValueError(
            f"Unknown preset '{name}'. Available presets: {available}"
        )

    if executor not in _PRESET_VARIANTS[name]:
        available = ', '.join(_PRESET_VARIANTS[name].keys())
        raise ValueError(
            f"Preset '{name}' has no variant for executor '{executor}'. "
            f"Available executors: {available}"
        )

    # Return a deep copy so modifications don't affect the original
    return _PRESET_VARIANTS[name][executor].model_copy(deep=True)


def list_presets() -> list[str]:
    """Get list of available preset names.

    Returns:
        List of preset names

    Examples:
        >>> presets = list_presets()
        >>> print(presets)
        ['default', 'iono', 'ionox']
    """
    return list(_PRESET_VARIANTS.keys())


def list_executors() -> list[str]:
    """Get list of available executor types.

    Returns:
        List of executor types

    Examples:
        >>> executors = list_executors()
        >>> print(executors)
        ['batch', 'streaming']
    """
    # All presets have the same executor variants
    return list(next(iter(_PRESET_VARIANTS.values())).keys())


def describe_preset(name: str, executor: str | None = None) -> str:
    """Get a description of a preset.

    Args:
        name: Preset name
        executor: Executor type ('batch', 'streaming'). If None, shows both.

    Returns:
        Human-readable description

    Examples:
        >>> print(describe_preset('iono', executor='batch'))
        Ionosphere Monitoring (batch):
          FFT: 8192, Batch: 16, Overlap: 75.0%
          Window: BLACKMAN (PERIODIC)
          Mode: BATCH

        >>> print(describe_preset('iono'))  # Shows both variants
        Ionosphere Monitoring:
          batch:     FFT: 8192, Batch: 16, Overlap: 75.0%
          streaming: FFT: 4096, Batch: 8, Overlap: 75.0%
    """
    if name not in _PRESET_VARIANTS:
        available = ', '.join(_PRESET_VARIANTS.keys())
        raise ValueError(f"Unknown preset '{name}'. Available: {available}")

    descriptions = {
        'default': 'General Purpose',
        'iono': 'Ionosphere Monitoring',
        'ionox': 'Extreme Ionosphere (High Resolution)'
    }

    title = descriptions.get(name, name.capitalize())

    if executor is not None:
        # Show single executor variant
        if executor not in _PRESET_VARIANTS[name]:
            available = ', '.join(_PRESET_VARIANTS[name].keys())
            raise ValueError(
                f"Preset '{name}' has no variant for executor '{executor}'. "
                f"Available: {available}"
            )

        config = _PRESET_VARIANTS[name][executor]
        return f"""{title} ({executor}):
  FFT: {config.nfft}, Batch: {config.batch}, Overlap: {config.overlap:.1%}
  Window: {config.window.value.upper()} ({config.window_symmetry.value.upper()})
  Mode: {config.mode.value.upper()}
  Sample Rate: {config.sample_rate_hz} Hz"""
    else:
        # Show all executor variants
        lines = [f"{title}:"]
        for exec_type, config in _PRESET_VARIANTS[name].items():
            lines.append(
                f"  {exec_type:10s}: "
                f"FFT: {config.nfft}, "
                f"Batch: {config.batch}, "
                f"Overlap: {config.overlap:.1%}"
            )
        return "\n".join(lines)


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
