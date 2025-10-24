#!/usr/bin/env python
"""
Quick Plot Utility for Ionosphere HPC Data
==========================================

Rapidly visualize experiment data without full analysis pipeline.
Great for debugging, exploration, and quick checks during experiments.

Usage:
    python quick_plot.py                          # Plot all available data
    python quick_plot.py --type throughput        # Plot only throughput data
    python quick_plot.py --config 1024 2          # Plot specific NFFT/batch config
    python quick_plot.py --latest                 # Plot only most recent data

Examples:
    python quick_plot.py --type latency --save
    python quick_plot.py --config 2048 4 --show
"""

import argparse
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

# Set style for consistent plots
plt.style.use('seaborn-v0_8')
sns.set_palette("husl")


def save_plot_with_format(output_path: Path, format_choice: str = 'png', dpi: int = 150):
    """Save plot in specified format(s)."""
    if format_choice == 'png':
        plt.savefig(output_path.with_suffix('.png'), dpi=dpi, bbox_inches='tight')
        print(f"Saved: {output_path.with_suffix('.png')}")
    elif format_choice == 'svg':
        plt.savefig(output_path.with_suffix('.svg'), bbox_inches='tight', format='svg')
        print(f"Saved: {output_path.with_suffix('.svg')}")
    elif format_choice == 'both':
        plt.savefig(output_path.with_suffix('.png'), dpi=dpi, bbox_inches='tight')
        plt.savefig(output_path.with_suffix('.svg'), bbox_inches='tight', format='svg')
        print(f"Saved: {output_path.with_suffix('.png')}")
        print(f"Saved: {output_path.with_suffix('.svg')}")


def find_data_files(data_dir: str = "artifacts/data", benchmark_type: str = None) -> list:
    """Find experiment data files."""
    data_path = Path(data_dir)

    if benchmark_type:
        pattern = f"{benchmark_type}_summary_*.csv"
    else:
        pattern = "*_summary_*.csv"

    files = list(data_path.glob(pattern))
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)  # Most recent first

    return files


def load_data(files: list, latest_only: bool = False) -> pd.DataFrame:
    """Load and combine data files."""
    if latest_only:
        files = files[:5]  # Only load most recent 5 files

    dataframes = []
    for file_path in files:
        try:
            df = pd.read_csv(file_path)
            # Infer benchmark type from filename
            filename = file_path.stem
            if 'throughput' in filename:
                df['benchmark_type'] = 'throughput'
            elif 'latency' in filename:
                df['benchmark_type'] = 'latency'
            elif 'accuracy' in filename:
                df['benchmark_type'] = 'accuracy'
            else:
                df['benchmark_type'] = 'unknown'

            df['source_file'] = file_path.name
            dataframes.append(df)
        except Exception as e:
            print(f"Warning: Could not load {file_path}: {e}")

    if not dataframes:
        return pd.DataFrame()

    combined = pd.concat(dataframes, ignore_index=True)
    print(f"Loaded {len(combined)} measurements from {len(dataframes)} files")
    return combined


