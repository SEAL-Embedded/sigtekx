"""
Visualization Module
====================

Interactive and static plotting for benchmark analysis.
Combines Plotly (interactive) and matplotlib (publication-quality) visualizations.

TODO: Port complete visualization suite from analysis overhaul.
This skeleton provides the basic structure.
"""

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import seaborn as sns
from plotly.subplots import make_subplots

# Set style
sns.set_palette("husl")
plt.style.use('seaborn-v0_8-darkgrid')


class VisualizationConfig:
    """Configuration for visualization styling."""

    def __init__(
        self,
        use_plotly: bool = True,
        use_matplotlib: bool = True,
        dpi: int = 300,
        figsize: tuple = (12, 8),
        color_palette: str = "husl"
    ):
        self.use_plotly = use_plotly
        self.use_matplotlib = use_matplotlib
        self.dpi = dpi
        self.figsize = figsize
        self.color_palette = color_palette


class StatisticalPlotter:
    """Statistical distribution and comparison plots."""

    def __init__(self, config: VisualizationConfig | None = None):
        self.config = config or VisualizationConfig()

    def plot_distribution(
        self,
        data: pd.DataFrame,
        metric: str,
        group_by: str | None = None,
        output_path: Path | None = None
    ) -> go.Figure:
        """Plot distribution with box plots and violin plots."""
        fig = go.Figure()

        if group_by:
            for group_val in data[group_by].unique():
                group_data = data[data[group_by] == group_val]
                fig.add_trace(go.Violin(
                    y=group_data[metric],
                    name=str(group_val),
                    box_visible=True,
                    meanline_visible=True
                ))
        else:
            fig.add_trace(go.Violin(
                y=data[metric],
                name=metric,
                box_visible=True,
                meanline_visible=True
            ))

        fig.update_layout(
            title=f"{metric} Distribution",
            yaxis_title=metric,
            showlegend=True
        )

        if output_path:
            fig.write_html(str(output_path))

        return fig

    def plot_comparison(
        self,
        baseline: pd.Series,
        target: pd.Series,
        title: str,
        output_path: Path | None = None
    ) -> go.Figure:
        """Plot comparison between two datasets."""
        fig = go.Figure()

        fig.add_trace(go.Box(y=baseline, name="Baseline"))
        fig.add_trace(go.Box(y=target, name="Target"))

        fig.update_layout(
            title=title,
            yaxis_title="Value",
            showlegend=True
        )

        if output_path:
            fig.write_html(str(output_path))

        return fig


