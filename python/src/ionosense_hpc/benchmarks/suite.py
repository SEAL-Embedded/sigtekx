"""
python/src/ionosense_hpc/benchmarks/suite.py
--------------------------------------------------------------------------------
Benchmark suite orchestrator using the new BaseBenchmark infrastructure.
Manages sequential execution of multiple benchmarks with unified reporting.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ionosense_hpc.benchmarks.accuracy import AccuracyBenchmark
from ionosense_hpc.benchmarks.base import (
    BenchmarkConfig,
    BenchmarkContext,
    BenchmarkResult,
    save_benchmark_results,
)
from ionosense_hpc.benchmarks.latency import LatencyBenchmark, StreamingLatencyBenchmark
from ionosense_hpc.benchmarks.realtime import RealtimeBenchmark
from ionosense_hpc.benchmarks.throughput import ScalingBenchmark, ThroughputBenchmark
from ionosense_hpc.config import Presets
from ionosense_hpc.utils import logger


@dataclass
class SuiteConfig:
    """Configuration for benchmark suite execution."""

    name: str = "comprehensive_suite"
    description: str = "Full benchmark suite for performance evaluation"

    # Benchmark selection
    benchmarks: list[str] = None  # None means all
    exclude: list[str] = None

    # Execution control
    stop_on_failure: bool = False
    save_intermediate: bool = True
    parallel: bool = False  # Future feature

    # Output configuration
    output_dir: str = "./benchmark_results"
    generate_report: bool = True
    report_format: str = "pdf"

    # Global overrides
    global_iterations: int | None = None
    global_warmup: int | None = None

    def __post_init__(self):
        if self.benchmarks is None:
            self.benchmarks = ['latency', 'throughput', 'realtime', 'accuracy']


class BenchmarkSuite:
    """
    Orchestrates execution of multiple benchmarks with unified reporting.
    
    This class manages the sequential execution of benchmarks, handles
    failures gracefully, and produces comprehensive reports suitable
    for publication or analysis.
    """

    # Registry of available benchmarks
    BENCHMARK_REGISTRY = {
        'latency': LatencyBenchmark,
        'latency_streaming': StreamingLatencyBenchmark,
        'throughput': ThroughputBenchmark,
        'scaling': ScalingBenchmark,
        'realtime': RealtimeBenchmark,
        'accuracy': AccuracyBenchmark,
    }

    def __init__(self, config: SuiteConfig | dict | str | None = None):
        """
        Initialize suite with configuration.
        
        Args:
            config: SuiteConfig, dict, YAML file path, or None for defaults
        """
        if isinstance(config, str):
            config = self._load_config(config)
        elif isinstance(config, dict):
            config = SuiteConfig(**config)
        elif config is None:
            config = SuiteConfig()

        self.config = config
        self.context = BenchmarkContext()
        self.results: list[BenchmarkResult] = []
        self.suite_metadata = {
            'name': self.config.name,
            'description': self.config.description,
            'start_time': None,
            'end_time': None,
            'total_duration_s': 0,
            'environment': self.context.to_dict()
        }

        # Create output directory
        self.output_dir = Path(self.config.output_dir) / f"{self.config.name}_{datetime.now():%Y%m%d_%H%M%S}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Save suite configuration
        self._save_suite_config()

    def _load_config(self, path: str) -> SuiteConfig:
        """Load configuration from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return SuiteConfig(**data)

    def _save_suite_config(self):
        """Save suite configuration for reproducibility."""
        config_path = self.output_dir / 'suite_config.json'
        with open(config_path, 'w') as f:
            json.dump({
                'config': self.config.__dict__,
                'context': self.context.to_dict()
            }, f, indent=2, default=str)

    def _get_benchmarks_to_run(self) -> list[str]:
        """Determine which benchmarks to run based on configuration."""
        benchmarks = self.config.benchmarks.copy()

        # Remove excluded benchmarks
        if self.config.exclude:
            benchmarks = [b for b in benchmarks if b not in self.config.exclude]

        # Validate benchmark names
        invalid = [b for b in benchmarks if b not in self.BENCHMARK_REGISTRY]
        if invalid:
            logger.warning(f"Unknown benchmarks will be skipped: {invalid}")
            benchmarks = [b for b in benchmarks if b in self.BENCHMARK_REGISTRY]

        return benchmarks

    def _create_benchmark_config(self, benchmark_name: str) -> BenchmarkConfig:
        """Create configuration for a specific benchmark."""
        # Start with defaults for the benchmark type
        base_config = {
            'name': f"{self.config.name}_{benchmark_name}",
            'iterations': 1000,
            'warmup_iterations': 100
        }

        # Apply global overrides
        if self.config.global_iterations is not None:
            base_config['iterations'] = self.config.global_iterations
        if self.config.global_warmup is not None:
            base_config['warmup_iterations'] = self.config.global_warmup

        # Set appropriate engine config based on benchmark type
        if 'latency' in benchmark_name or 'realtime' in benchmark_name:
            base_config['engine_config'] = Presets.realtime().model_dump()
        elif 'throughput' in benchmark_name or 'scaling' in benchmark_name:
            base_config['engine_config'] = Presets.throughput().model_dump()
        elif 'accuracy' in benchmark_name:
            base_config['engine_config'] = Presets.validation().model_dump()

        return BenchmarkConfig(**base_config)

    def run(self) -> dict[str, Any]:
        """
        Execute the benchmark suite.
        
        Returns:
            Dictionary containing all results and metadata
        """
        logger.info(f"Starting benchmark suite: {self.config.name}")
        logger.info(f"Output directory: {self.output_dir}")

        self.suite_metadata['start_time'] = datetime.now().isoformat()
        suite_start = time.perf_counter()

        benchmarks_to_run = self._get_benchmarks_to_run()
        logger.info(f"Will run {len(benchmarks_to_run)} benchmarks: {benchmarks_to_run}")

        failed_benchmarks = []

        for idx, benchmark_name in enumerate(benchmarks_to_run, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Running {idx}/{len(benchmarks_to_run)}: {benchmark_name}")
            logger.info(f"{'='*60}")

            try:
                # Get benchmark class
                benchmark_class = self.BENCHMARK_REGISTRY[benchmark_name]

                # Create configuration
                config = self._create_benchmark_config(benchmark_name)

                # Instantiate and run benchmark
                benchmark = benchmark_class(config)
                result = benchmark.run()

                # Add suite metadata to result
                result.metadata['suite'] = self.config.name
                result.metadata['benchmark_index'] = idx

                # Store result
                self.results.append(result)

                # Save intermediate results if configured
                if self.config.save_intermediate:
                    result_path = self.output_dir / f"{benchmark_name}_result.json"
                    save_benchmark_results(result, result_path)

                logger.info(f"✓ {benchmark_name} completed successfully")

                # Run analysis if available
                if hasattr(benchmark, 'analyze_results'):
                    analysis = benchmark.analyze_results(result)
                    result.metadata['analysis'] = analysis

            except Exception as e:
                logger.error(f"✗ {benchmark_name} failed: {e}")
                failed_benchmarks.append((benchmark_name, str(e)))

                if self.config.stop_on_failure:
                    logger.error("Stopping suite due to failure")
                    break

        # Calculate suite duration
        suite_end = time.perf_counter()
        self.suite_metadata['end_time'] = datetime.now().isoformat()
        self.suite_metadata['total_duration_s'] = suite_end - suite_start
        self.suite_metadata['completed_benchmarks'] = len(self.results)
        self.suite_metadata['failed_benchmarks'] = failed_benchmarks

        # Save complete results
        self._save_complete_results()

        # Generate report if configured
        if self.config.generate_report and self.results:
            self._generate_report()

        # Print summary
        self._print_summary()

        return {
            'metadata': self.suite_metadata,
            'results': [r.to_dict() for r in self.results],
            'summary': self._generate_summary()
        }

    def _save_complete_results(self):
        """Save all results in a single file."""
        results_path = self.output_dir / 'suite_results.json'

        data = {
            'suite_metadata': self.suite_metadata,
            'results': [r.to_dict() for r in self.results]
        }

        with open(results_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Complete results saved to: {results_path}")

    def _generate_report(self):
        """Generate comprehensive report using the reporting module."""
        try:
            from ionosense_hpc.benchmarks.reporting import BenchmarkReport, ReportConfig

            report_config = ReportConfig(
                title=f"{self.config.name} - Benchmark Report",
                output_format=self.config.report_format,
                include_raw_data=False,
                include_violin_plots=True,
                include_heatmaps=True
            )

            report = BenchmarkReport(self.results, report_config)
            report_path = self.output_dir / f"report.{self.config.report_format}"
            report.generate(report_path)

            logger.info(f"Report generated: {report_path}")

        except Exception as e:
            logger.error(f"Failed to generate report: {e}")

    def _generate_summary(self) -> dict[str, Any]:
        """Generate summary statistics across all benchmarks."""
        if not self.results:
            return {}

        summary = {
            'total_benchmarks': len(self.results),
            'successful': len([r for r in self.results if r.passed]),
            'failed': len([r for r in self.results if not r.passed])
        }

        # Aggregate key metrics
        latencies = []
        throughputs = []

        for result in self.results:
            if 'latency' in result.name.lower():
                if 'mean' in result.statistics:
                    latencies.append(result.statistics['mean'])
            elif 'throughput' in result.name.lower():
                if 'frames_per_second' in result.statistics:
                    throughputs.append(result.statistics['frames_per_second'])

        if latencies:
            summary['avg_latency_us'] = np.mean(latencies)
            summary['best_latency_us'] = np.min(latencies)

        if throughputs:
            summary['avg_throughput_fps'] = np.mean(throughputs)
            summary['best_throughput_fps'] = np.max(throughputs)

        return summary

    def _print_summary(self):
        """Print suite execution summary."""
        print("\n" + "="*60)
        print(f"SUITE SUMMARY: {self.config.name}")
        print("="*60)

        summary = self._generate_summary()

        print(f"Total benchmarks: {summary.get('total_benchmarks', 0)}")
        print(f"Successful: {summary.get('successful', 0)}")
        print(f"Failed: {summary.get('failed', 0)}")

        if 'avg_latency_us' in summary:
            print(f"Average latency: {summary['avg_latency_us']:.1f} µs")
            print(f"Best latency: {summary['best_latency_us']:.1f} µs")

        if 'avg_throughput_fps' in summary:
            print(f"Average throughput: {summary['avg_throughput_fps']:.0f} FPS")
            print(f"Best throughput: {summary['best_throughput_fps']:.0f} FPS")

        print(f"\nDuration: {self.suite_metadata['total_duration_s']:.1f} seconds")
        print(f"Output: {self.output_dir}")


def run_default_suite(preset: str = 'realtime', output_dir: str | None = None) -> dict[str, Any]:
    """
    Convenience function to run the default benchmark suite.
    
    Args:
        preset: Engine configuration preset name
        output_dir: Custom output directory
        
    Returns:
        Suite results dictionary
    """
    config = SuiteConfig(
        name=f"default_suite_{preset}",
        description=f"Default benchmark suite with {preset} preset",
        output_dir=output_dir or "./benchmark_results"
    )

    suite = BenchmarkSuite(config)
    return suite.run()


import time

import numpy as np


def main(argv: list[str] | None = None) -> int:
    """Console entrypoint for `ionosense-bench` script."""
    import argparse

    parser = argparse.ArgumentParser(description='Run benchmark suite')
    parser.add_argument('--config', help='Suite configuration YAML file')
    parser.add_argument('--preset', default='realtime', help='Engine preset')
    parser.add_argument('--output', help='Output directory')
    parser.add_argument('--benchmarks', nargs='+', help='Specific benchmarks to run')
    parser.add_argument('--exclude', nargs='+', help='Benchmarks to exclude')
    parser.add_argument('--no-report', action='store_true', help='Skip report generation')

    args = parser.parse_args(argv)

    if args.config:
        suite = BenchmarkSuite(args.config)
    else:
        config = SuiteConfig(
            benchmarks=args.benchmarks,
            exclude=args.exclude,
            output_dir=args.output or "./benchmark_results",
            generate_report=not args.no_report
        )
        suite = BenchmarkSuite(config)

    _ = suite.run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