def plot_throughput_quick(df: pd.DataFrame, save: bool = False, show: bool = True, format_choice: str = 'png'):
    """Quick throughput visualization."""
    throughput_data = df[df['benchmark_type'] == 'throughput']
    if throughput_data.empty:
        print("No throughput data found")
        return

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    # FPS vs NFFT
    axes[0].scatter(throughput_data['engine_nfft'], throughput_data['frames_per_second'],
                   c=throughput_data['engine_channels'], cmap='viridis', s=100, alpha=0.7)
    axes[0].set_xlabel('NFFT Size')
    axes[0].set_ylabel('Frames Per Second')
    axes[0].set_title('Throughput: FPS vs NFFT')
    axes[0].set_xscale('log', base=2)
    axes[0].grid(True, alpha=0.3)

    # Add colorbar for batch size
    scatter = axes[0].collections[0]
    cbar = plt.colorbar(scatter, ax=axes[0])
    cbar.set_label('Batch Size')

    # FPS vs Batch Size
    if 'gb_per_second' in throughput_data.columns:
        axes[1].scatter(throughput_data['engine_channels'], throughput_data['gb_per_second'],
                       c=throughput_data['engine_nfft'], cmap='plasma', s=100, alpha=0.7)
        axes[1].set_xlabel('Batch Size')
        axes[1].set_ylabel('GB/Second')
        axes[1].set_title('Throughput: GB/s vs Batch Size')

        scatter2 = axes[1].collections[0]
        cbar2 = plt.colorbar(scatter2, ax=axes[1])
        cbar2.set_label('NFFT Size')
    else:
        axes[1].scatter(throughput_data['engine_channels'], throughput_data['frames_per_second'],
                       c=throughput_data['engine_nfft'], cmap='plasma', s=100, alpha=0.7)
        axes[1].set_xlabel('Batch Size')
        axes[1].set_ylabel('Frames Per Second')
        axes[1].set_title('Throughput: FPS vs Batch Size')

    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()

    if save:
        output_path = Path("artifacts/figures/quick_throughput")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_plot_with_format(output_path, format_choice)

    if show:
        plt.show()


def plot_latency_quick(df: pd.DataFrame, save: bool = False, show: bool = True, format_choice: str = 'png'):
    """Quick latency visualization."""
    latency_data = df[df['benchmark_type'] == 'latency']
    if latency_data.empty:
        print("No latency data found")
        return

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    # Mean latency vs NFFT
    axes[0].scatter(latency_data['engine_nfft'], latency_data['mean_latency_us'],
                   c=latency_data['engine_channels'], cmap='viridis', s=100, alpha=0.7)
    axes[0].set_xlabel('NFFT Size')
    axes[0].set_ylabel('Mean Latency (us)')
    axes[0].set_title('Latency: Mean vs NFFT')
    axes[0].set_xscale('log', base=2)
    axes[0].set_yscale('log')
    axes[0].grid(True, alpha=0.3)

    scatter = axes[0].collections[0]
    cbar = plt.colorbar(scatter, ax=axes[0])
    cbar.set_label('Batch Size')

    # P95 vs Mean latency (if available)
    if 'p95_latency_us' in latency_data.columns:
        axes[1].scatter(latency_data['mean_latency_us'], latency_data['p95_latency_us'],
                       c=latency_data['engine_nfft'], cmap='plasma', s=100, alpha=0.7)
        axes[1].set_xlabel('Mean Latency (us)')
        axes[1].set_ylabel('P95 Latency (us)')
        axes[1].set_title('Latency: P95 vs Mean')
        axes[1].plot([latency_data['mean_latency_us'].min(), latency_data['mean_latency_us'].max()],
                    [latency_data['mean_latency_us'].min(), latency_data['mean_latency_us'].max()],
                    'r--', alpha=0.5, label='y=x')
        axes[1].legend()
    else:
        # Latency vs batch size
        axes[1].scatter(latency_data['engine_channels'], latency_data['mean_latency_us'],
                       c=latency_data['engine_nfft'], cmap='plasma', s=100, alpha=0.7)
        axes[1].set_xlabel('Batch Size')
        axes[1].set_ylabel('Mean Latency (us)')
        axes[1].set_title('Latency: Mean vs Batch Size')

    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()

    if save:
        output_path = Path("artifacts/figures/quick_latency")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_plot_with_format(output_path, format_choice)

    if show:
        plt.show()


