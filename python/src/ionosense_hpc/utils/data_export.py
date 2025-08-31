"""
ionosense_hpc.utils.data_export: Data serialization and export utilities.

Provides functions for saving processed data, benchmark results, and
experimental outputs in various formats for analysis and archival.
"""

from __future__ import annotations
import csv
import json
import h5py
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import numpy as np
from numpy.typing import NDArray


def save_to_csv(
    data: List[Dict[str, Any]],
    filepath: Union[str, Path],
    append: bool = False
) -> None:
    """
    Save tabular data to CSV file.
    
    Args:
        data: List of dictionaries, each representing a row.
        filepath: Output file path.
        append: If True, append to existing file.
    
    Example:
        >>> results = [
        ...     {'iteration': 1, 'latency_ms': 0.145},
        ...     {'iteration': 2, 'latency_ms': 0.138}
        ... ]
        >>> save_to_csv(results, 'benchmark_results.csv')
    """
    if not data:
        print(f"Warning: No data to save to {filepath}")
        return
    
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    mode = 'a' if append and filepath.exists() else 'w'
    write_header = not (append and filepath.exists())
    
    with open(filepath, mode, newline='') as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        if write_header:
            writer.writeheader()
        writer.writerows(data)


def save_to_npz(
    filepath: Union[str, Path],
    compressed: bool = True,
    **arrays: NDArray
) -> None:
    """
    Save multiple NumPy arrays to NPZ archive.
    
    Args:
        filepath: Output file path.
        compressed: Use compression (NPZ vs NP).
        **arrays: Named arrays to save.
    
    Example:
        >>> save_to_npz(
        ...     'results.npz',
        ...     magnitudes=mag_array,
        ...     frequencies=freq_array,
        ...     metadata={'fft_size': 4096}
        ... )
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    if compressed:
        np.savez_compressed(filepath, **arrays)
    else:
        np.savez(filepath, **arrays)


def load_from_npz(filepath: Union[str, Path]) -> Dict[str, NDArray]:
    """
    Load arrays from NPZ file.
    
    Args:
        filepath: NPZ file path.
    
    Returns:
        Dictionary of arrays.
    """
    with np.load(filepath, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def save_to_hdf5(
    filepath: Union[str, Path],
    data: Dict[str, Union[NDArray, Dict[str, Any]]],
    metadata: Optional[Dict[str, Any]] = None,
    compression: str = 'gzip'
) -> None:
    """
    Save data to HDF5 file with hierarchical structure.
    
    Args:
        filepath: Output HDF5 file path.
        data: Dictionary of datasets and groups.
        metadata: Global metadata to attach.
        compression: Compression algorithm ('gzip', 'lzf', None).
    
    Example:
        >>> save_to_hdf5(
        ...     'experiment.h5',
        ...     data={
        ...         'raw/ch1': channel1_data,
        ...         'raw/ch2': channel2_data,
        ...         'processed/fft': fft_results,
        ...     },
        ...     metadata={'sample_rate': 100000}
        ... )
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    with h5py.File(filepath, 'w') as f:
        # Save metadata as attributes
        if metadata:
            for key, value in metadata.items():
                f.attrs[key] = value
        
        # Save data
        for path, content in data.items():
            if isinstance(content, np.ndarray):
                # Create dataset with compression
                f.create_dataset(
                    path,
                    data=content,
                    compression=compression if compression else None
                )
            elif isinstance(content, dict):
                # Create group and add attributes
                group = f.create_group(path)
                for key, value in content.items():
                    group.attrs[key] = value


def load_from_hdf5(
    filepath: Union[str, Path],
    dataset_path: Optional[str] = None
) -> Union[Dict[str, Any], NDArray]:
    """
    Load data from HDF5 file.
    
    Args:
        filepath: HDF5 file path.
        dataset_path: Specific dataset to load. If None, loads all.
    
    Returns:
        Dictionary of all data or specific dataset.
    """
    filepath = Path(filepath)
    
    with h5py.File(filepath, 'r') as f:
        if dataset_path:
            return np.array(f[dataset_path])
        
        # Load all datasets
        result = {'metadata': dict(f.attrs)}
        
        def visitor(name, obj):
            if isinstance(obj, h5py.Dataset):
                result[name] = np.array(obj)
            elif isinstance(obj, h5py.Group):
                result[name] = dict(obj.attrs)
        
        f.visititems(visitor)
        return result


