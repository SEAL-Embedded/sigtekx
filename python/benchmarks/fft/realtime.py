#!/usr/bin/env python3
"""
benchmark_realtime_fft.py
---------------------------------------------------------------
Simulates a real-time, dual-channel FFT processing scenario to
measure and compare host-side latency between a CPU core and the
concurrent 3-stream CUDA engine.
"""
from __future__ import annotations

import argparse
import sys
import time

import numpy as np
from utils import (
    CudaFftEngine,
    build_signal,
    compute_stats,
    create_engine,
    fmt_t,
    is_profiler_attached,
    nvtx_range,
    print_header,
    print_separator,
    safe_print,
    tqdm,
)


# ───────────────────────── Core Benchmark Logic ───────────────────────────────
def run_rt_benchmark(mode: str, nfft: int, hop: int, sr: int, duration: float,
                     batch_size: int, use_graphs: bool, verbose: bool) -> dict[str, float]:
    """Runs a real-time benchmark with pacing to simulate a real-world stream."""
    assert mode in ("cpu", "gpu")

    # The time budget for processing one pair of frames
    budget_s_per_pair = hop / sr
    deadline_ms = budget_s_per_pair * 1000 * 0.8 # Target 80% of time budget

    # Quiet mode for profiler unless verbose is forced
    quiet = is_profiler_attached() and not verbose

    window = np.hanning(nfft).astype(np.float32)

    with nvtx_range(f"run_rt::{mode}"):
        # --- Initialization ---
        if mode == "gpu":
            eng = create_engine(nfft, batch_size, use_graphs, verbose_override=verbose)
            eng.set_window(window) # Preload window to GPU
            eng.prepare_for_execution()

        sig = build_signal(sr, duration + 2.0, nfft)

        latencies_ms = []
        stream_idx = 0
        pairs_per_batch = batch_size // 2

        # --- Real-Time Simulation Loop ---
        pbar = tqdm(total=duration, desc=f"Simulating ({mode.upper()})",
                    unit="s", disable=quiet)

        t_global_start = time.perf_counter()
        total_pairs_processed = 0

        with nvtx_range("rt_loop"):
            while (time.perf_counter() - t_global_start) < duration:
                # Calculate when the next batch of data would be "available"
                if mode == "gpu":
                    target_time = t_global_start + (total_pairs_processed / pairs_per_batch) * (budget_s_per_pair * pairs_per_batch)
                else: # CPU
                    target_time = t_global_start + total_pairs_processed * budget_s_per_pair

                # Pacing: Wait until the target time is reached
                while time.perf_counter() < target_time:
                    # Sleep for most of the wait time to yield the CPU
                    sleep_duration = target_time - time.perf_counter()
                    if sleep_duration > 2e-4:
                        time.sleep(sleep_duration - 2e-4)

                # --- Latency Measurement ---
                with nvtx_range(f"iter_compute::{mode}"):
                    t_iter_start = time.perf_counter()

                    if mode == "gpu":
                        # Ensure the stream's previous work is done and get its output
                        eng.sync_stream(stream_idx)
                        _ = eng.pinned_output(stream_idx)[0]

                        # Prepare the next batch of input data
                        offset = total_pairs_processed * hop
                        ch1_frames = [sig["ch1"][offset + i*hop : offset + i*hop + nfft] for i in range(pairs_per_batch)]
                        ch2_frames = [sig["ch2"][offset + i*hop : offset + i*hop + nfft] for i in range(pairs_per_batch)]
                        input_batch = np.concatenate(ch1_frames + ch2_frames).astype(np.float32, copy=False)

                        # Asynchronously execute
                        dst = eng.pinned_input(stream_idx)      # (batch, nfft) view
                        dst.ravel()[:] = input_batch            # flatten dest so shapes match (B*N,)
                        eng.execute_async(stream_idx)
                    else: # CPU
                        offset = total_pairs_processed * hop
                        ch1 = sig["ch1"][offset:offset+nfft] * window
                        ch2 = sig["ch2"][offset:offset+nfft] * window
                        _ = np.fft.rfft(ch1)
                        _ = np.fft.rfft(ch2)

                    latencies_ms.append((time.perf_counter() - t_iter_start) * 1e3)

                # Advance state for the next iteration
                if mode == "gpu":
                    stream_idx = (stream_idx + 1) % eng.num_streams
                    total_pairs_processed += pairs_per_batch
                else:
                    total_pairs_processed += 1

                pbar.n = min(time.perf_counter() - t_global_start, duration)
                pbar.refresh()

        if mode == "gpu":
            eng.synchronize_all_streams()
        pbar.close()

    stats = compute_stats(latencies_ms)
    stats['missed_dl'] = np.sum(np.array(latencies_ms) > deadline_ms)
    stats['deadline_ms'] = deadline_ms
    return stats

