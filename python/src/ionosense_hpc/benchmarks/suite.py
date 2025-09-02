"""Benchmark suite CLI dispatcher."""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np

from .latency import benchmark_latency, benchmark_jitter
from .throughput import benchmark_throughput, benchmark_batch_scaling
from .accuracy import benchmark_accuracy, benchmark_window_accuracy, benchmark_numerical_stability
from ..config import Presets, EngineConfig
from ..utils import logger, setup_logging, device_info


def run_full_suite(
    output_dir: Optional[Path] = None,
    config_preset: str = 'realtime'
) -> Dict[str, Any]:
    """Run complete benchmark suite.
    
    Args:
        output_dir: Directory to save results
        config_preset: Configuration preset name
        
    Returns:
        Combined benchmark results
    """
    logger.info("=" * 60)
    logger.info("IONOSENSE-HPC BENCHMARK SUITE")
    logger.info("=" * 60)
    
    # Get configuration
    preset_map = {
        'realtime': Presets.realtime(),
        'throughput': Presets.throughput(),
        'validation': Presets.validation(),
        'profiling': Presets.profiling()
    }
    config = preset_map.get(config_preset, Presets.realtime())
    
    # Device information
    dev_info = device_info()
    logger.info(f"Device: {dev_info['name']}")
    logger.info(f"Memory: {dev_info['memory_free_mb']}/{dev_info['memory_total_mb']} MB")
    logger.info(f"Config: {config}")
    logger.info("")
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'device': dev_info,
        'config': config.model_dump(),
        'benchmarks': {}
    }
    
    # 1. Latency benchmark
    logger.info("Running LATENCY benchmark...")
    results['benchmarks']['latency'] = benchmark_latency(
        config=config,
        n_iterations=1000,
        warmup_iterations=100
    )
    _print_latency_summary(results['benchmarks']['latency'])
    
    # 2. Throughput benchmark
    logger.info("\nRunning THROUGHPUT benchmark...")
    results['benchmarks']['throughput'] = benchmark_throughput(
        config=config,
        duration_seconds=10.0
    )
    _print_throughput_summary(results['benchmarks']['throughput'])
    
    # 3. Accuracy benchmark
    logger.info("\nRunning ACCURACY benchmark...")
    results['benchmarks']['accuracy'] = benchmark_accuracy(config=config)
    _print_accuracy_summary(results['benchmarks']['accuracy'])
    
    # 4. Jitter benchmark (for realtime configs)
    if config_preset == 'realtime':
        logger.info("\nRunning JITTER benchmark...")
        results['benchmarks']['jitter'] = benchmark_jitter(
            config=config,
            duration_seconds=5.0
        )
        _print_jitter_summary(results['benchmarks']['jitter'])
    
    # 5. Batch scaling (for throughput configs)
    if config_preset == 'throughput':
        logger.info("\nRunning BATCH SCALING benchmark...")
        results['benchmarks']['batch_scaling'] = benchmark_batch_scaling(
            nfft=config.nfft,
            batch_sizes=[1, 2, 4, 8, 16, 32],
            n_iterations=100
        )
        _print_scaling_summary(results['benchmarks']['batch_scaling'])
    
    # Save results if output directory specified
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"benchmark_{config_preset}_{timestamp}.json"
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"\nResults saved to: {output_file}")
        
        # Also save CSV summary
        csv_file = output_dir / f"benchmark_{config_preset}_{timestamp}.csv"
        _save_csv_summary(results, csv_file)
        logger.info(f"CSV summary saved to: {csv_file}")
    
    # Print overall summary
    logger.info("\n" + "=" * 60)
    logger.info("BENCHMARK COMPLETE")
    logger.info("=" * 60)
    _print_overall_summary(results)
    
    return results


def _print_latency_summary(results: Dict[str, Any]) -> None:
    """Print latency benchmark summary."""
    print(f"  Mean latency: {results['mean_us']:.1f} μs")
    print(f"  P99 latency: {results['p99_us']:.1f} μs")
    print(f"  Deadline misses (<200μs): {results['deadline_miss_rate']:.1%}")


def _print_throughput_summary(results: Dict[str, Any]) -> None:
    """Print throughput benchmark summary."""
    tp = results['throughput']
    print(f"  Throughput: {tp['gb_per_second']:.2f} GB/s")
    print(f"  Frame rate: {tp['frames_per_second']:.1f} FPS")
    print(f"  Samples/sec: {tp['samples_per_second']/1e6:.1f} MS/s")


def _print_accuracy_summary(results: Dict[str, Any]) -> None:
    """Print accuracy benchmark summary."""
    summary = results['summary']
    print(f"  Tests passed: {summary['passed']}/{summary['total_tests']}")
    print(f"  Pass rate: {summary['pass_rate']:.1%}")


