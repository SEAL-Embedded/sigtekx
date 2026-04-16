#!/usr/bin/env python
"""
Dataset Registry CLI Helper

Command-line interface for the persistent dataset registry. Called by
cli.ps1's Invoke-Dataset (and cli.sh) wrappers.

Usage:
    python dataset_helper.py save <name> [--tag <t>] [--message <msg>] [--source <s>]
    python dataset_helper.py list [--tag <t>] [--verbose]
    python dataset_helper.py compare <name1> <name2>
    python dataset_helper.py delete <name> [--force]
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from sigtekx.utils.datasets import DatasetRegistry


def cmd_save(args):
    """Save current artifacts as a named dataset."""
    registry = DatasetRegistry()

    try:
        dataset_path = registry.save(
            name=args.name,
            tag=args.tag,
            message=args.message or "",
            source=args.source or "local",
        )

        print(f"[SUCCESS] Dataset saved: {args.name}")
        print(f"   Location: {dataset_path}")

        manifest = registry.load_manifest(args.name)
        if manifest:
            print(f"   Source:   {manifest.get('source', 'local')}")
            print(f"   Tag:      {manifest.get('tag') or '—'}")
            print(f"   Size:     {manifest.get('size_mb', 0):.1f} MB")

            metrics = manifest.get("metrics", {})
            if metrics:
                print("   Metrics:")
                for key, value in list(metrics.items())[:3]:
                    print(f"     - {key}: {value}")

        return 0

    except Exception as e:
        print(f"[ERROR] Error saving dataset: {e}", file=sys.stderr)
        return 1


def cmd_list(args):
    """List all saved datasets."""
    registry = DatasetRegistry()

    try:
        datasets = registry.list_datasets(tag_filter=args.tag)

        if not datasets:
            print("No datasets found.")
            if args.tag:
                print(f"(filtered by tag '{args.tag}')")
            return 0

        print(f"\n{'Name':<32} {'Source':<12} {'Tag':<16} {'Created':<20} {'Size':>10}")
        print("=" * 95)

        for ds in datasets:
            name = ds.get("name", "Unknown")
            source = ds.get("source", "local")
            tag = ds.get("tag") or "—"
            created = (ds.get("created") or "N/A")[:19]
            size_mb = ds.get("size_mb", 0)
            print(f"{name:<32} {source:<12} {str(tag):<16} {created:<20} {size_mb:>9.1f}MB")

        print(f"\nTotal: {len(datasets)} dataset(s)")

        if args.verbose and datasets:
            print("\nDetails:")
            for ds in datasets:
                print(f"\n  {ds['name']}:")
                print(f"    Source:  {ds.get('source', 'local')}")
                print(f"    Tag:     {ds.get('tag') or '—'}")
                print(f"    Message: {ds.get('message') or 'No message'}")
                print(f"    Git:     {(ds.get('git_commit') or 'N/A')[:8]}")
                metrics = ds.get("metrics", {})
                if metrics:
                    print(f"    Metrics: {len(metrics)} recorded")

        return 0

    except Exception as e:
        print(f"[ERROR] Error listing datasets: {e}", file=sys.stderr)
        return 1


def cmd_compare(args):
    """Compare two datasets."""
    registry = DatasetRegistry()

    try:
        comparison = registry.compare_datasets(args.name1, args.name2)

        print(f"\n{'=' * 100}")
        print(f"Dataset Comparison: {args.name1} vs {args.name2}")
        print(f"{'=' * 100}")

        summary = comparison["summary"]
        manifest1 = comparison["dataset1"]
        manifest2 = comparison["dataset2"]

        print(f"\n{args.name1}:")
        print(f"  Source:   {manifest1.get('source', 'local')}")
        print(f"  Tag:      {summary.get('dataset1_tag') or '—'}")
        print(f"  Created:  {(summary.get('dataset1_created') or 'N/A')[:19]}")
        hw1 = manifest1.get("hardware", {}) or {}
        if hw1:
            print(f"  Hardware: {hw1.get('gpu_name', 'N/A')} | {hw1.get('cpu', 'N/A')}")

        print(f"\n{args.name2}:")
        print(f"  Source:   {manifest2.get('source', 'local')}")
        print(f"  Tag:      {summary.get('dataset2_tag') or '—'}")
        print(f"  Created:  {(summary.get('dataset2_created') or 'N/A')[:19]}")
        hw2 = manifest2.get("hardware", {}) or {}
        if hw2:
            print(f"  Hardware: {hw2.get('gpu_name', 'N/A')} | {hw2.get('cpu', 'N/A')}")
            if hw1 and hw1.get("gpu_name") != hw2.get("gpu_name"):
                print("\n[NOTE] Different GPUs — deltas reflect hardware as well as code changes.")

        metrics = comparison["metrics"]
        if not metrics:
            print("\nNo metrics available for comparison.")
            return 0

        def format_metric_row(name, val1, val2, delta, pct_change, lower_is_better=True):
            val1_str = f"{val1:.2f}" if val1 is not None else "N/A"
            val2_str = f"{val2:.2f}" if val2 is not None else "N/A"

            if delta is not None and pct_change is not None:
                delta_str = f"{delta:+.2f}"
                pct_str = f"{pct_change:+.1f}%"
                if lower_is_better:
                    indicator = "[+]" if pct_change < -1.0 else "[-]" if pct_change > 1.0 else "[=]"
                else:
                    indicator = "[+]" if pct_change > 1.0 else "[-]" if pct_change < -1.0 else "[=]"
                print(f"  {name:<45} {val1_str:<15} {val2_str:<15} {delta_str:<15} {pct_str:<10} {indicator}")
            else:
                print(f"  {name:<45} {val1_str:<15} {val2_str:<15} {'N/A':<15} {'N/A':<10}")

        latency_metrics = {k: v for k, v in metrics.items() if k.startswith("latency_")}
        throughput_metrics = {k: v for k, v in metrics.items() if k.startswith("throughput_")}
        realtime_metrics = {k: v for k, v in metrics.items() if k.startswith("realtime_")}
        accuracy_metrics = {k: v for k, v in metrics.items() if k.startswith("accuracy_")}

        if latency_metrics:
            print(f"\n{'-' * 100}")
            print("LATENCY METRICS (us)")
            print(f"{'-' * 100}")
            print(f"  {'Metric':<45} {args.name1:<15} {args.name2:<15} {'Delta':<15} {'Change':<10}")
            print(f"  {'-' * 95}")
            for rate in ["48k", "100k"]:
                for mode in ["batch", "streaming"]:
                    rate_mode_metrics = {k: v for k, v in latency_metrics.items() if f"_{rate}_{mode}_" in k}
                    if rate_mode_metrics:
                        print(f"\n  {rate.upper()} {mode.upper()}:")
                        for metric_name in sorted(rate_mode_metrics):
                            d = rate_mode_metrics[metric_name]
                            display_name = "_".join(metric_name.split("_")[-2:])
                            format_metric_row(
                                display_name, d.get("value1"), d.get("value2"),
                                d.get("delta"), d.get("pct_change"), lower_is_better=True,
                            )

        if throughput_metrics:
            print(f"\n{'-' * 100}")
            print("THROUGHPUT METRICS")
            print(f"{'-' * 100}")
            print(f"  {'Metric':<45} {args.name1:<15} {args.name2:<15} {'Delta':<15} {'Change':<10}")
            print(f"  {'-' * 95}")
            for rate in ["48k", "100k"]:
                for mode in ["batch", "streaming"]:
                    rate_mode_metrics = {k: v for k, v in throughput_metrics.items() if f"_{rate}_{mode}_" in k}
                    if rate_mode_metrics:
                        print(f"\n  {rate.upper()} {mode.upper()}:")
                        for metric_name in sorted(rate_mode_metrics):
                            d = rate_mode_metrics[metric_name]
                            display_name = metric_name.split("_")[-1]
                            lower_is_better = "gpu_util" in metric_name
                            format_metric_row(
                                display_name, d.get("value1"), d.get("value2"),
                                d.get("delta"), d.get("pct_change"), lower_is_better=lower_is_better,
                            )

        if realtime_metrics:
            print(f"\n{'-' * 100}")
            print("REALTIME METRICS")
            print(f"{'-' * 100}")
            print(f"  {'Metric':<45} {args.name1:<15} {args.name2:<15} {'Delta':<15} {'Change':<10}")
            print(f"  {'-' * 95}")
            for rate in ["48k", "100k"]:
                rate_metrics = {k: v for k, v in realtime_metrics.items() if f"_{rate}_" in k or k.endswith(f"_{rate}")}
                if rate_metrics:
                    print(f"\n  {rate.upper()} STREAMING:")
                    for metric_name in sorted(rate_metrics):
                        d = rate_metrics[metric_name]
                        display_name = "_".join(metric_name.split("_")[2:])
                        lower_is_better = any(x in metric_name for x in ["latency", "jitter", "misses"])
                        format_metric_row(
                            display_name, d.get("value1"), d.get("value2"),
                            d.get("delta"), d.get("pct_change"), lower_is_better=lower_is_better,
                        )

        if accuracy_metrics:
            print(f"\n{'-' * 100}")
            print("ACCURACY METRICS")
            print(f"{'-' * 100}")
            print(f"  {'Metric':<45} {args.name1:<15} {args.name2:<15} {'Delta':<15} {'Change':<10}")
            print(f"  {'-' * 95}\n")
            for metric_name in sorted(accuracy_metrics):
                d = accuracy_metrics[metric_name]
                display_name = "_".join(metric_name.split("_")[1:])
                format_metric_row(
                    display_name, d.get("value1"), d.get("value2"),
                    d.get("delta"), d.get("pct_change"), lower_is_better=False,
                )

        print(f"\n{'=' * 100}")
        print("Legend: [+] Improvement  [=] No change  [-] Regression")
        print(f"{'=' * 100}\n")
        return 0

    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[ERROR] Error comparing datasets: {e}", file=sys.stderr)
        return 1


def cmd_delete(args):
    """Delete a dataset."""
    registry = DatasetRegistry()

    try:
        manifest = registry.load_manifest(args.name)
        if manifest is None:
            print(f"[ERROR] Dataset '{args.name}' not found.", file=sys.stderr)
            return 1

        if not args.force:
            print(f"WARNING: About to delete dataset '{args.name}'")
            print(f"  Source:  {manifest.get('source', 'local')}")
            print(f"  Tag:     {manifest.get('tag') or '—'}")
            print(f"  Created: {(manifest.get('created') or 'N/A')[:19]}")
            print(f"  Size:    {manifest.get('size_mb', 0):.1f} MB")
            print()
            response = input("Are you sure? (yes/no): ").strip().lower()
            if response not in {"yes", "y"}:
                print("Deletion cancelled.")
                return 0

        registry.delete(args.name, force=args.force)
        print(f"[SUCCESS] Dataset '{args.name}' deleted.")
        return 0

    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[ERROR] Error deleting dataset: {e}", file=sys.stderr)
        return 1



def main():
    parser = argparse.ArgumentParser(
        description="Dataset registry for SigTekX benchmark result storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Dataset command")

    save_parser = subparsers.add_parser("save", help="Save current artifacts as dataset")
    save_parser.add_argument("name", help="Dataset name (e.g., local-rtx-run1)")
    save_parser.add_argument("--tag", help="Optional free-form tag (e.g., pre-optimization)")
    save_parser.add_argument("--message", help="Description of this dataset")
    save_parser.add_argument("--source", help="Origin label (default: local)")
    save_parser.set_defaults(func=cmd_save)

    list_parser = subparsers.add_parser("list", help="List saved datasets")
    list_parser.add_argument("--tag", help="Filter by tag")
    list_parser.add_argument("--verbose", action="store_true", help="Show detailed information")
    list_parser.set_defaults(func=cmd_list)

    compare_parser = subparsers.add_parser("compare", help="Compare two datasets")
    compare_parser.add_argument("name1", help="First dataset name")
    compare_parser.add_argument("name2", help="Second dataset name")
    compare_parser.set_defaults(func=cmd_compare)

    delete_parser = subparsers.add_parser("delete", help="Delete a dataset")
    delete_parser.add_argument("name", help="Dataset name to delete")
    delete_parser.add_argument("--force", action="store_true", help="Skip confirmation")
    delete_parser.set_defaults(func=cmd_delete)


    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
