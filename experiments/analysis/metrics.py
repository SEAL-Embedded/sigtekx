"""
Scientific Metrics Calculations
================================

Utility functions for calculating ionosphere research metrics:
- Real-Time Factor (RTF)
- Time Resolution
- Frequency Resolution
- Effective Frame Rate
- Hop Size

These calculations are also performed in benchmark runners, but this module
provides utilities for post-processing and analysis.
"""

from typing import Optional

from ionosense_hpc.config import EngineConfig


def calculate_hop_size(nfft: int, overlap: float) -> int:
    """Calculate hop size from NFFT and overlap."""
    return int(nfft * (1 - overlap))


def calculate_time_resolution(nfft: int, sample_rate_hz: int) -> float:
    """Calculate time resolution in milliseconds."""
    return (nfft / sample_rate_hz) * 1000


def calculate_freq_resolution(nfft: int, sample_rate_hz: int) -> float:
    """Calculate frequency resolution in Hz."""
    return sample_rate_hz / nfft


def calculate_effective_fps(sample_rate_hz: int, hop_size: int) -> float:
    """Calculate effective frame rate (frames per second)."""
    return sample_rate_hz / hop_size


def calculate_rtf(fps: float, hop_size: int, sample_rate_hz: int) -> float:
    """
    Calculate Real-Time Factor (RTF).

    RTF = (processing speed) / (signal speed)
    RTF = (fps * hop_size) / sample_rate_hz

    Interpretation:
    - RTF = 1.0: Exactly real-time (can process one stream)
    - RTF = 2.0: Can process 2 real-time streams simultaneously
    - RTF = 0.5: Can only process at half real-time speed
    """
    if fps <= 0:
        return 0.0
    return (fps * hop_size) / sample_rate_hz


def calculate_all_scientific_metrics(
    nfft: int,
    channels: int,
    overlap: float,
    sample_rate_hz: int,
    fps: Optional[float] = None
) -> dict:
    """
    Calculate all scientific metrics for a configuration.

    Args:
        nfft: FFT size
        channels: Number of channels
        overlap: Overlap factor (0.0 - 1.0)
        sample_rate_hz: Sample rate in Hz
        fps: Frames per second (optional, for RTF calculation)

    Returns:
        Dictionary with all scientific metrics
    """
    hop_size = calculate_hop_size(nfft, overlap)
    time_res = calculate_time_resolution(nfft, sample_rate_hz)
    freq_res = calculate_freq_resolution(nfft, sample_rate_hz)
    effective_fps = calculate_effective_fps(sample_rate_hz, hop_size)

    metrics = {
        'hop_size': hop_size,
        'time_resolution_ms': time_res,
        'freq_resolution_hz': freq_res,
        'effective_fps': effective_fps,
    }

    if fps is not None:
        metrics['rtf'] = calculate_rtf(fps, hop_size, sample_rate_hz)

    return metrics


def calculate_from_engine_config(
    config: EngineConfig,
    fps: Optional[float] = None
) -> dict:
    """
    Calculate all scientific metrics from an EngineConfig.

    Args:
        config: Engine configuration
        fps: Frames per second (optional, for RTF calculation)

    Returns:
        Dictionary with all scientific metrics
    """
    return calculate_all_scientific_metrics(
        nfft=config.nfft,
        channels=config.channels,
        overlap=config.overlap,
        sample_rate_hz=config.sample_rate_hz,
        fps=fps
    )


def assess_ionosphere_suitability(
    time_resolution_ms: float,
    freq_resolution_hz: float
) -> dict:
    """
    Assess configuration suitability for different ionosphere phenomena.

    Args:
        time_resolution_ms: Time resolution in milliseconds
        freq_resolution_hz: Frequency resolution in Hz

    Returns:
        Dictionary indicating suitability for each phenomenon type
    """
    return {
        'lightning_sprites': {
            'suitable': time_resolution_ms < 10.0,
            'reason': 'Requires <10ms time resolution for fast transients'
        },
        'sids': {
            'suitable': freq_resolution_hz < 1.0,
            'reason': 'Requires <1Hz frequency resolution for narrowband VLF transmitter detection'
        },
        'schumann_resonances': {
            'suitable': freq_resolution_hz < 0.5,
            'reason': 'Requires <0.5Hz frequency resolution for fine spectral features'
        },
        'whistlers': {
            'suitable': time_resolution_ms < 50.0 and freq_resolution_hz < 25.0,
            'reason': 'VLF phenomena require <50ms time resolution and <25Hz frequency resolution'
        },
        'general_vlf': {
            'suitable': freq_resolution_hz < 100.0,
            'reason': 'Broad VLF band (3-30 kHz) requires <100Hz frequency resolution'
        },
    }


def classify_rtf(rtf: float) -> tuple[str, str]:
    """
    Classify Real-Time Factor performance.

    Args:
        rtf: Real-Time Factor

    Returns:
        Tuple of (classification, description)
    """
    if rtf >= 2.0:
        return ("excellent", "Can process 2+ real-time streams simultaneously")
    elif rtf >= 1.0:
        return ("good", "Can process real-time data without falling behind")
    elif rtf >= 0.5:
        return ("marginal", "Near real-time, may have occasional delays")
    elif rtf >= 0.1:
        return ("insufficient", "Cannot keep up with real-time data")
    else:
        return ("very_poor", "Significantly slower than real-time")
