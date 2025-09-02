"""Benchmark suite CLI dispatcher."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ionosense_hpc.benchmarks.accuracy import benchmark_accuracy
from ionosense_hpc.benchmarks.latency import benchmark_jitter, benchmark_latency
from ionosense_hpc.benchmarks.throughput import benchmark_batch_scaling, benchmark_throughput
from ionosense_hpc.config import Presets
from ionosense_hpc.utils import device_info, logger, setup_logging


def run_full_suite(
    output_dir: Path | None = None,
    config_preset: str = 'realtime'
) -> dict[str, Any]:
    """Run complete benchmark suite."""
    logger.info("=" * 60)
    logger.info("IONOSENSE-HPC BENCHMARK SUITE")
    logger.info("=" * 60)

    preset_map = {
        'realtime': Presets.realtime(),
        'throughput': Presets.throughput(),
        'validation': Presets.validation(),
        'profiling': Presets.profiling()
    }
    config = preset_map.get(config_preset, Presets.realtime())

    dev_info = device_info()
    logger.info(f"Device: {dev_info.get('name', 'N/A')}")
    logger.info(f"Config: {config}")

    results = {
        'timestamp': datetime.now().isoformat(),
        'device': dev_info,
        'config': config.model_dump(),
        'benchmarks': {}
    }

    logger.info("\nRunning LATENCY benchmark...")
    results['benchmarks']['latency'] = benchmark_latency(config=config)
    _print_latency_summary(results['benchmarks']['latency'])

    logger.info("\nRunning THROUGHPUT benchmark...")
    results['benchmarks']['throughput'] = benchmark_throughput(config=config)
    _print_throughput_summary(results['benchmarks']['throughput'])

    logger.info("\nRunning ACCURACY benchmark...")
    results['benchmarks']['accuracy'] = benchmark_accuracy(config=Presets.validation())
    _print_accuracy_summary(results['benchmarks']['accuracy'])

    if config_preset == 'realtime':
        logger.info("\nRunning JITTER benchmark...")
        results['benchmarks']['jitter'] = benchmark_jitter(config=config)
        _print_jitter_summary(results['benchmarks']['jitter'])

    if config_preset == 'throughput':
        logger.info("\nRunning BATCH SCALING benchmark...")
        results['benchmarks']['batch_scaling'] = benchmark_batch_scaling(nfft=config.nfft)
        _print_scaling_summary(results['benchmarks']['batch_scaling'])

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"benchmark_{config_preset}_{timestamp}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"\nResults saved to: {output_file}")

    logger.info("\n" + "=" * 60 + "\nBENCHMARK COMPLETE\n" + "=" * 60)
    _print_overall_summary(results)

    return results

def _print_latency_summary(results: dict[str, Any]):
    print(f"  Mean latency: {results['mean_us']:.1f} µs | P99: {results.get('p99_us', 0):.1f} µs")

def _print_throughput_summary(results: dict[str, Any]):
    tp = results['throughput']
    print(f"  Throughput: {tp['gb_per_second']:.2f} GB/s | Rate: {tp['frames_per_second']:.0f} FPS")

def _print_accuracy_summary(results: dict[str, Any]):
    summary = results['summary']
    print(f"  Accuracy Pass Rate: {summary['pass_rate']:.1%}")

def _print_jitter_summary(results: dict[str, Any]):
    print(f"  Frame time: {results['frame_time']['mean_ms']:.2f} ± {results['frame_time']['std_ms']:.2f} ms")

def _print_scaling_summary(results: dict[str, Any]):
    print("  Batch | Throughput (MS/s) | Efficiency (%)")
    for i, batch in enumerate(results['batch_sizes']):
        tp = results['throughput_msps'][i]
        eff = results['efficiency_percent'][i]
        print(f"  {batch:5d} | {tp:17.2f} | {eff:14.1f}")

def _print_overall_summary(results: dict[str, Any]):
    print("Overall Summary:")
    if 'latency' in results['benchmarks']:
        _print_latency_summary(results['benchmarks']['latency'])
    if 'throughput' in results['benchmarks']:
        _print_throughput_summary(results['benchmarks']['throughput'])
    if 'accuracy' in results['benchmarks']:
        _print_accuracy_summary(results['benchmarks']['accuracy'])

def main():
    parser = argparse.ArgumentParser(description='Ionosense-HPC Benchmark Suite')
    parser.add_argument('--preset', choices=['realtime', 'throughput', 'validation', 'profiling'], default='realtime')
    parser.add_argument('--test', default='all')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--iterations', type=int, default=1000)
    parser.add_argument('--log-level', default='INFO')
    args = parser.parse_args()

    setup_logging(level=args.log_level)

    if args.test == 'all':
        run_full_suite(output_dir=args.output, config_preset=args.preset)
    else:
        config = Presets.realtime()
        if args.preset == 'throughput': config = Presets.throughput()
        elif args.preset == 'validation': config = Presets.validation()
        elif args.preset == 'profiling': config = Presets.profiling()

        results = {}
        if args.test == 'latency':
            results = benchmark_latency(config, n_iterations=args.iterations)
        elif args.test == 'throughput':
            results = benchmark_throughput(config)
        elif args.test == 'accuracy':
            results = benchmark_accuracy(config)
        elif args.test == 'jitter':
            results = benchmark_jitter(config)
        elif args.test == 'scaling':
            results = benchmark_batch_scaling(nfft=config.nfft, n_iterations=args.iterations)

        print(json.dumps(results, indent=2, default=str))

if __name__ == '__main__':
    sys.exit(main())