class PerformancePlotter:
    """Performance scaling and analysis plots."""

    def __init__(self, config: VisualizationConfig | None = None):
        self.config = config or VisualizationConfig()

    def plot_scaling(
        self,
        data: pd.DataFrame,
        x_col: str,
        y_col: str,
        group_by: str | None = None,
        log_x: bool = False,
        log_y: bool = False,
        output_path: Path | None = None
    ) -> go.Figure:
        """Plot performance scaling curves."""
        fig = go.Figure()

        if group_by:
            for group_val in sorted(data[group_by].unique()):
                group_data = data[data[group_by] == group_val].sort_values(x_col)
                fig.add_trace(go.Scatter(
                    x=group_data[x_col],
                    y=group_data[y_col],
                    mode='lines+markers',
                    name=f"{group_by}={group_val}"
                ))
        else:
            sorted_data = data.sort_values(x_col)
            fig.add_trace(go.Scatter(
                x=sorted_data[x_col],
                y=sorted_data[y_col],
                mode='lines+markers',
                name=y_col
            ))

        fig.update_layout(
            title=f"{y_col} vs {x_col} Scaling",
            xaxis_title=x_col,
            yaxis_title=y_col,
            xaxis_type='log' if log_x else 'linear',
            yaxis_type='log' if log_y else 'linear',
            showlegend=True
        )

        if output_path:
            fig.write_html(str(output_path))

        return fig

    def plot_heatmap(
        self,
        data: pd.DataFrame,
        x_col: str,
        y_col: str,
        z_col: str,
        output_path: Path | None = None
    ) -> go.Figure:
        """Plot 2D heatmap of performance metrics."""
        pivot = data.pivot_table(values=z_col, index=y_col, columns=x_col, aggfunc='mean')

        # Dynamically adjust figure height based on number of y-axis values
        # More rows = taller figure for better readability
        num_y_values = len(pivot.index)
        figure_height = max(400, 50 * num_y_values + 150)  # Minimum 400px, ~50px per row + margins
        figure_width = max(600, 80 * len(pivot.columns) + 200)  # Scale width with columns too

        # Use INDICES for y-axis to ensure equal spacing (not actual values)
        # This prevents exponential spacing for powers-of-2 like channels (2, 4, 8, 16, 32, 64, 128)
        y_indices = list(range(len(pivot.index)))

        fig = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=y_indices,  # Use indices (0, 1, 2, ...) not actual values
            colorscale='Viridis',
            colorbar=dict(title=z_col)
        ))

        fig.update_layout(
            title=f"{z_col} Heatmap",
            xaxis_title=x_col,
            yaxis_title=y_col,
            height=figure_height,
            width=figure_width,
            margin=dict(l=80, r=80, t=100, b=80)  # Adequate margins for tick labels
        )

        # Map indices to actual values with categorical tick labels
        # This gives equal visual spacing for all values (fixes exponential spacing issue)
        fig.update_yaxes(
            tickmode='array',
            tickvals=y_indices,  # Show all values
            ticktext=[str(int(val)) if isinstance(val, (int, float)) else str(val) for val in pivot.index],
            tickfont=dict(size=11)  # Readable font size
        )

        # Also improve x-axis readability
        fig.update_xaxes(
            tickfont=dict(size=11)
        )

        if output_path:
            fig.write_html(str(output_path))

        return fig

    def plot_rtf_vs_resolution(
        self,
        data: pd.DataFrame,
        output_path: Path | None = None
    ) -> go.Figure:
        """Plot Real-Time Factor vs Frequency Resolution (key ionosphere metric)."""
        if 'rtf' not in data.columns or 'freq_resolution_hz' not in data.columns:
            raise ValueError("Data must contain 'rtf' and 'freq_resolution_hz' columns")

        fig = go.Figure()

        # Color by NFFT for context
        if 'engine_nfft' in data.columns:
            for nfft in sorted(data['engine_nfft'].unique()):
                nfft_data = data[data['engine_nfft'] == nfft]
                fig.add_trace(go.Scatter(
                    x=nfft_data['freq_resolution_hz'],
                    y=nfft_data['rtf'],
                    mode='markers',
                    name=f"NFFT={nfft}",
                    marker=dict(size=10)
                ))
        else:
            fig.add_trace(go.Scatter(
                x=data['freq_resolution_hz'],
                y=data['rtf'],
                mode='markers',
                marker=dict(size=10)
            ))

        # Add reference lines
        fig.add_hline(y=1.0, line_dash="dash", line_color="red",
                      annotation_text="Real-time threshold")
        fig.add_hline(y=2.0, line_dash="dash", line_color="green",
                      annotation_text="2x real-time")

        fig.update_layout(
            title="Real-Time Factor vs Frequency Resolution",
            xaxis_title="Frequency Resolution (Hz)",
            yaxis_title="Real-Time Factor (RTF)",
            xaxis_type='log',
            showlegend=True
        )

        if output_path:
            fig.write_html(str(output_path))

        return fig


# Convenience functions for common plots
def plot_latency_analysis(data: pd.DataFrame, output_dir: Path) -> list[Path]:
    """Generate standard latency analysis plots."""
    plotter = PerformancePlotter()
    paths = []

    # Latency vs NFFT
    fig = plotter.plot_scaling(
        data, 'engine_nfft', 'mean_latency_us', group_by='engine_channels',
        output_path=output_dir / 'latency_vs_nfft.html'
    )
    paths.append(output_dir / 'latency_vs_nfft.html')

    # Latency heatmap
    if len(data['engine_nfft'].unique()) > 1 and len(data['engine_channels'].unique()) > 1:
        fig = plotter.plot_heatmap(
            data, 'engine_nfft', 'engine_channels', 'mean_latency_us',
            output_path=output_dir / 'latency_heatmap.html'
        )
        paths.append(output_dir / 'latency_heatmap.html')

    return paths


