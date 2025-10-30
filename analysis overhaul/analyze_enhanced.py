#!/usr/bin/env python
"""
Enhanced GPU Pipeline Analysis CLI
===================================

Command-line interface for comprehensive GPU benchmark analysis with
statistical rigor, caching, and advanced visualizations.

Usage:
    python analyze_enhanced.py [OPTIONS] COMMAND [ARGS]

Commands:
    analyze     Run full analysis on benchmark data
    compare     Compare two configurations statistically
    scaling     Analyze scaling patterns
    report      Generate comprehensive HTML report
    watch       Monitor directory for new results (real-time)

Examples:
    # Basic analysis
    python analyze_enhanced.py analyze --data-dir artifacts/data
    
    # With specific benchmarks
    python analyze_enhanced.py analyze --types latency throughput
    
    # Generate report
    python analyze_enhanced.py report --output report.html
    
    # Compare configurations
    python analyze_enhanced.py compare --config1 nfft=1024,channels=8 --config2 nfft=2048,channels=16
    
    # Scaling analysis
    python analyze_enhanced.py scaling --parameter nfft --metric mean_latency_us
    
    # Watch mode for live experiments
    python analyze_enhanced.py watch --interval 10
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.engine import AnalysisEngine
from analysis.models import BenchmarkType, ExperimentSummary
from analysis.visualization import ReportGenerator, VisualizationConfig


class DataLoader:
    """Unified data loader for various formats."""
    
    @staticmethod
    def load_from_directory(
        data_dir: Path,
        pattern: str = "*_summary_*.csv"
    ) -> pd.DataFrame:
        """Load and combine all matching CSV files."""
        
        files = list(data_dir.glob(pattern))
        if not files:
            raise ValueError(f"No data files found matching {pattern} in {data_dir}")
        
        print(f"Found {len(files)} data files")
        
        dataframes = []
        for file_path in sorted(files):
            try:
                df = pd.read_csv(file_path)
                
                # Infer benchmark type from filename
                filename = file_path.stem
                if 'throughput' in filename.lower():
                    df['benchmark_type'] = 'throughput'
                elif 'latency' in filename.lower():
                    df['benchmark_type'] = 'latency'
                elif 'accuracy' in filename.lower():
                    df['benchmark_type'] = 'accuracy'
                elif 'realtime' in filename.lower():
                    df['benchmark_type'] = 'realtime'
                
                # Add source file for traceability
                df['source_file'] = file_path.name
                
                dataframes.append(df)
                print(f"  Loaded: {file_path.name} ({len(df)} rows)")
                
            except Exception as e:
                print(f"  Warning: Could not load {file_path.name}: {e}")
        
        if not dataframes:
            raise ValueError("No valid data could be loaded")
        
        combined = pd.concat(dataframes, ignore_index=True)
        print(f"Combined dataset: {len(combined)} total measurements")
        
        return combined
    
    @staticmethod
    def load_from_mlflow(
        tracking_uri: str = "file:./mlruns",
        experiment_name: Optional[str] = None
    ) -> pd.DataFrame:
        """Load data from MLflow tracking server."""
        
        try:
            import mlflow
        except ImportError:
            raise ImportError("MLflow not installed. Install with: pip install mlflow")
        
        mlflow.set_tracking_uri(tracking_uri)
        
        # Get experiment
        if experiment_name:
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if not experiment:
                raise ValueError(f"Experiment '{experiment_name}' not found")
            experiment_id = experiment.experiment_id
        else:
            # Use default experiment
            experiment_id = "0"
        
        # Get all runs
        runs = mlflow.search_runs(experiment_ids=[experiment_id])
        
        if runs.empty:
            raise ValueError("No runs found in MLflow experiment")
        
        print(f"Found {len(runs)} runs in MLflow")
        
        # Extract relevant columns
        metric_cols = [col for col in runs.columns if col.startswith('metrics.')]
        param_cols = [col for col in runs.columns if col.startswith('params.')]
        
        # Rename columns
        for col in metric_cols:
            new_name = col.replace('metrics.', '')
            runs[new_name] = runs[col]
        
        for col in param_cols:
            new_name = col.replace('params.', '')
            runs[new_name] = runs[col]
        
        # Convert engine parameters
        if 'engine.nfft' in runs.columns:
            runs['engine_nfft'] = runs['engine.nfft'].astype(int)
        if 'engine.channels' in runs.columns:
            runs['engine_channels'] = runs['engine.channels'].astype(int)
        
        return runs
    
    @staticmethod
    def validate_data(df: pd.DataFrame) -> None:
        """Validate that data has required columns."""
        
        required_cols = ['engine_nfft', 'engine_channels']
        missing = [col for col in required_cols if col not in df.columns]
        
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        # Check for at least one metric column
        metric_keywords = ['latency', 'fps', 'throughput', 'accuracy', 'pass_rate', 'compliance']
        has_metric = any(
            any(keyword in col.lower() for keyword in metric_keywords)
            for col in df.columns
        )
        
        if not has_metric:
            print("Warning: No standard metric columns detected")
        
        print(f"Data validation passed: {len(df)} rows, {len(df.columns)} columns")


class EnhancedAnalysisCLI:
    """Main CLI application."""
    
    def __init__(self):
        self.engine = AnalysisEngine()
        self.report_gen = ReportGenerator()
        self.data: Optional[pd.DataFrame] = None
        self.summary: Optional[ExperimentSummary] = None
    
    def cmd_analyze(self, args: argparse.Namespace) -> None:
        """Run full analysis on benchmark data."""
        
        print("=" * 60)
        print("GPU BENCHMARK ANALYSIS")
        print("=" * 60)
        
        # Load data
        data_dir = Path(args.data_dir)
        if not data_dir.exists():
            print(f"Error: Data directory not found: {data_dir}")
            sys.exit(1)
        
        self.data = DataLoader.load_from_directory(data_dir, args.pattern)
        DataLoader.validate_data(self.data)
        
        # Filter by benchmark types if specified
        if args.types:
            print(f"Filtering to benchmark types: {args.types}")
            if 'benchmark_type' in self.data.columns:
                self.data = self.data[self.data['benchmark_type'].isin(args.types)]
                print(f"Filtered to {len(self.data)} measurements")
        
        # Generate summary
        print("\nRunning analysis...")
        self.summary = self.engine.generate_summary(
            self.data,
            experiment_name=args.name or "GPU Benchmark Analysis"
        )
        
        # Display results
        self._display_summary(self.summary)
        
        # Save results if requested
        if args.output:
            output_path = Path(args.output)
            self._save_results(self.summary, output_path)
    
    def cmd_compare(self, args: argparse.Namespace) -> None:
        """Compare two configurations statistically."""
        
        if self.data is None:
            print("Loading data first...")
            self.data = DataLoader.load_from_directory(Path(args.data_dir))
        
        # Parse configurations
        config1 = self._parse_config(args.config1)
        config2 = self._parse_config(args.config2)
        
        print(f"\nComparing configurations:")
        print(f"  Config 1: {config1}")
        print(f"  Config 2: {config2}")
        
        # Determine metric
        metric = args.metric
        if not metric:
            # Auto-detect primary metric
            for col in ['mean_latency_us', 'frames_per_second', 'pass_rate']:
                if col in self.data.columns:
                    metric = col
                    break
        
        if not metric:
            print("Error: No suitable metric found for comparison")
            sys.exit(1)
        
        print(f"  Metric: {metric}")
        
        # Run comparison
        comparison = self.engine.compare_configurations(
            self.data, config1, config2, metric
        )
        
        if comparison is None:
            print("Error: Could not perform comparison (insufficient data)")
            sys.exit(1)
        
        # Display results
        print("\n" + "=" * 60)
        print("STATISTICAL COMPARISON RESULTS")
        print("=" * 60)
        
        print(f"\nTest: {comparison.test_name}")
        print(f"P-value: {comparison.p_value:.6f}")
        print(f"Significant: {'YES' if comparison.is_significant else 'NO'} (α=0.05)")
        print(f"Effect size (Cohen's d): {comparison.effect_size:.3f}")
        
        print(f"\nBaseline (Config 1):")
        print(f"  Mean: {comparison.baseline.mean:.2f} ± {comparison.baseline.std:.2f}")
        print(f"  Median: {comparison.baseline.median:.2f}")
        print(f"  95% CI: [{comparison.baseline.confidence_interval[0]:.2f}, "
              f"{comparison.baseline.confidence_interval[1]:.2f}]")
        
        print(f"\nTarget (Config 2):")
        print(f"  Mean: {comparison.target.mean:.2f} ± {comparison.target.std:.2f}")
        print(f"  Median: {comparison.target.median:.2f}")
        print(f"  95% CI: [{comparison.target.confidence_interval[0]:.2f}, "
              f"{comparison.target.confidence_interval[1]:.2f}]")
        
        print(f"\nDifference:")
        print(f"  Mean diff: {comparison.mean_diff:.2f} ({comparison.mean_diff_pct:+.1f}%)")
        print(f"  Median diff: {comparison.median_diff:.2f} ({comparison.median_diff_pct:+.1f}%)")
        
        # Generate visualization
        if args.plot:
            from analysis.visualization import StatisticalPlotter
            
            # Get raw data for plotting
            data1 = self._filter_data(self.data, config1)[metric].values
            data2 = self._filter_data(self.data, config2)[metric].values
            
            plotter = StatisticalPlotter()
            fig = plotter.plot_distribution_comparison(
                data1, data2,
                labels=("Config 1", "Config 2"),
                title=f"Comparison: {metric}"
            )
            
            if args.plot == "show":
                fig.show()
            else:
                fig.write_html(args.plot)
                print(f"\nPlot saved to: {args.plot}")
    
    def cmd_scaling(self, args: argparse.Namespace) -> None:
        """Analyze scaling patterns."""
        
        if self.data is None:
            print("Loading data first...")
            self.data = DataLoader.load_from_directory(Path(args.data_dir))
        
        print(f"\nAnalyzing scaling for parameter: {args.parameter}")
        print(f"Metric: {args.metric}")
        
        # Run scaling analysis
        analyses = self.engine.analyze_scaling(
            self.data,
            parameters=[args.parameter],
            metrics=[args.metric] if args.metric else None
        )
        
        if not analyses:
            print("No scaling patterns found")
            sys.exit(1)
        
        for analysis in analyses:
            print("\n" + "=" * 60)
            print(f"SCALING ANALYSIS: {analysis.parameter}")
            print("=" * 60)
            
            print(f"\nScaling Type: {analysis.scaling_type}")
            print(f"Scaling Exponent: {analysis.scaling_exponent:.3f}")
            print(f"Correlation: {analysis.correlation:.3f}")
            print(f"Model R²: {analysis.model_r2:.3f}")
            print(f"Model RMSE: {analysis.model_rmse:.2f}")
            
            if analysis.saturation_point:
                print(f"Saturation Point: {analysis.saturation_point:.0f}")
            
            print(f"\nModel: y = {analysis.model_params['coefficient']:.2f} * x^{analysis.model_params['exponent']:.2f}")
            
            # Generate visualization
            if args.plot:
                from analysis.visualization import PerformancePlotter
                
                plotter = PerformancePlotter()
                fig = plotter.plot_scaling_analysis(analysis)
                
                if args.plot == "show":
                    fig.show()
                else:
                    fig.write_html(args.plot)
                    print(f"\nPlot saved to: {args.plot}")
    
    def cmd_report(self, args: argparse.Namespace) -> None:
        """Generate comprehensive HTML report."""
        
        # Run analysis if not already done
        if self.summary is None:
            print("Running analysis first...")
            self.cmd_analyze(args)
        
        output_path = Path(args.output)
        
        print(f"\nGenerating HTML report...")
        self.report_gen.generate_full_report(
            self.summary,
            output_path,
            include_raw_data=args.include_raw
        )
        
        print(f"Report saved to: {output_path}")
        
        # Open in browser if requested
        if args.open:
            import webbrowser
            webbrowser.open(str(output_path.absolute()))
    
    def cmd_watch(self, args: argparse.Namespace) -> None:
        """Monitor directory for new results."""
        
        data_dir = Path(args.data_dir)
        print(f"Watching directory: {data_dir}")
        print(f"Checking every {args.interval} seconds")
        print("Press Ctrl+C to stop\n")
        
        last_files = set()
        
        try:
            while True:
                current_files = set(data_dir.glob(args.pattern))
                new_files = current_files - last_files
                
                if new_files:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] New files detected:")
                    for f in new_files:
                        print(f"  + {f.name}")
                    
                    # Re-run analysis
                    try:
                        self.data = DataLoader.load_from_directory(data_dir, args.pattern)
                        self.summary = self.engine.generate_summary(self.data)
                        
                        # Display key metrics
                        print("\nUpdated metrics:")
                        for insight in self.summary.key_insights[:3]:
                            print(f"  • {insight}")
                        
                        # Auto-generate report if requested
                        if args.auto_report:
                            report_path = Path(args.auto_report)
                            self.report_gen.generate_full_report(
                                self.summary,
                                report_path
                            )
                            print(f"Report updated: {report_path}")
                    
                    except Exception as e:
                        print(f"Error processing new data: {e}")
                    
                    last_files = current_files
                
                time.sleep(args.interval)
        
        except KeyboardInterrupt:
            print("\nStopping watch mode")
    
    def _display_summary(self, summary: ExperimentSummary) -> None:
        """Display analysis summary to console."""
        
        print("\n" + "=" * 60)
        print("ANALYSIS SUMMARY")
        print("=" * 60)
        
        print(f"\nExperiment: {summary.experiment_name}")
        print(f"Timestamp: {summary.timestamp}")
        print(f"Total Measurements: {summary.total_measurements}")
        print(f"Configurations Tested: {len(summary.configurations_tested)}")
        
        # Display optimal configurations
        if summary.optimal_configs:
            print("\nOptimal Configurations:")
            for bench_type, config in summary.optimal_configs.items():
                print(f"  {bench_type}: NFFT={config.nfft}, Channels={config.channels}")
        
        # Display key insights
        if summary.key_insights:
            print("\nKey Insights:")
            for i, insight in enumerate(summary.key_insights[:5], 1):
                print(f"  {i}. {insight}")
        
        # Display warnings
        if summary.warnings:
            print("\nWarnings:")
            for warning in summary.warnings:
                print(f"  ⚠ {warning}")
        
        # Display scaling patterns
        if summary.scaling_analyses:
            print("\nScaling Patterns Detected:")
            for analysis in summary.scaling_analyses[:3]:
                print(f"  • {analysis.parameter}: {analysis.scaling_type} "
                      f"(exponent={analysis.scaling_exponent:.2f}, R²={analysis.model_r2:.3f})")
    
    def _save_results(self, summary: ExperimentSummary, output_path: Path) -> None:
        """Save analysis results to file."""
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if output_path.suffix == '.json':
            # Save as JSON
            with open(output_path, 'w') as f:
                json.dump(summary.dict(), f, indent=2, default=str)
            print(f"Results saved to: {output_path}")
        
        elif output_path.suffix == '.csv':
            # Save as CSV
            df = summary.to_dataframe()
            df.to_csv(output_path, index=False)
            print(f"Results saved to: {output_path}")
        
        else:
            print(f"Unsupported output format: {output_path.suffix}")
    
    def _parse_config(self, config_str: str) -> Dict[str, Any]:
        """Parse configuration string like 'nfft=1024,channels=8'."""
        
        config = {}
        for item in config_str.split(','):
            if '=' not in item:
                continue
            key, value = item.split('=', 1)
            
            # Try to convert to appropriate type
            try:
                # Try int first
                config[key] = int(value)
            except ValueError:
                try:
                    # Try float
                    config[key] = float(value)
                except ValueError:
                    # Keep as string
                    config[key] = value
        
        return config
    
    def _filter_data(self, data: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
        """Filter dataframe by configuration."""
        
        filtered = data.copy()
        for key, value in config.items():
            if key in filtered.columns:
                # Handle column name variations
                col_name = key
                if key == 'nfft' and 'engine_nfft' in filtered.columns:
                    col_name = 'engine_nfft'
                elif key == 'channels' and 'engine_channels' in filtered.columns:
                    col_name = 'engine_channels'
                
                filtered = filtered[filtered[col_name] == value]
        
        return filtered


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    
    parser = argparse.ArgumentParser(
        description="Enhanced GPU Pipeline Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Global options
    parser.add_argument(
        "--data-dir",
        default="artifacts/data",
        help="Directory containing benchmark data"
    )
    parser.add_argument(
        "--pattern",
        default="*_summary_*.csv",
        help="File pattern for data files"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Run full analysis")
    analyze_parser.add_argument(
        "--name",
        help="Experiment name"
    )
    analyze_parser.add_argument(
        "--types",
        nargs="+",
        choices=["latency", "throughput", "accuracy", "realtime"],
        help="Benchmark types to analyze"
    )
    analyze_parser.add_argument(
        "--output", "-o",
        help="Save results to file (JSON or CSV)"
    )
    
    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Compare configurations")
    compare_parser.add_argument(
        "--config1",
        required=True,
        help="First configuration (e.g., 'nfft=1024,channels=8')"
    )
    compare_parser.add_argument(
        "--config2",
        required=True,
        help="Second configuration"
    )
    compare_parser.add_argument(
        "--metric",
        help="Metric to compare (auto-detected if not specified)"
    )
    compare_parser.add_argument(
        "--plot",
        nargs="?",
        const="show",
        help="Generate plot (specify filename or 'show' for display)"
    )
    
    # Scaling command
    scaling_parser = subparsers.add_parser("scaling", help="Analyze scaling")
    scaling_parser.add_argument(
        "--parameter",
        default="engine_nfft",
        help="Parameter to analyze"
    )
    scaling_parser.add_argument(
        "--metric",
        help="Metric to analyze"
    )
    scaling_parser.add_argument(
        "--plot",
        nargs="?",
        const="show",
        help="Generate plot"
    )
    
    # Report command
    report_parser = subparsers.add_parser("report", help="Generate HTML report")
    report_parser.add_argument(
        "--output", "-o",
        default="analysis_report.html",
        help="Output file path"
    )
    report_parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Include raw data in report"
    )
    report_parser.add_argument(
        "--open",
        action="store_true",
        help="Open report in browser"
    )
    
    # Watch command
    watch_parser = subparsers.add_parser("watch", help="Monitor for new results")
    watch_parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Check interval in seconds"
    )
    watch_parser.add_argument(
        "--auto-report",
        help="Auto-generate report to this file"
    )
    
    return parser


def main():
    """Main entry point."""
    
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Create CLI instance
    cli = EnhancedAnalysisCLI()
    
    # Execute command
    try:
        if args.command == "analyze":
            cli.cmd_analyze(args)
        elif args.command == "compare":
            cli.cmd_compare(args)
        elif args.command == "scaling":
            cli.cmd_scaling(args)
        elif args.command == "report":
            cli.cmd_report(args)
        elif args.command == "watch":
            cli.cmd_watch(args)
        else:
            print(f"Unknown command: {args.command}")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\nOperation cancelled")
        sys.exit(130)
    except Exception as e:
        if args.verbose:
            import traceback
            traceback.print_exc()
        else:
            print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