def plot_accuracy_quick(df: pd.DataFrame, save: bool = False, show: bool = True, format_choice: str = 'png'):
    """Quick accuracy visualization."""
    accuracy_data = df[df['benchmark_type'] == 'accuracy']
    if accuracy_data.empty:
        print("No accuracy data found")
        return

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    # Pass rate vs NFFT
    axes[0].scatter(accuracy_data['engine_nfft'], accuracy_data['pass_rate'],
                   c=accuracy_data['engine_channels'], cmap='viridis', s=100, alpha=0.7)
    axes[0].set_xlabel('NFFT Size')
    axes[0].set_ylabel('Pass Rate')
    axes[0].set_title('Accuracy: Pass Rate vs NFFT')
    axes[0].set_xscale('log', base=2)
    axes[0].grid(True, alpha=0.3)

    scatter = axes[0].collections[0]
    cbar = plt.colorbar(scatter, ax=axes[0])
    cbar.set_label('Batch Size')

    # SNR vs Pass Rate (if available)
    if 'mean_snr_db' in accuracy_data.columns:
        axes[1].scatter(accuracy_data['mean_snr_db'], accuracy_data['pass_rate'],
                       c=accuracy_data['engine_nfft'], cmap='plasma', s=100, alpha=0.7)
        axes[1].set_xlabel('Mean SNR (dB)')
        axes[1].set_ylabel('Pass Rate')
        axes[1].set_title('Accuracy: Pass Rate vs SNR')
    else:
        # Pass rate vs batch size
        axes[1].scatter(accuracy_data['engine_channels'], accuracy_data['pass_rate'],
                       c=accuracy_data['engine_nfft'], cmap='plasma', s=100, alpha=0.7)
        axes[1].set_xlabel('Batch Size')
        axes[1].set_ylabel('Pass Rate')
        axes[1].set_title('Accuracy: Pass Rate vs Batch Size')

    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()

    if save:
        output_path = Path("artifacts/figures/quick_accuracy")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_plot_with_format(output_path, format_choice)

    if show:
        plt.show()


def plot_overview_quick(df: pd.DataFrame, save: bool = False, show: bool = True, format_choice: str = 'png'):
    """Quick overview of all available data."""
    if df.empty:
        print("No data to plot")
        return

    benchmark_types = df['benchmark_type'].unique()
    n_types = len(benchmark_types)

    if n_types == 0:
        print("No benchmark data found")
        return

    fig, axes = plt.subplots(1, n_types, figsize=(6*n_types, 6))
    if n_types == 1:
        axes = [axes]

    for i, benchmark_type in enumerate(benchmark_types):
        subset = df[df['benchmark_type'] == benchmark_type]

        if benchmark_type == 'throughput' and 'frames_per_second' in subset.columns:
            axes[i].scatter(subset['engine_nfft'], subset['frames_per_second'],
                           c=subset['engine_channels'], cmap='viridis', s=80, alpha=0.7)
            axes[i].set_ylabel('Frames Per Second')
            axes[i].set_title(f'Throughput Overview\n({len(subset)} measurements)')
        elif benchmark_type == 'latency' and 'mean_latency_us' in subset.columns:
            axes[i].scatter(subset['engine_nfft'], subset['mean_latency_us'],
                           c=subset['engine_channels'], cmap='plasma', s=80, alpha=0.7)
            axes[i].set_ylabel('Mean Latency (us)')
            axes[i].set_yscale('log')
            axes[i].set_title(f'Latency Overview\n({len(subset)} measurements)')
        elif benchmark_type == 'accuracy' and 'pass_rate' in subset.columns:
            axes[i].scatter(subset['engine_nfft'], subset['pass_rate'],
                           c=subset['engine_channels'], cmap='coolwarm', s=80, alpha=0.7)
            axes[i].set_ylabel('Pass Rate')
            axes[i].set_title(f'Accuracy Overview\n({len(subset)} measurements)')

        axes[i].set_xlabel('NFFT Size')
        axes[i].set_xscale('log', base=2)
        axes[i].grid(True, alpha=0.3)

    plt.tight_layout()

    if save:
        output_path = Path("artifacts/figures/quick_overview")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_plot_with_format(output_path, format_choice)

    if show:
        plt.show()


