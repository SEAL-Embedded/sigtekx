"""Data loading utilities with Streamlit caching."""

# Import existing data loading logic from analysis module
import sys
from pathlib import Path

import pandas as pd

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from analysis.cli import load_data as _load_data_impl


@st.cache_data(ttl=3600)
def load_benchmark_data(data_path: str | Path = "artifacts/data") -> pd.DataFrame:
    """
    Load benchmark data from CSV files with caching.

    Caches data for 1 hour to improve performance. Data is automatically
    reloaded when files change or cache expires.

    Args:
        data_path: Path to data directory or specific CSV file.
                   Defaults to "artifacts/data".

    Returns:
        Combined DataFrame with all benchmark data.

    Raises:
        ValueError: If path not found or no CSV files found.
    """
    if isinstance(data_path, str):
        data_path = Path(data_path)

    return _load_data_impl(data_path)


@st.cache_data(ttl=3600)
def get_available_configurations(data: pd.DataFrame) -> dict[str, list]:
    """
    Extract unique configuration parameters from benchmark data.

    Useful for populating filter dropdowns and understanding parameter space.

    Args:
        data: Benchmark DataFrame with engine configuration columns.

    Returns:
        Dictionary mapping parameter name to list of unique values.
    """
    config_params = {}

    # Numeric columns: ensure proper typing before sorting
    if 'engine_nfft' in data.columns:
        unique_vals = pd.to_numeric(data['engine_nfft'], errors='coerce').dropna().unique()
        config_params['nfft'] = sorted(unique_vals)

    if 'engine_channels' in data.columns:
        unique_vals = pd.to_numeric(data['engine_channels'], errors='coerce').dropna().unique()
        config_params['channels'] = sorted(unique_vals)

    if 'engine_overlap' in data.columns:
        unique_vals = pd.to_numeric(data['engine_overlap'], errors='coerce').dropna().unique()
        config_params['overlap'] = sorted(unique_vals)

    # String columns: can sort directly
    if 'engine_mode' in data.columns:
        unique_vals = data['engine_mode'].dropna().unique()
        config_params['mode'] = sorted([str(v) for v in unique_vals])

    if 'benchmark_type' in data.columns:
        unique_vals = data['benchmark_type'].dropna().unique()
        config_params['benchmark_type'] = sorted([str(v) for v in unique_vals])

    return config_params


def get_data_freshness(data_path: str | Path = "artifacts/data") -> str | None:
    """
    Get timestamp of most recently modified data file.

    Args:
        data_path: Path to data directory or file.

    Returns:
        Human-readable timestamp string or None if path doesn't exist.
    """
    if isinstance(data_path, str):
        data_path = Path(data_path)

    if not data_path.exists():
        return None

    if data_path.is_file():
        mtime = data_path.stat().st_mtime
    else:
        # Find most recent CSV file
        csv_files = list(data_path.glob("*_summary_*.csv"))
        if not csv_files:
            return None
        mtime = max(f.stat().st_mtime for f in csv_files)

    from datetime import datetime
    dt = datetime.fromtimestamp(mtime)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# =============================================================================
# Spectrogram Data Loading
# =============================================================================

