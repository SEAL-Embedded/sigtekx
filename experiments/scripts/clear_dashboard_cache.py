#!/usr/bin/env python
"""
Clear Streamlit Dashboard Cache
================================

This script clears the Streamlit cache to force reload of benchmark data
after RTF convention changes or CSV updates.

Usage:
    python experiments/scripts/clear_dashboard_cache.py
"""

import shutil
from pathlib import Path


def clear_streamlit_cache():
    """Clear Streamlit cache directory."""
    # Streamlit stores cache in .streamlit/cache directory relative to the app
    cache_paths = [
        Path("experiments/streamlit/.streamlit/cache"),
        Path(".streamlit/cache"),
        Path.home() / ".streamlit/cache"
    ]

    cleared = []
    for cache_path in cache_paths:
        if cache_path.exists():
            print(f"Clearing cache: {cache_path}")
            shutil.rmtree(cache_path)
            cleared.append(cache_path)
            print(f"  -> Removed {cache_path}")

    if cleared:
        print(f"\nCleared {len(cleared)} cache location(s)")
    else:
        print("No Streamlit cache directories found (cache may already be clear)")

    return len(cleared) > 0


def verify_csv_data():
    """Quick verification that CSV files have academic RTF values."""
    import pandas as pd

    data_dir = Path("artifacts/data")
    throughput_files = list(data_dir.glob("throughput_summary_*.csv"))

    if not throughput_files:
        print("\nWarning: No throughput CSV files found in artifacts/data")
        return False

    print(f"\nVerifying {len(throughput_files)} CSV files...")

    # Check first 3 files
    all_academic = True
    for csv_file in sorted(throughput_files)[:3]:
        df = pd.read_csv(csv_file)
        if 'rtf' in df.columns:
            rtf_val = df['rtf'].values[0]
            is_academic = rtf_val < 10.0  # Academic convention should be < 1.0, allow margin
            status = "OK (Academic)" if is_academic else "ERROR (Old Convention)"
            print(f"  {csv_file.name}: RTF={rtf_val:.6f} - {status}")
            all_academic = all_academic and is_academic

    if all_academic:
        print("\nAll CSV files use academic RTF convention (RTF < 1.0)")
    else:
        print("\nWARNING: Some CSV files still use old convention!")

    return all_academic


def main():
    print("=" * 70)
    print("Streamlit Dashboard Cache Cleaner")
    print("=" * 70)

    # Step 1: Verify CSV data
    print("\nStep 1: Verifying CSV data has academic RTF values...")
    csv_ok = verify_csv_data()

    if not csv_ok:
        print("\nERROR: CSV files have incorrect RTF values.")
        print("Run: python experiments/scripts/convert_rtf_to_academic.py")
        return 1

    # Step 2: Clear cache
    print("\nStep 2: Clearing Streamlit cache...")
    cache_cleared = clear_streamlit_cache()

    # Step 3: Instructions
    print("\n" + "=" * 70)
    print("NEXT STEPS:")
    print("=" * 70)
    print()
    print("1. If the dashboard is currently running, stop it (Ctrl+C)")
    print()
    print("2. Restart the dashboard:")
    print("   sigx dashboard")
    print("   OR: streamlit run experiments/streamlit/app.py")
    print()
    print("3. In your browser:")
    print("   - Clear browser cache (Ctrl+Shift+Delete)")
    print("   - Or use incognito/private window")
    print("   - Or force refresh (Ctrl+Shift+R)")
    print()
    print("4. Navigate to System Health page")
    print("   - All RTF values should now be < 1.0 (academic convention)")
    print("   - Heatmap should show green for low RTF (good performance)")
    print("   - Executive summary should show correct percentages")
    print()
    print("=" * 70)

    return 0


if __name__ == '__main__':
    exit(main())
