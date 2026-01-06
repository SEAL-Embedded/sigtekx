#!/usr/bin/env python
"""
Baseline Management CLI Helper

This script provides command-line interface for baseline archiving operations.
Called by scripts/cli.ps1's Invoke-Baseline function.

Usage:
    python baseline_helper.py save <name> [--phase <n>] [--message <msg>]
    python baseline_helper.py list [--phase <n>] [--verbose]
    python baseline_helper.py compare <name1> <name2>  # Phase 1 feature
    python baseline_helper.py delete <name> [--force]  # Phase 2 feature
    python baseline_helper.py export <name> <dest>     # Phase 2 feature
"""

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.sigtekx.utils.baseline import BaselineManager


def cmd_save(args):
    """Save current artifacts as a baseline."""
    manager = BaselineManager()

    try:
        baseline_path = manager.save_baseline(
            name=args.name,
            phase=args.phase,
            message=args.message or ""
        )

        # Success output
        print(f"[SUCCESS] Baseline saved: {args.name}")
        print(f"   Location: {baseline_path}")

        # Load metadata to show summary
        metadata = manager.load_baseline_metadata(args.name)
        if metadata:
            print(f"   Phase: {metadata.get('phase', 'N/A')}")
            print(f"   Size: {metadata.get('size_mb', 0):.1f} MB")

            # Show key metrics if available
            metrics = metadata.get('metrics', {})
            if metrics:
                print(f"   Metrics:")
                for key, value in list(metrics.items())[:3]:  # Show first 3 metrics
                    print(f"     - {key}: {value}")

        return 0

    except Exception as e:
        print(f"[ERROR] Error saving baseline: {e}", file=sys.stderr)
        return 1


def cmd_list(args):
    """List all saved baselines."""
    manager = BaselineManager()

    try:
        baselines = manager.list_baselines(phase_filter=args.phase)

        if not baselines:
            print("No baselines found.")
            if args.phase:
                print(f"(filtered by phase {args.phase})")
            return 0

        # Header
        print(f"\n{'Name':<30} {'Phase':<8} {'Created':<20} {'Size':>10}")
        print("=" * 75)

        # List baselines
        for baseline in baselines:
            name = baseline.get('name', 'Unknown')
            phase = baseline.get('phase', 'N/A')
            created = baseline.get('created', 'N/A')[:19]  # Trim timestamp
            size_mb = baseline.get('size_mb', 0)

            print(f"{name:<30} {str(phase):<8} {created:<20} {size_mb:>9.1f}MB")

        print(f"\nTotal: {len(baselines)} baseline(s)")

        # Verbose output
        if args.verbose and baselines:
            print("\nDetails:")
            for baseline in baselines:
                print(f"\n  {baseline['name']}:")
                print(f"    Phase: {baseline.get('phase', 'N/A')}")
                print(f"    Message: {baseline.get('message', 'No message')}")
                print(f"    Git commit: {baseline.get('git_commit', 'N/A')[:8]}")

                metrics = baseline.get('metrics', {})
                if metrics:
                    print(f"    Metrics: {len(metrics)} recorded")

        return 0

    except Exception as e:
        print(f"[ERROR] Error listing baselines: {e}", file=sys.stderr)
        return 1


