"""Stage definitions and metadata for the pipeline."""

from enum import Enum
from typing import Dict, Any


class StageType(Enum):
    """Types of processing stages in the pipeline."""
    WINDOW = "window"
    FFT = "fft"
    MAGNITUDE = "magnitude"
    PHASE = "phase"  # Future
    FILTER = "filter"  # Future
    RESAMPLE = "resample"  # Future


# Stage metadata for documentation and future extensibility
STAGE_METADATA: Dict[StageType, Dict[str, Any]] = {
    StageType.WINDOW: {
        "description": "Apply window function to reduce spectral leakage",
        "input": "Real-valued time-domain signal",
        "output": "Windowed time-domain signal",
        "parameters": ["window_type", "window_norm"],
        "implemented": True
    },
    StageType.FFT: {
        "description": "Fast Fourier Transform using cuFFT",
        "input": "Real or complex time-domain signal",
        "output": "Complex frequency-domain spectrum",
        "parameters": ["nfft", "batch"],
        "implemented": True
    },
    StageType.MAGNITUDE: {
        "description": "Compute magnitude from complex spectrum",
        "input": "Complex frequency-domain spectrum",
        "output": "Magnitude spectrum",
        "parameters": ["scale_policy"],
        "implemented": True
    },
    StageType.PHASE: {
        "description": "Compute phase from complex spectrum",
        "input": "Complex frequency-domain spectrum",
        "output": "Phase spectrum in radians",
        "parameters": ["unwrap"],
        "implemented": False
    },
    StageType.FILTER: {
        "description": "Apply frequency-domain filtering",
        "input": "Complex frequency-domain spectrum",
        "output": "Filtered complex spectrum",
        "parameters": ["filter_type", "cutoff_frequencies"],
        "implemented": False
    },
    StageType.RESAMPLE: {
        "description": "Resample signal to different rate",
        "input": "Time or frequency domain signal",
        "output": "Resampled signal",
        "parameters": ["target_rate", "method"],
        "implemented": False
    }
}


def get_stage_info(stage_type: StageType) -> Dict[str, Any]:
    """Get information about a stage type.
    
    Args:
        stage_type: Type of stage
        
    Returns:
        Stage metadata dictionary
    """
    return STAGE_METADATA.get(stage_type, {})


def list_implemented_stages() -> list:
    """List stages that are currently implemented.
    
    Returns:
        List of implemented stage types
    """
    return [
        stage_type
        for stage_type, info in STAGE_METADATA.items()
        if info.get("implemented", False)
    ]


def list_future_stages() -> list:
    """List planned but not yet implemented stages.
    
    Returns:
        List of future stage types
    """
    return [
        stage_type
        for stage_type, info in STAGE_METADATA.items()
        if not info.get("implemented", False)
    ]