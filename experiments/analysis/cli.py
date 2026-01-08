"""
Analysis CLI
============

Command-line interface for benchmark analysis.

For interactive reporting, use the Streamlit dashboard: iono dashboard

Usage:
    python -m experiments.analysis.cli analyze <data_dir>
    python -m experiments.analysis.cli compare <config1> <config2> --metric latency
    python -m experiments.analysis.cli scaling <data_dir> --parameter engine_nfft --metric latency
"""

import argparse
from pathlib import Path

import pandas as pd

from .analyzer import AnalysisEngine
from .models import BenchmarkType


def load_data(data_path: Path) -> pd.DataFrame:
    """
    Load benchmark data from CSV or directory of CSVs.

    Automatically aggregates multiple CSV files using glob pattern (*_summary_*.csv).
    Each benchmark configuration writes to a unique file during multirun sweeps:

        Pattern: {benchmark}_summary_{nfft}_{channels}_{overlap}_{mode}.csv
        Example: latency_summary_4096_2_0p7500_streaming.csv

    This function merges all matching files into a single DataFrame for analysis,
    adding metadata columns and harmonizing schema for backward compatibility.

    Args:
        data_path: Path to single CSV file or directory containing multiple CSVs.
                   When directory, glob pattern "*_summary_*.csv" matches all benchmark files.

    Returns:
        Merged DataFrame with additional columns:
            - 'source_file': Original CSV filename
            - 'benchmark_type': Inferred from filename (latency, throughput, realtime, accuracy)

        Schema is harmonized across all files for backward compatibility.

    Raises:
        ValueError: If path doesn't exist or no CSV files found in directory.

    Examples:
        >>> # Load all benchmarks from data directory
        >>> df = load_data(Path("artifacts/data"))
        >>> print(f"Loaded {len(df)} rows from {df['source_file'].nunique()} files")

        >>> # Load single CSV file
        >>> df = load_data(Path("artifacts/data/latency_summary_4096_2_0p7500_streaming.csv"))

    See Also:
        - Multirun safety: tests/test_csv_multirun_safety.py
        - Design rationale: docs/benchmarking/csv-file-organization.md
    """
    if data_path.is_file():
        return pd.read_csv(data_path)
    elif data_path.is_dir():
        # Load all CSV files in directory
        csv_files = list(data_path.glob("*_summary_*.csv"))
        if not csv_files:
            raise ValueError(f"No benchmark CSV files found in {data_path}")

        dataframes = []
        for csv_file in csv_files:
            df = pd.read_csv(csv_file)
            df['source_file'] = csv_file.name

            # Infer benchmark type from filename
            if 'latency' in csv_file.name:
                df['benchmark_type'] = BenchmarkType.LATENCY.value
            elif 'throughput' in csv_file.name:
                df['benchmark_type'] = BenchmarkType.THROUGHPUT.value
            elif 'realtime' in csv_file.name:
                df['benchmark_type'] = 'realtime'
            elif 'accuracy' in csv_file.name:
                df['benchmark_type'] = BenchmarkType.ACCURACY.value

            # Harmonize schema for legacy CSVs (backward compatibility)
            df = _harmonize_schema(df, csv_file.name)

            dataframes.append(df)

        return pd.concat(dataframes, ignore_index=True)
    else:
        raise ValueError(f"Path not found: {data_path}")