def cmd_compare(args):
    """Compare two baselines."""
    manager = BaselineManager()

    try:
        comparison = manager.compare_baselines(args.name1, args.name2)

        # Print header
        print(f"\n{'='*100}")
        print(f"Baseline Comparison: {args.name1} vs {args.name2}")
        print(f"{'='*100}")

        # Print baseline metadata
        summary = comparison['summary']
        metadata1 = comparison['baseline1']
        metadata2 = comparison['baseline2']

        print(f"\n{args.name1}:")
        print(f"  Phase: {summary.get('baseline1_phase', 'N/A')}")
        print(f"  Created: {summary.get('baseline1_created', 'N/A')[:19]}")
        hw1 = metadata1.get('hardware', {})
        if hw1:
            gpu_name = hw1.get('gpu_name', 'N/A')
            cpu_info = hw1.get('cpu', 'N/A')
            print(f"  Hardware: {gpu_name} | {cpu_info}")

        print(f"\n{args.name2}:")
        print(f"  Phase: {summary.get('baseline2_phase', 'N/A')}")
        print(f"  Created: {summary.get('baseline2_created', 'N/A')[:19]}")
        hw2 = metadata2.get('hardware', {})
        if hw2:
            gpu_name = hw2.get('gpu_name', 'N/A')
            cpu_info = hw2.get('cpu', 'N/A')
            print(f"  Hardware: {gpu_name} | {cpu_info}")

            # Warn if hardware differs
            if hw1 and hw1.get('gpu_name') != hw2.get('gpu_name'):
                print(f"\n[WARNING] Different GPUs detected - comparison may not be valid!")
                print(f"  {args.name1}: {hw1.get('gpu_name', 'N/A')}")
                print(f"  {args.name2}: {hw2.get('gpu_name', 'N/A')}")

        # Organize metrics by category
        metrics = comparison['metrics']
        if not metrics:
            print("\nNo metrics available for comparison.")
            return 0

        def format_metric_row(name, val1, val2, delta, pct_change, lower_is_better=True):
            """Format a single metric row with indicator."""
            val1_str = f"{val1:.2f}" if val1 is not None else "N/A"
            val2_str = f"{val2:.2f}" if val2 is not None else "N/A"

            if delta is not None and pct_change is not None:
                delta_str = f"{delta:+.2f}"
                pct_str = f"{pct_change:+.1f}%"

                # Determine improvement/regression based on metric type
                if lower_is_better:
                    if pct_change < -1.0:
                        indicator = "[+]"  # Improvement
                    elif pct_change > 1.0:
                        indicator = "[-]"  # Regression
                    else:
                        indicator = "[=]"  # No change
                else:  # Higher is better (e.g., throughput, compliance)
                    if pct_change > 1.0:
                        indicator = "[+]"  # Improvement
                    elif pct_change < -1.0:
                        indicator = "[-]"  # Regression
                    else:
                        indicator = "[=]"  # No change

                print(f"  {name:<45} {val1_str:<15} {val2_str:<15} {delta_str:<15} {pct_str:<10} {indicator}")
            else:
                print(f"  {name:<45} {val1_str:<15} {val2_str:<15} {'N/A':<15} {'N/A':<10}")

        # Organize metrics by category
        latency_metrics = {}
        throughput_metrics = {}
        realtime_metrics = {}
        accuracy_metrics = {}

        for metric_name, metric_data in metrics.items():
            if metric_name.startswith('latency_'):
                latency_metrics[metric_name] = metric_data
            elif metric_name.startswith('throughput_'):
                throughput_metrics[metric_name] = metric_data
            elif metric_name.startswith('realtime_'):
                realtime_metrics[metric_name] = metric_data
            elif metric_name.startswith('accuracy_'):
                accuracy_metrics[metric_name] = metric_data

        # Print LATENCY section
        if latency_metrics:
            print(f"\n{'-'*100}")
            print("LATENCY METRICS (us)")
            print(f"{'-'*100}")
            print(f"  {'Metric':<45} {args.name1:<15} {args.name2:<15} {'Delta':<15} {'Change':<10}")
            print(f"  {'-'*95}")

            # Organize by sample rate and mode
            for rate in ['48k', '100k']:
                for mode in ['batch', 'streaming']:
                    rate_mode_metrics = {k: v for k, v in latency_metrics.items()
                                        if f"_{rate}_{mode}_" in k}
                    if rate_mode_metrics:
                        print(f"\n  {rate.upper()} {mode.upper()}:")
                        for metric_name in sorted(rate_mode_metrics.keys()):
                            metric_data = rate_mode_metrics[metric_name]
                            display_name = metric_name.split('_')[-2] + '_' + metric_name.split('_')[-1]
                            format_metric_row(
                                display_name,
                                metric_data.get('value1'),
                                metric_data.get('value2'),
                                metric_data.get('delta'),
                                metric_data.get('pct_change'),
                                lower_is_better=True
                            )

        # Print THROUGHPUT section
        if throughput_metrics:
            print(f"\n{'-'*100}")
            print("THROUGHPUT METRICS")
            print(f"{'-'*100}")
            print(f"  {'Metric':<45} {args.name1:<15} {args.name2:<15} {'Delta':<15} {'Change':<10}")
            print(f"  {'-'*95}")

            for rate in ['48k', '100k']:
                for mode in ['batch', 'streaming']:
                    rate_mode_metrics = {k: v for k, v in throughput_metrics.items()
                                        if f"_{rate}_{mode}_" in k}
                    if rate_mode_metrics:
                        print(f"\n  {rate.upper()} {mode.upper()}:")
                        for metric_name in sorted(rate_mode_metrics.keys()):
                            metric_data = rate_mode_metrics[metric_name]
                            display_name = metric_name.split('_')[-1]
                            # FPS, RTF, GBPS are higher=better
                            lower_is_better = 'gpu_util' in metric_name
                            format_metric_row(
                                display_name,
                                metric_data.get('value1'),
                                metric_data.get('value2'),
                                metric_data.get('delta'),
                                metric_data.get('pct_change'),
                                lower_is_better=lower_is_better
                            )

        # Print REALTIME section
        if realtime_metrics:
            print(f"\n{'-'*100}")
            print("REALTIME METRICS")
            print(f"{'-'*100}")
            print(f"  {'Metric':<45} {args.name1:<15} {args.name2:<15} {'Delta':<15} {'Change':<10}")
            print(f"  {'-'*95}")

            for rate in ['48k', '100k']:
                rate_metrics = {k: v for k, v in realtime_metrics.items()
                               if f"_{rate}_" in k or k.endswith(f"_{rate}")}
                if rate_metrics:
                    print(f"\n  {rate.upper()} STREAMING:")
                    for metric_name in sorted(rate_metrics.keys()):
                        metric_data = rate_metrics[metric_name]
                        display_name = '_'.join(metric_name.split('_')[2:])  # Remove realtime_48k prefix
                        # Compliance and RTF are higher=better, latency/jitter/misses are lower=better
                        lower_is_better = any(x in metric_name for x in ['latency', 'jitter', 'misses'])
                        format_metric_row(
                            display_name,
                            metric_data.get('value1'),
                            metric_data.get('value2'),
                            metric_data.get('delta'),
                            metric_data.get('pct_change'),
                            lower_is_better=lower_is_better
                        )

        # Print ACCURACY section
        if accuracy_metrics:
            print(f"\n{'-'*100}")
            print("ACCURACY METRICS")
            print(f"{'-'*100}")
            print(f"  {'Metric':<45} {args.name1:<15} {args.name2:<15} {'Delta':<15} {'Change':<10}")
            print(f"  {'-'*95}\n")

            for metric_name in sorted(accuracy_metrics.keys()):
                metric_data = accuracy_metrics[metric_name]
                display_name = '_'.join(metric_name.split('_')[1:])  # Remove accuracy_ prefix
                # Pass rate and SNR are higher=better
                format_metric_row(
                    display_name,
                    metric_data.get('value1'),
                    metric_data.get('value2'),
                    metric_data.get('delta'),
                    metric_data.get('pct_change'),
                    lower_is_better=False
                )

        print(f"\n{'='*100}")
        print("Legend: [+] Improvement  [=] No change  [-] Regression")
        print(f"{'='*100}\n")
        return 0

    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[ERROR] Error comparing baselines: {e}", file=sys.stderr)
        return 1


