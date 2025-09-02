#!/usr/bin/env python3
"""
fft_graphs_comp.py
---------------------------------------------------------------
Benchmarks CUDA Graph performance vs traditional kernel launches
for the FFT engine. Performs A/B testing to measure:
1. Launch overhead reduction
2. Overall throughput improvement
3. Latency consistency (jitter reduction)
"""

import argparse
import sys
import time

import numpy as np

# Import shared components from the utils module
from utils import (
    CudaFftEngine,
    compute_stats,
    fmt_t,
    nvtx_range,
    print_header,
    print_separator,
    safe_print,
)

# ─────────────────────────── Benchmark Functions ────────────────────

def benchmark_latency(engine: CudaFftEngine,
                     num_iterations: int) -> dict[str, float]:
    """
    Measure per-iteration host-side latency for the FFT pipeline.
    This is a good proxy for measuring CPU overhead per call.
    """
    latencies = []
    stream_idx = 0
    data_size = engine.fft_size * engine.batch_size
    test_data = np.random.randn(data_size).astype(np.float32)

    # NVTX range to label the entire latency measurement loop
    mode_str = "Graphs" if engine.get_use_graphs() else "No-Graphs"
    with nvtx_range(f"Latency Loop ({mode_str})"):
        for _ in range(num_iterations):
            t_start = time.perf_counter()

            # This block represents the work a host would do in a tight loop
            engine.sync_stream(stream_idx)
            engine.pinned_input(stream_idx)[:] = test_data
            engine.execute_async(stream_idx)

            t_end = time.perf_counter()
            latencies.append((t_end - t_start) * 1000)  # Convert to ms

            stream_idx = (stream_idx + 1) % engine.num_streams

    # Final sync to ensure all work is complete before exiting
    for i in range(engine.num_streams):
        engine.sync_stream(i)

    # Skip first few iterations to avoid warmup effects in stats
    return compute_stats(latencies[10:])

def benchmark_throughput(engine: CudaFftEngine,
                        duration_sec: float) -> dict[str, float]:
    """
    Measure maximum throughput (iterations/sec) over a fixed duration.
    """
    stream_idx = 0
    iterations = 0
    data_size = engine.fft_size * engine.batch_size
    test_data = np.random.randn(data_size).astype(np.float32)

    t_start = time.perf_counter()
    t_end = t_start + duration_sec

    # NVTX range to label the entire throughput measurement loop
    mode_str = "Graphs" if engine.get_use_graphs() else "No-Graphs"
    with nvtx_range(f"Throughput Loop ({mode_str})"):
        while time.perf_counter() < t_end:
            engine.sync_stream(stream_idx)
            engine.pinned_input(stream_idx)[:] = test_data
            engine.execute_async(stream_idx)
            stream_idx = (stream_idx + 1) % engine.num_streams
            iterations += 1

    # Final sync to ensure GPU is idle before stopping the timer
    for i in range(engine.num_streams):
        engine.sync_stream(i)

    actual_duration = time.perf_counter() - t_start
    throughput = iterations / actual_duration if actual_duration > 0 else 0

    return {
        'iterations': iterations,
        'throughput_fps': throughput
    }

