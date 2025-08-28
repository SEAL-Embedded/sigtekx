#!/usr/bin/env python3
"""
benchmark_raw_fft.py
---------------------------------------------------------------
Measures the raw, unpaced throughput of the dual-channel FFT engine
by comparing a single-threaded CPU implementation against the 
concurrent 3-stream CUDA implementation.
"""
from __future__ import annotations
import argparse
import time
import numpy as np
import sys
from typing import Dict

# Import all shared components from the utils file
from utils import (
    CudaFftEngine, nvtx_range, build_signal, print_header, 
    print_separator, create_engine, tqdm, is_profiler_attached, safe_print
)

# ───────────────────────── Core Benchmark Logic ───────────────────────────────
def run_throughput_benchmark(mode: str, nfft: int, hop: int, sr: int, 
                             duration: float, batch_size: int, use_graphs: bool, verbose: bool) -> Dict[str, float]:
    """
    Runs a raw throughput benchmark.
    - 'gpu' mode uses the 3-stream asynchronous pipeline.
    - 'cpu' mode is a synchronous single-core loop.
    """
    assert mode in ("cpu", "gpu")
    
    # Calculate total number of FFT pairs to process based on duration
    num_pairs_total = int((duration * sr) / hop)
    
    # Determine the number of loop iterations
    if mode == "gpu":
        pairs_per_batch = batch_size // 2
        num_iterations = (num_pairs_total + pairs_per_batch - 1) // pairs_per_batch
    else: # cpu
        num_iterations = num_pairs_total

    # Quiet mode for profiler unless verbose is forced
    quiet = is_profiler_attached() and not verbose
    
    with nvtx_range(f"run_throughput::{mode}"):
        # --- Initialization ---
        if mode == "gpu":
            eng = create_engine(nfft, batch_size, use_graphs=use_graphs, verbose_override=verbose)
            eng.prepare_for_execution()
        else:
            window = np.hanning(nfft).astype(np.float32)
        
        sig = build_signal(sr, duration * 1.1, nfft) # Generate ample signal
        
        # --- Main Processing Loop ---
        stream_idx = 0
        total_pairs_processed = 0
        
        # Use tqdm for a progress bar
        pbar = tqdm(range(num_iterations), desc=f"Processing ({mode.upper()})", 
                    unit="iter", disable=quiet)
        
        t_start = time.perf_counter()
        with nvtx_range("throughput_loop"):
            for _ in pbar:
                if mode == "gpu":
                    pairs_per_batch = batch_size // 2
                    
                    # 1. Synchronize the current stream to ensure its resources are free
                    eng.sync_stream(stream_idx)
                    
                    # 2. Prepare batch data on the host
                    offset = total_pairs_processed * hop
                    ch1_frames = [sig["ch1"][offset + i*hop : offset + i*hop + nfft] for i in range(pairs_per_batch)]
                    ch2_frames = [sig["ch2"][offset + i*hop : offset + i*hop + nfft] for i in range(pairs_per_batch)]
                    batch_data = np.concatenate(ch1_frames + ch2_frames).astype(np.float32, copy=False)
                    
                    # 3. Copy data to pinned memory and execute asynchronously
                    dst = eng.pinned_input(stream_idx)      # (batch, nfft) view
                    dst.ravel()[:] = batch_data             # flatten dest so shapes match (B*N,)
                    eng.execute_async(stream_idx)
                    
                    total_pairs_processed += pairs_per_batch
                    stream_idx = (stream_idx + 1) % eng.num_streams
                else: # CPU mode
                    offset = total_pairs_processed * hop
                    ch1_frame = sig["ch1"][offset:offset+nfft] * window
                    ch2_frame = sig["ch2"][offset:offset+nfft] * window
                    _ = np.fft.rfft(ch1_frame)
                    _ = np.fft.rfft(ch2_frame)
                    total_pairs_processed += 1
        
        # --- Finalization ---
        if mode == "gpu":
            with nvtx_range("final_sync"):
                eng.synchronize_all_streams()
        
        t_end = time.perf_counter()

    total_time_s = t_end - t_start
    total_ffts = total_pairs_processed * 2
    throughput = total_ffts / total_time_s if total_time_s > 0 else 0
    
    return {"throughput_fps": throughput, "total_ffts": total_ffts}

