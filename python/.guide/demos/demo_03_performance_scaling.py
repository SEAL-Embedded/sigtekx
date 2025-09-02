#!/usr/bin/env python3
"""
demo_03_performance_scaling.py
==============================
Interactive performance explorer - see how batch size affects throughput!

This demo lets you experiment with different configurations
to understand GPU performance characteristics.

Run: python demo_03_performance_scaling.py
"""

import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from cuda_lib import CudaFftEngine


def benchmark_configuration(nfft, batch_size, duration=1.0, use_graphs=True):
    """Benchmark a specific configuration."""
    try:
        # Create engine
        engine = CudaFftEngine(nfft=nfft, batch=batch_size, use_graphs=use_graphs, verbose=False)

        # Prepare data
        data = np.random.randn(nfft * batch_size).astype(np.float32)

        # Warmup
        if use_graphs:
            engine.prepare_for_execution()
        for _ in range(5):
            engine.pinned_input(0)[:] = data
            engine.execute_async(0)
            engine.sync_stream(0)

        # Timed run
        iterations = 0
        stream_idx = 0
        start = time.perf_counter()

        while (time.perf_counter() - start) < duration:
            engine.pinned_input(stream_idx)[:] = data
            engine.execute_async(stream_idx)
            engine.sync_stream(stream_idx)
            stream_idx = (stream_idx + 1) % 3
            iterations += 1

        elapsed = time.perf_counter() - start

        # Calculate metrics
        total_ffts = iterations * batch_size
        throughput = total_ffts / elapsed
        latency_ms = (elapsed / iterations) * 1000

        return {
            'success': True,
            'throughput': throughput,
            'latency_ms': latency_ms,
            'total_ffts': total_ffts
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def main():
    print("="*70)
    print("🚀 GPU PERFORMANCE SCALING EXPLORER")
    print("="*70)
    print("\nThis demo shows how batch size affects performance.")
    print("We'll test different configurations and visualize the results.\n")

    # Test configurations
    nfft = 4096
    batch_sizes = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]

    print(f"Testing FFT size: {nfft}")
    print(f"Batch sizes: {batch_sizes}\n")

    # Run benchmarks
    results = {
        'batch_size': [],
        'throughput': [],
        'latency_ms': [],
        'efficiency': [],
        'with_graphs': [],
    }

    print("Running benchmarks...")
    print("-" * 50)

    for use_graphs in [False, True]:
        graph_mode = "WITH Graphs" if use_graphs else "NO Graphs"
        print(f"\n{graph_mode}:")

        for batch in batch_sizes:
            print(f"  Batch {batch:3d}: ", end='', flush=True)

            result = benchmark_configuration(nfft, batch, duration=0.5, use_graphs=use_graphs)

            if result['success']:
                results['batch_size'].append(batch)
                results['throughput'].append(result['throughput'])
                results['latency_ms'].append(result['latency_ms'])
                results['efficiency'].append(result['throughput'] / batch)  # Throughput per FFT
                results['with_graphs'].append(use_graphs)

                print(f"{result['throughput']:8.0f} FFTs/sec | {result['latency_ms']:6.2f} ms/batch")
            else:
                print(f"Failed: {result['error']}")

    # Convert to DataFrame for easy analysis
    df = pd.DataFrame(results)

    # ============ Visualization ============
    print("\n" + "="*70)
    print("📊 RESULTS VISUALIZATION")
    print("="*70)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'GPU Performance Analysis (NFFT={nfft})', fontsize=16)

    # Plot 1: Throughput vs Batch Size
    ax1 = axes[0, 0]
    for use_graphs in [False, True]:
        data = df[df['with_graphs'] == use_graphs]
        label = 'With CUDA Graphs' if use_graphs else 'Without Graphs'
        marker = 'o' if use_graphs else 's'
        ax1.plot(data['batch_size'], data['throughput'], marker=marker,
                label=label, linewidth=2, markersize=8)

    ax1.set_xscale('log', base=2)
    ax1.set_xlabel('Batch Size')
    ax1.set_ylabel('Throughput (FFTs/second)')
    ax1.set_title('🚀 Throughput Scaling')
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # Plot 2: Latency vs Batch Size
    ax2 = axes[0, 1]
    for use_graphs in [False, True]:
        data = df[df['with_graphs'] == use_graphs]
        label = 'With CUDA Graphs' if use_graphs else 'Without Graphs'
        marker = 'o' if use_graphs else 's'
        ax2.plot(data['batch_size'], data['latency_ms'], marker=marker,
                label=label, linewidth=2, markersize=8)

    ax2.set_xscale('log', base=2)
    ax2.set_xlabel('Batch Size')
    ax2.set_ylabel('Latency (ms per batch)')
    ax2.set_title('⏱️ Latency Characteristics')
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    # Plot 3: Efficiency (Throughput per FFT)
    ax3 = axes[1, 0]
    for use_graphs in [False, True]:
        data = df[df['with_graphs'] == use_graphs]
        label = 'With CUDA Graphs' if use_graphs else 'Without Graphs'
        marker = 'o' if use_graphs else 's'
        ax3.plot(data['batch_size'], data['efficiency'], marker=marker,
                label=label, linewidth=2, markersize=8)

    ax3.set_xscale('log', base=2)
    ax3.set_xlabel('Batch Size')
    ax3.set_ylabel('Efficiency (Throughput / Batch Size)')
    ax3.set_title('📈 Processing Efficiency')
    ax3.grid(True, alpha=0.3)
    ax3.legend()

    # Plot 4: CUDA Graphs Speedup
    ax4 = axes[1, 1]
    graphs_data = df[df['with_graphs'] == True].set_index('batch_size')
    no_graphs_data = df[df['with_graphs'] == False].set_index('batch_size')

    speedup = graphs_data['throughput'] / no_graphs_data['throughput']
    bars = ax4.bar(range(len(speedup)), speedup.values, color='green', alpha=0.7)
    ax4.set_xticks(range(len(speedup)))
    ax4.set_xticklabels(speedup.index)
    ax4.set_xlabel('Batch Size')
    ax4.set_ylabel('Speedup Factor')
    ax4.set_title('⚡ CUDA Graphs Speedup')
    ax4.axhline(y=1, color='red', linestyle='--', alpha=0.5)
    ax4.grid(True, alpha=0.3, axis='y')

    # Add value labels on bars
    for bar, val in zip(bars, speedup.values, strict=False):
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height,
                f'{val:.2f}x', ha='center', va='bottom')

    plt.tight_layout()

    # ============ Summary Statistics ============
    print("\n📈 KEY INSIGHTS:")
    print("-" * 50)

    # Find optimal batch size for throughput
    best_throughput_idx = df['throughput'].idxmax()
    best_throughput = df.loc[best_throughput_idx]
    print(f"✅ Best Throughput: {best_throughput['throughput']:.0f} FFTs/sec")
    print(f"   → Batch Size: {best_throughput['batch_size']}")
    print(f"   → CUDA Graphs: {'Yes' if best_throughput['with_graphs'] else 'No'}")

    # Find optimal batch size for latency
    best_latency_idx = df['latency_ms'].idxmin()
    best_latency = df.loc[best_latency_idx]
    print(f"\n✅ Best Latency: {best_latency['latency_ms']:.2f} ms")
    print(f"   → Batch Size: {best_latency['batch_size']}")
    print(f"   → CUDA Graphs: {'Yes' if best_latency['with_graphs'] else 'No'}")

    # CUDA Graphs average improvement
    avg_speedup = speedup.mean()
    print(f"\n⚡ CUDA Graphs Average Speedup: {avg_speedup:.2f}x")

    # Recommendations
    print("\n💡 RECOMMENDATIONS:")
    print("-" * 50)
    print("• For maximum throughput: Use batch size 128-256 with CUDA Graphs")
    print("• For minimum latency: Use batch size 1-4 with CUDA Graphs")
    print("• For balanced performance: Use batch size 32-64")
    print("• Always enable CUDA Graphs for 20-50% performance boost")

    plt.show()

if __name__ == "__main__":
    main()
