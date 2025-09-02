#!/usr/bin/env python3
"""
benchmark_scaling.py
---------------------------------------------------------------
A research-oriented script to systematically benchmark the raw
throughput of the CudaFftEngine across a range of batch sizes.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time

import numpy as np

# Import all shared components from the new utils file
from utils import CudaFftEngine


# ───────────────────────── Core Benchmark Logic ────────────────────────
def run_single_throughput_test(engine: CudaFftEngine,
                               duration: float) -> float:
    """
    Runs a single raw throughput test for a given duration and returns the
    throughput in FFTs per second.
    """
    stream_idx = 0
    total_ffts_processed = 0
    batch_size = engine.batch_size
    nfft = engine.fft_size

    t_start = time.perf_counter()
    t_end = t_start + duration

    # Create a dummy buffer once to avoid reallocation in the loop.
    # The content doesn't matter for a raw throughput test.
    input_buffer = np.empty(nfft * batch_size, dtype=np.float32)

    while time.perf_counter() < t_end:
        engine.sync_stream(stream_idx)
        engine.pinned_input(stream_idx)[:] = input_buffer
        engine.execute_async(stream_idx)

        stream_idx = (stream_idx + 1) % engine.num_streams
        total_ffts_processed += batch_size

    # Final sync to ensure all operations are complete
    for i in range(engine.num_streams):
        engine.sync_stream(i)

    actual_duration = time.perf_counter() - t_start

    return total_ffts_processed / actual_duration if actual_duration > 0 else 0.0

# ───────────────────────── Main Execution Flow ─────────────────────
def run_scaling_benchmark(args: argparse.Namespace):
    """
    Orchestrates the benchmark sweep across multiple batch sizes and K runs.
    """
    if CudaFftEngine is None: return

    print("Initializing scaling benchmark...")
    print(f"  - NFFT: {args.nfft}, Duration per run: {args.duration}s")
    print(f"  - K-runs per batch size: {args.k_runs}")
    print(f"  - Output CSV: {args.output_csv}")

    # Define the batch sizes to test
    batch_sizes = [2**i for i in range(int(np.log2(args.min_batch)), int(np.log2(args.max_batch)) + 1)]
    print(f"  - Batch sizes to be tested: {batch_sizes}\n")

    all_results = []

    try:
        for i, batch_size in enumerate(batch_sizes):
            print(f"--- Testing Batch Size = {batch_size} ({i+1}/{len(batch_sizes)}) ---")

            engine = CudaFftEngine(args.nfft, batch_size, use_graphs=True, verbose=False)

            run_throughputs = []
            for k in range(args.k_runs):
                print(f"  Running K = {k+1}/{args.k_runs}...", end='', flush=True)

                # Warmup before the timed run
                run_single_throughput_test(engine, 0.5)

                # Timed run
                throughput = run_single_throughput_test(engine, args.duration)
                run_throughputs.append(throughput)

                result = {
                    'nfft': args.nfft,
                    'batch_size': batch_size,
                    'run_id': k + 1,
                    'throughput_ffts_per_sec': throughput
                }
                all_results.append(result)
                print(f" done. Throughput: {throughput:,.1f} FFTs/sec")

            avg_throughput = np.mean(run_throughputs)
            std_throughput = np.std(run_throughputs)
            print(f"  Avg for Batch {batch_size}: {avg_throughput:,.1f} ± {std_throughput:,.1f} FFTs/sec\n")

            del engine

    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user.")

    finally:
        if not all_results:
            print("No results to save.")
            return

        print(f"Saving {len(all_results)} results to {args.output_csv}...")
        file_exists = os.path.isfile(args.output_csv)

        with open(args.output_csv, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=all_results[0].keys())
            if not file_exists or os.path.getsize(args.output_csv) == 0:
                writer.writeheader()
            writer.writerows(all_results)

        print("Save complete.")

# ─────────────────────────────── CLI ───────────────────────────────
def parse_cli() -> argparse.Namespace:
    """Parses command-line arguments."""
    p = argparse.ArgumentParser(description="Systematic throughput scaling benchmark for the CUDA FFT engine.")

    p.add_argument("--nfft", type=int, default=4096, help="FFT length.")
    p.add_argument("--sr", type=int, default=100_000, help="Sample rate (Hz).")
    p.add_argument("-k", "--k-runs", type=int, default=5, help="Number of runs (K) per batch size for statistical significance.")
    p.add_argument("--min-batch", type=int, default=2, help="Starting batch size (must be a power of 2).")
    p.add_argument("--max-batch", type=int, default=128, help="Maximum batch size (must be a power of 2).")
    p.add_argument("-d", "--duration", type=float, default=3.0, help="Duration of each individual benchmark run (seconds).")
    p.add_argument("-o", "--output-csv", type=str, default="scaling_results.csv", help="Path to save the output CSV file.")

    return p.parse_args()

# ───────────────────────────────── Main ───────────────────────────
if __name__ == "__main__":
    args = parse_cli()

    if not (args.min_batch > 0 and (args.min_batch & (args.min_batch - 1) == 0)) or \
       not (args.max_batch > 0 and (args.max_batch & (args.max_batch - 1) == 0)):
        print("Error: --min-batch and --max-batch must be powers of 2.", file=sys.stderr)
        sys.exit(1)

    try:
        run_scaling_benchmark(args)
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
