#!/usr/bin/env python
"""
Data Analysis Script for Ionosphere HPC Experiments
===================================================

Aggregates and analyzes experiment data from individual CSV files.
Creates summary statistics for downstream visualization and reporting.

Usage:
    python analyze.py

Input: Individual CSV files in artifacts/data/
Output: artifacts/data/summary_statistics.csv
"""

import warnings
from pathlib import Path

import pandas as pd

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')


def find_experiment_data(data_dir: str = "artifacts/data") -> dict[str, list[str]]:
    """Find all experiment data files by type."""
    data_path = Path(data_dir)

    files = {
        'throughput': list(data_path.glob("throughput_summary_*.csv")),
        'latency': list(data_path.glob("latency_summary_*.csv")),
        'accuracy': list(data_path.glob("accuracy_summary_*.csv"))
    }

    # Filter out empty lists and convert to strings
    files = {k: [str(f) for f in v] for k, v in files.items() if v}

    print("Found experiment data:")
    for benchmark_type, file_list in files.items():
        print(f"  {benchmark_type}: {len(file_list)} files")

    return files


def load_and_combine_data(files: list[str]) -> pd.DataFrame:
    """Load and combine multiple CSV files into a single DataFrame."""
    if not files:
        return pd.DataFrame()

    dataframes = []
    for file_path in files:
        try:
            df = pd.read_csv(file_path)
            # Add source file for debugging
            df['source_file'] = Path(file_path).name
            dataframes.append(df)
        except Exception as e:
            print(f"Warning: Could not load {file_path}: {e}")

    if not dataframes:
        return pd.DataFrame()

    combined = pd.concat(dataframes, ignore_index=True)
    print(f"  Combined {len(dataframes)} files into {len(combined)} rows")
    return combined


def analyze_throughput_data(df: pd.DataFrame) -> dict:
    """Analyze throughput benchmark data."""
    if df.empty:
        return {}

    analysis = {
        'benchmark_type': 'throughput',
        'total_runs': len(df),
        'parameter_ranges': {
            'nfft': {'min': df['engine_nfft'].min(), 'max': df['engine_nfft'].max()},
            'batch': {'min': df['engine_batch'].min(), 'max': df['engine_batch'].max()}
        }
    }

    # Performance metrics
    if 'frames_per_second' in df.columns:
        fps = df['frames_per_second']
        analysis['frames_per_second'] = {
            'mean': fps.mean(),
            'std': fps.std(),
            'min': fps.min(),
            'max': fps.max(),
            'median': fps.median()
        }

    if 'gb_per_second' in df.columns:
        gbps = df['gb_per_second']
        analysis['gb_per_second'] = {
            'mean': gbps.mean(),
            'std': gbps.std(),
            'min': gbps.min(),
            'max': gbps.max(),
            'median': gbps.median()
        }

    # Performance scaling analysis
    if len(df) > 1:
        # Group by nfft to see scaling
        nfft_scaling = df.groupby('engine_nfft')['frames_per_second'].agg(['mean', 'std', 'count'])
        analysis['nfft_scaling'] = nfft_scaling.to_dict('index')

        # Group by batch size to see scaling
        batch_scaling = df.groupby('engine_batch')['frames_per_second'].agg(['mean', 'std', 'count'])
        analysis['batch_scaling'] = batch_scaling.to_dict('index')

        # Find optimal configuration
        best_fps_idx = df['frames_per_second'].idxmax()
        analysis['best_performance'] = {
            'nfft': int(df.loc[best_fps_idx, 'engine_nfft']),
            'batch': int(df.loc[best_fps_idx, 'engine_batch']),
            'fps': float(df.loc[best_fps_idx, 'frames_per_second']),
            'efficiency': float(df.loc[best_fps_idx, 'gb_per_second']) if 'gb_per_second' in df.columns else None
        }

    return analysis


def analyze_latency_data(df: pd.DataFrame) -> dict:
    """Analyze latency benchmark data."""
    if df.empty:
        return {}

    analysis = {
        'benchmark_type': 'latency',
        'total_runs': len(df),
        'parameter_ranges': {
            'nfft': {'min': df['engine_nfft'].min(), 'max': df['engine_nfft'].max()},
            'batch': {'min': df['engine_batch'].min(), 'max': df['engine_batch'].max()}
        }
    }

    # Latency metrics
    if 'mean_latency_us' in df.columns:
        latency = df['mean_latency_us']
        analysis['mean_latency_us'] = {
            'mean': latency.mean(),
            'std': latency.std(),
            'min': latency.min(),
            'max': latency.max(),
            'median': latency.median()
        }

    # Find best latency configuration
    if len(df) > 1 and 'mean_latency_us' in df.columns:
        best_latency_idx = df['mean_latency_us'].idxmin()
        analysis['best_latency'] = {
            'nfft': int(df.loc[best_latency_idx, 'engine_nfft']),
            'batch': int(df.loc[best_latency_idx, 'engine_batch']),
            'latency_us': float(df.loc[best_latency_idx, 'mean_latency_us'])
        }

    return analysis