def _harmonize_schema(df: pd.DataFrame, filename: str = '') -> pd.DataFrame:
    """
    Add missing columns to legacy CSVs for backward compatibility.

    This allows old realtime CSVs (before schema fix) to work with dashboard.
    New CSVs will have all columns, so this is a no-op for them.
    """
    # Add missing metadata columns with fallback values
    if 'experiment_group' not in df.columns:
        df['experiment_group'] = 'legacy'

    if 'sample_rate_category' not in df.columns:
        # Infer from sample_rate_hz if available
        if 'engine_sample_rate_hz' in df.columns:
            df['sample_rate_category'] = df['engine_sample_rate_hz'].apply(
                lambda x: f"{int(x/1000)}kHz" if pd.notna(x) else 'unknown'
            )
        else:
            df['sample_rate_category'] = 'unknown'

    # Add missing engine config columns
    if 'engine_overlap' not in df.columns:
        df['engine_overlap'] = 0.0  # Default for realtime benchmarks

    if 'engine_sample_rate_hz' not in df.columns:
        df['engine_sample_rate_hz'] = 48000  # Default ionosphere sample rate

    if 'engine_mode' not in df.columns:
        # Infer from benchmark type
        if 'realtime' in filename.lower():
            df['engine_mode'] = 'streaming'
        else:
            df['engine_mode'] = 'batch'

    # Calculate derived metrics if missing
    if 'hop_size' not in df.columns:
        if 'engine_nfft' in df.columns and 'engine_overlap' in df.columns:
            df['hop_size'] = (df['engine_nfft'] * (1 - df['engine_overlap'])).astype(int)
        else:
            df['hop_size'] = pd.NA

    if 'time_resolution_ms' not in df.columns:
        if 'engine_nfft' in df.columns and 'engine_sample_rate_hz' in df.columns:
            df['time_resolution_ms'] = (df['engine_nfft'] / df['engine_sample_rate_hz']) * 1000
        else:
            df['time_resolution_ms'] = pd.NA

    if 'freq_resolution_hz' not in df.columns:
        if 'engine_sample_rate_hz' in df.columns and 'engine_nfft' in df.columns:
            df['freq_resolution_hz'] = df['engine_sample_rate_hz'] / df['engine_nfft']
        else:
            df['freq_resolution_hz'] = pd.NA

    # Calculate RTF if missing (for realtime benchmarks)
    if 'rtf' not in df.columns:
        if 'mean_latency_ms' in df.columns and 'hop_size' in df.columns and 'engine_sample_rate_hz' in df.columns:
            # RTF = mean_latency / frame_duration
            frame_duration_ms = (df['hop_size'] / df['engine_sample_rate_hz']) * 1000
            df['rtf'] = df['mean_latency_ms'] / frame_duration_ms
            # Replace inf/nan with high value
            df['rtf'] = df['rtf'].replace([float('inf'), -float('inf')], float('nan')).fillna(999.0)
        else:
            df['rtf'] = pd.NA

    # Harmonize latency units (convert ms to us where needed)
    if 'mean_latency_ms' in df.columns and 'mean_latency_us' not in df.columns:
        df['mean_latency_us'] = df['mean_latency_ms'] * 1000

    if 'p99_latency_ms' in df.columns and 'p99_latency_us' not in df.columns:
        df['p99_latency_us'] = df['p99_latency_ms'] * 1000

    # Add stage metrics columns with defaults (for backward compatibility)
    # These are only populated when measure_components=true in benchmark config
    stage_metric_cols = {
        'stage_window_us': 0.0,
        'stage_fft_us': 0.0,
        'stage_magnitude_us': 0.0,
        'stage_overhead_us': 0.0,
        'stage_total_measured_us': 0.0,
        'stage_metrics_enabled': False
    }

    for col, default_val in stage_metric_cols.items():
        if col not in df.columns:
            df[col] = default_val

    return df


def cmd_analyze(args):
    """Analyze benchmark data and generate summary."""
    data_path = Path(args.data_path)
    output_path = Path(args.output) if args.output else Path("artifacts/analysis/summary.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading data from {data_path}...")
    data = load_data(data_path)
    print(f"Loaded {len(data)} measurements")

    print("Analyzing...")
    analyzer = AnalysisEngine(cache_dir=Path(args.cache_dir) if args.cache_dir else None)
    summary = analyzer.generate_summary(data, experiment_name=args.experiment_name or "Benchmark Analysis")

    # Save summary
    output_path.write_text(summary.model_dump_json(indent=2), encoding='utf-8')
    print(f"Summary saved to {output_path}")

    # Print key insights
    print("\nKey Insights:")
    for insight in summary.key_insights:
        print(f"  - {insight}")