# ───────────────────────────────── Main ───────────────────────────────────────
def main(args: argparse.Namespace):
    if CudaFftEngine is None or tqdm is None:
        return

    if args.batch_size % 2 != 0:
        raise ValueError("Batch size must be an even number for a dual-channel system.")

    hop = int(args.nfft * (1 - args.overlap))
    use_graphs = not args.no_graphs

    # Use safe_print for ALL output to avoid Unicode issues
    print_header("Real-Time FFT Latency Benchmark")
    safe_print(f"Config: NFFT={args.nfft}, Batch={args.batch_size}, Fs={args.sr/1e3:.1f} kHz, "
               f"Hop={hop}, Duration={args.duration:.1f}s, CUDA Graphs: {'ON' if use_graphs else 'OFF'}")

    cpu_stats = {}
    if not args.no_cpu:
        cpu_stats = run_rt_benchmark("cpu", args.nfft, hop, args.sr, args.duration,
                                     args.batch_size, use_graphs=False, verbose=args.verbose)

    gpu_stats = {}
    if not args.no_gpu:
        gpu_stats = run_rt_benchmark("gpu", args.nfft, hop, args.sr, args.duration,
                                     args.batch_size, use_graphs, args.verbose)

    deadline = cpu_stats.get('deadline_ms', gpu_stats.get('deadline_ms', 0))
    print_header(f"Latency Results (Deadline: {deadline:.2f} ms)")
    safe_print(f"{'Metric':<12} {'CPU (1-Core)':>20} {'GPU (3-Stream)':>20} {'Improvement':>20}")
    print_separator()

    metrics = [('Mean', 'mean'), ('Median', 'median'), ('Std Dev', 'stdev'),
               ('Min', 'min'), ('Max', 'max'), ('P95', 'p95'), ('P99', 'p99')]

    for name, key in metrics:
        cpu_val = cpu_stats.get(key, 0)
        gpu_val = gpu_stats.get(key, 0)
        imp = ((cpu_val - gpu_val) / cpu_val * 100) if cpu_val > 0 else 0
        safe_print(f"{name:<12} {fmt_t(cpu_val):>20} {fmt_t(gpu_val):>20} {imp:>19.1f}%")

    print_separator()
    cpu_miss = cpu_stats.get('missed_dl', 0)
    gpu_miss = gpu_stats.get('missed_dl', 0)
    safe_print(f"{'Missed DL':<12} {cpu_miss:>20,} {gpu_miss:>20,}")
    print_separator()

    if gpu_stats.get('mean', 0) > 0 and cpu_stats.get('mean', 0) > 0:
        speed_up = cpu_stats['mean'] / gpu_stats['mean']
        safe_print(f"-> Average Latency Reduction: x{speed_up:,.2f}")  # Changed rocket emoji to ->

# ─────────────────────────────── CLI ──────────────────────────────────────────
def parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Real-time latency FFT benchmark comparing CPU and GPU.")
    p.add_argument("-n", "--nfft", type=int, default=4096, help="FFT length")
    p.add_argument("-b", "--batch-size", type=int, default=2, help="Total FFTs per GPU batch (must be even)")
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
        safe_print(f"\nERROR: An error occurred: {e}", file=sys.stderr)
        sys.exit(1)
