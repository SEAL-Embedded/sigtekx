"""
Report Generation
=================

Generate HTML reports for benchmark analysis.
Supports both general performance reports and ionosphere-specific reports.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .metrics import assess_ionosphere_suitability
from .visualization import (
    PerformancePlotter,
    ReportGenerator,
    StatisticalPlotter,
    VisualizationConfig,
)


class GeneralPerformanceReport:
    """Generate general performance report for all benchmarks."""

    def __init__(self, config: Optional[VisualizationConfig] = None):
        self.config = config or VisualizationConfig()
        self.report_gen = ReportGenerator(self.config)
        self.perf_plotter = PerformancePlotter(self.config)
        self.stat_plotter = StatisticalPlotter(self.config)

    def generate(
        self,
        data: pd.DataFrame,
        output_path: Path,
        title: str = "General Performance Report"
    ) -> None:
        """
        Generate comprehensive performance report.

        Args:
            data: Combined benchmark data
            output_path: Output HTML file path
            title: Report title
        """
        sections = []

        # Executive Summary
        sections.append({
            'title': 'Executive Summary',
            'content': self._generate_summary(data)
        })

        # Throughput Analysis
        if 'throughput' in data['benchmark_type'].values:
            throughput_data = data[data['benchmark_type'] == 'throughput']
            sections.append({
                'title': 'Throughput Analysis',
                'content': self._generate_throughput_analysis(throughput_data),
                'figure': self._plot_throughput_scaling(throughput_data)
            })

        # Latency Analysis
        if 'latency' in data['benchmark_type'].values:
            latency_data = data[data['benchmark_type'] == 'latency']
            sections.append({
                'title': 'Latency Analysis',
                'content': self._generate_latency_analysis(latency_data),
                'figure': self._plot_latency_scaling(latency_data)
            })

        # Accuracy Analysis
        if 'accuracy' in data['benchmark_type'].values:
            accuracy_data = data[data['benchmark_type'] == 'accuracy']
            sections.append({
                'title': 'Accuracy Analysis',
                'content': self._generate_accuracy_analysis(accuracy_data)
            })

        # Scaling Analysis
        sections.append({
            'title': 'Scaling Analysis',
            'content': self._generate_scaling_analysis(data),
            'figure': self._plot_parameter_heatmap(data)
        })

        # Configuration Recommendations
        sections.append({
            'title': 'Configuration Recommendations',
            'content': self._generate_recommendations(data)
        })

        self.report_gen.generate_html_report(title, sections, output_path)

    def _generate_summary(self, data: pd.DataFrame) -> str:
        """Generate executive summary text."""
        num_configs = len(data.groupby(['engine_nfft', 'engine_channels']))
        num_measurements = len(data)
        benchmark_types = data['benchmark_type'].nunique()

        summary = f"""
        <p><strong>Report Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Total Measurements:</strong> {num_measurements}</p>
        <p><strong>Configurations Tested:</strong> {num_configs}</p>
        <p><strong>Benchmark Types:</strong> {benchmark_types}</p>
        <br>
        """

        # Best performances
        if 'throughput' in data['benchmark_type'].values:
            throughput_data = data[data['benchmark_type'] == 'throughput']
            if 'frames_per_second' in throughput_data.columns:
                max_fps_idx = throughput_data['frames_per_second'].idxmax()
                best_row = throughput_data.loc[max_fps_idx]
                summary += f"""
                <p><strong>Peak Throughput:</strong> {best_row['frames_per_second']:.1f} FPS
                (NFFT={int(best_row['engine_nfft'])}, Channels={int(best_row['engine_channels'])})</p>
                """

        if 'latency' in data['benchmark_type'].values:
            latency_data = data[data['benchmark_type'] == 'latency']
            if 'mean_latency_us' in latency_data.columns:
                min_lat_idx = latency_data['mean_latency_us'].idxmin()
                best_row = latency_data.loc[min_lat_idx]
                summary += f"""
                <p><strong>Lowest Latency:</strong> {best_row['mean_latency_us']:.1f} μs
                (NFFT={int(best_row['engine_nfft'])}, Channels={int(best_row['engine_channels'])})</p>
                """

        return summary

    def _generate_throughput_analysis(self, data: pd.DataFrame) -> str:
        """Generate throughput analysis content."""
        if 'frames_per_second' not in data.columns:
            return "<p>No FPS data available</p>"

        fps_stats = data['frames_per_second'].describe()

        analysis = f"""
        <h3>Throughput Statistics</h3>
        <ul>
            <li><strong>Mean FPS:</strong> {fps_stats['mean']:.1f}</li>
            <li><strong>Median FPS:</strong> {fps_stats['50%']:.1f}</li>
            <li><strong>Max FPS:</strong> {fps_stats['max']:.1f}</li>
            <li><strong>Standard Deviation:</strong> {fps_stats['std']:.1f}</li>
        </ul>
        """

        # GB/s if available
        if 'gb_per_second' in data.columns:
            gb_stats = data['gb_per_second'].describe()
            analysis += f"""
            <h3>Data Throughput</h3>
            <ul>
                <li><strong>Mean:</strong> {gb_stats['mean']:.2f} GB/s</li>
                <li><strong>Max:</strong> {gb_stats['max']:.2f} GB/s</li>
            </ul>
            """

        return analysis

    def _generate_latency_analysis(self, data: pd.DataFrame) -> str:
        """Generate latency analysis content."""
        if 'mean_latency_us' not in data.columns:
            return "<p>No latency data available</p>"

        lat_stats = data['mean_latency_us'].describe()

        analysis = f"""
        <h3>Latency Statistics</h3>
        <ul>
            <li><strong>Mean Latency:</strong> {lat_stats['mean']:.1f} μs</li>
            <li><strong>Median Latency:</strong> {lat_stats['50%']:.1f} μs</li>
            <li><strong>Min Latency:</strong> {lat_stats['min']:.1f} μs</li>
            <li><strong>P95 Latency:</strong> {lat_stats['75%']:.1f} μs</li>
        </ul>
        """

        return analysis

    def _generate_accuracy_analysis(self, data: pd.DataFrame) -> str:
        """Generate accuracy analysis content."""
        if 'pass_rate' not in data.columns:
            return "<p>No accuracy data available</p>"

        pass_rate_stats = data['pass_rate'].describe()

        analysis = f"""
        <h3>Accuracy Statistics</h3>
        <ul>
            <li><strong>Mean Pass Rate:</strong> {pass_rate_stats['mean']*100:.1f}%</li>
            <li><strong>Min Pass Rate:</strong> {pass_rate_stats['min']*100:.1f}%</li>
        </ul>
        """

        return analysis

    def _generate_scaling_analysis(self, data: pd.DataFrame) -> str:
        """Generate scaling analysis content."""
        analysis = "<h3>Parameter Space Coverage</h3>"

        nfft_range = data['engine_nfft'].unique()
        channel_range = data['engine_channels'].unique()

        analysis += f"""
        <ul>
            <li><strong>NFFT Range:</strong> {min(nfft_range)} - {max(nfft_range)}</li>
            <li><strong>Channel Counts:</strong> {sorted(channel_range)}</li>
        </ul>
        """

        return analysis

    def _generate_recommendations(self, data: pd.DataFrame) -> str:
        """Generate configuration recommendations."""
        recommendations = "<h3>Optimal Configurations by Use Case</h3>"

        # Throughput-optimized
        if 'throughput' in data['benchmark_type'].values:
            throughput_data = data[data['benchmark_type'] == 'throughput']
            if 'frames_per_second' in throughput_data.columns:
                max_fps_idx = throughput_data['frames_per_second'].idxmax()
                best = throughput_data.loc[max_fps_idx]
                recommendations += f"""
                <p><strong>For Maximum Throughput:</strong></p>
                <ul>
                    <li>NFFT: {int(best['engine_nfft'])}</li>
                    <li>Channels: {int(best['engine_channels'])}</li>
                    <li>Performance: {best['frames_per_second']:.1f} FPS</li>
                </ul>
                """

        # Latency-optimized
        if 'latency' in data['benchmark_type'].values:
            latency_data = data[data['benchmark_type'] == 'latency']
            if 'mean_latency_us' in latency_data.columns:
                min_lat_idx = latency_data['mean_latency_us'].idxmin()
                best = latency_data.loc[min_lat_idx]
                recommendations += f"""
                <p><strong>For Minimum Latency:</strong></p>
                <ul>
                    <li>NFFT: {int(best['engine_nfft'])}</li>
                    <li>Channels: {int(best['engine_channels'])}</li>
                    <li>Performance: {best['mean_latency_us']:.1f} μs</li>
                </ul>
                """

        return recommendations

    def _plot_throughput_scaling(self, data: pd.DataFrame):
        """Create throughput scaling plot."""
        if 'frames_per_second' not in data.columns:
            return None

        return self.perf_plotter.plot_scaling(
            data, 'engine_nfft', 'frames_per_second',
            group_by='engine_channels', log_x=True
        )

    def _plot_latency_scaling(self, data: pd.DataFrame):
        """Create latency scaling plot."""
        if 'mean_latency_us' not in data.columns:
            return None

        return self.perf_plotter.plot_scaling(
            data, 'engine_nfft', 'mean_latency_us',
            group_by='engine_channels', log_x=True
        )

    def _plot_parameter_heatmap(self, data: pd.DataFrame):
        """Create parameter space heatmap."""
        # Use throughput data if available
        if 'throughput' in data['benchmark_type'].values:
            throughput_data = data[data['benchmark_type'] == 'throughput']
            if 'frames_per_second' in throughput_data.columns:
                return self.perf_plotter.plot_heatmap(
                    throughput_data, 'engine_nfft', 'engine_channels', 'frames_per_second'
                )

        return None


class IonosphereReport:
    """Generate ionosphere research-specific report."""

    def __init__(self, config: Optional[VisualizationConfig] = None):
        self.config = config or VisualizationConfig()
        self.report_gen = ReportGenerator(self.config)
        self.perf_plotter = PerformancePlotter(self.config)

    def generate(
        self,
        data: pd.DataFrame,
        output_path: Path,
        title: str = "Ionosphere Research Report"
    ) -> None:
        """
        Generate ionosphere-focused report.

        Args:
            data: Combined benchmark data with scientific metrics
            output_path: Output HTML file path
            title: Report title
        """
        sections = []

        # Introduction
        sections.append({
            'title': 'Introduction',
            'content': self._generate_introduction()
        })

        # Scientific Metrics Overview
        sections.append({
            'title': 'Scientific Metrics Overview',
            'content': self._generate_metrics_overview(data)
        })

        # Real-Time Factor Analysis
        if 'rtf' in data.columns:
            sections.append({
                'title': 'Real-Time Factor Analysis',
                'content': self._generate_rtf_analysis(data),
                'figure': self._plot_rtf_analysis(data)
            })

        # Time/Frequency Resolution Trade-offs
        if 'time_resolution_ms' in data.columns and 'freq_resolution_hz' in data.columns:
            sections.append({
                'title': 'Time/Frequency Resolution Trade-offs',
                'content': self._generate_resolution_tradeoffs(data),
                'figure': self._plot_resolution_tradeoffs(data)
            })

        # Phenomena Detection Suitability
        sections.append({
            'title': 'Phenomena Detection Suitability',
            'content': self._generate_phenomena_suitability(data)
        })

        # Multi-Channel Performance
        if len(data['engine_channels'].unique()) > 1:
            sections.append({
                'title': 'Multi-Channel Performance',
                'content': self._generate_multichannel_analysis(data)
            })

        # High-NFFT/High-Overlap Performance
        sections.append({
            'title': 'High-Resolution Configuration Analysis',
            'content': self._generate_highres_analysis(data)
        })

        # Computational Performance Context
        sections.append({
            'title': 'Computational Performance Summary',
            'content': self._generate_performance_context(data)
        })

        self.report_gen.generate_html_report(title, sections, output_path)

    def _generate_introduction(self) -> str:
        """Generate introduction text."""
        return """
        <p>This report analyzes GPU benchmark results in the context of VLF/ULF ionosphere research.</p>

        <p>The ionosense system is designed for real-time monitoring of ionospheric phenomena including:</p>
        <ul>
            <li><strong>Lightning and sprites:</strong> Fast transients (&lt;10ms time resolution required)</li>
            <li><strong>Sudden Ionospheric Disturbances (SIDs):</strong> Long-duration events requiring high frequency resolution</li>
            <li><strong>Schumann resonances:</strong> ~8Hz, 14Hz, 20Hz peaks requiring &lt;1Hz frequency resolution</li>
            <li><strong>Whistlers:</strong> Dispersive signals requiring both time and frequency resolution</li>
        </ul>

        <p><strong>Key Research Considerations:</strong></p>
        <ul>
            <li><strong>Time Resolution:</strong> Ability to capture fast transients and temporal evolution</li>
            <li><strong>Frequency Resolution:</strong> Spectral detail for phenomenon identification and characterization</li>
            <li><strong>Real-Time Factor (RTF):</strong> Processing capability for live monitoring (RTF &gt; 1.0 required)</li>
            <li><strong>Multi-Channel Support:</strong> Direction finding and polarization analysis capabilities</li>
        </ul>
        """

    def _generate_metrics_overview(self, data: pd.DataFrame) -> str:
        """Generate scientific metrics overview."""
        overview = "<h3>Parameter Ranges Tested</h3><ul>"

        if 'time_resolution_ms' in data.columns:
            time_res_range = f"{data['time_resolution_ms'].min():.2f} - {data['time_resolution_ms'].max():.2f} ms"
            overview += f"<li><strong>Time Resolution:</strong> {time_res_range}</li>"

        if 'freq_resolution_hz' in data.columns:
            freq_res_range = f"{data['freq_resolution_hz'].min():.3f} - {data['freq_resolution_hz'].max():.3f} Hz"
            overview += f"<li><strong>Frequency Resolution:</strong> {freq_res_range}</li>"

        if 'rtf' in data.columns:
            rtf_range = f"{data['rtf'].min():.2f} - {data['rtf'].max():.2f}"
            overview += f"<li><strong>Real-Time Factor:</strong> {rtf_range}</li>"

        if 'engine_overlap' in data.columns:
            overlap_range = data['engine_overlap'].unique()
            overview += f"<li><strong>Overlap Factors:</strong> {sorted(overlap_range)}</li>"

        overview += "</ul>"
        return overview

    def _generate_rtf_analysis(self, data: pd.DataFrame) -> str:
        """Generate Real-Time Factor analysis."""
        rtf_stats = data['rtf'].describe()

        # Count real-time capable configs
        realtime_count = (data['rtf'] >= 1.0).sum()
        total_count = len(data)
        realtime_pct = (realtime_count / total_count) * 100

        analysis = f"""
        <h3>Real-Time Processing Capability</h3>
        <ul>
            <li><strong>Mean RTF:</strong> {rtf_stats['mean']:.2f}x real-time</li>
            <li><strong>Median RTF:</strong> {rtf_stats['50%']:.2f}x real-time</li>
            <li><strong>Max RTF:</strong> {rtf_stats['max']:.2f}x real-time</li>
            <li><strong>Real-time capable configs:</strong> {realtime_count}/{total_count} ({realtime_pct:.1f}%)</li>
        </ul>

        <p><strong>Interpretation:</strong></p>
        <ul>
            <li>RTF &gt; 1.0: Real-time processing capable</li>
            <li>RTF &gt; 2.0: Headroom for additional processing (e.g., beamforming)</li>
            <li>RTF &lt; 1.0: Cannot keep up with live data (offline processing only)</li>
        </ul>
        """

        return analysis

    def _generate_resolution_tradeoffs(self, data: pd.DataFrame) -> str:
        """Generate time/frequency resolution trade-off analysis."""
        analysis = """
        <h3>Resolution Trade-off Space</h3>
        <p>Time and frequency resolution are inversely related through the uncertainty principle:</p>
        <ul>
            <li><strong>High Time Resolution (small NFFT):</strong> Good for transients, poor frequency detail</li>
            <li><strong>High Frequency Resolution (large NFFT):</strong> Good spectral detail, slower temporal response</li>
        </ul>
        """

        # Find configs suitable for different phenomena
        if 'time_resolution_ms' in data.columns and 'freq_resolution_hz' in data.columns:
            # Lightning/sprites: <10ms time res
            lightning_configs = data[data['time_resolution_ms'] < 10.0]
            if len(lightning_configs) > 0:
                best_lightning = lightning_configs.loc[lightning_configs['time_resolution_ms'].idxmin()]
                analysis += f"""
                <p><strong>Best for Lightning/Sprites:</strong> NFFT={int(best_lightning['engine_nfft'])},
                Time Res={best_lightning['time_resolution_ms']:.2f}ms</p>
                """

            # SIDs/Schumann: <1Hz freq res
            schumann_configs = data[data['freq_resolution_hz'] < 1.0]
            if len(schumann_configs) > 0:
                best_schumann = schumann_configs.loc[schumann_configs['freq_resolution_hz'].idxmin()]
                analysis += f"""
                <p><strong>Best for SIDs/Schumann:</strong> NFFT={int(best_schumann['engine_nfft'])},
                Freq Res={best_schumann['freq_resolution_hz']:.3f}Hz</p>
                """

        return analysis

    def _generate_phenomena_suitability(self, data: pd.DataFrame) -> str:
        """Generate phenomena detection suitability analysis."""
        if 'time_resolution_ms' not in data.columns or 'freq_resolution_hz' not in data.columns:
            return "<p>Insufficient data for phenomena suitability analysis</p>"

        analysis = "<h3>Configuration Suitability by Phenomenon Type</h3>"

        # Assess each configuration
        suitability_counts = {
            'lightning_sprites': 0,
            'sids': 0,
            'schumann_resonances': 0,
            'whistlers': 0,
            'general_vlf': 0
        }

        for _, row in data.iterrows():
            assessment = assess_ionosphere_suitability(
                row['time_resolution_ms'],
                row['freq_resolution_hz']
            )
            for phenomenon, result in assessment.items():
                if result['suitable']:
                    suitability_counts[phenomenon] += 1

        total = len(data)
        analysis += "<table border='1' cellpadding='10'><tr><th>Phenomenon</th><th>Suitable Configs</th></tr>"
        analysis += f"<tr><td>Lightning/Sprites</td><td>{suitability_counts['lightning_sprites']}/{total}</td></tr>"
        analysis += f"<tr><td>SIDs</td><td>{suitability_counts['sids']}/{total}</td></tr>"
        analysis += f"<tr><td>Schumann Resonances</td><td>{suitability_counts['schumann_resonances']}/{total}</td></tr>"
        analysis += f"<tr><td>Whistlers</td><td>{suitability_counts['whistlers']}/{total}</td></tr>"
        analysis += f"<tr><td>General VLF</td><td>{suitability_counts['general_vlf']}/{total}</td></tr>"
        analysis += "</table>"

        return analysis

    def _generate_multichannel_analysis(self, data: pd.DataFrame) -> str:
        """Generate multi-channel performance analysis."""
        analysis = "<h3>Multi-Channel Capabilities</h3>"

        channel_counts = sorted(data['engine_channels'].unique())
        analysis += f"<p><strong>Channel counts tested:</strong> {channel_counts}</p>"

        # Performance by channel count
        if 'frames_per_second' in data.columns:
            analysis += "<p><strong>Throughput by Channel Count:</strong></p><ul>"
            for channels in channel_counts:
                subset = data[data['engine_channels'] == channels]
                mean_fps = subset['frames_per_second'].mean() if 'frames_per_second' in subset.columns else 0
                analysis += f"<li>{channels} channels: {mean_fps:.1f} FPS average</li>"
            analysis += "</ul>"

        analysis += """
        <p><strong>Multi-Channel Use Cases:</strong></p>
        <ul>
            <li><strong>2 channels:</strong> Direction finding (E-W, N-S antenna pairs)</li>
            <li><strong>3 channels:</strong> 2D direction finding + H-field</li>
            <li><strong>4+ channels:</strong> Advanced beamforming and polarization analysis</li>
        </ul>
        """

        return analysis

    def _generate_highres_analysis(self, data: pd.DataFrame) -> str:
        """Generate high-resolution configuration analysis."""
        # High-res configs: NFFT >= 4096 and overlap >= 0.75
        highres_data = data[
            (data['engine_nfft'] >= 4096) &
            (data['engine_overlap'] >= 0.75)
        ] if 'engine_overlap' in data.columns else data[data['engine_nfft'] >= 4096]

        if len(highres_data) == 0:
            return "<p>No high-resolution configurations (NFFT ≥ 4096, overlap ≥ 0.75) tested</p>"

        analysis = f"""
        <h3>High-Resolution Configurations</h3>
        <p>Analyzed {len(highres_data)} high-resolution configurations (NFFT ≥ 4096, overlap ≥ 0.75)</p>
        """

        if 'frames_per_second' in highres_data.columns:
            fps_mean = highres_data['frames_per_second'].mean()
            analysis += f"<p><strong>Mean Throughput:</strong> {fps_mean:.1f} FPS</p>"

        if 'rtf' in highres_data.columns:
            rtf_mean = highres_data['rtf'].mean()
            realtime_capable = (highres_data['rtf'] >= 1.0).sum()
            analysis += f"""
            <p><strong>Mean RTF:</strong> {rtf_mean:.2f}x real-time</p>
            <p><strong>Real-time capable:</strong> {realtime_capable}/{len(highres_data)} configs</p>
            """

        return analysis

    def _generate_performance_context(self, data: pd.DataFrame) -> str:
        """Generate computational performance summary."""
        summary = "<h3>Performance Characteristics</h3>"

        if 'mean_latency_us' in data.columns:
            latency_stats = data['mean_latency_us'].describe()
            summary += f"""
            <p><strong>Latency Range:</strong> {latency_stats['min']:.1f} - {latency_stats['max']:.1f} μs</p>
            """

        if 'frames_per_second' in data.columns:
            fps_stats = data['frames_per_second'].describe()
            summary += f"""
            <p><strong>Throughput Range:</strong> {fps_stats['min']:.1f} - {fps_stats['max']:.1f} FPS</p>
            """

        summary += """
        <p><strong>System Context:</strong></p>
        <ul>
            <li>All benchmarks performed on GPU hardware</li>
            <li>Results represent sustained processing capability</li>
            <li>Real-world applications may include additional overhead (I/O, storage, networking)</li>
        </ul>
        """

        return summary

    def _plot_rtf_analysis(self, data: pd.DataFrame):
        """Plot Real-Time Factor analysis."""
        if 'rtf' not in data.columns or 'freq_resolution_hz' not in data.columns:
            return None

        return self.perf_plotter.plot_rtf_vs_resolution(data)

    def _plot_resolution_tradeoffs(self, data: pd.DataFrame):
        """Plot time vs frequency resolution trade-offs."""
        if 'time_resolution_ms' not in data.columns or 'freq_resolution_hz' not in data.columns:
            return None

        import plotly.graph_objects as go

        fig = go.Figure()

        # Color by NFFT
        if 'engine_nfft' in data.columns:
            for nfft in sorted(data['engine_nfft'].unique()):
                nfft_data = data[data['engine_nfft'] == nfft]
                fig.add_trace(go.Scatter(
                    x=nfft_data['time_resolution_ms'],
                    y=nfft_data['freq_resolution_hz'],
                    mode='markers',
                    name=f"NFFT={nfft}",
                    marker=dict(size=10)
                ))

        # Add reference lines for phenomena requirements
        fig.add_hline(y=1.0, line_dash="dash", line_color="green",
                      annotation_text="Schumann threshold (1Hz)")
        fig.add_vline(x=10.0, line_dash="dash", line_color="red",
                      annotation_text="Lightning threshold (10ms)")

        fig.update_layout(
            title="Time vs Frequency Resolution Trade-off Space",
            xaxis_title="Time Resolution (ms)",
            yaxis_title="Frequency Resolution (Hz)",
            yaxis_type='log',
            showlegend=True
        )

        return fig


def generate_both_reports(
    data: pd.DataFrame,
    output_dir: Path
) -> tuple[Path, Path]:
    """
    Generate both general and ionosphere reports.

    Args:
        data: Combined benchmark data
        output_dir: Directory for output reports

    Returns:
        Tuple of (general_report_path, ionosphere_report_path)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # General report
    general_report = GeneralPerformanceReport()
    general_path = output_dir / "general_performance_report.html"
    general_report.generate(data, general_path)

    # Ionosphere report
    iono_report = IonosphereReport()
    iono_path = output_dir / "ionosphere_research_report.html"
    iono_report.generate(data, iono_path)

    return general_path, iono_path
