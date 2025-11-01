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

        # Multi-Channel Scaling Analysis (if multiple channel counts present)
        if 'engine_channels' in data.columns and len(data['engine_channels'].unique()) > 1:
            sections.append({
                'title': 'Multi-Channel Scaling',
                'content': self._generate_multichannel_scaling(data)
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
            <li><strong>Mean FPS:</strong> {fps_stats['mean']:.1f}
            <em style='color: #666; font-size: 0.9em;'>(frames per second - FFT processing rate)</em></li>
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
                <li><strong>Mean:</strong> {gb_stats['mean']:.2f} GB/s
                <em style='color: #666; font-size: 0.9em;'>(memory bandwidth - indicates GPU utilization efficiency)</em></li>
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
            <li><strong>Mean Latency:</strong> {lat_stats['mean']:.1f} μs
            <em style='color: #666; font-size: 0.9em;'>(time to process one FFT frame - critical for real-time responsiveness)</em></li>
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
        <h3>Accuracy Validation Results</h3>
        <p>Single-channel, zero-overlap accuracy validation against reference NumPy FFT implementation.</p>
        <h4>Overall Statistics</h4>
        <ul>
            <li><strong>Mean Pass Rate:</strong> {pass_rate_stats['mean']*100:.2f}%
            <em style='color: #666; font-size: 0.9em;'>(percentage of FFT frames within error tolerance - indicates numerical correctness)</em></li>
            <li><strong>Min Pass Rate:</strong> {pass_rate_stats['min']*100:.2f}%</li>
            <li><strong>Max Pass Rate:</strong> {pass_rate_stats['max']*100:.2f}%</li>
            <li><strong>Configurations Tested:</strong> {len(data)}</li>
        </ul>
        """

        # Error metrics if available
        if 'max_relative_error' in data.columns:
            error_stats = data['max_relative_error'].describe()
            analysis += f"""
            <h4>Error Metrics</h4>
            <ul>
                <li><strong>Mean Max Error:</strong> {error_stats['mean']:.2e}</li>
                <li><strong>Worst-Case Error:</strong> {error_stats['max']:.2e}</li>
            </ul>
            """

        # Mode comparison if both modes tested
        if 'engine_mode' in data.columns and len(data['engine_mode'].unique()) > 1:
            analysis += "<h4>Executor Comparison</h4><table style='margin: 10px 0; border-collapse: collapse;'>"
            analysis += "<tr><th style='border: 1px solid #ddd; padding: 8px;'>Mode</th>"
            analysis += "<th style='border: 1px solid #ddd; padding: 8px;'>Mean Pass Rate</th>"
            analysis += "<th style='border: 1px solid #ddd; padding: 8px;'>Configs</th></tr>"

            for mode in ['streaming', 'batch']:
                mode_data = data[data['engine_mode'] == mode]
                if len(mode_data) > 0:
                    mean_pass = mode_data['pass_rate'].mean() * 100
                    analysis += f"<tr><td style='border: 1px solid #ddd; padding: 8px;'>{mode.title()}</td>"
                    analysis += f"<td style='border: 1px solid #ddd; padding: 8px;'>{mean_pass:.2f}%</td>"
                    analysis += f"<td style='border: 1px solid #ddd; padding: 8px;'>{len(mode_data)}</td></tr>"

            analysis += "</table>"
            analysis += "<p><em>Both executors should produce identical results within error threshold.</em></p>"

        # NFFT scaling
        if 'engine_nfft' in data.columns:
            analysis += "<h4>Accuracy vs NFFT</h4><table style='margin: 10px 0; border-collapse: collapse;'>"
            analysis += "<tr><th style='border: 1px solid #ddd; padding: 8px;'>NFFT</th>"
            analysis += "<th style='border: 1px solid #ddd; padding: 8px;'>Pass Rate</th></tr>"

            for nfft in sorted(data['engine_nfft'].unique()):
                nfft_data = data[data['engine_nfft'] == nfft]
                pass_rate = nfft_data['pass_rate'].mean() * 100
                analysis += f"<tr><td style='border: 1px solid #ddd; padding: 8px;'>{int(nfft)}</td>"
                analysis += f"<td style='border: 1px solid #ddd; padding: 8px;'>{pass_rate:.2f}%</td></tr>"

            analysis += "</table>"

        # Validation summary
        all_pass = (data['pass_rate'] >= 0.99).all()
        if all_pass:
            analysis += """
            <h4>✓ Validation Summary</h4>
            <p style='color: green;'><strong>All configurations passed validation</strong> (≥99% pass rate).
            GPU FFT implementation is numerically correct across all tested NFFT values and execution modes.</p>
            """
        else:
            failed_configs = data[data['pass_rate'] < 0.99]
            analysis += f"""
            <h4>⚠ Validation Summary</h4>
            <p style='color: orange;'><strong>{len(failed_configs)} configurations failed validation</strong> (< 99% pass rate).
            Review failed configurations for potential numerical issues.</p>
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

        # Note about ultra-high NFFT configurations
        ultra_high_nfft = [n for n in nfft_range if n > 32768]
        if ultra_high_nfft:
            analysis += """
            <p><strong>Note:</strong> Ultra-high NFFT configurations (65536, 131072) are tested
            for dual-channel only (Schumann resonances detection). These require extremely high
            frequency resolution (&lt;0.5Hz) and are shown separately from the main scaling heatmap
            to avoid NaN skewing.</p>
            """

            # Show ultra-high NFFT data in a small table
            if 'throughput' in data['benchmark_type'].values:
                throughput_data = data[data['benchmark_type'] == 'throughput']
                ultra_data = throughput_data[throughput_data['engine_nfft'] > 32768].copy()

                if len(ultra_data) > 0 and 'frames_per_second' in ultra_data.columns:
                    analysis += "<h4>Ultra-High NFFT Performance (Dual-Channel)</h4>"
                    analysis += "<table style='margin: 10px 0; border-collapse: collapse;'>"
                    analysis += "<tr><th style='border: 1px solid #ddd; padding: 8px;'>NFFT</th>"
                    analysis += "<th style='border: 1px solid #ddd; padding: 8px;'>Channels</th>"
                    analysis += "<th style='border: 1px solid #ddd; padding: 8px;'>FPS</th>"
                    analysis += "<th style='border: 1px solid #ddd; padding: 8px;'>Freq Res (Hz)</th></tr>"

                    for _, row in ultra_data.iterrows():
                        nfft = int(row['engine_nfft'])
                        channels = int(row['engine_channels'])
                        fps = row['frames_per_second']
                        freq_res = row.get('freq_resolution_hz', 48000.0 / nfft)

                        analysis += f"<tr><td style='border: 1px solid #ddd; padding: 8px;'>{nfft}</td>"
                        analysis += f"<td style='border: 1px solid #ddd; padding: 8px;'>{channels}</td>"
                        analysis += f"<td style='border: 1px solid #ddd; padding: 8px;'>{fps:.1f}</td>"
                        analysis += f"<td style='border: 1px solid #ddd; padding: 8px;'>{freq_res:.3f}</td></tr>"

                    analysis += "</table>"

        return analysis

    def _generate_multichannel_scaling(self, data: pd.DataFrame) -> str:
        """Generate multi-channel scaling analysis."""
        analysis = "<h3>Channel Scaling Performance</h3>"
        analysis += "<p>Analysis of how performance scales with increasing channel count.</p>"

        channel_counts = sorted(data['engine_channels'].unique())

        # Throughput scaling by channel
        if 'throughput' in data['benchmark_type'].values and 'frames_per_second' in data.columns:
            throughput_data = data[data['benchmark_type'] == 'throughput']

            analysis += "<h4>Throughput Scaling</h4><table style='margin: 10px 0; border-collapse: collapse;'>"
            analysis += "<tr><th style='border: 1px solid #ddd; padding: 8px;'>Channels</th>"
            analysis += "<th style='border: 1px solid #ddd; padding: 8px;'>Mean FPS</th>"
            analysis += "<th style='border: 1px solid #ddd; padding: 8px;'>Scaling Efficiency</th></tr>"

            baseline_fps = None
            for channels in channel_counts:
                channel_data = throughput_data[throughput_data['engine_channels'] == channels]
                if not channel_data.empty:
                    mean_fps = channel_data['frames_per_second'].mean()

                    if baseline_fps is None:
                        baseline_fps = mean_fps
                        efficiency = 100.0
                    else:
                        # Ideal scaling would maintain same FPS per channel
                        ideal_fps = baseline_fps
                        efficiency = (mean_fps / ideal_fps) * 100

                    analysis += f"<tr><td style='border: 1px solid #ddd; padding: 8px;'>{int(channels)}</td>"
                    analysis += f"<td style='border: 1px solid #ddd; padding: 8px;'>{mean_fps:.1f}</td>"
                    analysis += f"<td style='border: 1px solid #ddd; padding: 8px;'>{efficiency:.1f}%</td></tr>"

            analysis += "</table>"

        # Latency scaling by channel
        if 'latency' in data['benchmark_type'].values and 'mean_latency_us' in data.columns:
            latency_data = data[data['benchmark_type'] == 'latency']

            analysis += "<h4>Latency Scaling</h4><table style='margin: 10px 0; border-collapse: collapse;'>"
            analysis += "<tr><th style='border: 1px solid #ddd; padding: 8px;'>Channels</th>"
            analysis += "<th style='border: 1px solid #ddd; padding: 8px;'>Mean Latency (μs)</th>"
            analysis += "<th style='border: 1px solid #ddd; padding: 8px;'>Increase vs Baseline</th></tr>"

            baseline_latency = None
            for channels in channel_counts:
                channel_data = latency_data[latency_data['engine_channels'] == channels]
                if not channel_data.empty:
                    mean_latency = channel_data['mean_latency_us'].mean()

                    if baseline_latency is None:
                        baseline_latency = mean_latency
                        increase = "baseline"
                    else:
                        increase_pct = ((mean_latency / baseline_latency) - 1) * 100
                        increase = f"+{increase_pct:.1f}%" if increase_pct > 0 else f"{increase_pct:.1f}%"

                    analysis += f"<tr><td style='border: 1px solid #ddd; padding: 8px;'>{int(channels)}</td>"
                    analysis += f"<td style='border: 1px solid #ddd; padding: 8px;'>{mean_latency:.1f}</td>"
                    analysis += f"<td style='border: 1px solid #ddd; padding: 8px;'>{increase}</td></tr>"

            analysis += "</table>"

        # Key insights
        analysis += "<h4>Key Insights</h4><ul>"
        if len(channel_counts) >= 2:
            analysis += f"<li>Tested configurations range from {min(channel_counts)} to {max(channel_counts)} channels</li>"

            # Check if latency increases linearly
            if 'latency' in data['benchmark_type'].values and 'mean_latency_us' in data.columns:
                analysis += "<li>Latency scaling shows impact of multi-channel processing overhead</li>"

            # Check if throughput is maintained
            if 'throughput' in data['benchmark_type'].values and 'frames_per_second' in data.columns:
                analysis += "<li>Throughput analysis helps identify optimal channel count for batch processing</li>"

        analysis += "</ul>"

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
                # Filter to NFFT <= 32768 for main heatmap (avoids NaN skewing from ultra-high NFFT)
                # Ultra-high NFFT (65536, 131072) only tested for channels=2 (Schumann resonances)
                filtered_data = throughput_data[throughput_data['engine_nfft'] <= 32768].copy()

                if len(filtered_data) > 0:
                    return self.perf_plotter.plot_heatmap(
                        filtered_data, 'engine_nfft', 'engine_channels', 'frames_per_second'
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
        Generate ionosphere-focused report for dual-channel antenna system.

        Args:
            data: Combined benchmark data with scientific metrics
            output_path: Output HTML file path
            title: Report title
        """
        # Filter to dual-channel data only (ionosphere antenna pair)
        if 'engine_channels' in data.columns:
            dual_channel_data = data[data['engine_channels'] == 2].copy()

            if dual_channel_data.empty:
                print("WARNING: No dual-channel (channels=2) data found for ionosphere report.")
                print("Ionosphere report is designed for dual-channel antenna systems.")
                print("Skipping ionosphere report generation.")
                return

            n_filtered = len(data) - len(dual_channel_data)
            if n_filtered > 0:
                print(f"INFO: Filtered {n_filtered} non-dual-channel measurements from ionosphere report.")
                print(f"INFO: Using {len(dual_channel_data)} dual-channel measurements for ionosphere analysis.")

            data = dual_channel_data
        else:
            print("WARNING: 'engine_channels' column not found in data. Proceeding without filtering.")

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

        # Dual-Channel Streaming Performance
        sections.append({
            'title': 'Dual-Channel Streaming Performance',
            'content': self._generate_dual_channel_streaming(data)
        })

        # Real-Time Compliance & Reliability (if streaming metrics available)
        if 'deadline_compliance_rate' in data.columns:
            sections.append({
                'title': 'Real-Time Compliance & Reliability',
                'content': self._generate_compliance_analysis(data)
            })

        # Streaming vs Batch Comparison (if both modes present)
        if 'engine_mode' in data.columns and len(data['engine_mode'].unique()) > 1:
            sections.append({
                'title': 'Streaming vs Batch Mode Comparison',
                'content': self._generate_streaming_vs_batch(data)
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
            overview += f"<li><strong>Time Resolution:</strong> {time_res_range} "
            overview += "<em style='color: #666; font-size: 0.9em;'>(FFT frame duration - ability to resolve fast transients)</em></li>"

        if 'freq_resolution_hz' in data.columns:
            freq_res_range = f"{data['freq_resolution_hz'].min():.3f} - {data['freq_resolution_hz'].max():.3f} Hz"
            overview += f"<li><strong>Frequency Resolution:</strong> {freq_res_range} "
            overview += "<em style='color: #666; font-size: 0.9em;'>(spectral bin width - ability to resolve close frequencies)</em></li>"

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
            <li><strong>Mean RTF:</strong> {rtf_stats['mean']:.2f}x real-time
            <em style='color: #666; font-size: 0.9em;'>(Real-Time Factor - ratio of processing speed to data rate, &gt;1.0 means faster than real-time)</em></li>
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

    def _generate_dual_channel_streaming(self, data: pd.DataFrame) -> str:
        """Generate dual-channel streaming performance analysis."""
        # Filter to dual-channel data
        if 'engine_channels' in data.columns:
            dual_data = data[data['engine_channels'] == 2].copy()
        else:
            dual_data = data.copy()

        if len(dual_data) == 0:
            return "<p>No dual-channel (2-channel) data available for streaming analysis.</p>"

        analysis = """
        <h3>Dual-Channel Antenna System</h3>
        <p>The ionosense system uses a dual-channel configuration representing an E-W and N-S dipole antenna pair
        for direction finding and ionosphere monitoring.</p>
        """

        # Configuration summary
        nfft_values = sorted(dual_data['engine_nfft'].unique())
        overlap_values = sorted(dual_data['engine_overlap'].unique()) if 'engine_overlap' in dual_data.columns else []

        analysis += f"""
        <p><strong>Tested Configurations:</strong></p>
        <ul>
            <li><strong>NFFT values:</strong> {nfft_values}</li>
            <li><strong>Overlap values:</strong> {overlap_values}</li>
            <li><strong>Channel count:</strong> 2 (fixed dual-channel)</li>
        </ul>
        """

        # Performance metrics
        if 'frames_per_second' in dual_data.columns:
            fps_stats = dual_data['frames_per_second'].describe()
            analysis += f"""
            <p><strong>Throughput Performance:</strong></p>
            <ul>
                <li>Mean: {fps_stats['mean']:.1f} FPS</li>
                <li>Range: {fps_stats['min']:.1f} - {fps_stats['max']:.1f} FPS</li>
            </ul>
            """

        if 'mean_latency_us' in dual_data.columns:
            lat_stats = dual_data['mean_latency_us'].describe()
            analysis += f"""
            <p><strong>Latency Performance:</strong></p>
            <ul>
                <li>Mean: {lat_stats['mean']:.1f} μs</li>
                <li>Range: {lat_stats['min']:.1f} - {lat_stats['max']:.1f} μs</li>
            </ul>
            """

        if 'rtf' in dual_data.columns:
            rtf_stats = dual_data['rtf'].describe()
            realtime_capable = (dual_data['rtf'] >= 1.0).sum()
            analysis += f"""
            <p><strong>Real-Time Factor:</strong></p>
            <ul>
                <li>Mean RTF: {rtf_stats['mean']:.2f}x real-time</li>
                <li>Real-time capable configs: {realtime_capable}/{len(dual_data)}</li>
            </ul>
            """

        return analysis

    def _generate_compliance_analysis(self, data: pd.DataFrame) -> str:
        """Generate real-time compliance and reliability analysis."""
        if 'deadline_compliance_rate' not in data.columns:
            return "<p>No deadline compliance data available.</p>"

        analysis = """
        <h3>Deadline Compliance</h3>
        <p>For real-time streaming, deadline compliance measures the ability to process frames
        within their required time window. Target: >99% compliance for stable operation.</p>
        """

        compliance_stats = data['deadline_compliance_rate'].describe()
        high_compliance = (data['deadline_compliance_rate'] >= 0.99).sum()

        analysis += f"""
        <p><strong>Compliance Statistics:</strong></p>
        <ul>
            <li>Mean compliance rate: {compliance_stats['mean']*100:.1f}%
            <em style='color: #666; font-size: 0.9em;'>(fraction of frames processed within timing deadline - critical for real-time systems)</em></li>
            <li>Min compliance rate: {compliance_stats['min']*100:.1f}%</li>
            <li>Configs with >99% compliance: {high_compliance}/{len(data)}</li>
        </ul>
        """

        # Jitter analysis
        if 'mean_jitter_ms' in data.columns:
            jitter_stats = data['mean_jitter_ms'].describe()
            analysis += f"""
            <h3>Timing Stability (Jitter)</h3>
            <p><strong>Mean Jitter:</strong></p>
            <ul>
                <li>Average: {jitter_stats['mean']:.2f} ms
                <em style='color: #666; font-size: 0.9em;'>(timing variability between frames - lower means more consistent latency)</em></li>
                <li>Range: {jitter_stats['min']:.2f} - {jitter_stats['max']:.2f} ms</li>
            </ul>
            """

        if 'p99_jitter_ms' in data.columns:
            p99_jitter_stats = data['p99_jitter_ms'].describe()
            analysis += f"""
            <p><strong>P99 Jitter (worst-case):</strong></p>
            <ul>
                <li>Average P99: {p99_jitter_stats['mean']:.2f} ms</li>
                <li>Max P99: {p99_jitter_stats['max']:.2f} ms</li>
            </ul>
            """

        # Frame drops
        if 'frames_dropped' in data.columns:
            total_drops = data['frames_dropped'].sum()
            configs_with_drops = (data['frames_dropped'] > 0).sum()
            analysis += f"""
            <h3>Data Loss Assessment</h3>
            <p><strong>Frame Drops:</strong></p>
            <ul>
                <li>Total frames dropped: {int(total_drops)}</li>
                <li>Configurations with drops: {configs_with_drops}/{len(data)}</li>
            </ul>
            """

        return analysis

    def _generate_streaming_vs_batch(self, data: pd.DataFrame) -> str:
        """Generate streaming vs batch mode comparison."""
        if 'engine_mode' not in data.columns:
            return "<p>No execution mode data available for comparison.</p>"

        modes = data['engine_mode'].unique()
        if len(modes) < 2:
            return "<p>Only one execution mode tested - cannot compare streaming vs batch.</p>"

        analysis = """
        <h3>Execution Mode Comparison</h3>
        <p>Comparing streaming executor (real-time processing) vs batch executor (throughput-optimized).</p>
        """

        # Compare modes
        for mode in ['streaming', 'batch']:
            mode_data = data[data['engine_mode'] == mode]
            if len(mode_data) == 0:
                continue

            analysis += f"""
            <h4>{mode.title()} Mode ({len(mode_data)} measurements)</h4>
            """

            if 'frames_per_second' in mode_data.columns:
                fps_mean = mode_data['frames_per_second'].mean()
                analysis += f"<p><strong>Throughput:</strong> {fps_mean:.1f} FPS (mean)</p>"

            if 'mean_latency_us' in mode_data.columns:
                lat_mean = mode_data['mean_latency_us'].mean()
                analysis += f"<p><strong>Latency:</strong> {lat_mean:.1f} μs (mean)</p>"

            if 'deadline_compliance_rate' in mode_data.columns and mode == 'streaming':
                compliance_mean = mode_data['deadline_compliance_rate'].mean()
                analysis += f"<p><strong>Deadline Compliance:</strong> {compliance_mean*100:.1f}%</p>"

        # Trade-off summary
        analysis += """
        <h4>Trade-off Summary</h4>
        <ul>
            <li><strong>Streaming mode:</strong> Lower throughput, better latency, deadline compliance monitoring</li>
            <li><strong>Batch mode:</strong> Higher throughput, slightly higher latency, no real-time guarantees</li>
        </ul>
        <p><strong>Recommendation:</strong> Use streaming mode for real-time ionosphere monitoring where
        deadline compliance is critical. Use batch mode for offline analysis where maximum throughput is needed.</p>
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