def plot_throughput_analysis(data: pd.DataFrame, output_dir: Path) -> list[Path]:
    """Generate standard throughput analysis plots."""
    plotter = PerformancePlotter()
    paths = []

    # FPS vs Channels
    fig = plotter.plot_scaling(
        data, 'engine_channels', 'frames_per_second', group_by='engine_nfft',
        output_path=output_dir / 'fps_vs_channels.html'
    )
    paths.append(output_dir / 'fps_vs_channels.html')

    # RTF vs Frequency Resolution (if available)
    if 'rtf' in data.columns and 'freq_resolution_hz' in data.columns:
        fig = plotter.plot_rtf_vs_resolution(
            data, output_path=output_dir / 'rtf_vs_freq_resolution.html'
        )
        paths.append(output_dir / 'rtf_vs_freq_resolution.html')

    return paths


def plot_ionosphere_metrics(data: pd.DataFrame, output_dir: Path) -> list[Path]:
    """Generate ionosphere-specific scientific metric plots."""
    plotter = PerformancePlotter()
    paths = []

    # Time Resolution vs Latency
    if 'time_resolution_ms' in data.columns and 'mean_latency_us' in data.columns:
        fig = plotter.plot_scaling(
            data, 'time_resolution_ms', 'mean_latency_us',
            output_path=output_dir / 'time_res_vs_latency.html'
        )
        paths.append(output_dir / 'time_res_vs_latency.html')

    # Frequency Resolution vs NFFT
    if 'freq_resolution_hz' in data.columns:
        fig = plotter.plot_scaling(
            data, 'engine_nfft', 'freq_resolution_hz', log_x=True, log_y=True,
            output_path=output_dir / 'freq_res_vs_nfft.html'
        )
        paths.append(output_dir / 'freq_res_vs_nfft.html')

    return paths


def plot_deadline_compliance(data: pd.DataFrame, output_dir: Path) -> list[Path]:
    """Generate deadline compliance visualizations for streaming benchmarks."""
    if 'deadline_compliance_rate' not in data.columns:
        return []

    plotter = PerformancePlotter()
    paths = []

    # Compliance rate vs NFFT
    if 'engine_nfft' in data.columns:
        fig = go.Figure()

        for nfft in sorted(data['engine_nfft'].unique()):
            nfft_data = data[data['engine_nfft'] == nfft]
            fig.add_trace(go.Bar(
                x=[str(nfft)],
                y=[nfft_data['deadline_compliance_rate'].mean() * 100],
                name=f"NFFT={nfft}",
                error_y=dict(
                    type='data',
                    array=[nfft_data['deadline_compliance_rate'].std() * 100]
                )
            ))

        # Add 99% target line
        fig.add_hline(y=99, line_dash="dash", line_color="red",
                      annotation_text="99% Target")

        fig.update_layout(
            title="Deadline Compliance Rate by NFFT",
            xaxis_title="NFFT Size",
            yaxis_title="Compliance Rate (%)",
            yaxis_range=[95, 100],
            showlegend=True
        )

        output_path = output_dir / 'compliance_vs_nfft.html'
        fig.write_html(str(output_path))
        paths.append(output_path)

    # Compliance rate vs overlap
    if 'engine_overlap' in data.columns:
        fig = plotter.plot_scaling(
            data, 'engine_overlap', 'deadline_compliance_rate',
            output_path=output_dir / 'compliance_vs_overlap.html'
        )
        paths.append(output_dir / 'compliance_vs_overlap.html')

    return paths


def plot_jitter_analysis(data: pd.DataFrame, output_dir: Path) -> list[Path]:
    """Generate jitter analysis visualizations."""
    paths = []

    # Jitter heatmap
    if all(col in data.columns for col in ['engine_nfft', 'engine_overlap', 'mean_jitter_ms']):
        plotter = PerformancePlotter()
        fig = plotter.plot_heatmap(
            data, 'engine_nfft', 'engine_overlap', 'mean_jitter_ms',
            output_path=output_dir / 'jitter_heatmap.html'
        )
        paths.append(output_dir / 'jitter_heatmap.html')

    # Mean vs P99 jitter comparison
    if all(col in data.columns for col in ['mean_jitter_ms', 'p99_jitter_ms']):
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=data['mean_jitter_ms'],
            y=data['p99_jitter_ms'],
            mode='markers',
            marker=dict(size=10, color=data.index, colorscale='Viridis'),
            text=[f"NFFT={row['engine_nfft']}" if 'engine_nfft' in data.columns else ""
                  for _, row in data.iterrows()],
            name="Configurations"
        ))

        # Add diagonal line
        max_val = max(data['mean_jitter_ms'].max(), data['p99_jitter_ms'].max())
        fig.add_trace(go.Scatter(
            x=[0, max_val],
            y=[0, max_val],
            mode='lines',
            line=dict(dash='dash', color='red'),
            name="Mean=P99 line"
        ))

        fig.update_layout(
            title="Mean vs P99 Jitter",
            xaxis_title="Mean Jitter (ms)",
            yaxis_title="P99 Jitter (ms)",
            showlegend=True
        )

        output_path = output_dir / 'jitter_comparison.html'
        fig.write_html(str(output_path))
        paths.append(output_path)

    return paths


