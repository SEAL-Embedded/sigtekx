"""
Ionosphere Application Analysis
================================

48kHz dual-channel VLF/ULF phenomena detection (STREAMING mode focused).
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_benchmark_data

# Page configuration
st.set_page_config(page_title="Ionosphere Application", page_icon="🌐", layout="wide")

# Badge
st.markdown("""
<div style="background-color: #ff7f0e; color: white; padding: 10px; border-radius: 5px; text-align: center; margin-bottom: 20px;">
    <h3 style="margin: 0;">🌐 IONOSPHERE APPLICATION - 48kHz Dual-Channel</h3>
    <p style="margin: 5px 0 0 0; font-size: 14px;">VLF/ULF Phenomena Detection • E-W + N-S Dipoles • Real-Time Monitoring</p>
</div>
""", unsafe_allow_html=True)

st.title("🌐 Ionosphere Application Analysis")

# Load and filter data
try:
    data = load_benchmark_data("artifacts/data")

    # AUTOMATIC FILTER: 48kHz AND 2 channels (dual-antenna system)
    iono_data = data[
        (data['sample_rate_category'] == '48kHz') &
        (data['engine_channels'] == 2)
    ].copy()

    if len(iono_data) == 0:
        st.warning("No 48kHz dual-channel data found. Please run ionosphere experiments.")
        st.stop()

    st.info(f"📊 Analyzing **{len(iono_data)} ionosphere configurations** (48kHz, 2-channel, filtered from {len(data)} total)")

    # Add derived scientific metrics
    if 'engine_nfft' in iono_data.columns and 'engine_overlap' in iono_data.columns:
        sample_rate = 48000
        iono_data['freq_resolution_hz'] = sample_rate / iono_data['engine_nfft']
        iono_data['time_resolution_ms'] = (iono_data['engine_nfft'] / sample_rate) * 1000
        iono_data['hop_size'] = (iono_data['engine_nfft'] * (1 - iono_data['engine_overlap'])).astype(int)

    # Create tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview",
        "🎯 Phenomena Detection",
        "📈 Resolution Trade-Offs",
        "⏱️ Real-Time Performance",
        "🔬 Scientific Metrics"
    ])

    with tab1:
        st.header("Ionosphere Monitoring Overview")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Configurations", len(iono_data))

        with col2:
            if 'engine_mode' in iono_data.columns:
                streaming_count = len(iono_data[iono_data['engine_mode'] == 'streaming'])
                st.metric("STREAMING Mode", streaming_count)

        with col3:
            if 'freq_resolution_hz' in iono_data.columns:
                best_freq_res = iono_data['freq_resolution_hz'].min()
                st.metric("Best Freq Resolution", f"{best_freq_res:.3f} Hz")

        with col4:
            if 'rtf' in iono_data.columns:
                realtime_capable = len(iono_data[iono_data['rtf'] <= 1.0])
                st.metric("Real-Time Capable", realtime_capable)

        st.divider()

        st.subheader("🌐 VLF/ULF Ionosphere Monitoring System")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("""
            **System Configuration:**
            - **Sample Rate**: 48 kHz
            - **Channels**: 2 (Dual-antenna)
            - **Antenna Array**: E-W + N-S dipoles
            - **Primary Mode**: STREAMING (real-time)
            - **Application**: VLF/ULF phenomena detection
            """)

        with col2:
            st.markdown("""
            **Target Phenomena:**
            - **Lightning/Sprites**: <10ms time resolution
            - **SIDs**: <1Hz frequency resolution
            - **Schumann Resonances**: <0.5Hz frequency resolution (7.8Hz, 14Hz, 20Hz)
            - **Whistlers**: Dispersive VLF signals
            - **General VLF**: 3-30kHz monitoring
            """)

        # Mode breakdown
        if 'engine_mode' in iono_data.columns:
            st.subheader("Execution Mode Breakdown")

            mode_counts = iono_data['engine_mode'].value_counts()
            fig = px.pie(
                values=mode_counts.values,
                names=mode_counts.index,
                title="Ionosphere Configs by Execution Mode"
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.header("Phenomena Detection Capability")

        st.subheader("Detection Requirements")

        # Create phenomena requirements table
        phenomena_requirements = pd.DataFrame([
            {"Phenomenon": "Lightning/Sprites", "Freq Band": "Broadband", "Time Resolution": "<10ms", "Freq Resolution": "Any", "NFFT Range": "256-2048"},
            {"Phenomenon": "SIDs", "Freq Band": "VLF (3-30kHz)", "Time Resolution": "Any", "Freq Resolution": "<1Hz", "NFFT Range": "4096-16384"},
            {"Phenomenon": "Schumann Resonances", "Freq Band": "ELF (7.8, 14, 20Hz)", "Time Resolution": "Any", "Freq Resolution": "<0.5Hz", "NFFT Range": "65536-131072"},
            {"Phenomenon": "Whistlers", "Freq Band": "VLF (1-30kHz)", "Time Resolution": "<100ms", "Freq Resolution": "<100Hz", "NFFT Range": "512-4096"},
        ])

        st.dataframe(phenomena_requirements, use_container_width=True, hide_index=True)

        # Configuration suitability assessment
        if all(col in iono_data.columns for col in ['freq_resolution_hz', 'time_resolution_ms', 'engine_nfft']):
            st.subheader("Configuration Suitability Matrix")

            # Assess each config
            def assess_suitability(row):
                suitable_for = []

                # Lightning/sprites: <10ms time resolution
                if row['time_resolution_ms'] < 10:
                    suitable_for.append("Lightning/Sprites")

                # SIDs: <1Hz freq resolution
                if row['freq_resolution_hz'] < 1.0:
                    suitable_for.append("SIDs")

                # Schumann: <0.5Hz freq resolution
                if row['freq_resolution_hz'] < 0.5:
                    suitable_for.append("Schumann")

                # Whistlers: <100ms time, <100Hz freq
                if row['time_resolution_ms'] < 100 and row['freq_resolution_hz'] < 100:
                    suitable_for.append("Whistlers")

                return ", ".join(suitable_for) if suitable_for else "General VLF"

            iono_data['suitable_phenomena'] = iono_data.apply(assess_suitability, axis=1)

            # Summary by NFFT
            suitability_summary = iono_data.groupby('engine_nfft').agg({
                'suitable_phenomena': lambda x: x.mode()[0] if len(x.mode()) > 0 else "N/A",
                'freq_resolution_hz': 'mean',
                'time_resolution_ms': 'mean',
                'rtf': 'mean' if 'rtf' in iono_data.columns else lambda x: None
            }).round(3)

            suitability_summary.columns = ['Primary Phenomena', 'Freq Res (Hz)', 'Time Res (ms)', 'Mean RTF']
            st.dataframe(suitability_summary, use_container_width=True)

            # Phenomena counts
            st.subheader("Configurations by Phenomena")

            phenomena_counts = iono_data['suitable_phenomena'].value_counts()
            fig = px.bar(
                x=phenomena_counts.index,
                y=phenomena_counts.values,
                title="Number of Configurations Suitable for Each Phenomenon",
                labels={'x': 'Phenomena', 'y': 'Configuration Count'}
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.header("Resolution Trade-Offs")

        if all(col in iono_data.columns for col in ['time_resolution_ms', 'freq_resolution_hz']):
            st.subheader("Time vs Frequency Resolution")

            fig = go.Figure()

            # Scatter plot colored by RTF (if available) or NFFT
            color_col = 'rtf' if 'rtf' in iono_data.columns else 'engine_nfft'

            fig.add_trace(go.Scatter(
                x=iono_data['time_resolution_ms'],
                y=iono_data['freq_resolution_hz'],
                mode='markers',
                marker=dict(
                    size=10,
                    color=iono_data[color_col],
                    colorscale='Viridis',
                    showscale=True,
                    colorbar=dict(title=color_col.upper() if color_col == 'rtf' else 'NFFT'),
                ),
                text=[
                    f"NFFT: {row['engine_nfft']}<br>"
                    f"Overlap: {row['engine_overlap']:.3f}<br>"
                    f"Mode: {row.get('engine_mode', 'N/A')}"
                    for _, row in iono_data.iterrows()
                ],
                hovertemplate='%{text}<extra></extra>',
            ))

            # Add threshold lines for phenomena
            fig.add_hline(y=1.0, line_dash="dash", line_color="red",
                         annotation_text="SID threshold (<1Hz)", annotation_position="right")
            fig.add_hline(y=0.5, line_dash="dash", line_color="orange",
                         annotation_text="Schumann threshold (<0.5Hz)", annotation_position="right")
            fig.add_vline(x=10.0, line_dash="dash", line_color="green",
                         annotation_text="Lightning threshold (<10ms)", annotation_position="top")

            fig.update_layout(
                title="Resolution Trade-off Space (48kHz Ionosphere)",
                xaxis_title="Time Resolution (ms)",
                yaxis_title="Frequency Resolution (Hz)",
                xaxis_type="log",
                yaxis_type="log",
                height=600,
            )

            st.plotly_chart(fig, use_container_width=True)

            st.caption(
                "📍 **Detection Thresholds**: "
                "Red = SIDs (<1Hz), Orange = Schumann (<0.5Hz), Green = Lightning (<10ms)"
            )

            # Optimal configs by phenomenon
            st.subheader("Optimal Configurations by Phenomenon")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Fast Transients (Lightning/Sprites):**")
                fast_configs = iono_data.nsmallest(3, 'time_resolution_ms')
                for _, row in fast_configs.iterrows():
                    st.write(f"- NFFT={row['engine_nfft']}, Overlap={row['engine_overlap']:.3f} "
                            f"→ {row['time_resolution_ms']:.2f}ms")

            with col2:
                st.markdown("**High Freq Resolution (Schumann):**")
                hires_configs = iono_data.nsmallest(3, 'freq_resolution_hz')
                for _, row in hires_configs.iterrows():
                    st.write(f"- NFFT={row['engine_nfft']}, Overlap={row['engine_overlap']:.3f} "
                            f"→ {row['freq_resolution_hz']:.3f}Hz")

    with tab4:
        st.header("Real-Time Monitoring Performance")

        # Filter for STREAMING mode
        streaming_iono = iono_data[iono_data['engine_mode'] == 'streaming'] if 'engine_mode' in iono_data.columns else iono_data

        if len(streaming_iono) > 0 and 'rtf' in streaming_iono.columns:
            st.subheader("Real-Time Capability (STREAMING Mode)")

            col1, col2, col3 = st.columns(3)

            realtime_capable = len(streaming_iono[streaming_iono['rtf'] <= 1.0])
            soft_realtime = len(streaming_iono[streaming_iono['rtf'] <= 0.33])

            with col1:
                st.metric("Real-Time Configs (RTF ≤ 1.0)", realtime_capable)
            with col2:
                st.metric("Soft Real-Time (RTF ≤ 0.33)", soft_realtime)
            with col3:
                mean_rtf = streaming_iono['rtf'].mean()
                st.metric("Mean RTF", f"{mean_rtf:.2f}")

            # RTF by NFFT
            fig = px.bar(
                streaming_iono.groupby('engine_nfft')['rtf'].mean().reset_index(),
                x='engine_nfft',
                y='rtf',
                title="Mean RTF by NFFT (Ionosphere STREAMING)",
                labels={'engine_nfft': 'NFFT Size', 'rtf': 'Mean Real-Time Factor'}
            )

            fig.add_hline(y=1.0, line_dash="dash", line_color="red",
                         annotation_text="Real-Time Threshold")
            fig.add_hline(y=0.33, line_dash="dash", line_color="green",
                         annotation_text="Soft Real-Time Target")

            st.plotly_chart(fig, use_container_width=True)

            # Real-time capable configs table
            st.subheader("Real-Time Capable Configurations")

            if realtime_capable > 0:
                rt_configs = streaming_iono[streaming_iono['rtf'] <= 1.0].sort_values('rtf')
                rt_cols = ['engine_nfft', 'engine_overlap', 'rtf', 'frames_per_second', 'freq_resolution_hz', 'time_resolution_ms']
                available_cols = [col for col in rt_cols if col in rt_configs.columns]
                st.dataframe(rt_configs[available_cols], use_container_width=True, hide_index=True)
            else:
                st.warning("No real-time capable configurations found (RTF ≤ 1.0)")
        else:
            st.info("No STREAMING mode data available for real-time analysis")

    with tab5:
        st.header("Scientific Metrics")

        if all(col in iono_data.columns for col in ['freq_resolution_hz', 'time_resolution_ms', 'hop_size']):
            st.subheader("Spectral Analysis Parameters")

            # Summary statistics
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**Frequency Resolution**")
                st.write(f"Min: {iono_data['freq_resolution_hz'].min():.3f} Hz")
                st.write(f"Max: {iono_data['freq_resolution_hz'].max():.1f} Hz")
                st.write(f"Mean: {iono_data['freq_resolution_hz'].mean():.2f} Hz")

            with col2:
                st.markdown("**Time Resolution**")
                st.write(f"Min: {iono_data['time_resolution_ms'].min():.2f} ms")
                st.write(f"Max: {iono_data['time_resolution_ms'].max():.1f} ms")
                st.write(f"Mean: {iono_data['time_resolution_ms'].mean():.1f} ms")

            with col3:
                st.markdown("**Hop Size (samples)**")
                st.write(f"Min: {iono_data['hop_size'].min()} samples")
                st.write(f"Max: {iono_data['hop_size'].max()} samples")
                st.write(f"Mean: {iono_data['hop_size'].mean():.0f} samples")

            st.divider()

            # Detailed metrics table
            st.subheader("Complete Scientific Metrics by NFFT")

            metrics_by_nfft = iono_data.groupby('engine_nfft').agg({
                'freq_resolution_hz': 'mean',
                'time_resolution_ms': 'mean',
                'hop_size': 'mean',
                'engine_overlap': 'mean',
                'rtf': 'mean' if 'rtf' in iono_data.columns else lambda x: None
            }).round(3)

            metrics_by_nfft.columns = ['Freq Res (Hz)', 'Time Res (ms)', 'Hop Size (samples)', 'Mean Overlap', 'Mean RTF']
            st.dataframe(metrics_by_nfft, use_container_width=True)

            # Schumann harmonics detection capability
            st.subheader("Schumann Resonance Detection Capability")

            schumann_harmonics = [7.8, 14.3, 20.8, 27.3, 33.8]  # Hz
            st.write(f"**Target Harmonics**: {', '.join(f'{h}Hz' for h in schumann_harmonics)}")

            # Configs capable of resolving Schumann
            schumann_capable = iono_data[iono_data['freq_resolution_hz'] < 0.5]

            if len(schumann_capable) > 0:
                st.success(f"✅ **{len(schumann_capable)} configurations** capable of Schumann resonance detection (<0.5Hz resolution)")

                schumann_cols = ['engine_nfft', 'engine_overlap', 'freq_resolution_hz', 'time_resolution_ms', 'rtf']
                available_cols = [col for col in schumann_cols if col in schumann_capable.columns]
                st.dataframe(schumann_capable[available_cols], use_container_width=True, hide_index=True)
            else:
                st.warning("No configurations with sufficient frequency resolution for Schumann detection (<0.5Hz)")

except FileNotFoundError:
    st.error("No benchmark data found. Please run benchmarks first.")
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.exception(e)
