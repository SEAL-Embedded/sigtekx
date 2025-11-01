"""Data loading utilities with Streamlit caching."""

from pathlib import Path
from typing import Optional
import pandas as pd
import streamlit as st

# Import existing data loading logic from analysis module
import sys
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

    if 'engine_nfft' in data.columns:
        config_params['nfft'] = sorted(data['engine_nfft'].unique())

    if 'engine_channels' in data.columns:
        config_params['channels'] = sorted(data['engine_channels'].unique())

    if 'engine_overlap' in data.columns:
        config_params['overlap'] = sorted(data['engine_overlap'].unique())

    if 'engine_mode' in data.columns:
        config_params['mode'] = sorted(data['engine_mode'].unique())

    if 'benchmark_type' in data.columns:
        config_params['benchmark_type'] = sorted(data['benchmark_type'].unique())

    return config_params


def get_data_freshness(data_path: str | Path = "artifacts/data") -> Optional[str]:
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