# ───────────────────────────────── Main ───────────────────────────────────────
def main(args: argparse.Namespace):
    if CudaFftEngine is None or tqdm is None:
        return

    if args.batch_size % 2 != 0:
        raise ValueError("Batch size must be an even number for a dual-channel system.")

    hop = int(args.nfft * (1 - args.overlap))
    use_graphs = not args.no_graphs

    # Use safe_print for ALL output to avoid Unicode issues
    print_header("Raw Throughput FFT Benchmark")
    safe_print(f"Config: NFFT={args.nfft}, Batch={args.batch_size}, Fs={args.sr/1e3:.1f} kHz, "
               f"Hop={hop}, Duration~{args.duration:.1f}s, CUDA Graphs: {'ON' if use_graphs else 'OFF'}")  # Changed ≈ to ~

    cpu_stats = {}
    if not args.no_cpu:
        cpu_stats = run_throughput_benchmark("cpu", args.nfft, hop, args.sr, args.duration,
                                             args.batch_size, False, args.verbose)  # CPU never uses graphs

    gpu_stats = {}
    if not args.no_gpu:
        gpu_stats = run_throughput_benchmark("gpu", args.nfft, hop, args.sr, args.duration,
                                             args.batch_size, use_graphs, args.verbose)

    # Always print the final results table
    print_header("Results")
    safe_print(f"{'Metric':<24} {'CPU (1-Core)':>20} {'GPU (3-Stream)':>25}")
    print_separator()

    cpu_ffts = cpu_stats.get('total_ffts', 0)
    gpu_ffts = gpu_stats.get('total_ffts', 0)
    cpu_fps = cpu_stats.get('throughput_fps', 0)
    gpu_fps = gpu_stats.get('throughput_fps', 0)

    safe_print(f"{'Total FFTs Processed':<24} {cpu_ffts:>20,} {gpu_ffts:>25,}")
    safe_print(f"{'Throughput (FFTs/sec)':<24} {cpu_fps:>19,.1f} {gpu_fps:>24,.1f}")
    print_separator()

    if gpu_fps > 0 and cpu_fps > 0:
        speed_up = gpu_fps / cpu_fps
        safe_print(f" GPU Speed-up: x{speed_up:,.2f}")

# ─────────────────────────────── CLI ──────────────────────────────────────────
def parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Raw throughput FFT benchmark comparing CPU and GPU.")
    p.add_argument("-n", "--nfft", type=int, default=4096, help="FFT length")
    p.add_argument("-b", "--batch-size", type=int, default=32, help="Total FFTs per GPU batch (must be even)")
    p.add_argument("-s", "--sr", type=int, default=100_000, help="Sample rate (Hz)")
    p.add_argument("-o", "--overlap", type=float, default=0.50, help="Frame overlap [0.0, 1.0)")
    p.add_argument("-d", "--duration", type=float, default=5.0, help="Benchmark run time (seconds)")
    p.add_argument("--no-gpu", action="store_true", help="Skip GPU benchmark")
    p.add_argument("--no-cpu", action="store_true", help="Skip CPU benchmark")
    p.add_argument("--no-graphs", action="store_true", help="Disable CUDA Graphs for profiling individual operations")
    p.add_argument("--verbose", action="store_true", help="Force verbose output even when profiling")
    return p.parse_args()

if __name__ == "__main__":
    try:
        main(parse_cli())
    except Exception as e:
        # Use safe_print to avoid Unicode issues when running under profilers
        safe_print(f"\nERROR: An error occurred: {e}", file=sys.stderr)
        sys.exit(1)