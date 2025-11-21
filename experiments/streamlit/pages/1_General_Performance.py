"""
General Performance Report
==========================

Comprehensive performance analysis across all benchmark types:
throughput, latency, accuracy, and scaling characteristics.
"""

import json
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_benchmark_data
from analysis.visualization import PerformancePlotter, VisualizationConfig

SPECTROGRAM_DIR = Path("artifacts/figures/spectrograms")


def _load_spectrogram_metadata(filename: str) -> dict | None:
    path = SPECTROGRAM_DIR / filename
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None

# Page configuration
st.set_page_config(page_title="General Performance", page_icon="🏆", layout="wide")

st.title("🏆 General Performance Report")

# Load data
try:
    data = load_benchmark_data("artifacts/data")
except FileNotFoundError:
    st.error("⚠️ No benchmark data found. Please run benchmarks first.")
    st.stop()
except Exception as e:
    st.error(f"❌ Error loading data: {e}")
    st.stop()

# Create tabs for major sections
tabs = st.tabs([
    "Executive Summary",
    "Throughput Analysis",
    "Latency Analysis",
    "Accuracy Analysis",
    "Scaling Analysis",
    "Execution Mode Overhead",
    "Configuration Recommendations"
])

# Initialize plotter
plotter = PerformancePlotter(VisualizationConfig())

# ============================================================================
# TAB 1: EXECUTIVE SUMMARY
# ============================================================================
with tabs[0]:
    st.header("Executive Summary")

    col1, col2, col3, col4 = st.columns(4)

    # Basic stats
    num_configs = len(data.groupby(['engine_nfft', 'engine_channels']))
    num_measurements = len(data)
    benchmark_types = data['benchmark_type'].nunique()

    col1.metric("Total Measurements", num_measurements)
    col2.metric("Configurations Tested", num_configs)
    col3.metric("Benchmark Types", benchmark_types)
    col4.metric("Report Generated", datetime.now().strftime('%Y-%m-%d %H:%M'))

    st.divider()

    # Best performances
    st.subheader("🎯 Peak Performance Highlights")

    col1, col2, col3 = st.columns(3)

    # Peak throughput
    if 'throughput' in data['benchmark_type'].values:
        throughput_data = data[data['benchmark_type'] == 'throughput']
        if 'frames_per_second' in throughput_data.columns:
            max_fps_idx = throughput_data['frames_per_second'].idxmax()
            best_row = throughput_data.loc[max_fps_idx]

            col1.metric(
                "Peak Throughput",
                f"{best_row['frames_per_second']:.1f} FPS",
                help=f"NFFT={int(best_row['engine_nfft'])}, Channels={int(best_row['engine_channels'])}"
            )
            col1.caption(f"Config: NFFT={int(best_row['engine_nfft'])}, Ch={int(best_row['engine_channels'])}")

    # Lowest latency
    if 'latency' in data['benchmark_type'].values:
        latency_data = data[data['benchmark_type'] == 'latency']
        if 'mean_latency_us' in latency_data.columns:
            min_lat_idx = latency_data['mean_latency_us'].idxmin()
            best_row = latency_data.loc[min_lat_idx]

            col2.metric(
                "Lowest Latency",
                f"{best_row['mean_latency_us']:.1f} μs",
                help=f"NFFT={int(best_row['engine_nfft'])}, Channels={int(best_row['engine_channels'])}"
            )
            col2.caption(f"Config: NFFT={int(best_row['engine_nfft'])}, Ch={int(best_row['engine_channels'])}")

    # Best accuracy
    if 'accuracy' in data['benchmark_type'].values:
        accuracy_data = data[data['benchmark_type'] == 'accuracy']
        if 'pass_rate' in accuracy_data.columns:
            mean_accuracy = accuracy_data['pass_rate'].mean() * 100
            col3.metric(
                "Mean Accuracy",
                f"{mean_accuracy:.1f}%",
                help="Average pass rate across all accuracy tests"
            )

    st.divider()
    st.subheader("Reference Spectrogram Snapshot")
    general_image = SPECTROGRAM_DIR / "general_spectrogram.png"
    general_meta = _load_spectrogram_metadata("general_spectrogram.json")

    if general_image.exists():
        col_img, col_meta = st.columns([3, 1])
        col_img.image(
            str(general_image),
            caption="Synthetic multi-tone signal (NFFT=4096, overlap=0.75)",
            use_column_width=True
        )

        if general_meta:
            config = general_meta.get("config", {})
            col_meta.metric("NFFT", config.get("nfft", "—"))
            col_meta.metric("Overlap", f"{config.get('overlap', 0.0):.2f}")
            col_meta.metric("Duration", f"{general_meta.get('duration_sec', 0.0):.1f} s")
        else:
            col_meta.info("No metadata file detected.")
    else:
        st.info(
            "?? General spectrogram PNG missing. Run "
            "`snakemake generate_general_spectrogram` to refresh static plots."
        )