def cmd_compare(args):
    """Compare two configurations statistically."""
    data_path = Path(args.data_path)
    metric = args.metric

    print(f"Loading data from {data_path}...")
    data = load_data(data_path)

    # Parse config strings (format: "nfft=1024,channels=2")
    config1 = dict(pair.split('=') for pair in args.config1.split(','))
    config2 = dict(pair.split('=') for pair in args.config2.split(','))

    # Convert to proper types
    config1 = {k: int(v) if k in ['engine_nfft', 'engine_channels'] else float(v)
               for k, v in config1.items()}
    config2 = {k: int(v) if k in ['engine_nfft', 'engine_channels'] else float(v)
               for k, v in config2.items()}

    print("Comparing configurations:")
    print(f"  Config 1: {config1}")
    print(f"  Config 2: {config2}")
    print(f"  Metric: {metric}")

    analyzer = AnalysisEngine()
    comparison = analyzer.compare_configurations(data, config1, config2, metric)

    if comparison:
        print("\nComparison Results:")
        print(f"  Test: {comparison.test_name}")
        print(f"  p-value: {comparison.p_value:.6f}")
        print(f"  Significant: {comparison.is_significant}")
        print(f"  Mean difference: {comparison.mean_diff:.4f} ({comparison.mean_diff_pct:+.2f}%)")
        print(f"  Effect size (Cohen's d): {comparison.effect_size:.4f}")
        print(f"  Improvement: {comparison.improvement}")
    else:
        print("Comparison failed - insufficient data")


def cmd_scaling(args):
    """Analyze scaling patterns."""
    data_path = Path(args.data_path)
    parameter = args.parameter
    metric = args.metric

    print(f"Loading data from {data_path}...")
    data = load_data(data_path)

    print(f"Analyzing {metric} scaling with {parameter}...")
    analyzer = AnalysisEngine()
    analyses = analyzer.analyze_scaling(data, parameters=[parameter], metrics=[metric])

    if analyses:
        for analysis in analyses:
            print("\nScaling Analysis:")
            print(f"  Parameter: {analysis.parameter}")
            print(f"  Scaling type: {analysis.scaling_type}")
            print(f"  Scaling exponent: {analysis.scaling_exponent:.4f}")
            print(f"  Correlation: {analysis.correlation:.4f}")
            print(f"  R²: {analysis.model_r2:.4f}")
            if analysis.saturation_point:
                print(f"  Saturation point: {analysis.saturation_point:.2f}")
    else:
        print("No scaling analysis possible - insufficient data points")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Ionosense HPC Benchmark Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze benchmark data')
    analyze_parser.add_argument('data_path', type=str, help='Path to data file or directory')
    analyze_parser.add_argument('--output', '-o', type=str, help='Output file path')
    analyze_parser.add_argument('--experiment-name', type=str, help='Experiment name')
    analyze_parser.add_argument('--cache-dir', type=str, help='Cache directory for analysis results')

    # Compare command
    compare_parser = subparsers.add_parser('compare', help='Compare two configurations')
    compare_parser.add_argument('data_path', type=str, help='Path to data file or directory')
    compare_parser.add_argument('config1', type=str, help='First config (e.g., "engine_nfft=1024,engine_channels=2")')
    compare_parser.add_argument('config2', type=str, help='Second config')
    compare_parser.add_argument('--metric', '-m', type=str, required=True, help='Metric to compare')

    # Scaling command
    scaling_parser = subparsers.add_parser('scaling', help='Analyze scaling patterns')
    scaling_parser.add_argument('data_path', type=str, help='Path to data file or directory')
    scaling_parser.add_argument('--parameter', '-p', type=str, default='engine_nfft',
                                help='Parameter to analyze (default: engine_nfft)')
    scaling_parser.add_argument('--metric', '-m', type=str, required=True,
                                help='Metric to analyze')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Dispatch to command handlers
    if args.command == 'analyze':
        cmd_analyze(args)
    elif args.command == 'compare':
        cmd_compare(args)
    elif args.command == 'scaling':
        cmd_scaling(args)


if __name__ == '__main__':
    main()
