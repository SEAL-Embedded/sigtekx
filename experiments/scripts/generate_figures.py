#!/usr/bin/env python
"""
Figure Generation Script for Ionosphere HPC Experiments
=======================================================

Creates publication-quality visualizations from experiment summary data.
Modular design with focused plotting functions.

Usage:
    python generate_figures.py

Input: artifacts/data/summary_statistics.csv
Output: Multiple PNG files in artifacts/figures/
"""

import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

# Set up matplotlib for high-quality figures
plt.style.use('default')
sns.set_palette("husl")

# Figure configuration
FIGURE_DPI = 300
FIGURE_SIZE = (12, 8)
FONT_SIZE = 12

plt.rcParams.update({
    'figure.dpi': FIGURE_DPI,
    'savefig.dpi': FIGURE_DPI,
    'font.size': FONT_SIZE,
    'axes.titlesize': FONT_SIZE + 2,
    'axes.labelsize': FONT_SIZE,
    'xtick.labelsize': FONT_SIZE - 1,
    'ytick.labelsize': FONT_SIZE - 1,
    'legend.fontsize': FONT_SIZE - 1,
    'figure.titlesize': FONT_SIZE + 4
})


def save_figure_dual_format(fig, base_path: Path, close_fig: bool = True) -> None:
    """Save figure in both PNG and SVG formats for maximum compatibility."""
    # Save PNG (existing format for compatibility)
    png_path = base_path.with_suffix('.png')
    fig.savefig(png_path, dpi=FIGURE_DPI, bbox_inches='tight', format='png')

    # Save SVG (vector format for scalability)
    svg_path = base_path.with_suffix('.svg')
    fig.savefig(svg_path, bbox_inches='tight', format='svg')

    print(f"Saved: {png_path}")
    print(f"Saved: {svg_path}")

    if close_fig:
        plt.close(fig)


def load_summary_data(data_path: str = "artifacts/data/summary_statistics.csv") -> pd.DataFrame:
    """Load the summary statistics data."""
    if not Path(data_path).exists():
        raise FileNotFoundError(f"Summary data not found: {data_path}")

    df = pd.read_csv(data_path)
    print(f"Loaded summary data: {len(df)} measurements")
    print(f"Benchmark types: {df['benchmark_type'].unique()}")
    return df


