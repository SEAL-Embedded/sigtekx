"""Stage definitions and metadata for the processing pipeline.

This module defines the architectural framework for the extensible processing
pipeline, providing structured metadata and type definitions for all current
and planned processing stages.
"""

import warnings
from enum import Enum
from typing import Any

from sigtekx.stages.registry import get_global_registry


class StageType(Enum):
    """Enumeration of processing stages in the ionosense-hpc pipeline."""

    # Core processing stages (Implemented in v1.0)
    WINDOW = "window"
    """Applies a window function to reduce spectral leakage."""

    FFT = "fft"
    """Performs a Fast Fourier Transform using an optimized cuFFT implementation."""

    MAGNITUDE = "magnitude"
    """Calculates the magnitude spectrum from complex FFT results."""

    # Analysis extensions (Planned for v2.0)
    PHASE = "phase"
    """Extracts and unwraps the phase spectrum."""

    FILTER = "filter"
    """Applies frequency-domain filtering operations."""

    RESAMPLE = "resample"
    """Performs multi-rate signal processing and resampling."""


# Stage metadata dictionary containing comprehensive information about each processing stage
STAGE_METADATA: dict[StageType, dict[str, Any]] = {
    StageType.WINDOW: {
        "description": "Apply window function to reduce spectral leakage.",
        "implemented": True,
        "parameters": ["window_type", "window_symmetry", "window_norm"],
    },
    StageType.FFT: {
        "description": "Fast Fourier Transform using cuFFT.",
        "implemented": True,
        "parameters": ["scale_policy"],
    },
    StageType.MAGNITUDE: {
        "description": "Compute magnitude from complex spectrum.",
        "implemented": True,
        "parameters": [],
    },
    StageType.PHASE: {
        "description": "Compute phase from complex spectrum.",
        "implemented": False,
        "planned_version": "2.0",
        "parameters": ["unwrap"],
    },
    StageType.FILTER: {
        "description": "Apply frequency-domain filtering.",
        "implemented": False,
        "planned_version": "2.0",
        "parameters": ["filter_type", "cutoff_frequencies"],
    },
    StageType.RESAMPLE: {
        "description": "Resample signal to a different rate.",
        "implemented": False,
        "planned_version": "2.0",
        "parameters": ["target_rate", "method"],
    }
}


def get_stage_info(stage_type: StageType) -> dict[str, Any]:
    """Get comprehensive information about a specific processing stage.

    Args:
        stage_type: The processing stage to query.

    Returns:
        A dictionary of metadata for the specified stage.
    """
    return STAGE_METADATA.get(stage_type, {})


def list_implemented_stages() -> list[StageType]:
    """List all processing stages that are currently implemented.

    Returns:
        A list of StageType enums for all implemented stages.
    """
    return [
        stage_type
        for stage_type, info in STAGE_METADATA.items()
        if info.get("implemented", False)
    ]


def list_future_stages() -> list[StageType]:
    """List all processing stages planned for future implementation.

    Returns:
        A list of StageType enums for all planned stages.
    """
    return [
        stage_type
        for stage_type, info in STAGE_METADATA.items()
        if not info.get("implemented", False)
    ]


def get_stage_metadata_legacy() -> dict[StageType, dict[str, Any]]:
    """Legacy compatibility for direct STAGE_METADATA access.

    DEPRECATED: Prefer get_global_registry().get_metadata(name) for a unified
    registry source of truth. This helper mirrors the old structure while
    emitting a warning to guide migrations.
    """
    warnings.warn(
        "Direct STAGE_METADATA access is deprecated. Use "
        "get_global_registry().get_metadata(name) instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    registry = get_global_registry()
    registry.ensure_core_stages()

    legacy_metadata: dict[StageType, dict[str, Any]] = {}
    for stage_type in StageType:
        try:
            metadata = registry.get_metadata(stage_type.value)
        except ValueError:
            continue
        legacy_metadata[stage_type] = dict(metadata)

    return legacy_metadata