def analyze_accuracy_data(df: pd.DataFrame) -> dict:
    """Analyze accuracy benchmark data."""
    if df.empty:
        return {}

    analysis = {
        'benchmark_type': 'accuracy',
        'total_runs': len(df),
        'parameter_ranges': {
            'nfft': {'min': df['engine_nfft'].min(), 'max': df['engine_nfft'].max()},
            'batch': {'min': df['engine_batch'].min(), 'max': df['engine_batch'].max()}
        }
    }

    # Accuracy metrics
    if 'pass_rate' in df.columns:
        pass_rate = df['pass_rate']
        analysis['pass_rate'] = {
            'mean': pass_rate.mean(),
            'std': pass_rate.std(),
            'min': pass_rate.min(),
            'max': pass_rate.max(),
            'median': pass_rate.median()
        }

    return analysis


def create_summary_statistics(all_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Create a unified summary statistics DataFrame."""
    summary_rows = []

    for benchmark_type, df in all_data.items():
        if df.empty:
            continue

        for _, row in df.iterrows():
            summary_row = {
                'benchmark_type': benchmark_type,
                'engine_nfft': row['engine_nfft'],
                'engine_batch': row['engine_batch'],
                'source_file': row.get('source_file', 'unknown')
            }

            # Add benchmark-specific metrics
            if benchmark_type == 'throughput':
                summary_row.update({
                    'frames_per_second': row.get('frames_per_second', None),
                    'gb_per_second': row.get('gb_per_second', None),
                    'gpu_utilization': row.get('gpu_utilization', None)
                })
            elif benchmark_type == 'latency':
                summary_row.update({
                    'mean_latency_us': row.get('mean_latency_us', None),
                    'p95_latency_us': row.get('p95_latency_us', None),
                    'p99_latency_us': row.get('p99_latency_us', None)
                })
            elif benchmark_type == 'accuracy':
                summary_row.update({
                    'pass_rate': row.get('pass_rate', None),
                    'mean_snr_db': row.get('mean_snr_db', None),
                    'mean_error': row.get('mean_error', None)
                })

            summary_rows.append(summary_row)

    if not summary_rows:
        print("Warning: No data to summarize")
        return pd.DataFrame()

    summary_df = pd.DataFrame(summary_rows)
    print(f"Created summary with {len(summary_df)} total measurements")
    return summary_df


def main():
    """Main analysis function."""
    print("=" * 60)
    print("Ionosphere HPC Experiment Analysis")
    print("=" * 60)

    # Find all experiment data files
    experiment_files = find_experiment_data()

    if not experiment_files:
        print("No experiment data found in artifacts/data/")
        print("Make sure you've run some experiments first!")
        return

    # Load and analyze each benchmark type
    all_data = {}
    all_analyses = {}

    for benchmark_type, files in experiment_files.items():
        print(f"\nAnalyzing {benchmark_type} data...")
        df = load_and_combine_data(files)
        all_data[benchmark_type] = df

        if benchmark_type == 'throughput':
            analysis = analyze_throughput_data(df)
        elif benchmark_type == 'latency':
            analysis = analyze_latency_data(df)
        elif benchmark_type == 'accuracy':
            analysis = analyze_accuracy_data(df)
        else:
            analysis = {}

        all_analyses[benchmark_type] = analysis

        if analysis:
            print(f"  Total runs: {analysis.get('total_runs', 0)}")
            if 'best_performance' in analysis:
                best = analysis['best_performance']
                print(f"  Best performance: NFFT={best['nfft']}, Batch={best['batch']}, FPS={best['fps']:.1f}")
            if 'best_latency' in analysis:
                best = analysis['best_latency']
                print(f"  Best latency: NFFT={best['nfft']}, Batch={best['batch']}, Latency={best['latency_us']:.1f}us")

    # Create unified summary statistics
    print("\nCreating summary statistics...")
    summary_df = create_summary_statistics(all_data)

    if not summary_df.empty:
        # Save summary statistics
        output_dir = Path("artifacts/data")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "summary_statistics.csv"

        summary_df.to_csv(output_path, index=False)
        print(f"Saved summary statistics to: {output_path}")
        print(f"Summary contains {len(summary_df)} measurements across {summary_df['benchmark_type'].nunique()} benchmark types")

        # Print quick overview
        print("\nQuick Overview:")
        for benchmark_type in summary_df['benchmark_type'].unique():
            subset = summary_df[summary_df['benchmark_type'] == benchmark_type]
            print(f"  {benchmark_type}: {len(subset)} measurements")
            if benchmark_type == 'throughput' and 'frames_per_second' in subset.columns:
                fps_mean = subset['frames_per_second'].mean()
                print(f"    Average FPS: {fps_mean:.1f}")
    else:
        print("No data available for analysis")

    print("\nAnalysis complete!")


if __name__ == "__main__":
    main()