def plot_throughput_scaling(df: pd.DataFrame, output_dir: Path) -> None:
    """Create throughput scaling visualizations."""
    throughput_data = df[df['benchmark_type'] == 'throughput'].copy()

    if throughput_data.empty:
        print("No throughput data found for plotting")
        return

    # Remove any rows with missing FPS data
    throughput_data = throughput_data.dropna(subset=['frames_per_second'])

    if throughput_data.empty:
        print("No valid throughput data (missing frames_per_second)")
        return

    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle('Throughput Performance Analysis', fontsize=16, fontweight='bold')

    # 1. Throughput vs NFFT
    ax1 = axes[0, 0]
    if len(throughput_data['engine_nfft'].unique()) > 1:
        nfft_groups = throughput_data.groupby('engine_nfft')['frames_per_second'].agg(['mean', 'std', 'count'])
        nfft_values = nfft_groups.index
        fps_means = nfft_groups['mean']
        fps_stds = nfft_groups['std'].fillna(0)

        ax1.errorbar(nfft_values, fps_means, yerr=fps_stds,
                    marker='o', linewidth=2, markersize=8, capsize=5)
        ax1.set_xlabel('NFFT Size')
        ax1.set_ylabel('Frames per Second')
        ax1.set_title('Throughput vs NFFT Size')
        ax1.grid(True, alpha=0.3)
        ax1.set_xscale('log', base=2)
    else:
        ax1.text(0.5, 0.5, 'Insufficient NFFT variation\nfor scaling analysis',
                ha='center', va='center', transform=ax1.transAxes)
        ax1.set_title('Throughput vs NFFT Size (Insufficient Data)')

    # 2. Throughput vs Batch Size
    ax2 = axes[0, 1]
    if len(throughput_data['engine_channels'].unique()) > 1:
        batch_groups = throughput_data.groupby('engine_channels')['frames_per_second'].agg(['mean', 'std', 'count'])
        batch_values = batch_groups.index
        fps_means = batch_groups['mean']
        fps_stds = batch_groups['std'].fillna(0)

        ax2.errorbar(batch_values, fps_means, yerr=fps_stds,
                    marker='s', linewidth=2, markersize=8, capsize=5, color='orange')
        ax2.set_xlabel('Batch Size')
        ax2.set_ylabel('Frames per Second')
        ax2.set_title('Throughput vs Batch Size')
        ax2.grid(True, alpha=0.3)
    else:
        ax2.text(0.5, 0.5, 'Insufficient batch size\nvariation for scaling analysis',
                ha='center', va='center', transform=ax2.transAxes)
        ax2.set_title('Throughput vs Batch Size (Insufficient Data)')

    # 3. Performance Heatmap
    ax3 = axes[1, 0]
    if len(throughput_data) > 2:
        pivot_data = throughput_data.pivot_table(
            index='engine_nfft',
            columns='engine_channels',
            values='frames_per_second',
            aggfunc='mean'
        )

        if not pivot_data.empty:
            sns.heatmap(pivot_data, annot=True, fmt='.0f', cmap='viridis', ax=ax3)
            ax3.set_title('Performance Heatmap (FPS)')
            ax3.set_xlabel('Batch Size')
            ax3.set_ylabel('NFFT Size')
        else:
            ax3.text(0.5, 0.5, 'Insufficient data\nfor heatmap',
                    ha='center', va='center', transform=ax3.transAxes)
            ax3.set_title('Performance Heatmap (Insufficient Data)')
    else:
        ax3.text(0.5, 0.5, 'Insufficient data\nfor heatmap',
                ha='center', va='center', transform=ax3.transAxes)
        ax3.set_title('Performance Heatmap (Insufficient Data)')

    # 4. Data Throughput (GB/s)
    ax4 = axes[1, 1]
    if 'gb_per_second' in throughput_data.columns and not throughput_data['gb_per_second'].isna().all():
        valid_gb_data = throughput_data.dropna(subset=['gb_per_second'])
        if not valid_gb_data.empty:
            ax4.scatter(valid_gb_data['frames_per_second'], valid_gb_data['gb_per_second'],
                       s=60, alpha=0.7, c=valid_gb_data['engine_nfft'], cmap='plasma')
            ax4.set_xlabel('Frames per Second')
            ax4.set_ylabel('GB per Second')
            ax4.set_title('Data Throughput Correlation')
            ax4.grid(True, alpha=0.3)

            # Add colorbar
            scatter = ax4.collections[0]
            cbar = plt.colorbar(scatter, ax=ax4)
            cbar.set_label('NFFT Size')
        else:
            ax4.text(0.5, 0.5, 'No valid GB/s data',
                    ha='center', va='center', transform=ax4.transAxes)
            ax4.set_title('Data Throughput (No Data)')
    else:
        ax4.text(0.5, 0.5, 'No GB/s data available',
                ha='center', va='center', transform=ax4.transAxes)
        ax4.set_title('Data Throughput (No Data)')

    plt.tight_layout()

    # Save the figure in both formats
    output_file = output_dir / "throughput_scaling"
    save_figure_dual_format(fig, output_file)