def plot_streaming_vs_batch(data: pd.DataFrame, output_dir: Path) -> list[Path]:
    """Generate streaming vs batch mode comparison visualizations."""
    if 'engine_mode' not in data.columns or len(data['engine_mode'].unique()) < 2:
        return []

    paths = []

    # Latency distribution comparison
    if 'mean_latency_us' in data.columns:
        fig = go.Figure()

        for mode in ['streaming', 'batch']:
            mode_data = data[data['engine_mode'] == mode]
            if len(mode_data) > 0:
                fig.add_trace(go.Violin(
                    y=mode_data['mean_latency_us'],
                    name=mode.title(),
                    box_visible=True,
                    meanline_visible=True
                ))

        fig.update_layout(
            title="Latency Distribution: Streaming vs Batch",
            yaxis_title="Latency (μs)",
            showlegend=True
        )

        output_path = output_dir / 'latency_streaming_vs_batch.html'
        fig.write_html(str(output_path))
        paths.append(output_path)

    # Throughput comparison
    if 'frames_per_second' in data.columns:
        fig = go.Figure()

        modes = []
        fps_means = []
        fps_stds = []

        for mode in ['streaming', 'batch']:
            mode_data = data[data['engine_mode'] == mode]
            if len(mode_data) > 0:
                modes.append(mode.title())
                fps_means.append(mode_data['frames_per_second'].mean())
                fps_stds.append(mode_data['frames_per_second'].std())

        fig.add_trace(go.Bar(
            x=modes,
            y=fps_means,
            error_y=dict(type='data', array=fps_stds),
            marker_color=['lightblue', 'lightgreen']
        ))

        fig.update_layout(
            title="Throughput Comparison: Streaming vs Batch",
            yaxis_title="Frames per Second",
            showlegend=False
        )

        output_path = output_dir / 'fps_streaming_vs_batch.html'
        fig.write_html(str(output_path))
        paths.append(output_path)

    return paths


def plot_frame_drop_analysis(data: pd.DataFrame, output_dir: Path) -> list[Path]:
    """Generate frame drop analysis visualizations."""
    if 'frames_dropped' not in data.columns:
        return []

    paths = []
    plotter = PerformancePlotter()

    # Frame drops by configuration
    if 'engine_nfft' in data.columns:
        fig = go.Figure()

        for nfft in sorted(data['engine_nfft'].unique()):
            nfft_data = data[data['engine_nfft'] == nfft]
            fig.add_trace(go.Bar(
                x=[str(nfft)],
                y=[nfft_data['frames_dropped'].sum()],
                name=f"NFFT={nfft}"
            ))

        fig.update_layout(
            title="Total Frame Drops by NFFT",
            xaxis_title="NFFT Size",
            yaxis_title="Total Frames Dropped",
            showlegend=True
        )

        output_path = output_dir / 'frame_drops_by_nfft.html'
        fig.write_html(str(output_path))
        paths.append(output_path)

    return paths