# ============================================================================
# TAB 2: THROUGHPUT ANALYSIS
# ============================================================================
with tabs[1]:
    st.header("Throughput Analysis")

    if 'throughput' not in data['benchmark_type'].values:
        st.info("No throughput benchmark data available")
    else:
        throughput_data = data[data['benchmark_type'] == 'throughput']

        if 'frames_per_second' in throughput_data.columns:
            # Statistics
            fps_stats = throughput_data['frames_per_second'].describe()

            col1, col2, col3, col4 = st.columns(4)
            col1.metric(
                "Mean FPS",
                f"{fps_stats['mean']:.1f}",
                help="Frames per second - FFT processing rate"
            )
            col2.metric("Median FPS", f"{fps_stats['50%']:.1f}")
            col3.metric("Max FPS", f"{fps_stats['max']:.1f}")
            col4.metric("Std Dev", f"{fps_stats['std']:.1f}")

            # GB/s if available
            if 'gb_per_second' in throughput_data.columns:
                st.divider()
                gb_stats = throughput_data['gb_per_second'].describe()

                col1, col2 = st.columns(2)
                col1.metric(
                    "Mean Bandwidth",
                    f"{gb_stats['mean']:.2f} GB/s",
                    help="Memory bandwidth - indicates GPU utilization efficiency"
                )
                col2.metric("Max Bandwidth", f"{gb_stats['max']:.2f} GB/s")

            # Scaling plot
            st.divider()
            st.subheader("Throughput Scaling")

            fig = plotter.plot_scaling(
                throughput_data,
                x_col='engine_nfft',
                y_col='frames_per_second',
                group_by='engine_channels',
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.warning("No frames_per_second column in throughput data")

# ============================================================================
# TAB 3: LATENCY ANALYSIS
# ============================================================================
with tabs[2]:
    st.header("Latency Analysis")

    if 'latency' not in data['benchmark_type'].values:
        st.info("No latency benchmark data available")
    else:
        latency_data = data[data['benchmark_type'] == 'latency']

        if 'mean_latency_us' in latency_data.columns:
            # Statistics
            lat_stats = latency_data['mean_latency_us'].describe()

            col1, col2, col3, col4 = st.columns(4)
            col1.metric(
                "Mean Latency",
                f"{lat_stats['mean']:.1f} μs",
                help="Time to process one FFT frame - critical for real-time responsiveness"
            )
            col2.metric("Median Latency", f"{lat_stats['50%']:.1f} μs")
            col3.metric("Min Latency", f"{lat_stats['min']:.1f} μs")
            col4.metric("P95 Latency", f"{lat_stats['75%']:.1f} μs")

            # Scaling plot
            st.divider()
            st.subheader("Latency Scaling")

            fig = plotter.plot_scaling(
                latency_data,
                x_col='engine_nfft',
                y_col='mean_latency_us',
                group_by='engine_channels',
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.warning("No mean_latency_us column in latency data")

# ============================================================================
# TAB 4: ACCURACY ANALYSIS
# ============================================================================
with tabs[3]:
    st.header("Accuracy Analysis")

    if 'accuracy' not in data['benchmark_type'].values:
        st.info("No accuracy benchmark data available")
    else:
        accuracy_data = data[data['benchmark_type'] == 'accuracy']

        if 'pass_rate' in accuracy_data.columns:
            pass_rate_stats = accuracy_data['pass_rate'].describe()

            st.markdown("### Overall Statistics")
            st.caption("Single-channel, zero-overlap accuracy validation against reference NumPy FFT implementation.")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric(
                "Mean Pass Rate",
                f"{pass_rate_stats['mean']*100:.2f}%",
                help="Percentage of FFT frames within error tolerance - indicates numerical correctness"
            )
            col2.metric("Min Pass Rate", f"{pass_rate_stats['min']*100:.2f}%")
            col3.metric("Max Pass Rate", f"{pass_rate_stats['max']*100:.2f}%")
            col4.metric("Configurations Tested", len(accuracy_data))

            st.divider()
            st.markdown("### Spectrogram Comparison Snapshot")
            engine_img = SPECTROGRAM_DIR / "accuracy_engine.png"
            numpy_img = SPECTROGRAM_DIR / "accuracy_numpy.png"
            delta_img = SPECTROGRAM_DIR / "accuracy_difference.png"
            accuracy_meta = _load_spectrogram_metadata("accuracy_metrics.json")

            if engine_img.exists() and numpy_img.exists():
                col_img1, col_img2 = st.columns(2)
                col_img1.image(
                    str(engine_img),
                    caption="Ionosense Engine Spectrogram",
                    use_column_width=True
                )
                col_img2.image(
                    str(numpy_img),
                    caption="NumPy STFT Reference",
                    use_column_width=True
                )

                if delta_img.exists():
                    st.image(
                        str(delta_img),
                        caption="Absolute difference (Engine vs NumPy)",
                        use_column_width=True
                    )

                if accuracy_meta and "metrics" in accuracy_meta:
                    metrics = accuracy_meta["metrics"]
                    col_a, col_b, col_c, col_d = st.columns(4)
                    col_a.metric("Mean Abs Error", f"{metrics.get('mean_absolute_error', 0.0):.3e}")
                    col_b.metric("RMSE", f"{metrics.get('rmse', 0.0):.3e}")
                    col_c.metric("Max Abs Error", f"{metrics.get('max_absolute_error', 0.0):.3e}")
                    col_d.metric("SNR", f"{metrics.get('snr_db', 0.0):.1f} dB")
            else:
                st.info(
                    "?? Accuracy spectrogram artifacts missing. "
                    "Run `snakemake generate_accuracy_spectrograms` to regenerate static PNGs."
                )

            # Error metrics
            if 'max_relative_error' in accuracy_data.columns:
                st.divider()
                st.markdown("### Error Metrics")

                error_stats = accuracy_data['max_relative_error'].describe()
                col1, col2 = st.columns(2)
                col1.metric("Mean Max Error", f"{error_stats['mean']:.2e}")
                col2.metric("Worst-Case Error", f"{error_stats['max']:.2e}")

            # Mode comparison
            if 'engine_mode' in accuracy_data.columns and len(accuracy_data['engine_mode'].unique()) > 1:
                st.divider()
                st.markdown("### Executor Comparison")

                comparison_data = []
                for mode in ['streaming', 'batch']:
                    mode_data = accuracy_data[accuracy_data['engine_mode'] == mode]
                    if len(mode_data) > 0:
                        comparison_data.append({
                            'Mode': mode.title(),
                            'Mean Pass Rate': f"{mode_data['pass_rate'].mean() * 100:.2f}%",
                            'Configs': len(mode_data)
                        })

                if comparison_data:
                    st.dataframe(
                        pd.DataFrame(comparison_data),
                        use_container_width=True,
                        hide_index=True
                    )
                    st.caption("Both executors should produce identical results within error threshold.")

            # NFFT scaling
            if 'engine_nfft' in accuracy_data.columns:
                st.divider()
                st.markdown("### Accuracy vs NFFT")

                nfft_accuracy = []
                for nfft in sorted(accuracy_data['engine_nfft'].unique()):
                    nfft_data = accuracy_data[accuracy_data['engine_nfft'] == nfft]
                    pass_rate = nfft_data['pass_rate'].mean() * 100
                    nfft_accuracy.append({
                        'NFFT': int(nfft),
                        'Pass Rate': f"{pass_rate:.2f}%"
                    })

                st.dataframe(
                    pd.DataFrame(nfft_accuracy),
                    use_container_width=True,
                    hide_index=True
                )

            # Validation summary
            st.divider()
            all_pass = (accuracy_data['pass_rate'] >= 0.99).all()
            if all_pass:
                st.success(
                    "✅ **All configurations passed validation** (≥99% pass rate). "
                    "GPU FFT implementation is numerically correct across all tested NFFT values and execution modes."
                )
            else:
                failed_configs = accuracy_data[accuracy_data['pass_rate'] < 0.99]
                st.warning(
                    f"⚠️ **{len(failed_configs)} configurations failed validation** (<99% pass rate). "
                    "Review failed configurations for potential numerical issues."
                )
        else:
            st.warning("No pass_rate column in accuracy data")

# ============================================================================
# TAB 5: SCALING ANALYSIS
# ============================================================================
with tabs[4]:
    st.header("Scaling Analysis")

    # Parameter space coverage
    st.subheader("Parameter Space Coverage")

    nfft_range = data['engine_nfft'].unique()
    channel_range = data['engine_channels'].unique()

    col1, col2 = st.columns(2)
    col1.metric("NFFT Range", f"{min(nfft_range)} - {max(nfft_range)}")
    col2.metric("Channel Counts", ", ".join(map(str, sorted(channel_range))))

    # Heatmap
    if 'throughput' in data['benchmark_type'].values:
        throughput_data = data[data['benchmark_type'] == 'throughput']
        if 'frames_per_second' in throughput_data.columns:
            st.divider()
            st.subheader("Performance Heatmap")

            # Filter to NFFT <= 32768 for main heatmap
            filtered_data = throughput_data[throughput_data['engine_nfft'] <= 32768].copy()

            if len(filtered_data) > 0:
                fig = plotter.plot_heatmap(
                    filtered_data,
                    'engine_nfft',
                    'engine_channels',
                    'frames_per_second'
                )
                st.plotly_chart(fig, width="stretch")

            # Ultra-high NFFT table
            ultra_high_nfft = [n for n in nfft_range if n > 32768]
            if ultra_high_nfft:
                st.divider()
                st.info(
                    "**Note:** Ultra-high NFFT configurations (65536, 131072) are tested "
                    "for dual-channel only (Schumann resonances detection). These require extremely high "
                    "frequency resolution (<0.5Hz) and are shown separately to avoid NaN skewing."
                )

                ultra_data = throughput_data[throughput_data['engine_nfft'] > 32768].copy()
                if len(ultra_data) > 0:
                    st.subheader("Ultra-High NFFT Performance (Dual-Channel)")

                    display_cols = ['engine_nfft', 'engine_channels', 'engine_overlap', 'frames_per_second']
                    if 'rtf' in ultra_data.columns:
                        display_cols.append('rtf')

                    st.dataframe(
                        ultra_data[display_cols],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            'engine_nfft': st.column_config.NumberColumn('NFFT', format='%d'),
                            'engine_channels': st.column_config.NumberColumn('Channels', format='%d'),
                            'engine_overlap': st.column_config.NumberColumn('Overlap', format='%.3f'),
                            'frames_per_second': st.column_config.NumberColumn('FPS', format='%.1f'),
                            'rtf': st.column_config.NumberColumn('RTF', format='%.2f'),
                        }
                    )

# ============================================================================
# TAB 6: EXECUTION MODE OVERHEAD
# ============================================================================
with tabs[5]:
    st.header("Execution Mode Overhead Analysis")

    st.markdown("""
    ### BATCH vs STREAMING Mode Comparison

    The Ionosense HPC library supports two execution modes:
    - **BATCH Mode**: Direct buffer processing for discrete frames (minimal overhead)
    - **STREAMING Mode**: Ring buffer management for continuous real-time streams
    """)

    # Check if we have execution mode comparison data
    has_mode_column = 'engine_mode' in data.columns
    has_latency_data = 'latency' in data['benchmark_type'].values

    if not has_mode_column:
        st.warning("⚠️ No execution mode data available. Run the `execution_mode_comparison` experiment to analyze overhead.")
        st.code("""
# Run execution mode comparison experiment:
python benchmarks/run_latency.py experiment=execution_mode_comparison +benchmark=latency
        """)
    elif not has_latency_data:
        st.info("ℹ️ No latency benchmark data available for execution mode comparison.")
    else:
        # Filter latency data with both modes
        latency_data = data[data['benchmark_type'] == 'latency'].copy()

        # Check if we have both modes
        available_modes = latency_data['engine_mode'].unique() if 'engine_mode' in latency_data.columns else []

        if len(available_modes) < 2:
            st.info(f"ℹ️ Only {len(available_modes)} execution mode(s) tested: {', '.join(available_modes)}. "
                   "Run `execution_mode_comparison` experiment to compare BATCH vs STREAMING overhead.")
        else:
            # Group by NFFT and mode to calculate overhead
            if 'mean_latency_us' in latency_data.columns:
                st.subheader("📊 Latency Comparison")

                # Pivot table for side-by-side comparison
                pivot_data = latency_data.pivot_table(
                    index='engine_nfft',
                    columns='engine_mode',
                    values='mean_latency_us',
                    aggfunc='mean'
                )

                # Calculate overhead if both modes exist
                if 'batch' in pivot_data.columns and 'streaming' in pivot_data.columns:
                    pivot_data['Overhead (µs)'] = pivot_data['streaming'] - pivot_data['batch']
                    pivot_data['Overhead (%)'] = ((pivot_data['streaming'] / pivot_data['batch']) - 1) * 100

                    # Display comparison table
                    display_data = pivot_data.copy()
                    display_data = display_data.reset_index()

                    st.dataframe(
                        display_data,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            'engine_nfft': st.column_config.NumberColumn('NFFT', format='%d'),
                            'batch': st.column_config.NumberColumn('BATCH (µs)', format='%.1f'),
                            'streaming': st.column_config.NumberColumn('STREAMING (µs)', format='%.1f'),
                            'Overhead (µs)': st.column_config.NumberColumn('Overhead (µs)', format='%.1f'),
                            'Overhead (%)': st.column_config.NumberColumn('Overhead (%)', format='%.1f%%'),
                        }
                    )

                    # Visualizations
                    st.divider()
                    col1, col2 = st.columns(2)

                    with col1:
                        st.subheader("Absolute Latency")
                        fig = plotter.plot_scaling(
                            latency_data,
                            x_col='engine_nfft',
                            y_col='mean_latency_us',
                            group_by='engine_mode',
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    with col2:
                        st.subheader("Overhead Scaling")
                        # Plot overhead vs NFFT
                        import plotly.graph_objects as go
                        overhead_data = pivot_data.reset_index()
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=overhead_data['engine_nfft'],
                            y=overhead_data['Overhead (µs)'],
                            mode='lines+markers',
                            name='Overhead (µs)',
                            line=dict(width=3),
                            marker=dict(size=10)
                        ))
                        fig.update_layout(
                            xaxis_title='NFFT',
                            yaxis_title='STREAMING Overhead (µs)',
                            xaxis_type='log',
                            template='plotly_white',
                            height=400
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    # Summary statistics
                    st.divider()
                    st.subheader("📈 Overhead Summary")

                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric(
                        "Mean Overhead",
                        f"{pivot_data['Overhead (µs)'].mean():.1f} µs",
                        help="Average overhead of STREAMING vs BATCH mode"
                    )
                    col2.metric(
                        "Mean Overhead %",
                        f"{pivot_data['Overhead (%)'].mean():.1f}%"
                    )
                    col3.metric(
                        "Min Overhead",
                        f"{pivot_data['Overhead (µs)'].min():.1f} µs",
                        help="Smallest overhead observed (low NFFT)"
                    )
                    col4.metric(
                        "Max Overhead",
                        f"{pivot_data['Overhead (µs)'].max():.1f} µs",
                        help="Largest overhead observed (high NFFT)"
                    )

                    # Explanation
                    st.divider()
                    st.subheader("🔍 Understanding the Overhead")

                    st.markdown("""
                    **STREAMING mode overhead** comes from:
                    - Per-channel ring buffer allocation and management
                    - `extract_frame()` memory copies from ring buffers
                    - `advance()` pointer management for overlap handling
                    - Additional synchronization points

                    **When to use each mode:**
                    """)

                    mode_table = pd.DataFrame([
                        {
                            'Use Case': '📊 Single-frame latency benchmarks',
                            'Recommended Mode': 'BATCH',
                            'Reason': 'Minimal overhead, measures pure processing time'
                        },
                        {
                            'Use Case': '🚀 Throughput benchmarks',
                            'Recommended Mode': 'BATCH',
                            'Reason': 'Maximum throughput for discrete frame processing'
                        },
                        {
                            'Use Case': '🌊 Ionosphere research (continuous)',
                            'Recommended Mode': 'STREAMING',
                            'Reason': 'Ring buffer essential for overlap management & continuous data'
                        },
                        {
                            'Use Case': '📡 Real-time streaming applications',
                            'Recommended Mode': 'STREAMING',
                            'Reason': 'Seamless continuous data flow handling'
                        },
                        {
                            'Use Case': '📦 Batch processing (offline)',
                            'Recommended Mode': 'BATCH',
                            'Reason': 'Higher efficiency for discrete frame sets'
                        }
                    ])

                    st.dataframe(
                        mode_table,
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.warning("Not enough mode data for comparison. Expected both 'batch' and 'streaming' modes.")

# ============================================================================
# TAB 7: CONFIGURATION RECOMMENDATIONS
# ============================================================================
with tabs[6]:
    st.header("Configuration Recommendations")

    st.markdown("""
    Based on benchmark results, here are recommended configurations for different use cases:
    """)

    recommendations = []

    # High throughput
    if 'throughput' in data['benchmark_type'].values:
        throughput_data = data[data['benchmark_type'] == 'throughput']
        if 'frames_per_second' in throughput_data.columns:
            max_fps_idx = throughput_data['frames_per_second'].idxmax()
            best = throughput_data.loc[max_fps_idx]
            recommendations.append({
                'Use Case': '🚀 Maximum Throughput',
                'NFFT': int(best['engine_nfft']),
                'Channels': int(best['engine_channels']),
                'Overlap': f"{best['engine_overlap']:.3f}",
                'Performance': f"{best['frames_per_second']:.1f} FPS"
            })

    # Low latency
    if 'latency' in data['benchmark_type'].values:
        latency_data = data[data['benchmark_type'] == 'latency']
        if 'mean_latency_us' in latency_data.columns:
            min_lat_idx = latency_data['mean_latency_us'].idxmin()
            best = latency_data.loc[min_lat_idx]
            recommendations.append({
                'Use Case': '⚡ Lowest Latency',
                'NFFT': int(best['engine_nfft']),
                'Channels': int(best['engine_channels']),
                'Overlap': f"{best['engine_overlap']:.3f}",
                'Performance': f"{best['mean_latency_us']:.1f} μs"
            })

    # Real-time capable
    if 'rtf' in data.columns:
        rtf_data = data[data['rtf'] >= 1.0]
        if len(rtf_data) > 0:
            # Find config with highest channel count that's still real-time capable
            max_ch_idx = rtf_data['engine_channels'].idxmax()
            best = rtf_data.loc[max_ch_idx]
            recommendations.append({
                'Use Case': '🎯 Real-Time Processing',
                'NFFT': int(best['engine_nfft']),
                'Channels': int(best['engine_channels']),
                'Overlap': f"{best['engine_overlap']:.3f}",
                'Performance': f"{best['rtf']:.2f}x RTF"
            })

    if recommendations:
        st.dataframe(
            pd.DataFrame(recommendations),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Not enough data to generate recommendations")

    # Download report data
    st.divider()
    st.subheader("📥 Export Data")

    csv = data.to_csv(index=False)
    st.download_button(
        label="Download Full Benchmark Data (CSV)",
        data=csv,
        file_name=f"general_performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )
