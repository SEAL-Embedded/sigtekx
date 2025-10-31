"""
Visualization Module
====================

Interactive and static plotting for benchmark analysis.
Combines Plotly (interactive) and matplotlib (publication-quality) visualizations.

TODO: Port complete visualization suite from analysis overhaul.
This skeleton provides the basic structure.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

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

    def __init__(self, config: Optional[VisualizationConfig] = None):
        self.config = config or VisualizationConfig()

    def plot_distribution(
        self,
        data: pd.DataFrame,
        metric: str,
        group_by: Optional[str] = None,
        output_path: Optional[Path] = None
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
        output_path: Optional[Path] = None
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

    def __init__(self, config: Optional[VisualizationConfig] = None):
        self.config = config or VisualizationConfig()

    def plot_scaling(
        self,
        data: pd.DataFrame,
        x_col: str,
        y_col: str,
        group_by: Optional[str] = None,
        log_x: bool = False,
        log_y: bool = False,
        output_path: Optional[Path] = None
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
        output_path: Optional[Path] = None
    ) -> go.Figure:
        """Plot 2D heatmap of performance metrics."""
        pivot = data.pivot_table(values=z_col, index=y_col, columns=x_col, aggfunc='mean')

        fig = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale='Viridis',
            colorbar=dict(title=z_col)
        ))

        fig.update_layout(
            title=f"{z_col} Heatmap",
            xaxis_title=x_col,
            yaxis_title=y_col
        )

        # Force categorical y-axis tick labels (prevents interpolation for sparse data)
        # Important for channel counts: shows "2, 16, 32, 128" instead of "50, 100, 150"
        fig.update_yaxis(
            tickmode='array',
            tickvals=list(range(len(pivot.index))),
            ticktext=[str(int(val)) if isinstance(val, (int, float)) else str(val) for val in pivot.index]
        )

        if output_path:
            fig.write_html(str(output_path))

        return fig

    def plot_rtf_vs_resolution(
        self,
        data: pd.DataFrame,
        output_path: Optional[Path] = None
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


class ReportGenerator:
    """Generate HTML reports with embedded visualizations."""

    def __init__(self, config: Optional[VisualizationConfig] = None):
        self.config = config or VisualizationConfig()

    def generate_html_report(
        self,
        title: str,
        sections: List[Dict[str, Any]],
        output_path: Path
    ) -> None:
        """
        Generate HTML report with sections.

        Args:
            title: Report title
            sections: List of dicts with 'title', 'content', 'figure' keys
            output_path: Output file path
        """
        html_parts = [
            f"<!DOCTYPE html>",
            f"<html>",
            f"<head>",
            f"<title>{title}</title>",
            f"<style>",
            f"body {{ font-family: Arial, sans-serif; margin: 40px; }}",
            f"h1 {{ color: #333; }}",
            f"h2 {{ color: #666; margin-top: 30px; }}",
            f".section {{ margin-bottom: 40px; }}",
            f"</style>",
            f"</head>",
            f"<body>",
            f"<h1>{title}</h1>"
        ]

        for section in sections:
            html_parts.append(f"<div class='section'>")
            html_parts.append(f"<h2>{section['title']}</h2>")

            if 'content' in section:
                html_parts.append(f"<p>{section['content']}</p>")

            if 'figure' in section and section['figure']:
                # Embed Plotly figure as HTML
                fig_html = section['figure'].to_html(include_plotlyjs='cdn', full_html=False)
                html_parts.append(fig_html)

            html_parts.append(f"</div>")

        html_parts.extend([
            f"</body>",
            f"</html>"
        ])

        output_path.write_text('\n'.join(html_parts), encoding='utf-8')


# Convenience functions for common plots
def plot_latency_analysis(data: pd.DataFrame, output_dir: Path) -> List[Path]:
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


def plot_throughput_analysis(data: pd.DataFrame, output_dir: Path) -> List[Path]:
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


def plot_ionosphere_metrics(data: pd.DataFrame, output_dir: Path) -> List[Path]:
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


def plot_deadline_compliance(data: pd.DataFrame, output_dir: Path) -> List[Path]:
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


def plot_jitter_analysis(data: pd.DataFrame, output_dir: Path) -> List[Path]:
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


def plot_streaming_vs_batch(data: pd.DataFrame, output_dir: Path) -> List[Path]:
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


def plot_frame_drop_analysis(data: pd.DataFrame, output_dir: Path) -> List[Path]:
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