def cmd_delete(args):
    """Delete a baseline."""
    manager = BaselineManager()

    try:
        # Check if baseline exists
        metadata = manager.load_baseline_metadata(args.name)
        if metadata is None:
            print(f"[ERROR] Baseline '{args.name}' not found.", file=sys.stderr)
            return 1

        # Confirmation prompt (unless --force flag)
        if not args.force:
            print(f"WARNING: About to delete baseline '{args.name}'")
            print(f"  Phase: {metadata.get('phase', 'N/A')}")
            print(f"  Created: {metadata.get('created', 'N/A')[:19]}")
            print(f"  Size: {metadata.get('size_mb', 0):.1f} MB")
            print()
            response = input("Are you sure? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                print("Deletion cancelled.")
                return 0

        # Delete baseline
        manager.delete_baseline(args.name, force=args.force)

        print(f"[SUCCESS] Baseline '{args.name}' deleted successfully.")
        return 0

    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[ERROR] Error deleting baseline: {e}", file=sys.stderr)
        return 1


def cmd_export(args):
    """Export a baseline (Phase 2 feature - not implemented yet)."""
    print("[ERROR] Export feature not yet implemented.")
    print("   This is a Phase 2 feature - coming soon!")
    print(f"   Requested: export '{args.name}' to '{args.destination}'")
    return 1


def main():
    """Main entry point for baseline CLI."""
    parser = argparse.ArgumentParser(
        description="Baseline management for SigTekX experiment archiving",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='Baseline command')

    # Save command
    save_parser = subparsers.add_parser('save', help='Save current artifacts as baseline')
    save_parser.add_argument('name', help='Baseline name (e.g., pre-phase1)')
    save_parser.add_argument('--phase', type=int, help='Phase number (1-4)')
    save_parser.add_argument('--message', help='Description of this baseline')
    save_parser.set_defaults(func=cmd_save)

    # List command
    list_parser = subparsers.add_parser('list', help='List saved baselines')
    list_parser.add_argument('--phase', type=int, help='Filter by phase number')
    list_parser.add_argument('--verbose', action='store_true', help='Show detailed information')
    list_parser.set_defaults(func=cmd_list)

    # Compare command (Phase 1 - stubbed)
    compare_parser = subparsers.add_parser('compare', help='Compare two baselines (Phase 1 feature)')
    compare_parser.add_argument('name1', help='First baseline name')
    compare_parser.add_argument('name2', help='Second baseline name')
    compare_parser.set_defaults(func=cmd_compare)

    # Delete command (Phase 2 - stubbed)
    delete_parser = subparsers.add_parser('delete', help='Delete a baseline (Phase 2 feature)')
    delete_parser.add_argument('name', help='Baseline name to delete')
    delete_parser.add_argument('--force', action='store_true', help='Skip confirmation')
    delete_parser.set_defaults(func=cmd_delete)

    # Export command (Phase 2 - stubbed)
    export_parser = subparsers.add_parser('export', help='Export baseline archive (Phase 2 feature)')
    export_parser.add_argument('name', help='Baseline name to export')
    export_parser.add_argument('destination', help='Destination directory')
    export_parser.add_argument('--format', choices=['zip', 'tar'], default='zip', help='Archive format')
    export_parser.set_defaults(func=cmd_export)

    # Parse arguments
    args = parser.parse_args()

    # Execute command
    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
