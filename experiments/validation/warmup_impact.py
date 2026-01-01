"""Validate warmup impact on throughput measurements."""
import re
import subprocess
import sys
from pathlib import Path


def run_throughput_benchmark(warmup_iterations: int, warmup_duration_s: float, label: str) -> dict:
    """Run throughput benchmark and extract metrics."""
    print(f"\n{'='*60}")
    print(f"Running: {label}")
    print(f"  warmup_iterations={warmup_iterations}, warmup_duration_s={warmup_duration_s}")
    print(f"{'='*60}\n")

    cmd = [
        sys.executable,
        "benchmarks/run_throughput.py",
        "experiment=baseline",
        "+benchmark=throughput",
        f"benchmark.warmup_iterations={warmup_iterations}",
        f"benchmark.warmup_duration_s={warmup_duration_s}",
        "benchmark.test_duration_s=10.0",  # 10 second test
        "--config-path=../experiments/conf",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=Path(__file__).parent.parent.parent,  # 3 levels up to project root
        )

        # Look for metrics in stdout/stderr
        output = result.stdout + result.stderr

        # Try to find throughput metrics
        metrics = {}

        # Look for frames/second
        fps_match = re.search(r'frames_per_second["\']?\s*[:=]\s*([\d.]+)', output, re.IGNORECASE)
        if fps_match:
            metrics['fps'] = float(fps_match.group(1))

        # Look for GB/second
        gbs_match = re.search(r'gigabytes_per_second["\']?\s*[:=]\s*([\d.]+)', output, re.IGNORECASE)
        if gbs_match:
            metrics['gb_s'] = float(gbs_match.group(1))

        # Look for megasamples/second
        ms_match = re.search(r'megasamples_per_second["\']?\s*[:=]\s*([\d.]+)', output, re.IGNORECASE)
        if ms_match:
            metrics['ms_s'] = float(ms_match.group(1))

        # If no metrics found, try MLflow artifacts
        if not metrics:
            print("Warning: No metrics found in output, benchmark may have failed")
            print("Last 20 lines of output:")
            print('\n'.join(output.split('\n')[-20:]))

        return metrics

    except subprocess.TimeoutExpired:
        print("ERROR: Benchmark timed out after 120s")
        return {}
    except Exception as e:
        print(f"ERROR: {e}")
        return {}

def main():
    """Run validation."""
    print("\n" + "="*80)
    print("WARMUP IMPACT VALIDATION")
    print("="*80)

    # Test 1: No warmup (baseline - cold start bias)
    no_warmup_metrics = run_throughput_benchmark(
        warmup_iterations=0,
        warmup_duration_s=0.0,
        label="Baseline (NO WARMUP - includes cold-start bias)"
    )

    # Test 2: With warmup (bias removed)
    with_warmup_metrics = run_throughput_benchmark(
        warmup_iterations=1,
        warmup_duration_s=3.0,
        label="With Warmup (cold-start bias removed)"
    )

    # Compare results
    print("\n" + "="*80)
    print("RESULTS COMPARISON")
    print("="*80)

    if no_warmup_metrics and with_warmup_metrics:
        print(f"\n{'Metric':<25} {'No Warmup':>15} {'With Warmup':>15} {'Improvement':>15}")
        print("-" * 80)

        for key in no_warmup_metrics:
            if key in with_warmup_metrics:
                no_warmup = no_warmup_metrics[key]
                with_warmup = with_warmup_metrics[key]
                improvement = ((with_warmup - no_warmup) / no_warmup) * 100

                unit = {'fps': 'fps', 'gb_s': 'GB/s', 'ms_s': 'MS/s'}.get(key, '')
                print(f"{unit:<25} {no_warmup:>15.2f} {with_warmup:>15.2f} {improvement:>+14.1f}%")

        # Expected improvement: 1-5% (task description says ~2%)
        if 'fps' in no_warmup_metrics and 'fps' in with_warmup_metrics:
            improvement = ((with_warmup_metrics['fps'] - no_warmup_metrics['fps']) /
                          no_warmup_metrics['fps']) * 100
            print(f"\n{'='*80}")
            print(f"BIAS CORRECTION: +{improvement:.1f}% throughput improvement")
            if 1.0 <= improvement <= 10.0:
                print("✓ Within expected range (1-10% for cold-start removal)")
            elif improvement < 0:
                print("⚠ WARNING: Negative improvement - warmup may be introducing overhead")
            else:
                print(f"⚠ WARNING: Improvement higher than expected ({improvement:.1f}% > 10%)")
            print(f"{'='*80}\n")
    else:
        print("\n⚠ WARNING: Could not extract metrics from one or both runs")
        print("No warmup metrics:", no_warmup_metrics)
        print("With warmup metrics:", with_warmup_metrics)

if __name__ == "__main__":
    main()
