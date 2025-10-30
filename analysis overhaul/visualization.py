"""
Enhanced Visualization Module
=============================

Advanced plotting capabilities for GPU benchmark analysis with
interactive plots, statistical overlays, and publication-quality output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import seaborn as sns
from scipy import stats

from .models import (
    BenchmarkType,
    ComparisonResult,
    ExperimentSummary,
    ScalingAnalysis,
    StatisticalMetrics,
)


class VisualizationConfig:
    """Configuration for visualization appearance."""
    
    # Color schemes
    COLORS = {
        'latency': '#FF6B6B',      # Red
        'throughput': '#4ECDC4',   # Teal
        'accuracy': '#45B7D1',     # Blue
        'realtime': '#96CEB4',     # Green
        'memory': '#FECA57',       # Yellow
        'power': '#DDA0DD',        # Plum
    }
    
    # Style settings
    FIGURE_DPI = 150
    FIGURE_SIZE = (12, 8)
    FONT_SIZE = 12
    
    # Statistical visualization
    SHOW_CONFIDENCE_INTERVALS = True
    SHOW_OUTLIERS = True
    SHOW_TREND_LINES = True
    
    def __init__(self):
        self._setup_matplotlib()
        self._setup_seaborn()
    
    def _setup_matplotlib(self):
        """Configure matplotlib for publication quality."""
        plt.rcParams.update({
            'figure.dpi': self.FIGURE_DPI,
            'savefig.dpi': self.FIGURE_DPI,
            'font.size': self.FONT_SIZE,
            'axes.titlesize': self.FONT_SIZE + 2,
            'axes.labelsize': self.FONT_SIZE,
            'xtick.labelsize': self.FONT_SIZE - 1,
            'ytick.labelsize': self.FONT_SIZE - 1,
            'legend.fontsize': self.FONT_SIZE - 1,
            'figure.titlesize': self.FONT_SIZE + 4,
            'lines.linewidth': 2,
            'lines.markersize': 8,
        })
    
    def _setup_seaborn(self):
        """Configure seaborn style."""
        sns.set_style("whitegrid")
        sns.set_context("notebook")


class StatisticalPlotter:
    """Specialized plotter for statistical visualizations."""
    
    @staticmethod
    def plot_distribution_comparison(
        data1: np.ndarray,
        data2: np.ndarray,
        labels: Tuple[str, str],
        title: str = "Distribution Comparison"
    ) -> go.Figure:
        """Create interactive distribution comparison plot."""
        
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Distributions', 'Q-Q Plot', 'Box Plots', 'Violin Plots'),
            specs=[[{'type': 'histogram'}, {'type': 'scatter'}],
                   [{'type': 'box'}, {'type': 'violin'}]]
        )
        
        # Histograms
        fig.add_trace(
            go.Histogram(x=data1, name=labels[0], opacity=0.7, nbinsx=30),
            row=1, col=1
        )
        fig.add_trace(
            go.Histogram(x=data2, name=labels[1], opacity=0.7, nbinsx=30),
            row=1, col=1
        )
        
        # Q-Q Plot
        quantiles = np.percentile(data1, np.linspace(0, 100, 100))
        quantiles2 = np.percentile(data2, np.linspace(0, 100, 100))
        fig.add_trace(
            go.Scatter(x=quantiles, y=quantiles2, mode='markers', name='Q-Q',
                      marker=dict(size=5)),
            row=1, col=2
        )
        # Add diagonal reference line
        min_val = min(quantiles.min(), quantiles2.min())
        max_val = max(quantiles.max(), quantiles2.max())
        fig.add_trace(
            go.Scatter(x=[min_val, max_val], y=[min_val, max_val],
                      mode='lines', line=dict(dash='dash'),
                      name='y=x', showlegend=False),
            row=1, col=2
        )
        
        # Box plots
        fig.add_trace(
            go.Box(y=data1, name=labels[0], boxpoints='outliers'),
            row=2, col=1
        )
        fig.add_trace(
            go.Box(y=data2, name=labels[1], boxpoints='outliers'),
            row=2, col=1
        )
        
        # Violin plots
        fig.add_trace(
            go.Violin(y=data1, name=labels[0], box_visible=True, meanline_visible=True),
            row=2, col=2
        )
        fig.add_trace(
            go.Violin(y=data2, name=labels[1], box_visible=True, meanline_visible=True),
            row=2, col=2
        )
        
        fig.update_layout(
            title=title,
            height=800,
            showlegend=True,
            barmode='overlay'
        )
        
        # Update axes labels
        fig.update_xaxes(title_text="Value", row=1, col=1)
        fig.update_xaxes(title_text=labels[0], row=1, col=2)
        fig.update_yaxes(title_text="Count", row=1, col=1)
        fig.update_yaxes(title_text=labels[1], row=1, col=2)
        
        return fig
    
    @staticmethod
    def plot_confidence_intervals(
        groups: Dict[str, StatisticalMetrics],
        metric_name: str = "Metric"
    ) -> go.Figure:
        """Plot means with confidence intervals."""
        
        labels = list(groups.keys())
        means = [g.mean for g in groups.values()]
        ci_lower = [g.confidence_interval[0] for g in groups.values()]
        ci_upper = [g.confidence_interval[1] for g in groups.values()]
        
        fig = go.Figure()
        
        # Add confidence interval as error bars
        fig.add_trace(go.Scatter(
            x=labels,
            y=means,
            error_y=dict(
                type='data',
                symmetric=False,
                array=[u - m for u, m in zip(ci_upper, means)],
                arrayminus=[m - l for m, l in zip(means, ci_lower)],
                width=10,
                thickness=2
            ),
            mode='markers',
            marker=dict(size=12, color='#3498db'),
            name='Mean ± 95% CI'
        ))
        
        # Add median as reference
        medians = [g.median for g in groups.values()]
        fig.add_trace(go.Scatter(
            x=labels,
            y=medians,
            mode='markers',
            marker=dict(size=8, color='#e74c3c', symbol='diamond'),
            name='Median'
        ))
        
        fig.update_layout(
            title=f"{metric_name} with Confidence Intervals",
            xaxis_title="Configuration",
            yaxis_title=metric_name,
            height=500
        )
        
        return fig


class PerformancePlotter:
    """Performance-specific visualizations."""
    
    @staticmethod
    def plot_scaling_analysis(scaling: ScalingAnalysis) -> go.Figure:
        """Visualize scaling patterns with model fit."""
        
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                'Scaling Pattern',
                'Log-Log Plot', 
                'Efficiency',
                'Residuals'
            )
        )
        
        values = np.array(scaling.values)
        metrics = np.array(scaling.metrics)
        
        # Compute model predictions
        model_metrics = scaling.model_params['coefficient'] * values ** scaling.model_params['exponent']
        
        # 1. Main scaling plot
        fig.add_trace(
            go.Scatter(x=values, y=metrics, mode='markers',
                      name='Observed', marker=dict(size=10)),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=values, y=model_metrics, mode='lines',
                      name=f'Model (R²={scaling.model_r2:.3f})',
                      line=dict(dash='dash')),
            row=1, col=1
        )
        
        # 2. Log-log plot
        fig.add_trace(
            go.Scatter(x=np.log(values), y=np.log(metrics),
                      mode='markers', name='Log data',
                      marker=dict(size=8)),
            row=1, col=2
        )
        # Add fitted line
        log_fit = scaling.scaling_exponent * np.log(values) + np.log(scaling.model_params['coefficient'])
        fig.add_trace(
            go.Scatter(x=np.log(values), y=log_fit,
                      mode='lines', name=f'Slope={scaling.scaling_exponent:.2f}',
                      line=dict(dash='dot')),
            row=1, col=2
        )
        
        # 3. Efficiency plot
        fig.add_trace(
            go.Scatter(x=values, y=scaling.ideal_scaling_efficiency,
                      mode='lines+markers', name='Scaling Efficiency',
                      marker=dict(size=8)),
            row=2, col=1
        )
        fig.add_hline(y=1.0, row=2, col=1, line_dash="dash", 
                     line_color="gray", annotation_text="Ideal")
        
        # 4. Residuals
        residuals = metrics - model_metrics
        fig.add_trace(
            go.Scatter(x=values, y=residuals,
                      mode='markers', name='Residuals',
                      marker=dict(size=8)),
            row=2, col=2
        )
        fig.add_hline(y=0, row=2, col=2, line_dash="solid", line_color="gray")
        
        # Update layout
        fig.update_layout(
            title=f"Scaling Analysis: {scaling.parameter} ({scaling.scaling_type})",
            height=800,
            showlegend=True
        )
        
        # Update axes
        fig.update_xaxes(title_text=scaling.parameter, row=1, col=1)
        fig.update_xaxes(title_text=f"log({scaling.parameter})", row=1, col=2)
        fig.update_xaxes(title_text=scaling.parameter, row=2, col=1)
        fig.update_xaxes(title_text=scaling.parameter, row=2, col=2)
        
        fig.update_yaxes(title_text="Metric", row=1, col=1)
        fig.update_yaxes(title_text="log(Metric)", row=1, col=2)
        fig.update_yaxes(title_text="Efficiency", row=2, col=1)
        fig.update_yaxes(title_text="Residual", row=2, col=2)
        
        # Add saturation point if exists
        if scaling.saturation_point:
            fig.add_vline(x=scaling.saturation_point, row=1, col=1,
                         line_dash="dash", line_color="red",
                         annotation_text="Saturation")
        
        return fig
    
    @staticmethod
    def plot_latency_breakdown(data: pd.DataFrame) -> go.Figure:
        """Detailed latency analysis plot."""
        
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                'Latency Distribution by Config',
                'Tail Latency Analysis',
                'Jitter Analysis',
                'Latency Heatmap'
            )
        )
        
        configs = data.groupby(['engine_nfft', 'engine_channels'])
        
        # 1. Distribution by config
        for (nfft, channels), group in configs:
            if 'mean_latency_us' in group.columns:
                fig.add_trace(
                    go.Box(y=group['mean_latency_us'],
                          name=f"{nfft}x{channels}",
                          boxpoints='outliers'),
                    row=1, col=1
                )
        
        # 2. Tail latency
        if 'p95_latency_us' in data.columns and 'mean_latency_us' in data.columns:
            fig.add_trace(
                go.Scatter(x=data['mean_latency_us'],
                          y=data['p95_latency_us'],
                          mode='markers',
                          marker=dict(size=8,
                                    color=data['engine_nfft'],
                                    colorscale='Viridis',
                                    showscale=True,
                                    colorbar=dict(title="NFFT")),
                          name='P95 vs Mean'),
                row=1, col=2
            )
            # Add reference line for y=x
            max_val = max(data['mean_latency_us'].max(), data['p95_latency_us'].max())
            fig.add_trace(
                go.Scatter(x=[0, max_val], y=[0, max_val],
                          mode='lines', line=dict(dash='dash'),
                          name='y=x', showlegend=False),
                row=1, col=2
            )
        
        # 3. Jitter analysis (if we have time series data)
        # For now, show CV by configuration
        cv_data = []
        for (nfft, channels), group in configs:
            if 'mean_latency_us' in group.columns and len(group) > 1:
                cv = group['mean_latency_us'].std() / group['mean_latency_us'].mean()
                cv_data.append({
                    'config': f"{nfft}x{channels}",
                    'cv': cv,
                    'nfft': nfft
                })
        
        if cv_data:
            cv_df = pd.DataFrame(cv_data)
            fig.add_trace(
                go.Bar(x=cv_df['config'], y=cv_df['cv'],
                      marker=dict(color=cv_df['nfft'],
                                colorscale='RdYlGn_r'),
                      name='CV'),
                row=2, col=1
            )
        
        # 4. Heatmap
        if 'mean_latency_us' in data.columns:
            pivot = data.pivot_table(
                values='mean_latency_us',
                index='engine_nfft',
                columns='engine_channels',
                aggfunc='mean'
            )
            fig.add_trace(
                go.Heatmap(z=pivot.values,
                          x=pivot.columns,
                          y=pivot.index,
                          colorscale='RdYlGn_r',
                          text=np.round(pivot.values, 1),
                          texttemplate='%{text}',
                          textfont={"size": 10}),
                row=2, col=2
            )
        
        fig.update_layout(
            title="Latency Performance Analysis",
            height=800,
            showlegend=True
        )
        
        # Update axes
        fig.update_xaxes(title_text="Configuration", row=1, col=1)
        fig.update_yaxes(title_text="Latency (μs)", row=1, col=1)
        fig.update_xaxes(title_text="Mean Latency (μs)", row=1, col=2)
        fig.update_yaxes(title_text="P95 Latency (μs)", row=1, col=2)
        fig.update_xaxes(title_text="Configuration", row=2, col=1)
        fig.update_yaxes(title_text="Coefficient of Variation", row=2, col=1)
        fig.update_xaxes(title_text="Channels", row=2, col=2)
        fig.update_yaxes(title_text="NFFT", row=2, col=2)
        
        return fig
    
    @staticmethod
    def plot_throughput_analysis(data: pd.DataFrame) -> go.Figure:
        """Comprehensive throughput visualization."""
        
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                'Throughput Scaling',
                'Memory Bandwidth Utilization',
                'GPU Efficiency',
                'Performance Surface'
            ),
            specs=[[{'type': 'scatter'}, {'type': 'scatter'}],
                   [{'type': 'scatter'}, {'type': 'surface'}]]
        )
        
        # 1. Throughput scaling
        if 'frames_per_second' in data.columns:
            for nfft in data['engine_nfft'].unique():
                subset = data[data['engine_nfft'] == nfft]
                fig.add_trace(
                    go.Scatter(x=subset['engine_channels'],
                              y=subset['frames_per_second'],
                              mode='lines+markers',
                              name=f'NFFT={nfft}'),
                    row=1, col=1
                )
        
        # 2. Memory bandwidth
        if 'gb_per_second' in data.columns:
            fig.add_trace(
                go.Scatter(x=data['engine_nfft'] * data['engine_channels'],
                          y=data['gb_per_second'],
                          mode='markers',
                          marker=dict(size=10,
                                    color=data['frames_per_second'],
                                    colorscale='Viridis',
                                    showscale=True,
                                    colorbar=dict(title="FPS")),
                          name='Bandwidth'),
                row=1, col=2
            )
            # Add theoretical limit line
            fig.add_hline(y=936.2, row=1, col=2, line_dash="dash",
                         line_color="red",
                         annotation_text="Theoretical Max (936.2 GB/s)")
        
        # 3. GPU utilization/efficiency
        if 'gpu_utilization' in data.columns:
            fig.add_trace(
                go.Scatter(x=data['frames_per_second'],
                          y=data['gpu_utilization'],
                          mode='markers',
                          marker=dict(size=10,
                                    color=data['engine_nfft'],
                                    colorscale='Plasma'),
                          name='GPU Util'),
                row=2, col=1
            )
        
        # 4. 3D surface plot
        if 'frames_per_second' in data.columns:
            pivot = data.pivot_table(
                values='frames_per_second',
                index='engine_nfft',
                columns='engine_channels',
                aggfunc='mean'
            )
            
            fig.add_trace(
                go.Surface(x=pivot.columns,
                          y=pivot.index,
                          z=pivot.values,
                          colorscale='Viridis',
                          name='FPS Surface'),
                row=2, col=2
            )
        
        fig.update_layout(
            title="Throughput Performance Analysis",
            height=900,
            showlegend=True
        )
        
        # Update axes
        fig.update_xaxes(title_text="Channels", row=1, col=1)
        fig.update_yaxes(title_text="Frames/Second", row=1, col=1)
        fig.update_xaxes(title_text="Total Samples", row=1, col=2)
        fig.update_yaxes(title_text="GB/Second", row=1, col=2)
        fig.update_xaxes(title_text="Frames/Second", row=2, col=1)
        fig.update_yaxes(title_text="GPU Utilization (%)", row=2, col=1)
        
        # Update 3D axes
        fig.update_scenes(
            xaxis_title="Channels",
            yaxis_title="NFFT",
            zaxis_title="FPS",
            row=2, col=2
        )
        
        return fig


class ReportGenerator:
    """Generate comprehensive HTML reports."""
    
    def __init__(self, config: Optional[VisualizationConfig] = None):
        self.config = config or VisualizationConfig()
        self.stat_plotter = StatisticalPlotter()
        self.perf_plotter = PerformancePlotter()
    
    def generate_full_report(
        self,
        summary: ExperimentSummary,
        output_path: Path,
        include_raw_data: bool = False
    ) -> None:
        """Generate complete HTML report with all visualizations."""
        
        from plotly.subplots import make_subplots
        import plotly.offline as pyo
        
        # Create HTML sections
        html_sections = []
        
        # Header
        html_sections.append(f"""
        <html>
        <head>
            <title>{summary.experiment_name} - Analysis Report</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #34495e; margin-top: 30px; }}
                h3 {{ color: #7f8c8d; }}
                .summary {{ background: #ecf0f1; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                .insight {{ background: #e8f8f5; padding: 15px; border-left: 4px solid #27ae60; margin: 10px 0; }}
                .warning {{ background: #fef5e7; padding: 15px; border-left: 4px solid #f39c12; margin: 10px 0; }}
                .metric {{ display: inline-block; margin: 10px 20px; }}
                .metric-value {{ font-size: 24px; font-weight: bold; color: #2980b9; }}
                .metric-label {{ color: #7f8c8d; font-size: 14px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #3498db; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
        """)
        
        # Title and metadata
        html_sections.append(f"""
        <h1>{summary.experiment_name}</h1>
        <div class="summary">
            <p><strong>Generated:</strong> {summary.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>Total Measurements:</strong> {summary.total_measurements}</p>
            <p><strong>Benchmark Types:</strong> {', '.join(bt.value for bt in summary.benchmark_types)}</p>
            <p><strong>Configurations Tested:</strong> {len(summary.configurations_tested)}</p>
        </div>
        """)
        
        # Key insights
        if summary.key_insights:
            html_sections.append("<h2>Key Insights</h2>")
            for insight in summary.key_insights:
                html_sections.append(f'<div class="insight">{insight}</div>')
        
        # Warnings
        if summary.warnings:
            html_sections.append("<h2>Warnings</h2>")
            for warning in summary.warnings:
                html_sections.append(f'<div class="warning">{warning}</div>')
        
        # Optimal configurations
        if summary.optimal_configs:
            html_sections.append("<h2>Optimal Configurations</h2>")
            html_sections.append("<table>")
            html_sections.append("<tr><th>Benchmark</th><th>NFFT</th><th>Channels</th><th>Memory (MB)</th></tr>")
            for bench_type, config in summary.optimal_configs.items():
                html_sections.append(f"""
                <tr>
                    <td>{bench_type}</td>
                    <td>{config.nfft}</td>
                    <td>{config.channels}</td>
                    <td>{config.memory_footprint_mb:.1f}</td>
                </tr>
                """)
            html_sections.append("</table>")
        
        # Generate visualizations
        html_sections.append("<h2>Performance Visualizations</h2>")
        
        # Convert summary to DataFrame for plotting
        df = summary.to_dataframe()
        
        # Latency analysis
        if BenchmarkType.LATENCY in summary.benchmark_types:
            latency_data = df[df['benchmark_type'] == BenchmarkType.LATENCY]
            if not latency_data.empty:
                fig = self.perf_plotter.plot_latency_breakdown(latency_data)
                html_sections.append(pyo.plot(fig, output_type='div', include_plotlyjs=False))
        
        # Throughput analysis
        if BenchmarkType.THROUGHPUT in summary.benchmark_types:
            throughput_data = df[df['benchmark_type'] == BenchmarkType.THROUGHPUT]
            if not throughput_data.empty:
                fig = self.perf_plotter.plot_throughput_analysis(throughput_data)
                html_sections.append(pyo.plot(fig, output_type='div', include_plotlyjs=False))
        
        # Scaling analyses
        if summary.scaling_analyses:
            html_sections.append("<h2>Scaling Analysis</h2>")
            for analysis in summary.scaling_analyses[:3]:  # Limit to top 3
                fig = self.perf_plotter.plot_scaling_analysis(analysis)
                html_sections.append(pyo.plot(fig, output_type='div', include_plotlyjs=False))
        
        # Statistical comparisons
        if summary.comparisons:
            html_sections.append("<h2>Statistical Comparisons</h2>")
            html_sections.append("<table>")
            html_sections.append("""
            <tr>
                <th>Comparison</th>
                <th>Mean Diff (%)</th>
                <th>P-Value</th>
                <th>Significant</th>
                <th>Effect Size</th>
            </tr>
            """)
            for comp in summary.comparisons:
                sig_marker = "✓" if comp.is_significant else "✗"
                html_sections.append(f"""
                <tr>
                    <td>{comp.name}</td>
                    <td>{comp.mean_diff_pct:.1f}%</td>
                    <td>{comp.p_value:.4f}</td>
                    <td>{sig_marker}</td>
                    <td>{comp.effect_size:.3f}</td>
                </tr>
                """)
            html_sections.append("</table>")
        
        # Include Plotly JS
        html_sections.insert(2, '<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>')
        
        # Footer
        html_sections.append("""
        </body>
        </html>
        """)
        
        # Write report
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write('\n'.join(html_sections))
        
        print(f"Report generated: {output_path}")
