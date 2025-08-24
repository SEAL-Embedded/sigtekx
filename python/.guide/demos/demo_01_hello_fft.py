#!/usr/bin/env python3
"""
demo_01_hello_fft.py
====================
Your first GPU-accelerated FFT! 

This demo shows the absolute basics:
1. Create the engine
2. Process a simple signal
3. Compare GPU vs CPU speed

Run: python demo_01_hello_fft.py
"""

import numpy as np
import time
from cuda_lib import CudaFftEngine
import matplotlib.pyplot as plt

def main():
    print("🚀 Hello FFT - Your First GPU Acceleration!\n")
    
    # Configuration
    nfft = 4096        # FFT size (must be power of 2)
    batch_size = 32    # Process 32 signals at once
    
    # Create the GPU engine
    print("Creating GPU engine...")
    engine = CudaFftEngine(nfft=nfft, batch=batch_size, use_graphs=True, verbose=False)
    engine.prepare_for_execution()  # Warm up the GPU
    
    # Generate test signals (32 different frequencies)
    print("\nGenerating test signals...")
    signals = []
    sample_rate = 48000  # Hz
    duration = nfft / sample_rate
    t = np.linspace(0, duration, nfft, dtype=np.float32)
    
    for i in range(batch_size):
        # Each signal has a different frequency
        freq = 1000 + i * 100  # 1000Hz, 1100Hz, 1200Hz, etc.
        signal = np.sin(2 * np.pi * freq * t)
        signals.append(signal)
    
    signals = np.array(signals, dtype=np.float32).flatten()
    
    # ============ GPU Processing ============
    print("\n⚡ GPU Processing...")
    gpu_start = time.perf_counter()
    
    # Copy to GPU, process, and get results
    engine.pinned_input(0)[:] = signals
    engine.execute_async(0)
    engine.sync_stream(0)
    gpu_results = engine.pinned_output(0).copy()
    
    gpu_time = time.perf_counter() - gpu_start
    
    # ============ CPU Processing ============
    print("🐌 CPU Processing...")
    cpu_start = time.perf_counter()
    
    cpu_results = []
    for i in range(batch_size):
        signal = signals[i*nfft:(i+1)*nfft]
        fft = np.fft.rfft(signal)
        magnitude = np.abs(fft)
        cpu_results.append(magnitude)
    
    cpu_results = np.array(cpu_results).flatten()
    cpu_time = time.perf_counter() - cpu_start
    
    # ============ Results ============
    print("\n" + "="*50)
    print("📊 RESULTS")
    print("="*50)
    print(f"GPU Time: {gpu_time*1000:.2f} ms")
    print(f"CPU Time: {cpu_time*1000:.2f} ms")
    print(f"Speedup:  {cpu_time/gpu_time:.1f}x faster! 🎉")
    
    # Verify accuracy
    error = np.mean(np.abs(gpu_results - cpu_results))
    print(f"\nAccuracy check (mean error): {error:.6f}")
    print("✅ Results match!" if error < 1e-3 else "❌ Results differ!")
    
    # ============ Visualization ============
    print("\n📈 Plotting first signal's spectrum...")
    
    freq_bins = np.fft.rfftfreq(nfft, 1/sample_rate)
    first_spectrum = gpu_results[:nfft//2+1]
    
    plt.figure(figsize=(10, 6))
    plt.plot(freq_bins[:500], first_spectrum[:500])
    plt.title(f'First Signal Spectrum (1000 Hz sine wave)')
    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Magnitude')
    plt.grid(True, alpha=0.3)
    plt.axvline(x=1000, color='r', linestyle='--', label='Expected peak')
    plt.legend()
    plt.tight_layout()
    plt.show()
    
    print("\n🎯 Congratulations! You just accelerated FFTs by", f"{cpu_time/gpu_time:.0f}x!")
    print("Try changing nfft or batch_size to see how performance scales.")

if __name__ == "__main__":
    main()