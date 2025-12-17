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


from sigtekx.config import EngineConfig


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
    Calculate Real-Time Factor (RTF) using academic convention.

    RTF = (signal duration) / (processing time)
    RTF = sample_rate_hz / (fps * hop_size)

    This is the latency-based convention used in ASR, radar, and SDR literature.
    Lower RTF values indicate better performance.

    Interpretation:
    - RTF < 1.0: Faster than real-time (good) ✅
    - RTF = 1.0: Exactly real-time (theoretical limit)
    - RTF > 1.0: Slower than real-time (falling behind) ❌

    Example:
        >>> calculate_rtf(fps=250, hop_size=1024, sample_rate_hz=100000)
        0.39  # Processing uses 39% of available time (good)

    Note:
        This is the INVERSE of throughput-based RTF used in GPU metrics.
        Academic RTF = 1.0 / Throughput RTF
    """
    if fps <= 0:
        return float('inf')  # Cannot process (worst case)

    # Academic convention: RTF = signal_duration / processing_time (lower is better)
    return sample_rate_hz / (fps * hop_size)


def calculate_all_scientific_metrics(
    nfft: int,
    channels: int,
    overlap: float,
    sample_rate_hz: int,
    fps: float | None = None
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
    fps: float | None = None
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
    Classify Real-Time Factor performance using academic convention.

    Academic RTF: Lower is better (RTF < 1.0 = good performance)

    Args:
        rtf: Real-Time Factor (academic convention, lower is better)

    Returns:
        Tuple of (classification, description)

    Classification Tiers:
        - RTF ≤ 0.10: Exceptional (10× faster than real-time)
        - RTF ≤ 0.20: Excellent (5× faster than real-time)
        - RTF ≤ 0.33: Very Good (3× faster than real-time)
        - RTF ≤ 0.40: Good (2.5× faster, ASR industry standard)
        - RTF ≤ 0.50: Acceptable (2× faster than real-time)
        - RTF ≤ 1.0: Marginal (barely real-time)
        - RTF > 1.0: Insufficient (falling behind)
    """
    if rtf <= 0.10:
        return ("exceptional", "RTF ≤0.10: Exceptional performance (10× faster than real-time)")
    elif rtf <= 0.20:
        return ("excellent", "RTF ≤0.20: Excellent performance (5× faster than real-time)")
    elif rtf <= 0.33:
        return ("very_good", "RTF ≤0.33: Very good performance (3× faster than real-time)")
    elif rtf <= 0.40:
        return ("good", "RTF ≤0.40: Good performance (ASR industry standard)")
    elif rtf <= 0.50:
        return ("acceptable", "RTF ≤0.50: Acceptable performance (2× faster than real-time)")
    elif rtf <= 1.0:
        return ("marginal", "RTF ≤1.0: Marginal performance (barely real-time)")
    else:
        return ("insufficient", f"RTF ={rtf:.2f}: Cannot keep up with real-time data")