def plot_latency_analysis(df: pd.DataFrame, output_dir: Path) -> None:
    """Create latency analysis visualizations."""
    latency_data = df[df['benchmark_type'] == 'latency'].copy()

    if latency_data.empty:
        print("No latency data found for plotting")
        return

    # Remove any rows with missing latency data
    latency_data = latency_data.dropna(subset=['mean_latency_us'])

    if latency_data.empty:
        print("No valid latency data (missing mean_latency_us)")
        return

    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle('Latency Performance Analysis', fontsize=16, fontweight='bold')

    # 1. Latency vs NFFT
    ax1 = axes[0, 0]
    if len(latency_data['engine_nfft'].unique()) > 1:
        nfft_groups = latency_data.groupby('engine_nfft')['mean_latency_us'].agg(['mean', 'std', 'count'])
        nfft_values = nfft_groups.index
        latency_means = nfft_groups['mean']
        latency_stds = nfft_groups['std'].fillna(0)

        ax1.errorbar(nfft_values, latency_means, yerr=latency_stds,
                    marker='o', linewidth=2, markersize=8, capsize=5, color='red')
        ax1.set_xlabel('NFFT Size')
        ax1.set_ylabel('Mean Latency (μs)')
        ax1.set_title('Latency vs NFFT Size')
        ax1.grid(True, alpha=0.3)
        ax1.set_xscale('log', base=2)
    else:
        ax1.text(0.5, 0.5, 'Insufficient NFFT variation\nfor latency analysis',
                ha='center', va='center', transform=ax1.transAxes)
        ax1.set_title('Latency vs NFFT Size (Insufficient Data)')

    # 2. Latency vs Batch Size
    ax2 = axes[0, 1]
    if len(latency_data['engine_channels'].unique()) > 1:
        batch_groups = latency_data.groupby('engine_channels')['mean_latency_us'].agg(['mean', 'std', 'count'])
        batch_values = batch_groups.index
        latency_means = batch_groups['mean']
        latency_stds = batch_groups['std'].fillna(0)

        ax2.errorbar(batch_values, latency_means, yerr=latency_stds,
                    marker='s', linewidth=2, markersize=8, capsize=5, color='purple')
        ax2.set_xlabel('Batch Size')
        ax2.set_ylabel('Mean Latency (μs)')
        ax2.set_title('Latency vs Batch Size')
        ax2.grid(True, alpha=0.3)
    else:
        ax2.text(0.5, 0.5, 'Insufficient batch size\nvariation for latency analysis',
                ha='center', va='center', transform=ax2.transAxes)
        ax2.set_title('Latency vs Batch Size (Insufficient Data)')

    # 3. Latency Distribution
    ax3 = axes[1, 0]
    ax3.hist(latency_data['mean_latency_us'], bins=min(20, len(latency_data)),
             alpha=0.7, color='skyblue', edgecolor='black')
    ax3.set_xlabel('Mean Latency (μs)')
    ax3.set_ylabel('Frequency')
    ax3.set_title('Latency Distribution')
    ax3.grid(True, alpha=0.3)

    # Add statistics text
    mean_lat = latency_data['mean_latency_us'].mean()
    ax3.axvline(mean_lat, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean_lat:.1f}μs')
    ax3.legend()

    # 4. Latency Heatmap
    ax4 = axes[1, 1]
    if len(latency_data) > 2:
        pivot_data = latency_data.pivot_table(
            index='engine_nfft',
            columns='engine_channels',
            values='mean_latency_us',
            aggfunc='mean'
        )

        if not pivot_data.empty:
            sns.heatmap(pivot_data, annot=True, fmt='.0f', cmap='Reds', ax=ax4)
            ax4.set_title('Latency Heatmap (μs)')
            ax4.set_xlabel('Batch Size')
            ax4.set_ylabel('NFFT Size')
        else:
            ax4.text(0.5, 0.5, 'Insufficient data\nfor heatmap',
                    ha='center', va='center', transform=ax4.transAxes)
            ax4.set_title('Latency Heatmap (Insufficient Data)')
    else:
        ax4.text(0.5, 0.5, 'Insufficient data\nfor heatmap',
                ha='center', va='center', transform=ax4.transAxes)
        ax4.set_title('Latency Heatmap (Insufficient Data)')

    plt.tight_layout()

    # Save the figure in both formats
    output_file = output_dir / "latency_vs_nfft"
    save_figure_dual_format(fig, output_file)


