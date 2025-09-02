"""Utilities for printing clean, formatted benchmark reports to the console."""

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
    print(f"\n{bar}")
    print(f" {title.upper()}")
    print(f"{bar}")

def print_dict_as_json(data: dict[str, Any]):
    """Prints a dictionary as a nicely formatted JSON string."""
    print(json.dumps(data, indent=2, default=str))

def fmt_ms_to_us(val_ms: float) -> str:
    """Formats time in milliseconds, switching to microseconds for sub-millisecond values."""
    if val_ms < 1.0:
        return f"{val_ms * 1000:.2f} µs"
    return f"{val_ms:.2f} ms"

def print_latency_report(results: dict[str, Any], title: str = "Latency Report"):
    """Prints a formatted latency report using tabulate if available."""
    print_header(title)

    headers = ["Metric", "Value"]
    table = [
        ["Mean", fmt_ms_to_us(results.get('mean_us', 0) / 1000)],
        ["Std Dev", fmt_ms_to_us(results.get('std_us', 0) / 1000)],
        ["Median (p50)", fmt_ms_to_us(results.get('p50_us', 0) / 1000)],
        ["p95", fmt_ms_to_us(results.get('p90_us', 0) / 1000)],
        ["p99", fmt_ms_to_us(results.get('p99_us', 0) / 1000)],
        ["Min", fmt_ms_to_us(results.get('min_us', 0) / 1000)],
        ["Max", fmt_ms_to_us(results.get('max_us', 0) / 1000)],
    ]

    # Add real-time specific metrics if they exist
    if 'deadline_ms' in results:
        table.append(["-" * 15, "-" * 15]) # Separator
        table.append(["Deadline", f"{results['deadline_ms']:.2f} ms"])
        table.append(["Missed Deadlines", f"{results.get('missed_dl', 0)} ({results.get('miss_rate', 0):.2%})"])

    if TABULATE_AVAILABLE:
        print(tabulate(table, headers=headers, tablefmt="heavy_outline", stralign="right"))
    else:
        print("\n".join([f"  {row[0]:<20}: {row[1]}" for row in table]))


def print_throughput_report(results: dict[str, Any], title: str = "Throughput Report"):
    """Prints a formatted throughput report."""
    print_header(title)
    tp = results.get('throughput', {})
    rt = results.get('runtime', {})

    headers = ["Metric", "Value"]
    table = [
        ["Duration", f"{rt.get('elapsed_seconds', 0):.2f} s"],
        ["Frames Processed", f"{rt.get('frames_processed', 0):,}"],
        ["Frames per Second", f"{tp.get('frames_per_second', 0):,.1f} FPS"],
        ["Data Throughput", f"{tp.get('gb_per_second', 0):.2f} GB/s"],
    ]
    if TABULATE_AVAILABLE:
        print(tabulate(table, headers=headers, tablefmt="heavy_outline", stralign="right"))
    else:
        print("\n".join([f"  {row[0]:<20}: {row[1]}" for row in table]))

def print_accuracy_report(results: dict[str, Any], title: str = "Accuracy Report"):
    """Prints a formatted accuracy report."""
    print_header(title)
    summary = results['summary']
    pass_rate = summary.get('pass_rate', 0)
    status = "✅ PASSED" if pass_rate == 1.0 else "⚠️  WARNING" if pass_rate > 0 else "❌ FAILED"

    print(f"Overall Result: {status} ({summary['passed']}/{summary['total_tests']} tests passed, {pass_rate:.1%})")
    print(f"Tolerance: {results['tolerance']:.1e}\n")

    headers = ["Signal Type", "Passed", "Max Relative Error"]
    table = []
    for test in results['tests']:
        table.append([
            test['signal']['type'],
            "✅" if test['passed'] else "❌",
            f"{test['max_error']:.3e}"
        ])

    if TABULATE_AVAILABLE:
        print(tabulate(table, headers=headers, tablefmt="heavy_outline", stralign="center"))
    else:
        for row in table:
            print(f"  {row[0]:<15} {row[1]:<7} {row[2]}")
