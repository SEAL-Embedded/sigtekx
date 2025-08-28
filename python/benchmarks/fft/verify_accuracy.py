#!/usr/bin/env python3
"""
verify_accuracy.py
---------------------------------------------------------------
An end-to-end verification script to confirm the numerical
accuracy of the CUDA FFT engine against a NumPy reference.

Its primary purpose is to prove correctness. It also provides a
basic, non-real-time throughput benchmark to correlate performance
gains with numerical precision.
"""

from __future__ import annotations
import argparse
import time
import numpy as np
import sys

from utils import (
    CudaFftEngine,
    nvtx_range,
    build_signal,
    print_header,
    print_separator,
    safe_print
)

def mean_squared_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calculates the Mean Squared Error."""
    return np.mean(np.square(y_true - y_pred))

def run_verification(nfft: int, batch_size: int, sr: int, duration: float) -> None:
    """
    Runs the full verification and non-real-time performance test.
    """
    if CudaFftEngine is None:
        safe_print("FATAL: CudaFftEngine not available. Aborting.", file=sys.stderr)
        sys.exit(1)

    safe_print(f"Config: NFFT={nfft}, Batch={batch_size}, Fs={sr/1e3:.1f} kHz, Duration={duration:.1f}s")
    print_separator()

    # --- Test Data Generation ---
    with nvtx_range("build_signal"):
        sig = build_signal(sr, duration, nfft)
        window = np.hanning(nfft).astype(np.float32)
        total_frames = (len(sig['ch1']) - nfft) // nfft
        num_pairs_in_batch = batch_size // 2

    # --- 1. CPU Reference Implementation ---
    safe_print("Running CPU reference...")
    cpu_results = []
    
    with nvtx_range("cpu_run"):
        t_start_cpu = time.perf_counter()
        loop_iterations = range(0, total_frames, num_pairs_in_batch)
        for i in loop_iterations:
            ch1_frames = [sig["ch1"][ (i + j) * nfft : (i + j) * nfft + nfft] for j in range(num_pairs_in_batch)]
            ch2_frames = [sig["ch2"][ (i + j) * nfft : (i + j) * nfft + nfft] for j in range(num_pairs_in_batch)]

            ref_ch1_fft = [np.abs(np.fft.rfft(frame * window)) for frame in ch1_frames]
            ref_ch2_fft = [np.abs(np.fft.rfft(frame * window)) for frame in ch2_frames]
            
            if (i + num_pairs_in_batch) >= total_frames:
                cpu_results = np.concatenate(ref_ch1_fft + ref_ch2_fft)
        t_end_cpu = time.perf_counter()

    cpu_time_ms = (t_end_cpu - t_start_cpu) * 1000
    safe_print(f"  -> CPU processing finished in {cpu_time_ms:.3f} ms")


    # --- 2. GPU Implementation ---
    safe_print("\nRunning GPU implementation...")
    gpu_results = []

    with nvtx_range("gpu_run"):
        eng = CudaFftEngine(nfft, batch_size, use_graphs=True, verbose=False)
        eng.set_window(window)
        eng.prepare_for_execution()
        stream_idx = 0

        t_start_gpu = time.perf_counter()
        for i in loop_iterations:
            eng.sync_stream(stream_idx)
            
            ch1_frames = [sig["ch1"][ (i + j) * nfft : (i + j) * nfft + nfft] for j in range(num_pairs_in_batch)]
            ch2_frames = [sig["ch2"][ (i + j) * nfft : (i + j) * nfft + nfft] for j in range(num_pairs_in_batch)]
            input_batch = np.concatenate(ch1_frames + ch2_frames)
            
            eng.pinned_input(stream_idx)[:] = input_batch
            eng.execute_async(stream_idx)
            
            stream_idx = (stream_idx + 1) % eng.num_streams

        for i in range(eng.num_streams):
            eng.sync_stream(i)
        
        t_end_gpu = time.perf_counter()

        last_stream_idx = (stream_idx - 1 + eng.num_streams) % eng.num_streams
        gpu_results = eng.pinned_output(last_stream_idx)

    gpu_time_ms = (t_end_gpu - t_start_gpu) * 1000
    safe_print(f"  -> GPU processing finished in {gpu_time_ms:.3f} ms")


    # --- 3. Verification and Reporting ---
    safe_print("")
    print_header("Verification & Performance Report")
    
    # Throughput Calculation
    total_ffts_processed = len(loop_iterations) * batch_size
    cpu_ffts_per_sec = total_ffts_processed / (cpu_time_ms / 1000.0) if cpu_time_ms > 0 else 0
    gpu_ffts_per_sec = total_ffts_processed / (gpu_time_ms / 1000.0) if gpu_time_ms > 0 else 0

    # --- Side-by-Side Performance Report ---
    safe_print(f"{'Performance Metric':<25} {'CPU (Single Thread)':>20} {'GPU (3-Stream)':>20}")
    print_separator()
    safe_print(f"{'Total Processing Time':<25} {f'{cpu_time_ms:.2f} ms':>20} {f'{gpu_time_ms:.2f} ms':>20}")
    safe_print(f"{'Throughput (FFTs/sec)':<25} {f'{cpu_ffts_per_sec:,.0f}':>20} {f'{gpu_ffts_per_sec:,.0f}':>20}")
    
    safe_print("")
    
    # --- Accuracy Report ---
    if cpu_results.size == 0 or gpu_results.size == 0:
         safe_print("Could not perform accuracy check: one of the results was empty.")
    else:
        max_abs_error = np.max(np.abs(cpu_results - gpu_results))
        mse = mean_squared_error(cpu_results, gpu_results)
        
        safe_print(f"{'Accuracy Metric':<25} {'Value'}")
        print_separator()
        safe_print(f"{'Max Absolute Error':<25} {f'{max_abs_error:.9f}':>20}")
        safe_print(f"{'Mean Squared Error (MSE)':<25} {f'{mse:.9f}':>20}")

        # Final pass/fail verdict
        print_separator()
        if max_abs_error < 1e-5:
            safe_print("[PASS] Verification PASSED")
            if gpu_time_ms > 0:
                speed_up = cpu_time_ms / gpu_time_ms
                safe_print(f"-> Throughput Speed-up: x{speed_up:,.2f}")
        else:
            safe_print("[FAIL] Verification FAILED")

def parse_cli() -> argparse.Namespace:
    """Parses command-line arguments."""
    p = argparse.ArgumentParser(description="End-to-end numerical accuracy and throughput benchmark.")
    p.add_argument("-n", "--nfft", type=int, default=4096, help="FFT length")
    p.add_argument("-b", "--batch-size", type=int, default=2, help="Total FFTs per GPU batch (must be even)")
    p.add_argument("-s", "--sr", type=int, default=100_000, help="Sample rate (Hz)")
    p.add_argument("-d", "--duration", type=float, default=5.0, help="Duration of signal to process (seconds)")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_cli()
    if args.batch_size % 2 != 0:
        raise ValueError("Batch size must be an even number for a dual-channel system.")

    print_header("CUDA FFT Engine Verification")
    run_verification(args.nfft, args.batch_size, args.sr, args.duration)