def plot_combined_analysis(df: pd.DataFrame, output_dir: Path) -> None:
    """Create combined multi-metric analysis."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('Combined Performance Analysis', fontsize=16, fontweight='bold')

    # 1. Performance Overview by Benchmark Type
    ax1 = axes[0, 0]
    benchmark_types = df['benchmark_type'].unique()

    if 'throughput' in benchmark_types:
        throughput_data = df[df['benchmark_type'] == 'throughput']
        if not throughput_data.empty and 'frames_per_second' in throughput_data.columns:
            valid_throughput = throughput_data.dropna(subset=['frames_per_second'])
            if not valid_throughput.empty:
                ax1.scatter(valid_throughput['engine_nfft'], valid_throughput['frames_per_second'],
                           s=60, alpha=0.7, label='Throughput (FPS)', color='blue')

    if 'latency' in benchmark_types:
        latency_data = df[df['benchmark_type'] == 'latency']
        if not latency_data.empty and 'mean_latency_us' in latency_data.columns:
            valid_latency = latency_data.dropna(subset=['mean_latency_us'])
            if not valid_latency.empty:
                # Scale latency to make it visible with FPS (divide by 1000)
                scaled_latency = valid_latency['mean_latency_us'] / 1000
                ax1.scatter(valid_latency['engine_nfft'], scaled_latency,
                           s=60, alpha=0.7, label='Latency (ms)', color='red', marker='^')

    ax1.set_xlabel('NFFT Size')
    ax1.set_ylabel('Performance Metric')
    ax1.set_title('Performance vs NFFT Size')
    ax1.set_xscale('log', base=2)
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # 2. Parameter Space Coverage
    ax2 = axes[0, 1]
    for i, benchmark_type in enumerate(benchmark_types):
        subset = df[df['benchmark_type'] == benchmark_type]
        if not subset.empty:
            colors = ['blue', 'red', 'green', 'orange', 'purple']
            ax2.scatter(subset['engine_nfft'], subset['engine_channels'],
                       s=60, alpha=0.7, label=benchmark_type, color=colors[i % len(colors)])

    ax2.set_xlabel('NFFT Size')
    ax2.set_ylabel('Batch Size')
    ax2.set_title('Parameter Space Coverage')
    ax2.set_xscale('log', base=2)
    ax2.set_yscale('log', base=2)
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    # 3. Summary Statistics
    ax3 = axes[1, 0]
    summary_text = "Experiment Summary:\n\n"

    for benchmark_type in benchmark_types:
        subset = df[df['benchmark_type'] == benchmark_type]
        summary_text += f"{benchmark_type.title()}:\n"
        summary_text += f"  Measurements: {len(subset)}\n"

        if benchmark_type == 'throughput' and 'frames_per_second' in subset.columns:
            valid_data = subset.dropna(subset=['frames_per_second'])
            if not valid_data.empty:
                mean_fps = valid_data['frames_per_second'].mean()
                max_fps = valid_data['frames_per_second'].max()
                summary_text += f"  Avg FPS: {mean_fps:.1f}\n"
                summary_text += f"  Max FPS: {max_fps:.1f}\n"

        elif benchmark_type == 'latency' and 'mean_latency_us' in subset.columns:
            valid_data = subset.dropna(subset=['mean_latency_us'])
            if not valid_data.empty:
                mean_lat = valid_data['mean_latency_us'].mean()
                min_lat = valid_data['mean_latency_us'].min()
                summary_text += f"  Avg Latency: {mean_lat:.1f}μs\n"
                summary_text += f"  Min Latency: {min_lat:.1f}μs\n"

        summary_text += "\n"

    ax3.text(0.05, 0.95, summary_text, transform=ax3.transAxes,
             verticalalignment='top', fontfamily='monospace', fontsize=10)
    ax3.set_xlim(0, 1)
    ax3.set_ylim(0, 1)
    ax3.axis('off')
    ax3.set_title('Summary Statistics')

    # 4. Best Configurations
    ax4 = axes[1, 1]
    best_configs_text = "Optimal Configurations:\n\n"

    # Find best throughput configuration
    if 'throughput' in benchmark_types:
        throughput_data = df[df['benchmark_type'] == 'throughput']
        if not throughput_data.empty and 'frames_per_second' in throughput_data.columns:
            valid_throughput = throughput_data.dropna(subset=['frames_per_second'])
            if not valid_throughput.empty:
                best_idx = valid_throughput['frames_per_second'].idxmax()
                best_row = valid_throughput.loc[best_idx]
                best_configs_text += "Best Throughput:\n"
                best_configs_text += f"  NFFT: {int(best_row['engine_nfft'])}\n"
                best_configs_text += f"  Batch: {int(best_row['engine_channels'])}\n"
                best_configs_text += f"  FPS: {best_row['frames_per_second']:.1f}\n\n"

    # Find best latency configuration
    if 'latency' in benchmark_types:
        latency_data = df[df['benchmark_type'] == 'latency']
        if not latency_data.empty and 'mean_latency_us' in latency_data.columns:
            valid_latency = latency_data.dropna(subset=['mean_latency_us'])
            if not valid_latency.empty:
                best_idx = valid_latency['mean_latency_us'].idxmin()
                best_row = valid_latency.loc[best_idx]
                best_configs_text += "Best Latency:\n"
                best_configs_text += f"  NFFT: {int(best_row['engine_nfft'])}\n"
                best_configs_text += f"  Batch: {int(best_row['engine_channels'])}\n"
                best_configs_text += f"  Latency: {best_row['mean_latency_us']:.1f}μs\n\n"

    ax4.text(0.05, 0.95, best_configs_text, transform=ax4.transAxes,
             verticalalignment='top', fontfamily='monospace', fontsize=10)
    ax4.set_xlim(0, 1)
    ax4.set_ylim(0, 1)
    ax4.axis('off')
    ax4.set_title('Optimal Configurations')

    plt.tight_layout()

    # Save the figure in both formats
    output_file = output_dir / "combined_analysis"
    save_figure_dual_format(fig, output_file)


def plot_accuracy_analysis(df: pd.DataFrame, output_dir: Path) -> None:
    """Create accuracy analysis visualizations."""
    accuracy_data = df[df['benchmark_type'] == 'accuracy'].copy()

    if accuracy_data.empty:
        print("No accuracy data found for plotting")
        # Create placeholder file to satisfy Snakemake expectations
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, 'No Accuracy Data Available\n\nRun accuracy benchmarks to generate this plot',
                ha='center', va='center', fontsize=16, transform=ax.transAxes,
                bbox={'boxstyle': "round,pad=0.3", 'facecolor': "lightgray", 'alpha': 0.7})
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        ax.set_title('Accuracy Analysis', fontsize=16, fontweight='bold')

        output_path = output_dir / "accuracy_heatmap"
        save_figure_dual_format(fig, output_path, close_fig=True)
        print("Created placeholder for accuracy analysis")
        return

    # Create a simple accuracy plot if we have data
    fig, ax = plt.subplots(1, 1, figsize=(10, 6))
    fig.suptitle('Accuracy Analysis', fontsize=16, fontweight='bold')

    if 'pass_rate' in accuracy_data.columns:
        valid_data = accuracy_data.dropna(subset=['pass_rate'])
        if not valid_data.empty:
            ax.scatter(valid_data['engine_nfft'], valid_data['pass_rate'],
                      s=100, alpha=0.7, c=valid_data['engine_channels'], cmap='viridis')
            ax.set_xlabel('NFFT Size')
            ax.set_ylabel('Pass Rate')
            ax.set_title('Accuracy vs NFFT Size')
            ax.set_xscale('log', base=2)
            ax.grid(True, alpha=0.3)

            # Add colorbar
            scatter = ax.collections[0]
            cbar = plt.colorbar(scatter, ax=ax)
            cbar.set_label('Batch Size')
        else:
            ax.text(0.5, 0.5, 'No valid accuracy data',
                   ha='center', va='center', transform=ax.transAxes)
    else:
        ax.text(0.5, 0.5, 'No pass_rate column found',
               ha='center', va='center', transform=ax.transAxes)

    plt.tight_layout()

    # Save the figure in both formats
    output_file = output_dir / "accuracy_heatmap"
    save_figure_dual_format(fig, output_file)


def main():
    """Main figure generation function."""
    print("=" * 60)
    print("Ionosphere HPC Figure Generation")
    print("=" * 60)

    # Setup output directory
    output_dir = Path("artifacts/figures")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Load summary data
        df = load_summary_data()

        if df.empty:
            print("No data available for visualization")
            return

        print("\nGenerating figures...")

        # Generate all visualizations
        plot_throughput_scaling(df, output_dir)
        plot_latency_analysis(df, output_dir)
        plot_accuracy_analysis(df, output_dir)
        plot_combined_analysis(df, output_dir)

        print("\nFigure generation complete!")
        print(f"All figures saved to: {output_dir}")

        # List generated files
        figure_files = list(output_dir.glob("*.png"))
        if figure_files:
            print("\nGenerated figures:")
            for fig_file in sorted(figure_files):
                print(f"  {fig_file.name}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Make sure to run the analysis script first:")
        print("  python experiments/scripts/analyze.py")
    except Exception as e:
        print(f"Error generating figures: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
