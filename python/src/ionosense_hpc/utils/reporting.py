"""Console reporting utilities for formatted benchmark and analysis output.

This module provides functions to print structured and human-readable reports
for performance, throughput, and accuracy, suitable for research documentation
and analysis.
"""

import json
from typing import Any

try:
    from tabulate import tabulate
    TABULATE_AVAILABLE = True
except ImportError:
    TABULATE_AVAILABLE = False


def print_header(title: str):
    """Prints a formatted header to the console."""
    bar = "=" * 80
    print(f"\n{bar}\n {title.upper()}\n{bar}")


def print_dict_as_json(data: dict[str, Any]):
    """Prints a dictionary as pretty-printed JSON."""
    print(json.dumps(data, indent=2, default=str))


def fmt_ms_to_us(val_ms: float) -> str:
    """Formats a millisecond value to μs or ms for readability."""
    return f"{val_ms * 1000:.2f} μs" if val_ms < 1.0 else f"{val_ms:.2f} ms"


def print_latency_report(results: dict[str, Any], title: str = "Latency Report"):
    """Prints a formatted report of latency benchmark results."""
    print_header(title)
    table = [
        ["Mean", fmt_ms_to_us(results.get('mean_us', 0) / 1000)],
        ["Std Dev", fmt_ms_to_us(results.get('std_us', 0) / 1000)],
        ["Median (p50)", fmt_ms_to_us(results.get('p50_us', 0) / 1000)],
        ["p95", fmt_ms_to_us(results.get('p90_us', 0) / 1000)],
        ["p99", fmt_ms_to_us(results.get('p99_us', 0) / 1000)],
        ["Min", fmt_ms_to_us(results.get('min_us', 0) / 1000)],
        ["Max", fmt_ms_to_us(results.get('max_us', 0) / 1000)],
    ]
    if 'deadline_ms' in results:
        table.extend([
            ["-"*15, "-"*15],
            ["Deadline", f"{results['deadline_ms']:.2f} ms"],
            ["Missed Deadlines", f"{results.get('missed_dl', 0)} ({results.get('miss_rate', 0):.2%})"]
        ])

    if TABULATE_AVAILABLE:
        print(tabulate(table, headers=["Metric", "Value"], tablefmt="heavy_outline", stralign="right"))
    else:
        for row in table:
            print(f"  {row[0]:<20}: {row[1]}")


def print_throughput_report(results: dict[str, Any], title: str = "Throughput Report"):
    """Prints a formatted report of throughput benchmark results."""
    print_header(title)
    tp = results.get('throughput', {})
    rt = results.get('runtime', {})
    table = [
        ["Duration", f"{rt.get('elapsed_seconds', 0):.2f} s"],
        ["Frames Processed", f"{rt.get('frames_processed', 0):,}"],
        ["Frames per Second", f"{tp.get('frames_per_second', 0):,.1f} FPS"],
        ["Data Throughput", f"{tp.get('gb_per_second', 0):.2f} GB/s"],
    ]
    if TABULATE_AVAILABLE:
        print(tabulate(table, headers=["Metric", "Value"], tablefmt="heavy_outline", stralign="right"))
    else:
        for row in table:
            print(f"  {row[0]:<20}: {row[1]}")


def print_accuracy_report(results: dict[str, Any], title: str = "Accuracy Report"):
    """Prints a formatted report of accuracy validation results."""
    print_header(title)
    summary = results['summary']
    pass_rate = summary.get('pass_rate', 0)

    status = "✅ PASSED" if pass_rate == 1.0 else ("⚠️  WARNING" if pass_rate > 0 else "❌ FAILED")
    print(f"Overall Result: {status} ({summary['passed']}/{summary['total_tests']} tests passed, {pass_rate:.1%})")
    print(f"Tolerance: {results['tolerance']:.1e}\n")

    table = [[test['signal']['type'], "✅" if test['passed'] else "❌", f"{test['max_error']:.3e}"]
             for test in results['tests']]

    if TABULATE_AVAILABLE:
        print(tabulate(table, headers=["Signal Type", "Passed", "Max Relative Error"], tablefmt="heavy_outline", stralign="center"))
    else:
        for row in table:
            print(f"  {row[0]:<15} {row[1]:<7} {row[2]}")