def print_data_summary(df: pd.DataFrame):
    """Print a quick summary of available data."""
    if df.empty:
        print("No data found")
        return

    print("\n** Data Summary **")
    print(f"Total measurements: {len(df)}")

    if 'benchmark_type' in df.columns:
        for benchmark_type in df['benchmark_type'].unique():
            subset = df[df['benchmark_type'] == benchmark_type]
            print(f"  {benchmark_type}: {len(subset)} measurements")

            if len(subset) > 0:
                configs = subset[['engine_nfft', 'engine_channels']].drop_duplicates()
                print(f"    Configurations: {len(configs)} unique NFFT/batch combinations")
                print(f"    NFFT range: {subset['engine_nfft'].min()}-{subset['engine_nfft'].max()}")
                print(f"    Batch range: {subset['engine_channels'].min()}-{subset['engine_channels'].max()}")

    print()


def main():
    parser = argparse.ArgumentParser(description='Quick plotting utility for ionosphere HPC data')

    parser.add_argument('--type', choices=['throughput', 'latency', 'accuracy', 'overview'],
                       help='Type of plot to generate')
    parser.add_argument('--config', nargs=2, type=int, metavar=('NFFT', 'BATCH'),
                       help='Plot specific NFFT and batch configuration')
    parser.add_argument('--latest', action='store_true',
                       help='Plot only most recent data files')
    parser.add_argument('--save', action='store_true',
                       help='Save plots to artifacts/figures/')
    parser.add_argument('--no-show', action='store_true',
                       help='Do not display plots (useful when saving)')
    parser.add_argument('--data-dir', default='artifacts/data',
                       help='Directory containing data files')
    parser.add_argument('--format', choices=['png', 'svg', 'both'], default='png',
                       help='Output format for saved plots (default: png)')

    args = parser.parse_args()

    print("Quick Plot Utility for Ionosphere HPC Data")
    print("=" * 50)

    # Find and load data
    files = find_data_files(args.data_dir, args.type)
    if not files:
        print(f"No data files found in {args.data_dir}")
        if args.type:
            print(f"Specifically looking for {args.type} data")
        return

    print(f"Found {len(files)} data files")
    df = load_data(files, args.latest)

    if df.empty:
        print("No valid data loaded")
        return

    # Filter by specific configuration if requested
    if args.config:
        nfft, batch = args.config
        df = df[(df['engine_nfft'] == nfft) & (df['engine_channels'] == batch)]
        print(f"Filtered to NFFT={nfft}, Batch={batch}: {len(df)} measurements")
        if df.empty:
            print("No data matches the specified configuration")
            return

    print_data_summary(df)

    show_plots = not args.no_show

    # Generate plots based on type
    if args.type == 'throughput':
        plot_throughput_quick(df, args.save, show_plots, args.format)
    elif args.type == 'latency':
        plot_latency_quick(df, args.save, show_plots, args.format)
    elif args.type == 'accuracy':
        plot_accuracy_quick(df, args.save, show_plots, args.format)
    elif args.type == 'overview':
        plot_overview_quick(df, args.save, show_plots, args.format)
    else:
        # Auto-detect and plot all available types
        available_types = df['benchmark_type'].unique() if 'benchmark_type' in df.columns else []

        if 'throughput' in available_types:
            print("\n** Throughput Plots **")
            plot_throughput_quick(df, args.save, show_plots, args.format)

        if 'latency' in available_types:
            print("\n** Latency Plots **")
            plot_latency_quick(df, args.save, show_plots, args.format)

        if 'accuracy' in available_types:
            print("\n** Accuracy Plots **")
            plot_accuracy_quick(df, args.save, show_plots, args.format)

        # Always show overview if multiple types
        if len(available_types) > 1:
            print("\n** Overview Plot **")
            plot_overview_quick(df, args.save, show_plots, args.format)

    print("\nQuick plotting complete!")


if __name__ == "__main__":
    main()
