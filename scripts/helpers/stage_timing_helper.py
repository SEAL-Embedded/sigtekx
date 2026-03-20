#!/usr/bin/env python
"""
Stage Timing Development Helper

Quick commands for running per-stage timing profiling experiments.
Provides easy access to batch and streaming mode stage breakdowns.

Usage:
    python stage_timing_helper.py batch [--full] [--nfft N]
    python stage_timing_helper.py stream [--full] [--nfft N]
    python stage_timing_helper.py both [--full]

Examples:
    # Quick batch test (4 configs, ~30s)
    python stage_timing_helper.py batch

    # Full batch sweep (20+ configs, ~5min)
    python stage_timing_helper.py batch --full

    # Streaming test with specific NFFT
    python stage_timing_helper.py stream --nfft 4096

    # Run both modes (quick test)
    python stage_timing_helper.py both
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_batch_experiment(full=False, nfft=None):
    """Run BATCH mode stage timing experiment."""
    print("=" * 70)
    print("BATCH Mode Stage Timing Profiling")
    print("=" * 70)

    if full:
        print("Mode: FULL sweep (baseline_batch_48k_latency with measure_components)")
        print("Expected: 45 configs, ~5-8 minutes")
        print()

        cmd = [
            "python", "benchmarks/run_latency.py",
            "experiment=baseline_batch_48k_latency",
            "+benchmark=latency",
            "benchmark.measure_components=true"
        ]
    else:
        print("Mode: QUICK test (ionosphere_test)")
        print("Expected: 4 configs, ~30 seconds")
        print()

        cmd = [
            "python", "benchmarks/run_latency.py",
            "experiment=ionosphere_test",
            "+benchmark=latency",
            "benchmark.measure_components=true",
            "benchmark.iterations=5"
        ]

    # Add NFFT override if specified
    if nfft:
        cmd.append(f"engine.nfft={nfft}")
        print(f"Override: NFFT={nfft}")
        print()

    print(f"Command: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(cmd, check=True)
        print()
        print("[SUCCESS] BATCH stage timing complete!")
        print(f"   CSV: artifacts/data/latency_summary_*_batch.csv")
        print(f"   Dashboard: sigx dashboard -> 'BATCH Execution' -> 'Stage Breakdown'")
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] BATCH experiment failed: {e}", file=sys.stderr)
        return e.returncode


def run_stream_experiment(full=False, nfft=None):
    """Run STREAMING mode stage timing experiment."""
    print("=" * 70)
    print("STREAMING Mode Stage Timing Profiling")
    print("=" * 70)

    if full:
        print("Mode: FULL sweep (baseline_streaming_48k_latency with measure_components)")
        print("Expected: 45 configs, ~5-8 minutes")
        print()

        cmd = [
            "python", "benchmarks/run_latency.py",
            "experiment=baseline_streaming_48k_latency",
            "+benchmark=latency_streaming",
            "benchmark.measure_components=true"
        ]
    else:
        print("Mode: QUICK test (streaming_stage_timing_test)")
        print("Expected: 4 configs, ~30 seconds")
        print()

        cmd = [
            "python", "benchmarks/run_latency.py",
            "experiment=streaming_stage_timing_test",
            "+benchmark=latency_streaming",
            "benchmark.measure_components=true",
            "benchmark.iterations=5"
        ]

    # Add NFFT override if specified
    if nfft:
        cmd.append(f"engine.nfft={nfft}")
        print(f"Override: NFFT={nfft}")
        print()

    print(f"Command: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(cmd, check=True)
        print()
        print("[SUCCESS] STREAMING stage timing complete!")
        print(f"   CSV: artifacts/data/latency_summary_*_streaming.csv")
        print(f"   Dashboard: sigx dashboard -> 'STREAMING Execution' -> 'Stage Breakdown'")
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] STREAMING experiment failed: {e}", file=sys.stderr)
        return e.returncode


def run_both_experiments(full=False):
    """Run both BATCH and STREAMING experiments."""
    print("=" * 70)
    print("Running BOTH Batch + Streaming Stage Timing")
    print("=" * 70)
    print()

    # Run batch first
    ret_batch = run_batch_experiment(full=full)
    print()
    print("-" * 70)
    print()

    # Run streaming second
    ret_stream = run_stream_experiment(full=full)
    print()

    if ret_batch == 0 and ret_stream == 0:
        print("=" * 70)
        print("[SUCCESS] Both experiments completed successfully!")
        print("=" * 70)
        print()
        print("View results:")
        print("  sigx dashboard")
        print("    -> BATCH Execution -> Stage Breakdown")
        print("    -> STREAMING Execution -> Stage Breakdown")
        return 0
    else:
        print("[WARNING] One or more experiments failed. Check output above.")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Stage Timing Development Helper - Quick profiling commands",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s batch              # Quick batch test (4 configs)
  %(prog)s batch --full       # Full batch sweep (45 configs)
  %(prog)s stream             # Quick streaming test (4 configs)
  %(prog)s stream --nfft 4096 # Streaming with specific NFFT
  %(prog)s both               # Run both batch + streaming (quick)
        """
    )

    subparsers = parser.add_subparsers(dest='mode', help='Execution mode')

    # Batch mode
    parser_batch = subparsers.add_parser('batch', help='Run BATCH mode stage timing')
    parser_batch.add_argument('--full', action='store_true',
                             help='Full sweep (45 configs) instead of quick test (4 configs)')
    parser_batch.add_argument('--nfft', type=int,
                             help='Override NFFT size (e.g., 4096)')

    # Stream mode
    parser_stream = subparsers.add_parser('stream', help='Run STREAMING mode stage timing')
    parser_stream.add_argument('--full', action='store_true',
                              help='Full sweep (45 configs) instead of quick test (4 configs)')
    parser_stream.add_argument('--nfft', type=int,
                              help='Override NFFT size (e.g., 4096)')

    # Both modes
    parser_both = subparsers.add_parser('both', help='Run both BATCH and STREAMING')
    parser_both.add_argument('--full', action='store_true',
                            help='Full sweep for both modes')

    args = parser.parse_args()

    if not args.mode:
        parser.print_help()
        return 1

    # Change to project root
    project_root = Path(__file__).parent.parent
    import os
    os.chdir(project_root)

    # Execute requested mode
    if args.mode == 'batch':
        return run_batch_experiment(full=args.full, nfft=args.nfft)
    elif args.mode == 'stream':
        return run_stream_experiment(full=args.full, nfft=args.nfft)
    elif args.mode == 'both':
        return run_both_experiments(full=args.full)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