class SpectrogramPlotter:
    """Interactive spectrogram visualization for Streamlit and web dashboards.

    Provides Plotly-based interactive spectrogram plots with:
    - Zoom and pan capabilities
    - Hover tooltips with time/frequency/magnitude
    - Configurable color scales and dB scaling
    - Multiple spectrograms side-by-side comparison
    """

    def __init__(self, config: VisualizationConfig | None = None):
        self.config = config or VisualizationConfig()

    def plot_spectrogram_interactive(
        self,
        spectrogram: Any,  # np.ndarray
        times: Any,  # np.ndarray
        frequencies: Any,  # np.ndarray
        title: str = "Spectrogram",
        db_scale: bool = True,
        vmin: float | None = None,
        vmax: float | None = None,
        colorscale: str = 'Viridis',
        output_path: Path | None = None,
        height: int = 600,
        width: int = 1000
    ) -> go.Figure:
        """Create interactive Plotly spectrogram visualization.

        Args:
            spectrogram: 2D array (time_steps, freq_bins) of magnitude values
            times: 1D array of time values in seconds
            frequencies: 1D array of frequency values in Hz
            title: Plot title
            db_scale: If True, convert to dB scale (20*log10)
            vmin: Minimum value for color scale (None = auto)
            vmax: Maximum value for color scale (None = auto)
            colorscale: Plotly colorscale name (Viridis, Plasma, Jet, etc.)
            output_path: Optional path to save HTML file
            height: Figure height in pixels
            width: Figure width in pixels

        Returns:
            Plotly Figure object
        """
        import numpy as np

        # Convert to dB scale if requested
        if db_scale:
            # Add small epsilon to avoid log(0)
            spec_db = 20 * np.log10(spectrogram + 1e-10)
            z_data = spec_db
            colorbar_title = "Magnitude (dB)"
        else:
            z_data = spectrogram
            colorbar_title = "Magnitude"

        # Create heatmap
        fig = go.Figure(data=go.Heatmap(
            z=z_data.T,  # Transpose so frequency is on y-axis
            x=times,
            y=frequencies,
            colorscale=colorscale,
            zmin=vmin,
            zmax=vmax,
            colorbar=dict(title=colorbar_title),
            hovertemplate='Time: %{x:.3f}s<br>Frequency: %{y:.1f}Hz<br>Magnitude: %{z:.1f}<extra></extra>'
        ))

        # Update layout
        fig.update_layout(
            title=title,
            xaxis_title="Time (s)",
            yaxis_title="Frequency (Hz)",
            height=height,
            width=width,
            hovermode='closest'
        )

        # Save if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fig.write_html(str(output_path))

        return fig

    def plot_spectrogram_comparison(
        self,
        spectrograms: list[dict[str, Any]],
        db_scale: bool = True,
        colorscale: str = 'Viridis',
        output_path: Path | None = None,
        height: int = 400,
        width: int = 1200
    ) -> go.Figure:
        """Create side-by-side comparison of multiple spectrograms.

        Args:
            spectrograms: List of dicts with keys:
                - 'spectrogram': 2D array
                - 'times': 1D array
                - 'frequencies': 1D array
                - 'title': Subplot title
            db_scale: If True, convert to dB scale
            colorscale: Plotly colorscale name
            output_path: Optional path to save HTML file
            height: Figure height in pixels
            width: Figure width in pixels

        Returns:
            Plotly Figure with subplots
        """
        import numpy as np

        num_specs = len(spectrograms)
        if num_specs == 0:
            raise ValueError("No spectrograms provided")

        # Create subplots
        fig = make_subplots(
            rows=1,
            cols=num_specs,
            subplot_titles=[s['title'] for s in spectrograms],
            horizontal_spacing=0.1
        )

        # Add each spectrogram
        for idx, spec_data in enumerate(spectrograms, start=1):
            spectrogram = spec_data['spectrogram']
            times = spec_data['times']
            frequencies = spec_data['frequencies']

            # Convert to dB if requested
            if db_scale:
                z_data = 20 * np.log10(spectrogram + 1e-10)
            else:
                z_data = spectrogram

            fig.add_trace(
                go.Heatmap(
                    z=z_data.T,
                    x=times,
                    y=frequencies,
                    colorscale=colorscale,
                    colorbar=dict(
                        title="Magnitude (dB)" if db_scale else "Magnitude",
                        x=1.0 + (idx - 1) * 0.05  # Offset colorbars
                    ),
                    hovertemplate='Time: %{x:.3f}s<br>Frequency: %{y:.1f}Hz<br>Magnitude: %{z:.1f}<extra></extra>'
                ),
                row=1,
                col=idx
            )

            # Update axes
            fig.update_xaxes(title_text="Time (s)", row=1, col=idx)
            if idx == 1:
                fig.update_yaxes(title_text="Frequency (Hz)", row=1, col=idx)

        # Update layout
        fig.update_layout(
            height=height,
            width=width,
            hovermode='closest'
        )

        # Save if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fig.write_html(str(output_path))

        return fig

    def plot_spectrogram_with_slices(
        self,
        spectrogram: Any,  # np.ndarray
        times: Any,  # np.ndarray
        frequencies: Any,  # np.ndarray
        time_slice_idx: int | None = None,
        freq_slice_idx: int | None = None,
        db_scale: bool = True,
        colorscale: str = 'Viridis',
        output_path: Path | None = None
    ) -> go.Figure:
        """Create spectrogram with time and frequency slice views.

        Shows main spectrogram plus:
        - Frequency spectrum at a specific time
        - Time series at a specific frequency

        Args:
            spectrogram: 2D array (time_steps, freq_bins)
            times: 1D array of time values
            frequencies: 1D array of frequency values
            time_slice_idx: Index for time slice (None = middle)
            freq_slice_idx: Index for frequency slice (None = middle)
            db_scale: If True, convert to dB scale
            colorscale: Plotly colorscale name
            output_path: Optional path to save HTML file

        Returns:
            Plotly Figure with subplots
        """
        import numpy as np

        # Default to middle slices
        if time_slice_idx is None:
            time_slice_idx = len(times) // 2
        if freq_slice_idx is None:
            freq_slice_idx = len(frequencies) // 2

        # Convert to dB if requested
        if db_scale:
            z_data = 20 * np.log10(spectrogram + 1e-10)
            y_label = "Magnitude (dB)"
        else:
            z_data = spectrogram
            y_label = "Magnitude"

        # Create subplots: main spectrogram + 2 slice plots
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                "Spectrogram",
                f"Spectrum at t={times[time_slice_idx]:.3f}s",
                f"Time series at f={frequencies[freq_slice_idx]:.1f}Hz",
                ""
            ),
            specs=[[{"rowspan": 2}, {}], [None, {}]],
            horizontal_spacing=0.15,
            vertical_spacing=0.12
        )

        # Main spectrogram
        fig.add_trace(
            go.Heatmap(
                z=z_data.T,
                x=times,
                y=frequencies,
                colorscale=colorscale,
                colorbar=dict(title=y_label),
                hovertemplate='Time: %{x:.3f}s<br>Frequency: %{y:.1f}Hz<br>Magnitude: %{z:.1f}<extra></extra>'
            ),
            row=1, col=1
        )

        # Frequency spectrum at specific time
        fig.add_trace(
            go.Scatter(
                x=frequencies,
                y=z_data[time_slice_idx, :],
                mode='lines',
                name='Spectrum'
            ),
            row=1, col=2
        )

        # Time series at specific frequency
        fig.add_trace(
            go.Scatter(
                x=times,
                y=z_data[:, freq_slice_idx],
                mode='lines',
                name='Time series',
                line=dict(color='orange')
            ),
            row=2, col=2
        )

        # Update axes
        fig.update_xaxes(title_text="Time (s)", row=1, col=1)
        fig.update_yaxes(title_text="Frequency (Hz)", row=1, col=1)
        fig.update_xaxes(title_text="Frequency (Hz)", row=1, col=2)
        fig.update_yaxes(title_text=y_label, row=1, col=2)
        fig.update_xaxes(title_text="Time (s)", row=2, col=2)
        fig.update_yaxes(title_text=y_label, row=2, col=2)

        # Update layout
        fig.update_layout(
            height=800,
            width=1400,
            showlegend=False
        )

        # Save if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fig.write_html(str(output_path))

        return fig


# Convenience functions for spectrogram visualization
def plot_spectrogram_interactive(
    spectrogram: Any,
    times: Any,
    frequencies: Any,
    title: str = "Spectrogram",
    db_scale: bool = True,
    output_path: Path | None = None,
    **kwargs
) -> go.Figure:
    """Create interactive Plotly spectrogram (convenience function).

    Args:
        spectrogram: 2D array (time_steps, freq_bins)
        times: 1D array of time values in seconds
        frequencies: 1D array of frequency values in Hz
        title: Plot title
        db_scale: If True, convert to dB scale
        output_path: Optional path to save HTML file
        **kwargs: Additional arguments passed to SpectrogramPlotter.plot_spectrogram_interactive()

    Returns:
        Plotly Figure object
    """
    plotter = SpectrogramPlotter()
    return plotter.plot_spectrogram_interactive(
        spectrogram, times, frequencies, title, db_scale, output_path=output_path, **kwargs
    )