def _print_jitter_summary(results: Dict[str, Any]) -> None:
    """Print jitter benchmark summary."""
    print(f"  Frame time: {results['frame_time']['mean_ms']:.2f} ± "
          f"{results['frame_time']['std_ms']:.2f} ms")
    print(f"  Interval jitter: {results['interval']['jitter_ms']:.2f} ms")


def _print_scaling_summary(results: Dict[str, Any]) -> None:
    """Print batch scaling summary."""
    print("  Batch  Throughput  Efficiency")
    for i, batch in enumerate(results['batch_sizes']):
        tp = results['throughput'][i] / 1e6  # Convert to MS/s
        eff = results['efficiency'][i]
        print(f"  {batch:5d}  {tp:8.1f} MS/s  {eff:6.1f}%")


def _print_overall_summary(results: Dict[str, Any]) -> None:
    """Print overall benchmark summary."""
    benchmarks = results['benchmarks']
    
    # Key metrics
    if 'latency' in benchmarks:
        lat = benchmarks['latency']
        print(f"Latency: {lat['mean_us']:.1f} μs (P99: {lat['p99_us']:.1f} μs)")
    
    if 'throughput' in benchmarks:
        tp = benchmarks['throughput']['throughput']
        print(f"Throughput: {tp['gb_per_second']:.2f} GB/s")
    
    if 'accuracy' in benchmarks:
        acc = benchmarks['accuracy']['summary']
        print(f"Accuracy: {acc['pass_rate']:.0%} tests passed")


def _save_csv_summary(results: Dict[str, Any], filepath: Path) -> None:
    """Save benchmark summary as CSV."""
    import csv
    
    rows = []
    
    # Header with metadata
    rows.append(['Timestamp', results['timestamp']])
    rows.append(['Device', results['device']['name']])
    rows.append(['NFFT', results['config']['nfft']])
    rows.append(['Batch', results['config']['batch']])
    rows.append([])
    
    # Benchmark results
    rows.append(['Metric', 'Value', 'Unit'])
    
    benchmarks = results['benchmarks']
    if 'latency' in benchmarks:
        lat = benchmarks['latency']
        rows.append(['Latency (mean)', lat['mean_us'], 'μs'])
        rows.append(['Latency (P99)', lat['p99_us'], 'μs'])
        rows.append(['Deadline misses', lat['deadline_miss_rate'] * 100, '%'])
    
    if 'throughput' in benchmarks:
        tp = benchmarks['throughput']['throughput']
        rows.append(['Throughput', tp['gb_per_second'], 'GB/s'])
        rows.append(['Frame rate', tp['frames_per_second'], 'FPS'])
    
    if 'accuracy' in benchmarks:
        acc = benchmarks['accuracy']['summary']
        rows.append(['Accuracy', acc['pass_rate'] * 100, '%'])
    
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def main():
    """Main entry point for benchmark CLI."""
    parser = argparse.ArgumentParser(
        description='Ionosense-HPC Benchmark Suite',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m ionosense_hpc.benchmarks.suite --preset realtime
  python -m ionosense_hpc.benchmarks.suite --preset throughput --output results/
  python -m ionosense_hpc.benchmarks.suite --test latency --iterations 1000
        """
    )
    
    parser.add_argument(
        '--preset',
        choices=['realtime', 'throughput', 'validation', 'profiling'],
        default='realtime',
        help='Configuration preset'
    )
    
    parser.add_argument(
        '--test',
        choices=['all', 'latency', 'throughput', 'accuracy', 'jitter', 'scaling'],
        default='all',
        help='Specific test to run'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Output directory for results'
    )
    
    parser.add_argument(
        '--iterations',
        type=int,
        default=1000,
        help='Number of iterations for benchmarks'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(level=args.log_level)
    
    # Run benchmarks
    if args.test == 'all':
        results = run_full_suite(
            output_dir=Path(args.output) if args.output else None,
            config_preset=args.preset
        )
    else:
        # Run specific benchmark
        config = {
            'realtime': Presets.realtime(),
            'throughput': Presets.throughput(),
            'validation': Presets.validation(),
            'profiling': Presets.profiling()
        }[args.preset]
        
        if args.test == 'latency':
            results = benchmark_latency(config, n_iterations=args.iterations)
        elif args.test == 'throughput':
            results = benchmark_throughput(config, duration_seconds=10.0)
        elif args.test == 'accuracy':
            results = benchmark_accuracy(config)
        elif args.test == 'jitter':
            results = benchmark_jitter(config, duration_seconds=5.0)
        elif args.test == 'scaling':
            results = benchmark_batch_scaling(nfft=config.nfft)
        
        # Print results as JSON
        print(json.dumps(results, indent=2, default=str))
    
    return 0


if __name__ == '__main__':
    sys.exit(main())