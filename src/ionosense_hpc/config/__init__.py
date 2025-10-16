"""Configuration module for Ionosense HPC.

This module exports the unified configuration API:
- EngineConfig: Single configuration class for all engine parameters
- Enums: WindowType, WindowSymmetry, WindowNorm, ScalePolicy, etc.
- Presets: Built-in configurations (default, iono, ionox)
- Validation: Input/config validation utilities
"""

from .presets import compare_presets, describe_preset, get_preset, list_presets
from .schemas import (
    EngineConfig,
    ExecutionMode,
    OutputMode,
    ScalePolicy,
    WindowNorm,
    WindowSymmetry,
    WindowType,
)
from .validation import (
    estimate_memory_usage_mb,
    validate_batch_size,
    validate_config_device_compatibility,
    validate_input_array,
)

__all__ = [
    # Main configuration class
    'EngineConfig',

    # Enumerations
    'WindowType',
    'WindowSymmetry',
    'WindowNorm',
    'ScalePolicy',
    'OutputMode',
    'ExecutionMode',

    # Preset functions
    'get_preset',
    'list_presets',
    'describe_preset',
    'compare_presets',

    # Validation utilities
    'validate_config_device_compatibility',
    'estimate_memory_usage_mb',
    'validate_input_array',
    'validate_batch_size'
]
