"""
BATCH Execution Mode Analysis
==============================

Discrete frame processing analysis (offline, maximum throughput, no ring buffer overhead).
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
st.set_page_config(page_title="BATCH Execution", page_icon="⚡", layout="wide")

# Badge
st.markdown("""
<div style="background-color: #1f77b4; color: white; padding: 10px; border-radius: 5px; text-align: center; margin-bottom: 20px;">
    <h3 style="margin: 0;">⚡ BATCH MODE - Discrete Frame Processing</h3>
    <p style="margin: 5px 0 0 0; font-size: 14px;">Offline processing • Maximum throughput • Zero ring buffer overhead</p>
</div>
""", unsafe_allow_html=True)

st.title("⚡ BATCH Execution Mode Analysis")

# Load and filter data
try:
    data = load_benchmark_data("artifacts/data")

    # AUTOMATIC FILTER: BATCH mode only
    batch_data = data[data['engine_mode'] == 'batch'].copy()

    if len(batch_data) == 0:
        st.warning("No BATCH mode data found. Please run BATCH mode benchmarks.")
        st.stop()

    st.info(f"📊 Analyzing **{len(batch_data)} BATCH mode configurations** (filtered from {len(data)} total)")

    # Create tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Executive Summary",
        "🚀 Throughput",
        "⏱️ Latency",
        "📈 Scaling",
        "✓ Accuracy",
        "💡 Use Cases"
    ])

    with tab1:
        st.header("Executive Summary")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if 'frames_per_second' in batch_data.columns:
                peak_fps = batch_data['frames_per_second'].max()
                st.metric("Peak Throughput", f"{peak_fps:.1f} FPS")

        with col2:
            if 'mean_latency_us' in batch_data.columns:
                min_latency = batch_data['mean_latency_us'].min()
                st.metric("Lowest Latency", f"{min_latency:.1f} μs")

        with col3:
            st.metric("Configurations", len(batch_data))

        with col4:
            if 'engine_nfft' in batch_data.columns:
                nfft_range = f"{batch_data['engine_nfft'].min()}-{batch_data['engine_nfft'].max()}"
                st.metric("NFFT Range", nfft_range)

        st.divider()

        st.subheader("What is BATCH Mode?")
        st.markdown("""
        **BATCH mode** processes discrete frames without ring buffer management:

        - **Use Case**: Offline analysis, post-processing, maximum throughput scenarios
        - **Characteristics**:
          - No ring buffer overhead
          - Maximum processing speed
          - Typically zero overlap
          - Discrete frame boundaries
        - **Best For**:
          - Offline file processing
          - Benchmarking maximum performance
          - Non-real-time applications
        """)

    with tab2:
        st.header("Throughput Analysis")

        if 'frames_per_second' in batch_data.columns:
            # Throughput by NFFT
            st.subheader("Throughput Scaling by NFFT")

            # Only use gb_per_second for size if ALL values are valid (no NaNs)
            size_col = None
            if 'gb_per_second' in batch_data.columns and batch_data['gb_per_second'].notna().all():
                size_col = 'gb_per_second'

            fig = px.scatter(
                batch_data,
                x='engine_nfft',
                y='frames_per_second',
                color='engine_channels' if 'engine_channels' in batch_data.columns else None,
                size=size_col,
                log_x=True,
                title="BATCH Mode Throughput vs NFFT",
                labels={
                    'engine_nfft': 'NFFT Size',
                    'frames_per_second': 'Throughput (FPS)',
                    'engine_channels': 'Channels'
                }
            )
            st.plotly_chart(fig, use_container_width=True)

            # Top configurations
            st.subheader("Top 10 Throughput Configurations")
            top_configs = batch_data.nlargest(10, 'frames_per_second')[
                ['engine_nfft', 'engine_channels', 'engine_overlap', 'frames_per_second', 'gb_per_second']
            ]
            st.dataframe(top_configs, use_container_width=True, hide_index=True)
        else:
            st.info("No throughput data available")

    with tab3:
        st.header("Latency Analysis")

        if 'mean_latency_us' in batch_data.columns:
            # Latency by NFFT
            st.subheader("Latency Scaling by NFFT")

            fig = px.scatter(
                batch_data,
                x='engine_nfft',
                y='mean_latency_us',
                color='engine_channels' if 'engine_channels' in batch_data.columns else None,
                log_x=True,
                log_y=True,
                title="BATCH Mode Latency vs NFFT",
                labels={
                    'engine_nfft': 'NFFT Size',
                    'mean_latency_us': 'Mean Latency (μs)',
                    'engine_channels': 'Channels'
                }
            )
            st.plotly_chart(fig, use_container_width=True)

            # Latency statistics
            st.subheader("Latency Statistics")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Mean", f"{batch_data['mean_latency_us'].mean():.1f} μs")
            with col2:
                st.metric("Median", f"{batch_data['mean_latency_us'].median():.1f} μs")
            with col3:
                st.metric("Std Dev", f"{batch_data['mean_latency_us'].std():.1f} μs")
        else:
            st.info("No latency data available")

    with tab4:
        st.header("Scaling Analysis")

        st.subheader("Parameter Space Coverage")

        col1, col2, col3 = st.columns(3)

        with col1:
            if 'engine_nfft' in batch_data.columns:
                nfft_values = sorted(batch_data['engine_nfft'].unique())
                st.write("**NFFT Values:**")
                st.write(", ".join(map(str, nfft_values)))

        with col2:
            if 'engine_channels' in batch_data.columns:
                channel_values = sorted(batch_data['engine_channels'].unique())
                st.write("**Channel Counts:**")
                st.write(", ".join(map(str, channel_values)))

        with col3:
            if 'engine_overlap' in batch_data.columns:
                overlap_values = sorted(batch_data['engine_overlap'].unique())
                st.write("**Overlap Values:**")
                st.write(", ".join(f"{v:.3f}" for v in overlap_values))

        # Heatmap if we have throughput data
        if all(col in batch_data.columns for col in ['engine_nfft', 'engine_channels', 'frames_per_second']):
            st.subheader("Throughput Heatmap (NFFT × Channels)")

            pivot = batch_data.pivot_table(
                values='frames_per_second',
                index='engine_channels',
                columns='engine_nfft',
                aggfunc='mean'
            )

            # Convert to categorical labels for even spacing
            x_labels = [str(int(x)) for x in pivot.columns]
            y_labels = [str(int(y)) for y in pivot.index]

            # Dynamic height based on number of rows (50px per row, min 400px)
            heatmap_height = max(400, len(pivot.index) * 50)

            fig = go.Figure(data=go.Heatmap(
                z=pivot.values,
                x=x_labels,
                y=y_labels,
                colorscale='Viridis',
                text=pivot.values,
                texttemplate='%{text:.1f}',
                textfont={"size": 10},
                colorbar=dict(title="FPS"),
                hovertemplate='NFFT: %{x}<br>Channels: %{y}<br>Throughput: %{z:.1f} FPS<extra></extra>'
            ))

            fig.update_layout(
                title="Mean Throughput by NFFT and Channels",
                xaxis_title="NFFT Size",
                yaxis_title="Channel Count",
                xaxis=dict(type='category'),  # Even spacing for x-axis
                yaxis=dict(type='category'),  # Even spacing for y-axis
                height=heatmap_height
            )

            st.plotly_chart(fig, use_container_width=True)

            # Show missing configurations if any NaN values
            nan_count = pivot.isna().sum().sum()
            if nan_count > 0:
                st.info(f"ℹ️ {nan_count} configuration(s) missing throughput data. Run additional batch throughput experiments to fill gaps.")

    with tab5:
        st.header("Accuracy Validation")

        # Filter for accuracy data
        accuracy_data = batch_data[batch_data['benchmark_type'] == 'accuracy']

        if len(accuracy_data) > 0 and 'pass_rate' in accuracy_data.columns:
            st.subheader("BATCH Mode Numerical Correctness")

            col1, col2, col3 = st.columns(3)

            with col1:
                mean_pass_rate = accuracy_data['pass_rate'].mean() * 100
                st.metric("Mean Pass Rate", f"{mean_pass_rate:.1f}%")

            with col2:
                min_pass_rate = accuracy_data['pass_rate'].min() * 100
                st.metric("Min Pass Rate", f"{min_pass_rate:.1f}%")

            with col3:
                configs_pass = len(accuracy_data[accuracy_data['pass_rate'] >= 0.99])
                st.metric("Configs with ≥99%", configs_pass)

            # Pass rate by NFFT
            if 'engine_nfft' in accuracy_data.columns:
                fig = px.bar(
                    accuracy_data,
                    x='engine_nfft',
                    y='pass_rate',
                    title="Accuracy Pass Rate by NFFT",
                    labels={'engine_nfft': 'NFFT Size', 'pass_rate': 'Pass Rate'},
                )
                fig.update_yaxes(range=[0, 1])
                st.plotly_chart(fig, use_container_width=True)

            # Accuracy table
            st.subheader("Accuracy Details")
            accuracy_cols = ['engine_nfft', 'engine_channels', 'pass_rate', 'mean_snr_db', 'mean_error']
            available_cols = [col for col in accuracy_cols if col in accuracy_data.columns]
            st.dataframe(accuracy_data[available_cols], use_container_width=True, hide_index=True)
        else:
            st.info("No accuracy validation data available for BATCH mode")

    with tab6:
        st.header("Use Cases & Recommendations")

        st.subheader("When to Use BATCH Mode")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("""
            **✅ Ideal For:**
            - Offline file processing
            - Post-processing recorded data
            - Maximum throughput scenarios
            - Benchmarking peak performance
            - Non-real-time applications
            - Archival data analysis
            """)

        with col2:
            st.markdown("""
            **❌ Not Suitable For:**
            - Real-time monitoring
            - Live data streaming
            - Continuous processing
            - Deadline-critical applications
            - Ring buffer management scenarios
            """)

        st.divider()

        st.subheader("Optimal Configurations")

        if 'frames_per_second' in batch_data.columns:
            # High throughput configs
            st.markdown("**High Throughput (Top 3):**")
            top_3 = batch_data.nlargest(3, 'frames_per_second')
            for idx, row in top_3.iterrows():
                st.write(f"- NFFT={row.get('engine_nfft', 'N/A')}, "
                        f"Channels={row.get('engine_channels', 'N/A')}, "
                        f"Overlap={row.get('engine_overlap', 'N/A'):.3f} "
                        f"→ {row['frames_per_second']:.1f} FPS")

        if 'mean_latency_us' in batch_data.columns:
            # Low latency configs
            st.markdown("**Low Latency (Top 3):**")
            low_lat = batch_data.nsmallest(3, 'mean_latency_us')
            for idx, row in low_lat.iterrows():
                st.write(f"- NFFT={row.get('engine_nfft', 'N/A')}, "
                        f"Channels={row.get('engine_channels', 'N/A')}, "
                        f"Overlap={row.get('engine_overlap', 'N/A'):.3f} "
                        f"→ {row['mean_latency_us']:.1f} μs")

except FileNotFoundError:
    st.error("No benchmark data found. Please run benchmarks first.")
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.exception(e)
