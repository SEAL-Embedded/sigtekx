"""
BATCH Execution Mode Analysis
==============================

Discrete frame processing analysis (offline, maximum throughput, no ring buffer overhead).
"""

import sys
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_selected_datasets
from utils.dataset_registry import render_sidebar_picker

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
render_sidebar_picker()

try:
    data = load_selected_datasets()
    if "dataset" in data.columns and data["dataset"].nunique() > 1:
        names = ", ".join(sorted(data["dataset"].unique()))
        st.info(f"Comparing datasets: {names} (rows tagged by dataset column)")

    # AUTOMATIC FILTER: BATCH mode only
    batch_data = data[data['engine_mode'] == 'batch'].copy()

    if len(batch_data) == 0:
        st.warning("No BATCH mode data found. Please run BATCH mode benchmarks.")
        st.stop()

    st.info(f"📊 Analyzing **{len(batch_data)} BATCH mode configurations** (filtered from {len(data)} total)")

    # Create tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 Executive Summary",
        "🚀 Throughput",
        "⏱️ Latency",
        "📈 Scaling",
        "✓ Accuracy",
        "💡 Use Cases",
        "⚙️ Stage Breakdown"
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

    with tab7:
        st.header("⚙️ Per-Stage Performance Breakdown")

        # Check if stage metrics are available
        stage_cols = ['stage_window_us', 'stage_fft_us', 'stage_magnitude_us',
                      'stage_overhead_us', 'stage_total_measured_us', 'stage_metrics_enabled']
        has_stage_metrics = all(col in batch_data.columns for col in stage_cols)

        if not has_stage_metrics:
            st.warning("""
            **No stage metrics data available.**

            To collect per-stage timing data:
            1. Run benchmarks with `measure_components=true` in your config
            2. Example: `python benchmarks/run_latency.py +benchmark=profiling experiment=baseline_batch_48k_latency`

            Note: Stage metrics add ~1-2µs overhead per stage and are only available in BATCH mode.
            """)
        else:
            # Filter to only configs with stage metrics enabled
            stage_data = batch_data[batch_data['stage_metrics_enabled'] == True].copy()

            if len(stage_data) == 0:
                st.info("""
                No configurations found with stage metrics enabled.

                Run benchmarks with `measure_components: true` to collect stage timing data.
                """)
            else:
                st.success(f"📊 Analyzing **{len(stage_data)} configurations** with component timing enabled")

                # Performance insights panel
                st.subheader("Performance Insights")
                col1, col2, col3, col4 = st.columns(4)

                avg_window = stage_data['stage_window_us'].mean()
                avg_fft = stage_data['stage_fft_us'].mean()
                avg_mag = stage_data['stage_magnitude_us'].mean()
                avg_overhead = stage_data['stage_overhead_us'].mean()

                with col1:
                    st.metric("Avg Window Time", f"{avg_window:.1f} μs")
                with col2:
                    st.metric("Avg FFT Time", f"{avg_fft:.1f} μs")
                with col3:
                    st.metric("Avg Magnitude Time", f"{avg_mag:.1f} μs")
                with col4:
                    st.metric("Avg Overhead", f"{avg_overhead:.1f} μs")

                st.divider()

                # Aggregate by NFFT for visualization
                stage_summary = stage_data.groupby('engine_nfft').agg({
                    'stage_window_us': 'mean',
                    'stage_fft_us': 'mean',
                    'stage_magnitude_us': 'mean',
                    'stage_overhead_us': 'mean'
                }).reset_index()

                # Chart 1: Stacked Bar Chart
                st.subheader("Pipeline Stage Breakdown by NFFT")

                fig = go.Figure()
                stages = [
                    ('Window', 'stage_window_us', '#1f77b4'),
                    ('FFT', 'stage_fft_us', '#ff7f0e'),
                    ('Magnitude', 'stage_magnitude_us', '#2ca02c'),
                    ('Overhead', 'stage_overhead_us', '#d62728')
                ]

                for stage_name, col, color in stages:
                    fig.add_trace(go.Bar(
                        name=stage_name,
                        x=stage_summary['engine_nfft'],
                        y=stage_summary[col],
                        marker_color=color,
                        hovertemplate=f'{stage_name}: %{{y:.2f}} μs<extra></extra>'
                    ))

                fig.update_layout(
                    barmode='stack',
                    title="Mean Execution Time per Stage (Stacked)",
                    xaxis_title="NFFT Size",
                    yaxis_title="Execution Time (μs)",
                    xaxis_type='log',
                    height=500,
                    hovermode='x unified'
                )
                st.plotly_chart(fig, use_container_width=True)

                # Chart 2: Percentage Contribution
                st.subheader("Stage Percentage Contribution")

                stage_summary['total'] = (stage_summary['stage_window_us'] +
                                          stage_summary['stage_fft_us'] +
                                          stage_summary['stage_magnitude_us'] +
                                          stage_summary['stage_overhead_us'])

                for stage in ['window', 'fft', 'magnitude', 'overhead']:
                    stage_summary[f'{stage}_pct'] = (
                        stage_summary[f'stage_{stage}_us'] / stage_summary['total'] * 100
                    )

                fig2 = go.Figure()

                pct_stages = [
                    ('Window %', 'window_pct', '#1f77b4'),
                    ('FFT %', 'fft_pct', '#ff7f0e'),
                    ('Magnitude %', 'magnitude_pct', '#2ca02c'),
                    ('Overhead %', 'overhead_pct', '#d62728')
                ]

                for stage_name, col, color in pct_stages:
                    fig2.add_trace(go.Scatter(
                        name=stage_name,
                        x=stage_summary['engine_nfft'],
                        y=stage_summary[col],
                        mode='lines+markers',
                        line=dict(color=color, width=2),
                        marker=dict(size=8),
                        hovertemplate=f'{stage_name}: %{{y:.1f}}%<extra></extra>'
                    ))

                fig2.update_layout(
                    title="Percentage of Total Execution Time by Stage",
                    xaxis_title="NFFT Size",
                    yaxis_title="Percentage (%)",
                    xaxis_type='log',
                    height=400,
                    hovermode='x unified'
                )
                st.plotly_chart(fig2, use_container_width=True)

                # Chart 3: Bottleneck Analysis
                st.subheader("Bottleneck Analysis")

                # Identify dominant stage for each NFFT
                dominant_stage = stage_data.groupby('engine_nfft').apply(
                    lambda x: x[['stage_window_us', 'stage_fft_us', 'stage_magnitude_us']].mean().idxmax()
                ).reset_index()
                dominant_stage.columns = ['engine_nfft', 'dominant_stage']
                dominant_stage['dominant_stage'] = dominant_stage['dominant_stage'].str.replace('stage_', '').str.replace('_us', '')

                # Count by dominant stage
                dominant_counts = dominant_stage['dominant_stage'].value_counts()

                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**Dominant Stage by NFFT Configuration:**")
                    for stage, count in dominant_counts.items():
                        pct = (count / len(dominant_stage)) * 100
                        st.write(f"- **{stage.capitalize()}**: {count} configs ({pct:.1f}%)")

                with col2:
                    if 'fft' in dominant_counts.index:
                        st.info(f"FFT is the performance bottleneck in {dominant_counts['fft']} of {len(dominant_stage)} NFFT configurations.")
                    else:
                        st.info("No single stage dominates across all configurations.")

                # Chart 4: Detailed Metrics Table
                st.subheader("Detailed Stage Metrics")

                display_cols = [
                    'engine_nfft', 'engine_channels', 'engine_overlap',
                    'stage_window_us', 'stage_fft_us', 'stage_magnitude_us',
                    'stage_overhead_us', 'stage_total_measured_us',
                    'mean_latency_us'
                ]
                available_cols = [col for col in display_cols if col in stage_data.columns]

                if len(available_cols) > 0:
                    top_configs = stage_data.nlargest(20, 'frames_per_second')[available_cols]
                    st.dataframe(
                        top_configs.style.format({
                            col: "{:.2f}" for col in available_cols if '_us' in col or 'overlap' in col
                        }),
                        use_container_width=True,
                        hide_index=True
                    )

                # Optimization recommendations
                st.divider()
                st.subheader("Optimization Recommendations")

                # Identify if any stage is significantly slower
                avg_total = avg_window + avg_fft + avg_mag
                window_ratio = (avg_window / avg_total) * 100
                fft_ratio = (avg_fft / avg_total) * 100
                mag_ratio = (avg_mag / avg_total) * 100

                if fft_ratio > 50:
                    st.warning(f"**FFT dominates** ({fft_ratio:.1f}% of stage time). Consider optimizing FFT configuration or using smaller NFFT.")
                elif mag_ratio > 40:
                    st.warning(f"**Magnitude calculation is significant** ({mag_ratio:.1f}% of stage time). Verify output mode and data types.")
                elif window_ratio > 30:
                    st.info(f"**Window function overhead** ({window_ratio:.1f}% of stage time) is notable. Consider simpler window types if appropriate.")

                if avg_overhead > avg_total * 0.3:
                    st.warning(f"**High pipeline overhead** ({avg_overhead:.1f}µs avg). This includes stream synchronization and memory transfers.")
                else:
                    st.success(f"**Pipeline overhead is reasonable** ({avg_overhead:.1f}µs avg, {(avg_overhead/avg_total)*100:.1f}% of stage time).")

except FileNotFoundError:
    st.error("No benchmark data found. Please run benchmarks first.")
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.exception(e)
