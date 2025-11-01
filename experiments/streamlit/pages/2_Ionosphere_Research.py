"""
Ionosphere Research Report
===========================

VLF/ULF ionosphere research analysis for dual-channel antenna systems.
Focuses on scientific metrics, phenomena detection, and real-time processing capabilities.
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
import sys
import plotly.graph_objects as go

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_benchmark_data
from analysis.visualization import PerformancePlotter, VisualizationConfig
from analysis.metrics import assess_ionosphere_suitability

# Page configuration
st.set_page_config(page_title="Ionosphere Research", page_icon="🔬", layout="wide")

st.title("🔬 Ionosphere Research Report")

# Load data
try:
    data = load_benchmark_data("artifacts/data")
except FileNotFoundError:
    st.error("⚠️ No benchmark data found. Please run benchmarks first.")
    st.stop()
except Exception as e:
    st.error(f"❌ Error loading data: {e}")
    st.stop()

# Filter to dual-channel data (ionosphere antenna pair: E-W and N-S dipoles)
if 'engine_channels' in data.columns:
    dual_channel_data = data[data['engine_channels'] == 2].copy()

    if dual_channel_data.empty:
        st.warning(
            "⚠️ **No dual-channel (channels=2) data found.** "
            "Ionosphere report is designed for dual-channel antenna systems (E-W and N-S dipole pair). "
            "Please run ionosphere benchmarks with channels=2."
        )
        st.stop()

    n_filtered = len(data) - len(dual_channel_data)
    if n_filtered > 0:
        st.info(
            f"Filtered {n_filtered} non-dual-channel measurements. "
            f"Using {len(dual_channel_data)} dual-channel measurements for ionosphere analysis."
        )

    data = dual_channel_data
else:
    st.warning("'engine_channels' column not found in data. Proceeding without filtering.")

# Create tabs for major sections
tabs = st.tabs([
    "Introduction",
    "Scientific Metrics",
    "Real-Time Factor",
    "Resolution Trade-offs",
    "Phenomena Detection",
    "Streaming Performance",
    "Compliance & Reliability"
])

# Initialize plotter
plotter = PerformancePlotter(VisualizationConfig())

# ============================================================================
# TAB 1: INTRODUCTION
# ============================================================================
with tabs[0]:
    st.header("Introduction")

    st.markdown("""
    This report analyzes GPU benchmark results in the context of **VLF/ULF ionosphere research**.

    The ionosense system is designed for real-time monitoring of ionospheric phenomena including:

    - **Lightning and sprites:** Fast transients (<10ms time resolution required)
    - **Sudden Ionospheric Disturbances (SIDs):** Long-duration events requiring high frequency resolution
    - **Schumann resonances:** ~8Hz, 14Hz, 20Hz peaks requiring <1Hz frequency resolution
    - **Whistlers:** Dispersive signals requiring both time and frequency resolution

    ### Key Research Considerations

    - **Time Resolution:** Ability to capture fast transients and temporal evolution
    - **Frequency Resolution:** Spectral detail for phenomenon identification and characterization
    - **Real-Time Factor (RTF):** Processing capability for live monitoring (RTF > 1.0 required)
    - **Multi-Channel Support:** Direction finding and polarization analysis capabilities (dual-channel E-W/N-S dipole pair)
    """)

# ============================================================================
# TAB 2: SCIENTIFIC METRICS
# ============================================================================
with tabs[1]:
    st.header("Scientific Metrics Overview")

    st.subheader("Parameter Ranges Tested")

    col1, col2, col3 = st.columns(3)

    if 'time_resolution_ms' in data.columns:
        time_res_range = f"{data['time_resolution_ms'].min():.2f} - {data['time_resolution_ms'].max():.2f} ms"
        col1.metric(
            "Time Resolution",
            time_res_range,
            help="FFT frame duration - ability to resolve fast transients"
        )

    if 'freq_resolution_hz' in data.columns:
        freq_res_range = f"{data['freq_resolution_hz'].min():.3f} - {data['freq_resolution_hz'].max():.3f} Hz"
        col2.metric(
            "Frequency Resolution",
            freq_res_range,
            help="Spectral bin width - ability to resolve close frequencies"
        )

    if 'rtf' in data.columns:
        rtf_range = f"{data['rtf'].min():.2f} - {data['rtf'].max():.2f}"
        col3.metric("Real-Time Factor", rtf_range)

    if 'engine_overlap' in data.columns:
        st.divider()
        overlap_vals = sorted(data['engine_overlap'].unique())
        st.metric("Overlap Factors", ", ".join(f"{x:.3f}" for x in overlap_vals))

# ============================================================================
# TAB 3: REAL-TIME FACTOR ANALYSIS
# ============================================================================
with tabs[2]:
    st.header("Real-Time Factor Analysis")

    if 'rtf' not in data.columns:
        st.info("No RTF data available")
    else:
        rtf_stats = data['rtf'].describe()
        realtime_count = (data['rtf'] >= 1.0).sum()
        total_count = len(data)
        realtime_pct = (realtime_count / total_count) * 100

        st.subheader("Real-Time Processing Capability")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            "Mean RTF",
            f"{rtf_stats['mean']:.2f}x",
            help="Real-Time Factor - ratio of processing speed to data rate, >1.0 means faster than real-time"
        )
        col2.metric("Median RTF", f"{rtf_stats['50%']:.2f}x")
        col3.metric("Max RTF", f"{rtf_stats['max']:.2f}x")
        col4.metric("Real-Time Capable", f"{realtime_count}/{total_count} ({realtime_pct:.1f}%)")

        st.divider()

        st.markdown("### Interpretation")
        st.markdown("""
        - **RTF > 1.0:** Real-time processing capable
        - **RTF > 2.0:** Headroom for additional processing (e.g., beamforming)
        - **RTF < 1.0:** Cannot keep up with live data (offline processing only)
        """)

        # RTF scaling plot
        if 'engine_nfft' in data.columns:
            st.divider()
            st.subheader("RTF vs NFFT")

            fig = plotter.plot_scaling(
                data,
                x_col='engine_nfft',
                y_col='rtf',
                group_by='engine_overlap',
            )

            # Add threshold line
            fig.add_hline(
                y=1.0,
                line_dash="dash",
                line_color="red",
                annotation_text="Real-time threshold (RTF=1.0)",
                annotation_position="right"
            )

            st.plotly_chart(fig, width="stretch")

# ============================================================================
# TAB 4: RESOLUTION TRADE-OFFS
# ============================================================================
with tabs[3]:
    st.header("Time/Frequency Resolution Trade-offs")

    if 'time_resolution_ms' not in data.columns or 'freq_resolution_hz' not in data.columns:
        st.info("Insufficient data for resolution trade-off analysis")
    else:
        st.markdown("""
        ### Resolution Trade-off Space

        Time and frequency resolution are inversely related through the uncertainty principle:

        - **High Time Resolution (small NFFT):** Good for transients, poor frequency detail
        - **High Frequency Resolution (large NFFT):** Good spectral detail, slower temporal response
        """)

        st.divider()

        # Find best configs for different phenomena
        col1, col2 = st.columns(2)

        # Lightning/sprites: <10ms time res
        lightning_configs = data[data['time_resolution_ms'] < 10.0]
        if len(lightning_configs) > 0:
            best_lightning = lightning_configs.loc[lightning_configs['time_resolution_ms'].idxmin()]
            col1.success(
                f"**Best for Lightning/Sprites:** NFFT={int(best_lightning['engine_nfft'])}, "
                f"Time Res={best_lightning['time_resolution_ms']:.2f}ms"
            )

        # SIDs/Schumann: <1Hz freq res
        schumann_configs = data[data['freq_resolution_hz'] < 1.0]
        if len(schumann_configs) > 0:
            best_schumann = schumann_configs.loc[schumann_configs['freq_resolution_hz'].idxmin()]
            col2.success(
                f"**Best for SIDs/Schumann:** NFFT={int(best_schumann['engine_nfft'])}, "
                f"Freq Res={best_schumann['freq_resolution_hz']:.3f}Hz"
            )

        # Scatter plot
        st.divider()
        st.subheader("Resolution Trade-off Visualization")

        # Color by RTF if available
        color_col = 'rtf' if 'rtf' in data.columns else None

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=data['time_resolution_ms'],
            y=data['freq_resolution_hz'],
            mode='markers',
            marker=dict(
                size=10,
                color=data[color_col] if color_col else 'blue',
                colorscale='Viridis',
                showscale=True if color_col else False,
                colorbar=dict(title='RTF') if color_col else None,
            ),
            text=[
                f"NFFT: {row['engine_nfft']}<br>" +
                f"Overlap: {row['engine_overlap']:.3f}<br>" +
                (f"RTF: {row['rtf']:.2f}" if 'rtf' in data.columns else "")
                for _, row in data.iterrows()
            ],
            hovertemplate='%{text}<extra></extra>',
        ))

        # Add threshold lines
        fig.add_hline(
            y=1.0, line_dash="dash", line_color="red",
            annotation_text="Schumann threshold (<1Hz)",
            annotation_position="right"
        )
        fig.add_vline(
            x=10.0, line_dash="dash", line_color="orange",
            annotation_text="Lightning threshold (<10ms)",
            annotation_position="top"
        )

        fig.update_layout(
            title="Time vs Frequency Resolution Trade-off",
            xaxis_title="Time Resolution (ms)",
            yaxis_title="Frequency Resolution (Hz)",
            xaxis_type="log",
            yaxis_type="log",
            height=600,
        )

        st.plotly_chart(fig, width="stretch")

        st.caption(
            "📍 **Thresholds:** Red = Schumann resonances (<1Hz freq), "
            "Orange = Lightning/sprites (<10ms time)"
        )

# ============================================================================
# TAB 5: PHENOMENA DETECTION SUITABILITY
# ============================================================================
with tabs[4]:
    st.header("Phenomena Detection Suitability")

    if 'time_resolution_ms' not in data.columns or 'freq_resolution_hz' not in data.columns:
        st.info("Insufficient data for phenomena suitability analysis")
    else:
        st.markdown("""
        ### Configuration Suitability by Phenomenon Type

        This section evaluates which configurations meet the requirements for detecting
        specific ionosphere phenomena.
        """)

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

        # Display as metrics
        col1, col2, col3, col4, col5 = st.columns(5)

        col1.metric(
            "Lightning/Sprites",
            f"{suitability_counts['lightning_sprites']}/{total}",
            help="Fast transients (<10ms time resolution)"
        )
        col2.metric(
            "SIDs",
            f"{suitability_counts['sids']}/{total}",
            help="Narrowband VLF transmitter detection (<1Hz freq resolution)"
        )
        col3.metric(
            "Schumann",
            f"{suitability_counts['schumann_resonances']}/{total}",
            help="Earth resonance modes (<0.5Hz freq resolution)"
        )
        col4.metric(
            "Whistlers",
            f"{suitability_counts['whistlers']}/{total}",
            help="Dispersive VLF phenomena"
        )
        col5.metric(
            "General VLF",
            f"{suitability_counts['general_vlf']}/{total}",
            help="Broad VLF band monitoring"
        )

        # Detailed table
        st.divider()
        st.subheader("Configuration Suitability Details")

        suitability_data = []
        for _, row in data.iterrows():
            assessment = assess_ionosphere_suitability(
                row['time_resolution_ms'],
                row['freq_resolution_hz']
            )

            suitable_for = [k.replace('_', ' ').title() for k, v in assessment.items() if v['suitable']]

            suitability_data.append({
                'NFFT': int(row['engine_nfft']),
                'Overlap': f"{row['engine_overlap']:.3f}",
                'Time Res (ms)': f"{row['time_resolution_ms']:.2f}",
                'Freq Res (Hz)': f"{row['freq_resolution_hz']:.3f}",
                'Suitable For': ", ".join(suitable_for) if suitable_for else "None"
            })

        st.dataframe(
            pd.DataFrame(suitability_data),
            use_container_width=True,
            hide_index=True
        )

# ============================================================================
# TAB 6: STREAMING PERFORMANCE
# ============================================================================
with tabs[5]:
    st.header("Dual-Channel Streaming Performance")

    st.markdown("""
    ### Dual-Channel Antenna System

    The ionosense system uses a dual-channel configuration representing an **E-W and N-S dipole antenna pair**
    for direction finding and ionosphere monitoring.
    """)

    # Configuration summary
    nfft_values = sorted(data['engine_nfft'].unique())
    overlap_values = sorted(data['engine_overlap'].unique()) if 'engine_overlap' in data.columns else []

    st.subheader("Tested Configurations")

    col1, col2 = st.columns(2)
    col1.metric("NFFT Values", ", ".join(map(str, nfft_values)))
    col2.metric("Overlap Values", ", ".join(f"{x:.3f}" for x in overlap_values))

    # Performance metrics
    if 'frames_per_second' in data.columns or 'rtf' in data.columns:
        st.divider()
        st.subheader("Performance Summary")

        summary_data = []
        for nfft in nfft_values:
            nfft_data = data[data['engine_nfft'] == nfft]

            row_data = {'NFFT': int(nfft)}

            if 'frames_per_second' in nfft_data.columns:
                row_data['Mean FPS'] = f"{nfft_data['frames_per_second'].mean():.1f}"

            if 'rtf' in nfft_data.columns:
                row_data['Mean RTF'] = f"{nfft_data['rtf'].mean():.2f}x"

            if 'time_resolution_ms' in nfft_data.columns:
                row_data['Time Res (ms)'] = f"{nfft_data['time_resolution_ms'].iloc[0]:.2f}"

            if 'freq_resolution_hz' in nfft_data.columns:
                row_data['Freq Res (Hz)'] = f"{nfft_data['freq_resolution_hz'].iloc[0]:.3f}"

            summary_data.append(row_data)

        st.dataframe(
            pd.DataFrame(summary_data),
            use_container_width=True,
            hide_index=True
        )

# ============================================================================
# TAB 7: COMPLIANCE & RELIABILITY
# ============================================================================
with tabs[6]:
    st.header("Real-Time Compliance & Reliability")

    if 'deadline_compliance_rate' not in data.columns:
        st.info("No deadline compliance data available (streaming benchmark metrics)")
    else:
        st.markdown("""
        ### Deadline Compliance

        For real-time streaming, deadline compliance measures the ability to process frames
        within their required time window. Target: **>99% compliance** for stable operation.
        """)

        compliance_stats = data['deadline_compliance_rate'].describe()
        high_compliance = (data['deadline_compliance_rate'] >= 0.99).sum()

        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Mean Compliance",
            f"{compliance_stats['mean']*100:.1f}%",
            help="Fraction of frames processed within timing deadline - critical for real-time systems"
        )
        col2.metric("Min Compliance", f"{compliance_stats['min']*100:.1f}%")
        col3.metric("High Compliance Configs", f"{high_compliance}/{len(data)}")

        # Jitter analysis
        if 'mean_jitter_ms' in data.columns:
            st.divider()
            st.subheader("Timing Stability (Jitter)")

            jitter_stats = data['mean_jitter_ms'].describe()

            col1, col2 = st.columns(2)
            col1.metric(
                "Mean Jitter",
                f"{jitter_stats['mean']:.2f} ms",
                help="Timing variability between frames - lower means more consistent latency"
            )
            col2.metric("Jitter Range", f"{jitter_stats['min']:.2f} - {jitter_stats['max']:.2f} ms")

        if 'p99_jitter_ms' in data.columns:
            p99_jitter_stats = data['p99_jitter_ms'].describe()

            col1, col2 = st.columns(2)
            col1.metric("Average P99 Jitter", f"{p99_jitter_stats['mean']:.2f} ms")
            col2.metric("Max P99 Jitter", f"{p99_jitter_stats['max']:.2f} ms")

        # Frame drops
        if 'frames_dropped' in data.columns:
            st.divider()
            st.subheader("Data Loss Assessment")

            total_drops = data['frames_dropped'].sum()
            configs_with_drops = (data['frames_dropped'] > 0).sum()

            col1, col2 = st.columns(2)
            col1.metric("Total Frames Dropped", int(total_drops))
            col2.metric("Configurations with Drops", f"{configs_with_drops}/{len(data)}")

    # Streaming vs Batch comparison
    if 'engine_mode' in data.columns and len(data['engine_mode'].unique()) > 1:
        st.divider()
        st.subheader("Streaming vs Batch Mode Comparison")

        st.markdown("""
        Comparing **streaming executor** (real-time processing) vs **batch executor** (throughput-optimized).
        """)

        comparison_data = []
        for mode in ['streaming', 'batch']:
            mode_data = data[data['engine_mode'] == mode]
            if len(mode_data) == 0:
                continue

            row_data = {'Mode': mode.title(), 'Configs': len(mode_data)}

            if 'frames_per_second' in mode_data.columns:
                row_data['Mean FPS'] = f"{mode_data['frames_per_second'].mean():.1f}"

            if 'mean_latency_us' in mode_data.columns:
                row_data['Mean Latency (μs)'] = f"{mode_data['mean_latency_us'].mean():.1f}"

            if 'rtf' in mode_data.columns:
                row_data['Mean RTF'] = f"{mode_data['rtf'].mean():.2f}x"

            comparison_data.append(row_data)

        if comparison_data:
            st.dataframe(
                pd.DataFrame(comparison_data),
                use_container_width=True,
                hide_index=True
            )

# Footer
st.divider()
col1, col2 = st.columns(2)

# Download data
csv = data.to_csv(index=False)
col1.download_button(
    label="📥 Download Ionosphere Data (CSV)",
    data=csv,
    file_name=f"ionosphere_research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
    mime="text/csv",
)

# Report metadata
col2.caption(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
col2.caption(f"Dual-channel configurations analyzed: {len(data)}")