def save_benchmark_results(
    results: Dict[str, Any],
    output_dir: Union[str, Path],
    prefix: str = "benchmark"
) -> Path:
    """
    Save comprehensive benchmark results.
    
    Args:
        results: Benchmark results dictionary.
        output_dir: Output directory.
        prefix: Filename prefix.
    
    Returns:
        Path to saved results file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.json"
    filepath = output_dir / filename
    
    # Add metadata
    results['metadata'] = {
        'timestamp': timestamp,
        'version': _get_library_version(),
        'platform': _get_platform_info(),
    }
    
    # Save as JSON with formatting
    with open(filepath, 'w') as f:
        json.dump(results, f, indent=2, default=_json_encoder)
    
    # Also save raw timings as NPZ if present
    if 'raw_timings' in results:
        npz_path = filepath.with_suffix('.npz')
        save_to_npz(
            npz_path,
            timings=np.array(results['raw_timings']),
            metadata=results['metadata']
        )
    
    return filepath


def load_benchmark_results(
    filepath: Union[str, Path]
) -> Dict[str, Any]:
    """
    Load benchmark results from file.
    
    Args:
        filepath: Results file path (JSON or NPZ).
    
    Returns:
        Results dictionary.
    """
    filepath = Path(filepath)
    
    if filepath.suffix == '.json':
        with open(filepath) as f:
            return json.load(f)
    elif filepath.suffix == '.npz':
        return load_from_npz(filepath)
    else:
        raise ValueError(f"Unsupported file type: {filepath.suffix}")


def export_for_matlab(
    data: Dict[str, NDArray],
    filepath: Union[str, Path]
) -> None:
    """
    Export data in MATLAB-compatible format.
    
    Args:
        data: Dictionary of arrays to export.
        filepath: Output .mat file path.
    """
    from scipy.io import savemat
    
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # Ensure all values are arrays
    mat_data = {}
    for key, value in data.items():
        # MATLAB doesn't like certain characters in variable names
        clean_key = key.replace('/', '_').replace('-', '_')
        mat_data[clean_key] = np.asarray(value)
    
    savemat(filepath, mat_data)


def create_experiment_archive(
    experiment_name: str,
    results: Dict[str, Any],
    code_files: Optional[List[Path]] = None,
    output_dir: Union[str, Path] = "experiments"
) -> Path:
    """
    Create a complete experiment archive with results and code.
    
    Args:
        experiment_name: Name of the experiment.
        results: Experiment results.
        code_files: List of source code files to include.
        output_dir: Base output directory.
    
    Returns:
        Path to experiment directory.
    """
    import shutil
    import zipfile
    
    output_dir = Path(output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_dir = output_dir / f"{experiment_name}_{timestamp}"
    exp_dir.mkdir(parents=True, exist_ok=True)
    
    # Save results
    results_file = exp_dir / "results.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=_json_encoder)
    
    # Copy code files if provided
    if code_files:
        code_dir = exp_dir / "code"
        code_dir.mkdir(exist_ok=True)
        for file in code_files:
            if file.exists():
                shutil.copy2(file, code_dir)
    
    # Create README
    readme = exp_dir / "README.md"
    with open(readme, 'w') as f:
        f.write(f"# Experiment: {experiment_name}\n\n")
        f.write(f"Generated: {timestamp}\n\n")
        f.write("## Contents\n")
        f.write("- `results.json`: Experiment results\n")
        if code_files:
            f.write("- `code/`: Source code snapshot\n")
    
    # Create zip archive
    zip_path = exp_dir.with_suffix('.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in exp_dir.rglob('*'):
            if file.is_file():
                zf.write(file, file.relative_to(exp_dir.parent))
    
    return exp_dir


def _json_encoder(obj):
    """Custom JSON encoder for NumPy types."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, Path):
        return str(obj)
    return str(obj)


def _get_library_version() -> str:
    """Get ionosense_hpc version."""
    try:
        from .. import __version__
        return __version__
    except:
        return "unknown"


def _get_platform_info() -> Dict[str, str]:
    """Get platform information."""
    import platform
    import sys
    
    return {
        'python': sys.version,
        'platform': platform.platform(),
        'processor': platform.processor(),
        'hostname': platform.node(),
    }