#!/usr/bin/env python
"""Quick script to verify error logging is working in MLflow."""

# Set tracking URI (use file:// prefix with forward slashes)
import os

import mlflow
import pandas as pd

tracking_uri = f"file:///{os.path.join(os.getcwd(), 'artifacts', 'mlruns').replace(chr(92), '/')}"
mlflow.set_tracking_uri(tracking_uri)

# Get all experiments
experiments = mlflow.search_experiments()
print(f"Found {len(experiments)} experiment(s)\n")

# Search recent runs
recent_runs = mlflow.search_runs(
    experiment_ids=[exp.experiment_id for exp in experiments],
    order_by=["start_time DESC"],
    max_results=5
)

if recent_runs.empty:
    print("No runs found!")
else:
    print("Recent Runs with Error Metrics:")
    print("=" * 80)

    # Select relevant columns
    columns = [
        'run_id',
        'start_time',
        'metrics.error_count',
        'metrics.error_rate',
        'metrics.latency.mean',
        'status'
    ]

    # Filter to columns that exist
    available_cols = [col for col in columns if col in recent_runs.columns]

    # Display
    display_df = recent_runs[available_cols].head()

    # Format for readability
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', 20)

    print(display_df.to_string(index=False))
    print()

    # Verify error metrics are present
    if 'metrics.error_count' in recent_runs.columns:
        print("[OK] error_count metric is logged!")
        print(f"     Recent values: {recent_runs['metrics.error_count'].head().tolist()}")
    else:
        print("[ERROR] error_count metric NOT found")

    if 'metrics.error_rate' in recent_runs.columns:
        print("[OK] error_rate metric is logged!")
        print(f"     Recent values: {recent_runs['metrics.error_rate'].head().tolist()}")
    else:
        print("[ERROR] error_rate metric NOT found")

    # Check for any error type metrics
    error_type_cols = [col for col in recent_runs.columns if col.startswith('metrics.errors_')]
    if error_type_cols:
        print(f"[OK] Found {len(error_type_cols)} error type breakdown metric(s):")
        for col in error_type_cols:
            print(f"     - {col}")
    else:
        print("[INFO] No error type breakdown metrics (expected if no errors occurred)")
