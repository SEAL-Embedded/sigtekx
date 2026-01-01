#!/usr/bin/env python
"""
Comprehensive RTF Convention Verification
==========================================

Verifies that ALL components of SigTekX use academic RTF convention:
1. Core calculation function
2. Benchmark runners
3. CSV data files
4. Dashboard code
5. Documentation

Usage:
    python experiments/scripts/verify_rtf_convention.py
"""

from pathlib import Path

import pandas as pd


def check_core_calculation():
    """Verify experiments/analysis/metrics.py uses academic convention."""
    metrics_file = Path("experiments/analysis/metrics.py")
    content = metrics_file.read_text(encoding='utf-8')

    # Check for academic formula in calculate_rtf
    has_academic_formula = "sample_rate_hz / (fps * hop_size)" in content
    has_academic_comment = "Academic convention" in content or "lower is better" in content

    print("1. Core Calculation Function (experiments/analysis/metrics.py)")
    print(f"   Formula uses academic convention: {has_academic_formula}")
    print(f"   Comments reference academic convention: {has_academic_comment}")

    return has_academic_formula and has_academic_comment


def check_benchmark_runner():
    """Verify benchmarks/run_throughput.py uses centralized calculation."""
    benchmark_file = Path("benchmarks/run_throughput.py")
    content = benchmark_file.read_text(encoding='utf-8')

    # Check for import and usage of calculate_rtf
    has_import = "from analysis.metrics import calculate_rtf" in content
    has_usage = "calculate_rtf(fps, hop_size" in content
    no_inline = "(fps * hop_size) / engine_config.sample_rate_hz" not in content

    print("\n2. Benchmark Runner (benchmarks/run_throughput.py)")
    print(f"   Imports centralized calculate_rtf: {has_import}")
    print(f"   Uses centralized function: {has_usage}")
    print(f"   No inline calculation (old formula): {no_inline}")

    return has_import and has_usage and no_inline


def check_csv_data():
    """Verify all throughput CSV files have academic RTF values."""
    data_dir = Path("artifacts/data")
    throughput_files = list(data_dir.glob("throughput_summary_*.csv"))

    if not throughput_files:
        print("\n3. CSV Data Files")
        print("   WARNING: No throughput CSV files found")
        return False

    all_academic = True
    old_convention_files = []

    for csv_file in throughput_files:
        df = pd.read_csv(csv_file)
        if 'rtf' in df.columns:
            # Academic convention: RTF should be < 1.0 for most configs
            # Allow up to 10.0 as sanity check (realtime is when CSV shows no RTF column)
            rtf_vals = df['rtf'].values
            if any(v > 10.0 for v in rtf_vals):
                all_academic = False
                old_convention_files.append(csv_file.name)

    print("\n3. CSV Data Files (artifacts/data)")
    print(f"   Total throughput CSV files: {len(throughput_files)}")
    print(f"   All files use academic convention: {all_academic}")

    if old_convention_files:
        print(f"   Files with old convention ({len(old_convention_files)}):")
        for filename in old_convention_files[:5]:
            print(f"     - {filename}")

    return all_academic


def check_dashboard_code():
    """Verify System Health dashboard uses academic convention."""
    dashboard_file = Path("experiments/streamlit/pages/4_System_Health.py")
    content = dashboard_file.read_text(encoding='utf-8')

    # Check for key academic convention patterns
    checks = {
        "Uses <= comparisons": "rtf_data['rtf'] <= 1.0" in content,
        "Threshold at 0.33": "rtf_data['rtf'] <= 0.33" in content,
        "Reversed color scale": "'RdYlGn_r'" in content,
        "Academic midpoint 0.40": "color_continuous_midpoint=0.40" in content,
        "Range [0, 1.0]": "range_color=[0, 1.0]" in content,
        "Academic convention text": "Academic Convention" in content
    }

    print("\n4. Dashboard Code (experiments/streamlit/pages/4_System_Health.py)")
    all_correct = True
    for check_name, result in checks.items():
        print(f"   {check_name}: {result}")
        all_correct = all_correct and result

    return all_correct


def check_documentation():
    """Verify key documentation references academic convention."""
    docs = {
        "RTF Convention Doc": Path("docs/benchmarking/rtf-convention-mapping.md"),
        "Methods Paper Roadmap": Path("docs/development/methods-paper-roadmap.md"),
    }

    print("\n5. Documentation")
    all_correct = True

    for doc_name, doc_path in docs.items():
        if not doc_path.exists():
            print(f"   {doc_name}: FILE NOT FOUND")
            all_correct = False
            continue

        content = doc_path.read_text(encoding='utf-8')

        # Check for academic convention references
        has_academic = "academic" in content.lower() or "latency-based" in content.lower()
        has_lower_better = "lower" in content.lower() and "better" in content.lower()

        print(f"   {doc_name}: {has_academic and has_lower_better}")

        if not (has_academic and has_lower_better):
            all_correct = False

    return all_correct


def main():
    print("=" * 70)
    print("RTF Convention Verification Report")
    print("=" * 70)

    results = {
        "Core Calculation": check_core_calculation(),
        "Benchmark Runner": check_benchmark_runner(),
        "CSV Data": check_csv_data(),
        "Dashboard Code": check_dashboard_code(),
        "Documentation": check_documentation()
    }

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_pass = all(results.values())

    for component, passed in results.items():
        status = "PASS" if passed else "FAIL"
        symbol = "[OK]" if passed else "[FAIL]"
        print(f"  {symbol} {component}: {status}")

    print()
    if all_pass:
        print("ALL CHECKS PASSED")
        print()
        print("All components correctly use academic RTF convention (lower = better).")
        print()
        print("If dashboard still shows old values:")
        print("  1. Stop dashboard (Ctrl+C)")
        print("  2. Clear browser cache (Ctrl+Shift+Delete) or use incognito")
        print("  3. Restart: sigx dashboard")
        print("  4. Force refresh browser (Ctrl+Shift+R)")
        print()
        return 0
    else:
        print("SOME CHECKS FAILED")
        print()
        print("Please review the failed components above.")
        return 1


if __name__ == '__main__':
    exit(main())
