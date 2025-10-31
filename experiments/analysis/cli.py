"""
Analysis CLI
============

Command-line interface for benchmark analysis.

Usage:
    python -m experiments.analysis.cli analyze <data_dir>
    python -m experiments.analysis.cli report <data_file> --output report.html
    python -m experiments.analysis.cli compare <config1> <config2> --metric latency
"""

import argparse
from pathlib import Path
from typing import Optional

import pandas as pd

from .analyzer import AnalysisEngine
from .models import BenchmarkType
from .reporting import generate_both_reports
from .visualization import plot_latency_analysis, plot_throughput_analysis, plot_ionosphere_metrics


def load_data(data_path: Path) -> pd.DataFrame:
    """Load benchmark data from CSV or directory of CSVs."""
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
            elif 'accuracy' in csv_file.name:
                df['benchmark_type'] = BenchmarkType.ACCURACY.value

            dataframes.append(df)

        return pd.concat(dataframes, ignore_index=True)
    else:
        raise ValueError(f"Path not found: {data_path}")


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


def cmd_report(args):
    """Generate HTML reports."""
    data_path = Path(args.data_path)
    output_dir = Path(args.output_dir) if args.output_dir else Path("artifacts/reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading data from {data_path}...")
    data = load_data(data_path)
    print(f"Loaded {len(data)} measurements")

    print("Generating reports...")
    general_path, iono_path = generate_both_reports(data, output_dir)

    print(f"\nReports generated:")
    print(f"  General: {general_path}")
    print(f"  Ionosphere: {iono_path}")

    # Generate visualizations
    if args.generate_plots:
        plot_dir = output_dir / "plots"
        plot_dir.mkdir(parents=True, exist_ok=True)

        print("\nGenerating plots...")

        if 'mean_latency_us' in data.columns:
            paths = plot_latency_analysis(data, plot_dir)
            print(f"  Latency plots: {len(paths)} generated")

        if 'frames_per_second' in data.columns:
            paths = plot_throughput_analysis(data, plot_dir)
            print(f"  Throughput plots: {len(paths)} generated")

        if 'rtf' in data.columns and 'freq_resolution_hz' in data.columns:
            paths = plot_ionosphere_metrics(data, plot_dir)
            print(f"  Ionosphere plots: {len(paths)} generated")


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

    print(f"Comparing configurations:")
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
            print(f"\nScaling Analysis:")
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

    # Report command
    report_parser = subparsers.add_parser('report', help='Generate HTML reports')
    report_parser.add_argument('data_path', type=str, help='Path to data file or directory')
    report_parser.add_argument('--output-dir', '-o', type=str, help='Output directory')
    report_parser.add_argument('--generate-plots', action='store_true', help='Generate visualization plots')

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
    elif args.command == 'report':
        cmd_report(args)
    elif args.command == 'compare':
        cmd_compare(args)
    elif args.command == 'scaling':
        cmd_scaling(args)


if __name__ == '__main__':
    main()
