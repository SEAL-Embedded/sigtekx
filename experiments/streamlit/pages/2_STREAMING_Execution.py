"""
STREAMING Execution Mode Analysis
==================================

Continuous real-time processing analysis (live monitoring, ring buffer management, deadline compliance).
"""

import sys
from pathlib import Path

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.visualization import PerformancePlotter, VisualizationConfig
from utils.data_loader import load_benchmark_data

# Page configuration
st.set_page_config(page_title="STREAMING Execution", page_icon="🔄", layout="wide")

# Badge
st.markdown("""
<div style="background-color: #2ca02c; color: white; padding: 10px; border-radius: 5px; text-align: center; margin-bottom: 20px;">
    <h3 style="margin: 0;">🔄 STREAMING MODE - Continuous Real-Time Processing</h3>
    <p style="margin: 5px 0 0 0; font-size: 14px;">Live monitoring • Ring buffer management • Deadline compliance</p>
</div>
""", unsafe_allow_html=True)

st.title("🔄 STREAMING Execution Mode Analysis")

# Load and filter data
try:
    data = load_benchmark_data("artifacts/data")

    # AUTOMATIC FILTER: STREAMING mode only
    # Defensive: check if column exists before filtering
    if 'engine_mode' in data.columns:
        streaming_data = data[data['engine_mode'] == 'streaming'].copy()
    else:
        st.warning("⚠️ engine_mode column missing. Showing all data. Please re-run benchmarks to get proper categorization.")
        streaming_data = data.copy()

    if len(streaming_data) == 0:
        st.warning("No STREAMING mode data found. Please run STREAMING mode benchmarks.")
        st.stop()

    st.info(f"📊 Analyzing **{len(streaming_data)} STREAMING mode configurations** (filtered from {len(data)} total)")

    # Create tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 Executive Summary",
        "🚀 Sustained Throughput",
        "✓ Real-Time Compliance",
        "⏱️ Streaming Latency",
        "📈 High-NFFT Streaming",
        "🔒 Reliability",
        "💡 Use Cases"
    ])

    with tab1:
        st.header("Executive Summary")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if 'rtf' in streaming_data.columns:
                realtime_capable = len(streaming_data[streaming_data['rtf'] <= 1.0])
                realtime_pct = (realtime_capable / len(streaming_data) * 100) if len(streaming_data) > 0 else 0
                st.metric("Real-Time Capable", f"{realtime_pct:.1f}%", help="RTF ≤ 1.0")

        with col2:
            if 'frames_per_second' in streaming_data.columns:
                peak_fps = streaming_data['frames_per_second'].max()
                st.metric("Peak Sustained FPS", f"{peak_fps:.1f}")

        with col3:
            if 'mean_latency_us' in streaming_data.columns:
                mean_latency = streaming_data['mean_latency_us'].mean()
                st.metric("Mean Latency", f"{mean_latency:.1f} μs")

        with col4:
            st.metric("Configurations", len(streaming_data))

        st.divider()

        st.subheader("What is STREAMING Mode?")
        st.markdown("""
        **STREAMING mode** enables continuous real-time processing with ring buffer management:

        - **Use Case**: Live monitoring, real-time analysis, continuous data streams
        - **Characteristics**:
          - Ring buffer management overhead
          - Deadline compliance tracking
          - Continuous frame flow
          - Real-time factor (RTF) critical
        - **Best For**:
          - Real-time monitoring systems
          - Live alert systems
          - Continuous data acquisition
          - Streaming applications
        """)

        # Real-time capability breakdown
        if 'rtf' in streaming_data.columns:
            st.subheader("Real-Time Capability Breakdown")

            rtf_bins = [
                ("Soft Real-Time (RTF ≤ 0.33)", streaming_data[streaming_data['rtf'] <= 0.33]),
                ("Real-Time (0.33 < RTF ≤ 1.0)", streaming_data[(streaming_data['rtf'] > 0.33) & (streaming_data['rtf'] <= 1.0)]),
                ("Near Real-Time (1.0 < RTF ≤ 2.0)", streaming_data[(streaming_data['rtf'] > 1.0) & (streaming_data['rtf'] <= 2.0)]),
                ("Not Real-Time (RTF > 2.0)", streaming_data[streaming_data['rtf'] > 2.0])
            ]

            col1, col2, col3, col4 = st.columns(4)
            for col, (label, subset) in zip([col1, col2, col3, col4], rtf_bins):
                count = len(subset)
                pct = (count / len(streaming_data) * 100) if len(streaming_data) > 0 else 0
                col.metric(label, f"{count} ({pct:.0f}%)")

    with tab2:
        st.header("Sustained Throughput")

        if 'frames_per_second' in streaming_data.columns:
            st.subheader("Sustained FPS in STREAMING Mode")

            # Only use engine_overlap for size if ALL values are valid (no NaNs)
            size_col = None
            if 'engine_overlap' in streaming_data.columns and streaming_data['engine_overlap'].notna().all():
                size_col = 'engine_overlap'

            fig = px.scatter(
                streaming_data,
                x='engine_nfft',
                y='frames_per_second',
                color='engine_channels' if 'engine_channels' in streaming_data.columns else None,
                size=size_col,
                log_x=True,
                title="STREAMING Mode Sustained Throughput",
                labels={
                    'engine_nfft': 'NFFT Size',
                    'frames_per_second': 'Sustained FPS',
                    'engine_channels': 'Channels'
                }
            )
            st.plotly_chart(fig, use_container_width=True)

            # Top streaming configs
            st.subheader("Top 10 Sustained Throughput Configurations")
            top_cols = ['engine_nfft', 'engine_channels', 'engine_overlap', 'frames_per_second']
            if 'rtf' in streaming_data.columns:
                top_cols.append('rtf')
            available_top_cols = [col for col in top_cols if col in streaming_data.columns]
            top_configs = streaming_data.nlargest(10, 'frames_per_second')[available_top_cols]
            st.dataframe(top_configs, use_container_width=True, hide_index=True)
        else:
            st.info("No sustained throughput data available")

    with tab3:
        st.header("Real-Time Compliance")

        if 'rtf' in streaming_data.columns:
            st.subheader("Real-Time Factor (RTF) Distribution")

            fig = px.histogram(
                streaming_data,
                x='rtf',
                nbins=50,
                title="RTF Distribution (Streaming Mode)",
                labels={'rtf': 'Real-Time Factor', 'count': 'Number of Configurations'}
            )

            # Add threshold lines
            fig.add_vline(x=1.0, line_dash="dash", line_color="red",
                         annotation_text="Real-Time Threshold (RTF=1.0)")
            fig.add_vline(x=0.33, line_dash="dash", line_color="green",
                         annotation_text="Soft Real-Time (RTF=0.33)")

            st.plotly_chart(fig, use_container_width=True)

            # RTF by NFFT
            st.subheader("RTF Scaling by NFFT")

            fig = px.box(
                streaming_data,
                x='engine_nfft',
                y='rtf',
                title="RTF by NFFT Size",
                labels={'engine_nfft': 'NFFT Size', 'rtf': 'Real-Time Factor'},
                log_x=True
            )

            fig.add_hline(y=1.0, line_dash="dash", line_color="red",
                         annotation_text="RTF=1.0")
            st.plotly_chart(fig, use_container_width=True)

            # Real-time capable configs by NFFT
            st.subheader("Real-Time Capability by NFFT")

            if 'engine_nfft' in streaming_data.columns:
                rtf_summary = streaming_data.groupby('engine_nfft').agg({
                    'rtf': ['mean', 'min', 'max', lambda x: (x <= 1.0).sum()],
                }).round(3)
                rtf_summary.columns = ['Mean RTF', 'Min RTF', 'Max RTF', 'RT Capable Count']
                st.dataframe(rtf_summary, use_container_width=True)
        else:
            st.info("No RTF data available")

    with tab4:
        st.header("Streaming Latency")

        if 'mean_latency_us' in streaming_data.columns:
            st.subheader("Latency in STREAMING Mode")

            fig = px.scatter(
                streaming_data,
                x='engine_nfft',
                y='mean_latency_us',
                color='rtf' if 'rtf' in streaming_data.columns else None,
                log_x=True,
                log_y=True,
                title="Streaming Latency vs NFFT",
                labels={
                    'engine_nfft': 'NFFT Size',
                    'mean_latency_us': 'Mean Latency (μs)',
                    'rtf': 'RTF'
                }
            )
            st.plotly_chart(fig, use_container_width=True)

            # Latency statistics
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Mean Latency", f"{streaming_data['mean_latency_us'].mean():.1f} μs")
            with col2:
                st.metric("Median Latency", f"{streaming_data['mean_latency_us'].median():.1f} μs")
            with col3:
                st.metric("Std Dev", f"{streaming_data['mean_latency_us'].std():.1f} μs")
        else:
            st.info("No latency data available")

    with tab5:
        st.header("High-NFFT Streaming")

        # Filter for high-NFFT configs (>= 16384)
        high_nfft_data = streaming_data[streaming_data['engine_nfft'] >= 16384] if 'engine_nfft' in streaming_data.columns else streaming_data[0:0]

        if len(high_nfft_data) > 0:
            st.subheader(f"High-Resolution Streaming Performance (NFFT ≥ 16384)")
            st.write(f"Found **{len(high_nfft_data)} high-NFFT streaming configurations**")

            if 'rtf' in high_nfft_data.columns:
                # RTF for high-NFFT streaming
                fig = px.bar(
                    high_nfft_data.sort_values('engine_nfft'),
                    x='engine_nfft',
                    y='rtf',
                    color='engine_overlap' if 'engine_overlap' in high_nfft_data.columns else None,
                    title="High-NFFT Streaming RTF (Schumann Resonance Capable)",
                    labels={'engine_nfft': 'NFFT Size', 'rtf': 'Real-Time Factor'}
                )

                fig.add_hline(y=1.0, line_dash="dash", line_color="red",
                             annotation_text="Real-Time Threshold")

                st.plotly_chart(fig, use_container_width=True)

                # Schumann-capable configs (NFFT >= 65536 with RTF <= 1.0)
                schumann_data = high_nfft_data[(high_nfft_data['engine_nfft'] >= 65536) & (high_nfft_data['rtf'] <= 1.0)]
                if len(schumann_data) > 0:
                    st.success(f"✅ **{len(schumann_data)} configurations** capable of real-time Schumann resonance detection (NFFT ≥ 65536, RTF ≤ 1.0)")
                    schumann_cols = ['engine_nfft', 'engine_channels', 'engine_overlap', 'rtf']
                    if 'mean_latency_us' in schumann_data.columns:
                        schumann_cols.append('mean_latency_us')
                    st.dataframe(schumann_data[schumann_cols],
                               use_container_width=True, hide_index=True)
                else:
                    st.warning("No configurations capable of real-time Schumann detection (NFFT ≥ 65536 with RTF ≤ 1.0)")
            else:
                st.info("RTF data not available for high-NFFT analysis. Please re-run benchmarks.")

            # High-NFFT table
            st.subheader("All High-NFFT Streaming Configurations")
            high_nfft_cols = ['engine_nfft', 'engine_channels', 'engine_overlap', 'rtf', 'frames_per_second', 'mean_latency_us']
            available_cols = [col for col in high_nfft_cols if col in high_nfft_data.columns]
            st.dataframe(high_nfft_data[available_cols].sort_values('engine_nfft'),
                       use_container_width=True, hide_index=True)
        else:
            st.info("No high-NFFT streaming data (NFFT ≥ 16384) available yet. Run ionosphere_streaming_hires experiment.")

    with tab6:
        st.header("Reliability & Stability")

        # Frame drops
        if 'frames_dropped' in streaming_data.columns:
            st.subheader("Frame Drops (Data Loss)")

            total_drops = streaming_data['frames_dropped'].sum()
            configs_with_drops = len(streaming_data[streaming_data['frames_dropped'] > 0])

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Frame Drops", int(total_drops))
            with col2:
                st.metric("Configs with Drops", configs_with_drops)

            if configs_with_drops > 0:
                st.warning("Some configurations experienced frame drops - review reliability")
                drops_data = streaming_data[streaming_data['frames_dropped'] > 0]
                st.dataframe(drops_data[['engine_nfft', 'engine_channels', 'frames_dropped']],
                           use_container_width=True, hide_index=True)
            else:
                st.success("✅ Zero frame drops across all configurations - excellent reliability")

        # Timing stability (CV)
        if 'frame_time_cv' in streaming_data.columns:
            st.subheader("Timing Stability (Coefficient of Variation)")

            stable_configs = len(streaming_data[streaming_data['frame_time_cv'] <= 0.10])
            stable_pct = (stable_configs / len(streaming_data) * 100) if len(streaming_data) > 0 else 0

            st.metric("Stable Configs (CV ≤ 10%)", f"{stable_configs} ({stable_pct:.0f}%)")

            fig = px.histogram(
                streaming_data,
                x='frame_time_cv',
                nbins=30,
                title="Frame Time Stability Distribution",
                labels={'frame_time_cv': 'Coefficient of Variation', 'count': 'Configurations'}
            )
            fig.add_vline(x=0.10, line_dash="dash", line_color="green",
                         annotation_text="Stable (CV=0.10)")
            st.plotly_chart(fig, use_container_width=True)

    with tab7:
        st.header("Use Cases & Recommendations")

        st.subheader("When to Use STREAMING Mode")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("""
            **✅ Ideal For:**
            - Live monitoring systems
            - Real-time alert systems
            - Continuous data streams
            - Deadline-critical applications
            - Live visualization
            - Direction finding (continuous)
            """)

        with col2:
            st.markdown("""
            **❌ Not Suitable For:**
            - Offline file processing
            - Maximum throughput scenarios
            - Post-processing recorded data
            - Benchmarking peak performance
            """)

        st.divider()

        st.subheader("Optimal Real-Time Configurations")

        if 'rtf' in streaming_data.columns:
            # Best RTF configs
            realtime_configs = streaming_data[streaming_data['rtf'] <= 1.0]

            if len(realtime_configs) > 0:
                st.markdown("**Best Real-Time Configurations (RTF ≤ 1.0):**")
                best_rtf = realtime_configs.nsmallest(5, 'rtf')

                for idx, row in best_rtf.iterrows():
                    st.write(f"- NFFT={row.get('engine_nfft', 'N/A')}, "
                            f"Channels={row.get('engine_channels', 'N/A')}, "
                            f"Overlap={row.get('engine_overlap', 'N/A'):.3f} "
                            f"→ RTF={row['rtf']:.3f}")
            else:
                st.warning("No real-time capable configurations (RTF ≤ 1.0) found")

except FileNotFoundError:
    st.error("No benchmark data found. Please run benchmarks first.")
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.exception(e)
