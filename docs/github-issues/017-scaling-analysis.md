# Generate Scaling Analysis Heatmap for Paper Figure 2 (Phase 4 Task 4.6)

## Problem

We need to **characterize performance across parameter space** (NFFT vs channels) to identify the "sweet spot" for RTF <0.3. Without comprehensive scaling analysis, we cannot claim to understand system behavior or guide user configuration choices.

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 4 Task 4.6 / Experiment 6):
- NFFT sweep: 1024, 2048, 4096, 8192, 16384
- Channel sweep: 1, 2, 4, 8, 16
- Generate heatmap: RTF(NFFT, channels)
- Expected: Linear scaling with NFFT, sub-linear with channels (GPU parallelism)

**Impact:**
- Cannot provide user guidance on configuration trade-offs
- Missing Figure 2 in methods paper (scaling analysis heatmap)
- No characterization of system limits (max NFFT × channels for RTF <0.3)

## Current Implementation

**No scaling analysis exists.** Individual configurations tested (Issue #013), but no comprehensive sweep.

## Proposed Solution

**Create Hydra multirun experiment with analysis script:**

```yaml
# experiments/conf/experiment/scaling_analysis.yaml (NEW)
# Scaling analysis: NFFT × Channels grid sweep

defaults:
  - override /engine: ionosphere_realtime

# Multirun sweep (5 NFFT × 5 Channels = 25 configs)
engine:
  nfft: 1024, 2048, 4096, 8192, 16384
  channels: 1, 2, 4, 8, 16
  overlap: 0.75
  mode: streaming

benchmark:
  duration: 10  # 10 seconds per config
  lock_gpu_clocks: true
```

```python
# experiments/analysis/scaling.py (NEW FILE)
"""
Scaling analysis for NFFT × Channels parameter space.

Generates:
- Heatmap: RTF(NFFT, Channels)
- Line plots: RTF vs NFFT, RTF vs Channels
- Sweet spot identification (max config with RTF <0.3)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import mlflow

def load_results(experiment_name="scaling_analysis"):
    """
    Load results from MLflow experiment.

    Args:
        experiment_name: MLflow experiment name

    Returns:
        DataFrame with (nfft, channels, rtf_mean, rtf_p99, ...)
    """
    client = mlflow.tracking.MlflowClient()
    experiment = client.get_experiment_by_name(experiment_name)

    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string="tags.status = 'SUCCESS'"
    )

    data = []
    for run in runs:
        data.append({
            'nfft': run.data.params['nfft'],
            'channels': run.data.params['channels'],
            'rtf_mean': run.data.metrics['rtf_mean'],
            'rtf_p99': run.data.metrics['rtf_p99'],
            'deadline_compliance': run.data.metrics['deadline_compliance']
        })

    df = pd.DataFrame(data)
    df['nfft'] = df['nfft'].astype(int)
    df['channels'] = df['channels'].astype(int)

    return df


def generate_heatmap(df, metric='rtf_mean', output_path='rtf_heatmap.png'):
    """
    Generate RTF heatmap (NFFT vs Channels).

    Args:
        df: Results DataFrame
        metric: Metric to plot ('rtf_mean' or 'rtf_p99')
        output_path: Output file path
    """
    # Pivot to matrix format
    pivot = df.pivot(index='channels', columns='nfft', values=metric)

    # Create heatmap
    plt.figure(figsize=(10, 6))
    sns.heatmap(
        pivot,
        annot=True,
        fmt='.3f',
        cmap='RdYlGn_r',  # Red = high RTF, Green = low RTF
        vmin=0.0,
        vmax=0.5,
        cbar_kws={'label': 'Real-Time Factor (RTF)'}
    )

    # Add RTF <0.3 threshold line
    plt.axhline(y=0, color='blue', linewidth=2, label='RTF < 0.3 (target)')

    plt.title(f'Real-Time Factor Scaling: NFFT × Channels')
    plt.xlabel('NFFT')
    plt.ylabel('Channels')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    print(f"Saved heatmap: {output_path}")


def generate_line_plots(df, output_path_nfft='rtf_vs_nfft.png', output_path_channels='rtf_vs_channels.png'):
    """
    Generate line plots: RTF vs NFFT, RTF vs Channels.

    Args:
        df: Results DataFrame
        output_path_nfft: Output for NFFT plot
        output_path_channels: Output for Channels plot
    """
    # RTF vs NFFT (for each channel count)
    plt.figure(figsize=(10, 6))
    for channels in sorted(df['channels'].unique()):
        subset = df[df['channels'] == channels].sort_values('nfft')
        plt.plot(subset['nfft'], subset['rtf_mean'], marker='o', label=f'{channels} channels')

    plt.axhline(y=0.3, color='red', linestyle='--', label='RTF = 0.3 (target)')
    plt.xlabel('NFFT')
    plt.ylabel('Real-Time Factor (RTF)')
    plt.title('RTF Scaling vs NFFT')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.xscale('log', base=2)
    plt.tight_layout()
    plt.savefig(output_path_nfft, dpi=300)
    print(f"Saved NFFT plot: {output_path_nfft}")

    # RTF vs Channels (for each NFFT)
    plt.figure(figsize=(10, 6))
    for nfft in sorted(df['nfft'].unique()):
        subset = df[df['nfft'] == nfft].sort_values('channels')
        plt.plot(subset['channels'], subset['rtf_mean'], marker='o', label=f'NFFT={nfft}')

    plt.axhline(y=0.3, color='red', linestyle='--', label='RTF = 0.3 (target)')
    plt.xlabel('Channels')
    plt.ylabel('Real-Time Factor (RTF)')
    plt.title('RTF Scaling vs Channels')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path_channels, dpi=300)
    print(f"Saved Channels plot: {output_path_channels}")


def find_sweet_spot(df, rtf_threshold=0.3):
    """
    Identify "sweet spot" (max NFFT × Channels with RTF <threshold).

    Args:
        df: Results DataFrame
        rtf_threshold: RTF threshold (default: 0.3)

    Returns:
        Sweet spot configuration (nfft, channels, rtf)
    """
    # Filter configs with RTF < threshold
    valid = df[df['rtf_mean'] < rtf_threshold]

    if len(valid) == 0:
        print(f"⚠ No configs meet RTF <{rtf_threshold} target")
        return None

    # Sort by product (NFFT × Channels) descending
    valid['product'] = valid['nfft'] * valid['channels']
    valid = valid.sort_values('product', ascending=False)

    sweet_spot = valid.iloc[0]

    print()
    print("=" * 80)
    print("Sweet Spot Identification:")
    print("-" * 80)
    print(f"Max config with RTF <{rtf_threshold}:")
    print(f"  NFFT:     {sweet_spot['nfft']}")
    print(f"  Channels: {sweet_spot['channels']}")
    print(f"  RTF:      {sweet_spot['rtf_mean']:.4f}")
    print(f"  Product:  {sweet_spot['product']:.0f}")
    print("=" * 80)

    return sweet_spot


def main():
    """Generate scaling analysis plots."""
    print("=" * 80)
    print("Scaling Analysis")
    print("=" * 80)
    print()

    # Load results from MLflow
    print("Loading results from MLflow...")
    df = load_results(experiment_name="scaling_analysis")
    print(f"Loaded {len(df)} configurations")
    print()

    # Generate heatmap
    print("Generating heatmap...")
    generate_heatmap(df, metric='rtf_mean', output_path='artifacts/figures/rtf_heatmap.png')
    print()

    # Generate line plots
    print("Generating line plots...")
    generate_line_plots(
        df,
        output_path_nfft='artifacts/figures/rtf_vs_nfft.png',
        output_path_channels='artifacts/figures/rtf_vs_channels.png'
    )
    print()

    # Find sweet spot
    sweet_spot = find_sweet_spot(df, rtf_threshold=0.3)

    # Print summary table
    print()
    print("Results Summary:")
    print("-" * 80)
    print(df.sort_values(['channels', 'nfft']).to_string(index=False))
    print("-" * 80)


if __name__ == "__main__":
    main()
```

## Additional Technical Insights

- **Linear Scaling (NFFT)**: RTF should increase linearly with NFFT (FFT complexity O(N log N))

- **Sub-linear Scaling (Channels)**: GPU parallelism means 8 channels < 8× latency of 1 channel

- **Sweet Spot**: Maximum (NFFT × Channels) product with RTF <0.3. Example: NFFT=8192, Channels=4

- **Heatmap Interpretation**: Red = high RTF (not real-time), Green = low RTF (real-time), Blue line = target threshold

## Implementation Tasks

- [ ] Create `experiments/conf/experiment/scaling_analysis.yaml`
- [ ] Define multirun sweep (5 NFFT × 5 channels = 25 configs)
- [ ] Create `experiments/analysis/scaling.py`
- [ ] Implement `load_results()` (query MLflow)
- [ ] Implement `generate_heatmap()` (seaborn heatmap)
- [ ] Implement `generate_line_plots()` (RTF vs NFFT, RTF vs channels)
- [ ] Implement `find_sweet_spot()` (max product with RTF <0.3)
- [ ] Run multirun experiment: `python benchmarks/run_throughput.py --multirun experiment=scaling_analysis +benchmark=throughput`
- [ ] Run analysis: `python experiments/analysis/scaling.py`
- [ ] Verify: Heatmap shows expected scaling patterns
- [ ] Add figures to paper: Figure 2 (heatmap), Figure 3 (line plots)
- [ ] Update documentation: `docs/experiments/scaling-analysis.md`
- [ ] Commit: `feat(experiments): add scaling analysis across NFFT × channels`

## Edge Cases to Handle

- **No Configs Meet Threshold**: All RTF >0.3
  - Mitigation: Report warning, show closest config

- **MLflow Experiment Not Found**: User hasn't run multirun
  - Mitigation: Print instructions to run experiment first

- **Missing Metrics**: Some runs failed
  - Mitigation: Filter by `tags.status = 'SUCCESS'`

## Testing Strategy

```bash
# Step 1: Run multirun experiment (generates 25 configs)
python benchmarks/run_throughput.py --multirun experiment=scaling_analysis +benchmark=throughput
# Expected: ~25 MLflow runs, each 10 seconds = ~4 minutes total

# Step 2: Generate analysis plots
python experiments/analysis/scaling.py

# Expected output:
# Loading results from MLflow...
# Loaded 25 configurations
#
# Generating heatmap...
# Saved heatmap: artifacts/figures/rtf_heatmap.png
#
# Generating line plots...
# Saved NFFT plot: artifacts/figures/rtf_vs_nfft.png
# Saved Channels plot: artifacts/figures/rtf_vs_channels.png
#
# Sweet Spot Identification:
# Max config with RTF <0.3:
#   NFFT:     8192
#   Channels: 4
#   RTF:      0.28
#   Product:  32768
```

## Acceptance Criteria

- [ ] `scaling_analysis.yaml` multirun config created
- [ ] 25 configurations run (5 NFFT × 5 channels)
- [ ] `scaling.py` analysis script implemented
- [ ] Heatmap generated (RTF vs NFFT × Channels)
- [ ] Line plots generated (RTF vs NFFT, RTF vs Channels)
- [ ] Sweet spot identified (max product with RTF <0.3)
- [ ] Expected scaling patterns observed (linear NFFT, sub-linear channels)
- [ ] Figures added to methods paper (Figure 2, 3)
- [ ] Documentation includes scaling results

## Benefits

- **Parameter Space Characterized**: Understand system behavior across configurations
- **User Guidance**: Identify optimal NFFT × channels for RTF <0.3 target
- **Methods Paper Ready**: Figure 2 (heatmap), Figure 3 (scaling plots)
- **Scaling Validation**: Proves expected linear/sub-linear scaling patterns
- **Sweet Spot Identified**: Recommend max config for production deployment

---

**Labels:** `task`, `team-4-research`, `research`, `performance`

**Estimated Effort:** 4-6 hours (multirun + analysis script + plotting)

**Priority:** High (Critical for v1.0 paper Figure 2)

**Roadmap Phase:** Phase 4 (v1.0)

**Dependencies:** Issue #013 (RTF validation), Issue #004 (per-stage timing)

**Blocks:** None (final validation task)