@st.cache_data(ttl=3600)
def list_available_spectrograms(
    spectrogram_dir: str | Path = "artifacts/data/spectrograms"
) -> list[dict[str, any]]:
    """
    Discover all available spectrogram NPZ files.

    Args:
        spectrogram_dir: Directory containing spectrogram NPZ files.

    Returns:
        List of dicts with spectrogram metadata:
        - path: Path to NPZ file
        - filename: Base filename
        - timestamp: File modification time
        - nfft: NFFT size (from filename)
        - channels: Number of channels (from filename)
        - overlap: Overlap factor (from filename)
        - benchmark: Benchmark name (from filename)
    """
    if isinstance(spectrogram_dir, str):
        spectrogram_dir = Path(spectrogram_dir)

    if not spectrogram_dir.exists():
        return []

    # Find all NPZ files
    npz_files = list(spectrogram_dir.glob("*.npz"))

    spectrograms = []
    for npz_file in npz_files:
        # Parse filename to extract metadata
        # Expected format: {benchmark}_nfft{N}_ch{C}_ovlp{O}_{timestamp}.npz
        filename = npz_file.stem  # Without .npz extension
        parts = filename.split('_')

        metadata = {
            'path': str(npz_file),
            'filename': npz_file.name,
            'timestamp': pd.Timestamp.fromtimestamp(npz_file.stat().st_mtime)
        }

        # Try to extract NFFT
        nfft_parts = [p for p in parts if p.startswith('nfft')]
        if nfft_parts:
            try:
                metadata['nfft'] = int(nfft_parts[0].replace('nfft', ''))
            except ValueError:
                metadata['nfft'] = None
        else:
            metadata['nfft'] = None

        # Try to extract channels
        ch_parts = [p for p in parts if p.startswith('ch') and not p.startswith('channel')]
        if ch_parts:
            try:
                metadata['channels'] = int(ch_parts[0].replace('ch', ''))
            except ValueError:
                metadata['channels'] = None
        else:
            metadata['channels'] = None

        # Try to extract overlap
        ovlp_parts = [p for p in parts if p.startswith('ovlp')]
        if ovlp_parts:
            try:
                metadata['overlap'] = float(ovlp_parts[0].replace('ovlp', ''))
            except ValueError:
                metadata['overlap'] = None
        else:
            metadata['overlap'] = None

        # Extract benchmark name (first part before _nfft)
        if parts:
            # Find index of first nfft part
            nfft_idx = next((i for i, p in enumerate(parts) if p.startswith('nfft')), None)
            if nfft_idx and nfft_idx > 0:
                metadata['benchmark'] = '_'.join(parts[:nfft_idx])
            else:
                metadata['benchmark'] = parts[0]
        else:
            metadata['benchmark'] = 'unknown'

        spectrograms.append(metadata)

    # Sort by timestamp (newest first)
    spectrograms.sort(key=lambda x: x['timestamp'], reverse=True)

    return spectrograms


@st.cache_data(ttl=3600)
def load_spectrogram(npz_path: str | Path) -> dict[str, any]:
    """
    Load a spectrogram from NPZ file.

    Args:
        npz_path: Path to NPZ file containing spectrogram data.

    Returns:
        Dictionary with:
        - spectrogram: 2D numpy array (time_steps, freq_bins)
        - times: 1D numpy array of time values (seconds)
        - frequencies: 1D numpy array of frequency values (Hz)
        - config: Dictionary of engine configuration parameters
        - channel: Channel index

    Raises:
        FileNotFoundError: If NPZ file doesn't exist.
        ValueError: If NPZ file is invalid or missing required arrays.
    """
    # Import here to avoid circular dependencies
    from analysis.spectrogram import load_spectrogram as _load_spec

    if isinstance(npz_path, str):
        npz_path = Path(npz_path)

    # Load using the core utility
    spec_data = _load_spec(npz_path)

    # Convert to dictionary format for Streamlit/Plotly
    return {
        'spectrogram': spec_data.spectrogram,
        'times': spec_data.times,
        'frequencies': spec_data.frequencies,
        'config': {
            'nfft': spec_data.config.nfft,
            'channels': spec_data.config.channels,
            'overlap': spec_data.config.overlap,
            'sample_rate_hz': spec_data.config.sample_rate_hz,
            'window': spec_data.config.window.value,
            'window_symmetry': spec_data.config.window_symmetry.value,
            'window_norm': spec_data.config.window_norm.value,
            'scale': spec_data.config.scale.value
        },
        'channel': spec_data.channel
    }


@st.cache_data(ttl=3600)
def get_spectrogram_filters(
    spectrogram_dir: str | Path = "artifacts/data/spectrograms"
) -> dict[str, list]:
    """
    Get unique filter values from available spectrograms.

    Useful for populating filter dropdowns in the Streamlit UI.

    Args:
        spectrogram_dir: Directory containing spectrogram NPZ files.

    Returns:
        Dictionary with lists of unique values for:
        - nfft: Unique NFFT sizes
        - channels: Unique channel counts
        - overlap: Unique overlap values
        - benchmarks: Unique benchmark names
    """
    spectrograms = list_available_spectrograms(spectrogram_dir)

    if not spectrograms:
        return {
            'nfft': [],
            'channels': [],
            'overlap': [],
            'benchmarks': []
        }

    # Extract unique values (filtering out None)
    nfft_values = sorted(set(s['nfft'] for s in spectrograms if s['nfft'] is not None))
    channel_values = sorted(set(s['channels'] for s in spectrograms if s['channels'] is not None))
    overlap_values = sorted(set(s['overlap'] for s in spectrograms if s['overlap'] is not None))
    benchmark_values = sorted(set(s['benchmark'] for s in spectrograms))

    return {
        'nfft': nfft_values,
        'channels': channel_values,
        'overlap': overlap_values,
        'benchmarks': benchmark_values
    }