# ─────────────────────────── Main Benchmark ────────────────────────
def run_comparison(nfft: int, batch: int, iterations: int, duration: float):
    """Run complete comparison between graph and non-graph modes."""
    if CudaFftEngine is None: return

    print_header("CUDA FFT Engine Graph Benchmark")
    safe_print(f"Configuration: NFFT={nfft}, Batch={batch}\n")

    # ──────────── Test with Graphs Disabled ────────────
    with nvtx_range("Test Without Graphs"):
        safe_print("[NO GRAPHS] Testing WITHOUT graphs...")
        engine_no_graph = CudaFftEngine(nfft, batch, use_graphs=False, verbose=False)

        with nvtx_range("Warmup (No-Graphs)"):
            safe_print("   Warming up GPU...")
            for i in range(20):
                engine_no_graph.execute_async(i % engine_no_graph.num_streams)
            for i in range(engine_no_graph.num_streams):
                engine_no_graph.sync_stream(i)

        safe_print(f"   Running latency test ({iterations} iterations)...")
        latency_no_graph = benchmark_latency(engine_no_graph, iterations)

        safe_print(f"   Running throughput test ({duration:.1f}s)...")
        throughput_no_graph = benchmark_throughput(engine_no_graph, duration)

        del engine_no_graph # Clean up resources
        time.sleep(0.5)

    # ──────────── Test with Graphs Enabled (Corrected) ────────────
    with nvtx_range("Test With Graphs"):
        safe_print("\n[GRAPHS] Testing WITH graphs...")
        engine_graph = CudaFftEngine(nfft, batch, use_graphs=True, verbose=True)

        with nvtx_range("Warmup and Capture (Graphs)"):
            safe_print("   Warming up and capturing graphs...")
            engine_graph.prepare_for_execution()
            safe_print(f"   Graphs ready: {engine_graph.graphs_ready()}")

        safe_print(f"   Running latency test ({iterations} iterations)...")
        latency_graph = benchmark_latency(engine_graph, iterations)

        safe_print(f"   Running throughput test ({duration:.1f}s)...")
        throughput_graph = benchmark_throughput(engine_graph, duration)

        del engine_graph # Clean up resources

    # ──────────── Display Results ────────────
    safe_print("")
    print_header("Results")

    # Latency comparison
    safe_print("\n== LATENCY COMPARISON (Host-side per iteration) ==")
    print_separator(width=70)
    safe_print(f"{'Metric':<20} {'No Graphs':>15} {'With Graphs':>15} {'Improvement':>15}")
    print_separator(width=70)

    metrics = [('Mean', 'mean'), ('Median', 'median'), ('Std Dev', 'stdev'),
               ('Min', 'min'), ('Max', 'max'), ('P95', 'p95'), ('P99', 'p99')]

    for name, key in metrics:
        no_graph_val = latency_no_graph[key]
        graph_val = latency_graph[key]
        improvement = ((no_graph_val - graph_val) / no_graph_val * 100) if no_graph_val > 0 else 0
        safe_print(f"{name:<20} {fmt_t(no_graph_val):>15} {fmt_t(graph_val):>15} {improvement:>14.1f}%")

    # Throughput comparison
    safe_print("\n== THROUGHPUT COMPARISON ==")
    print_separator(width=70)
    safe_print(f"{'Metric':<20} {'No Graphs':>15} {'With Graphs':>15} {'Improvement':>15}")
    print_separator(width=70)

    no_graph_fps = throughput_no_graph['throughput_fps']
    graph_fps = throughput_graph['throughput_fps']
    fps_improvement = ((graph_fps - no_graph_fps) / no_graph_fps * 100) if no_graph_fps > 0 else 0

    safe_print(f"{'Throughput (FPS)':<20} {no_graph_fps:>14.1f} {graph_fps:>14.1f} {fps_improvement:>14.1f}%")
    safe_print(f"{'Total iterations':<20} {throughput_no_graph['iterations']:>14,} {throughput_graph['iterations']:>14,}")

    # Summary
    safe_print("")
    print_header("Summary")
    latency_reduction = ((latency_no_graph['mean'] - latency_graph['mean']) / latency_no_graph['mean'] * 100)
    jitter_reduction = ((latency_no_graph['stdev'] - latency_graph['stdev']) / latency_no_graph['stdev'] * 100) if latency_no_graph['stdev'] > 0 else 0

    safe_print(f"[OK] Average latency reduction: {latency_reduction:.1f}%")
    safe_print(f"[OK] Throughput improvement: {fps_improvement:.1f}%")
    safe_print(f"[OK] Jitter (stdev) reduction: {jitter_reduction:.1f}%")

# ─────────────────────────── CLI ────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(description="Benchmark CUDA Graph performance for FFT engine")
    parser.add_argument('-n', '--nfft', type=int, default=4096, help='FFT size (default: 4096)')
    parser.add_argument('-b', '--batch', type=int, default=2, help='Batch size (default: 2)')
    parser.add_argument('-i', '--iterations', type=int, default=1000, help='Number of iterations for latency test (default: 1000)')
    parser.add_argument('-d', '--duration', type=float, default=5.0, help='Duration for throughput test in seconds (default: 5.0)')
    return parser.parse_args()

# ─────────────────────────── Main ────────────────────────────
if __name__ == "__main__":
    args = parse_args()
    try:
        run_comparison(
            nfft=args.nfft,
            batch=args.batch,
            iterations=args.iterations,
            duration=args.duration
        )
    except Exception as e:
        safe_print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
