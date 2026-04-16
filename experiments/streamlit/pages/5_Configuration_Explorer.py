"""
Configuration Explorer
======================

Interactive tool for exploring parameter space and comparing configurations.
Filter by NFFT, channels, overlap, and execution mode to find optimal settings.
"""

import sys
from pathlib import Path

import streamlit as st

# Add parent directory to path for imports from experiments.analysis
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import from our local utils (relative to experiments/streamlit/pages/)
sys.path.insert(0, str(Path(__file__).parent.parent))
# Import from experiments.analysis
from analysis.visualization import PerformancePlotter, VisualizationConfig
from utils.data_loader import get_available_configurations, load_selected_datasets
from utils.dataset_registry import render_sidebar_picker

# Page configuration
st.set_page_config(page_title="Configuration Explorer", page_icon="⚙️", layout="wide")

# Title
st.title("⚙️ Configuration Explorer")

st.markdown("""
Interactively filter and compare benchmark configurations to find optimal
parameters for your ionosphere research application.
""")

# Load data
render_sidebar_picker()

try:
    data = load_selected_datasets()
    if "dataset" in data.columns and data["dataset"].nunique() > 1:
        names = ", ".join(sorted(data["dataset"].unique()))
        st.info(f"Comparing datasets: {names} (rows tagged by dataset column)")
    config_params = get_available_configurations(data)
except FileNotFoundError:
    st.error("No benchmark data found. Please run benchmarks first.")
    st.stop()
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.stop()

# Sidebar filters
st.sidebar.header("🔍 Filters")

# ============================================================================
# PROMINENT: Execution Mode Filter (TOP OF SIDEBAR)
# ============================================================================
st.sidebar.markdown("### ⚡ Execution Mode")
st.sidebar.markdown("*Primary filter - mode affects all performance characteristics*")

if 'mode' in config_params:
    selected_modes = st.sidebar.multiselect(
        "Execution Mode",
        options=config_params['mode'],
        default=config_params['mode'],
        help="BATCH: discrete frames (minimal overhead), STREAMING: continuous real-time (ring buffer management)"
    )
else:
    selected_modes = None

st.sidebar.divider()

# Benchmark type filter (also prominent)
if 'benchmark_type' in config_params:
    selected_benchmarks = st.sidebar.multiselect(
        "Benchmark Type",
        options=config_params['benchmark_type'],
        default=config_params['benchmark_type'],
        help="throughput, latency, realtime, accuracy"
    )
else:
    selected_benchmarks = None

st.sidebar.divider()

# ============================================================================
# Standard Filters
# ============================================================================

# NFFT filter
if 'nfft' in config_params:
    selected_nfft = st.sidebar.multiselect(
        "NFFT Size",
        options=config_params['nfft'],
        default=config_params['nfft'],
        help="Filter by FFT size (larger = better frequency resolution, worse time resolution)"
    )
else:
    selected_nfft = None

# Channels filter
if 'channels' in config_params:
    selected_channels = st.sidebar.multiselect(
        "Channels",
        options=config_params['channels'],
        default=config_params['channels'],
        help="Number of channels (ionosphere typically uses 2 for E-W and N-S dipoles)"
    )
else:
    selected_channels = None

# Overlap filter
if 'overlap' in config_params:
    overlap_range = st.sidebar.slider(
        "Overlap Range",
        min_value=float(min(config_params['overlap'])),
        max_value=float(max(config_params['overlap'])),
        value=(float(min(config_params['overlap'])), float(max(config_params['overlap']))),
        help="Filter by window overlap (higher = more temporal coverage)"
    )
else:
    overlap_range = None

# NEW: Experiment group filter
if 'experiment_group' in config_params:
    selected_groups = st.sidebar.multiselect(
        "Experiment Group",
        options=config_params['experiment_group'],
        default=config_params['experiment_group'],
        help="Filter by experiment category (baseline, scaling, grid, ionosphere, profiling, validation)"
    )
else:
    selected_groups = None

# NEW: Sample rate filter
if 'sample_rate_category' in config_params:
    selected_sample_rates = st.sidebar.multiselect(
        "Sample Rate",
        options=config_params['sample_rate_category'],
        default=config_params['sample_rate_category'],
        help="Filter by sampling frequency (100kHz for academic, 48kHz for ionosphere)"
    )
else:
    selected_sample_rates = None

# Apply filters
filtered_data = data.copy()

if selected_nfft:
    filtered_data = filtered_data[filtered_data['engine_nfft'].isin(selected_nfft)]

if selected_channels:
    filtered_data = filtered_data[filtered_data['engine_channels'].isin(selected_channels)]

if overlap_range:
    filtered_data = filtered_data[
        (filtered_data['engine_overlap'] >= overlap_range[0]) &
        (filtered_data['engine_overlap'] <= overlap_range[1])
    ]

if selected_modes:
    filtered_data = filtered_data[filtered_data['engine_mode'].isin(selected_modes)]

if selected_benchmarks:
    filtered_data = filtered_data[filtered_data['benchmark_type'].isin(selected_benchmarks)]

# NEW: Apply experiment group filter
if selected_groups and 'experiment_group' in filtered_data.columns:
    filtered_data = filtered_data[filtered_data['experiment_group'].isin(selected_groups)]

# NEW: Apply sample rate filter
if selected_sample_rates and 'sample_rate_category' in filtered_data.columns:
    filtered_data = filtered_data[filtered_data['sample_rate_category'].isin(selected_sample_rates)]

# Display filter results
st.subheader("📊 Filtered Results")

col1, col2, col3 = st.columns(3)
col1.metric("Configurations", len(filtered_data), delta=f"{len(filtered_data) - len(data)}")
col2.metric("Unique NFFFTs", filtered_data['engine_nfft'].nunique() if len(filtered_data) > 0 else 0)
col3.metric("Unique Channel Counts", filtered_data['engine_channels'].nunique() if len(filtered_data) > 0 else 0)

if len(filtered_data) == 0:
    st.warning("⚠️ No configurations match the selected filters. Try relaxing some constraints.")
    st.stop()

# Configuration table
st.subheader("🗂️ Configuration Details")

# Select columns to display
display_columns = ['engine_nfft', 'engine_channels', 'engine_overlap', 'benchmark_type']
if 'engine_mode' in filtered_data.columns:
    display_columns.append('engine_mode')
if 'frames_per_second' in filtered_data.columns:
    display_columns.append('frames_per_second')
if 'mean_latency_us' in filtered_data.columns:
    display_columns.append('mean_latency_us')
if 'rtf' in filtered_data.columns:
    display_columns.append('rtf')
if 'pass_rate' in filtered_data.columns:
    display_columns.append('pass_rate')

# Configure column display
column_config = {
    "engine_nfft": st.column_config.NumberColumn("NFFT", format="%d"),
    "engine_channels": st.column_config.NumberColumn("Channels", format="%d"),
    "engine_overlap": st.column_config.NumberColumn("Overlap", format="%.3f"),
    "engine_mode": st.column_config.TextColumn("Mode", help="BATCH (discrete frames) vs STREAMING (continuous real-time)"),
    "frames_per_second": st.column_config.NumberColumn("FPS", format="%.1f"),
    "mean_latency_us": st.column_config.NumberColumn("Latency (μs)", format="%.1f"),
    "rtf": st.column_config.NumberColumn("RTF", format="%.2f"),
    "pass_rate": st.column_config.ProgressColumn("Pass Rate", format="%.1f%%", min_value=0, max_value=1),
}

st.dataframe(
    filtered_data[display_columns],
    column_config=column_config,
    use_container_width=True,
    hide_index=True,
)

# Download filtered data
csv = filtered_data.to_csv(index=False)
st.download_button(
    label="📥 Download Filtered Data (CSV)",
    data=csv,
    file_name="filtered_configurations.csv",
    mime="text/csv",
)

# Visualizations
st.divider()
st.subheader("📈 Performance Visualizations")

# Create tabs for different chart types
tab1, tab2, tab3 = st.tabs(["Scaling", "Latency", "Resolution"])

with tab1:
    st.markdown("### Throughput Scaling")

    if 'frames_per_second' in filtered_data.columns:
        # Let user select X-axis
        x_axis = st.selectbox(
            "X-axis parameter",
            options=['engine_nfft', 'engine_channels', 'engine_overlap'],
            index=0,
            key="scaling_x"
        )

        # Create scaling plot using existing visualization module
        try:
            plotter = PerformancePlotter(VisualizationConfig())
            fig = plotter.plot_scaling(
                filtered_data,
                x_col=x_axis,
                y_col='frames_per_second',
                group_by='engine_channels' if x_axis != 'engine_channels' else 'engine_nfft',
            )
            st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.error(f"Error generating plot: {e}")
    else:
        st.info("No throughput data available (frames_per_second column missing)")

with tab2:
    st.markdown("### Latency Analysis")

    if 'mean_latency_us' in filtered_data.columns:
        # Let user select X-axis
        x_axis = st.selectbox(
            "X-axis parameter",
            options=['engine_nfft', 'engine_channels', 'engine_overlap'],
            index=0,
            key="latency_x"
        )

        # Create latency plot
        try:
            plotter = PerformancePlotter(VisualizationConfig())
            fig = plotter.plot_scaling(
                filtered_data,
                x_col=x_axis,
                y_col='mean_latency_us',
                group_by='engine_channels' if x_axis != 'engine_channels' else 'engine_nfft',
            )
            st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.error(f"Error generating plot: {e}")
    else:
        st.info("No latency data available (mean_latency_us column missing)")

with tab3:
    st.markdown("### Time vs Frequency Resolution")

    if 'time_resolution_ms' in filtered_data.columns and 'freq_resolution_hz' in filtered_data.columns:
        try:
            import plotly.graph_objects as go

            fig = go.Figure()

            # Scatter plot colored by RTF or FPS
            color_col = 'rtf' if 'rtf' in filtered_data.columns else 'frames_per_second'
            hover_data = ['engine_nfft', 'engine_channels', 'engine_overlap']

            fig.add_trace(go.Scatter(
                x=filtered_data['time_resolution_ms'],
                y=filtered_data['freq_resolution_hz'],
                mode='markers',
                marker=dict(
                    size=10,
                    color=filtered_data[color_col] if color_col in filtered_data.columns else 'blue',
                    colorscale='Viridis',
                    showscale=True,
                    colorbar=dict(title=color_col.upper() if color_col == 'rtf' else 'FPS'),
                ),
                text=[
                    f"NFFT: {row['engine_nfft']}<br>" +
                    f"Channels: {row['engine_channels']}<br>" +
                    f"Overlap: {row['engine_overlap']}"
                    for _, row in filtered_data.iterrows()
                ],
                hovertemplate='%{text}<extra></extra>',
            ))

            # Add threshold lines for phenomena detection
            fig.add_hline(y=1.0, line_dash="dash", line_color="red",
                         annotation_text="Schumann (<1Hz)", annotation_position="right")
            fig.add_vline(x=10.0, line_dash="dash", line_color="orange",
                         annotation_text="Lightning (<10ms)", annotation_position="top")

            fig.update_layout(
                title="Resolution Trade-off Space",
                xaxis_title="Time Resolution (ms)",
                yaxis_title="Frequency Resolution (Hz)",
                xaxis_type="log",
                yaxis_type="log",
                height=600,
            )

            st.plotly_chart(fig, width="stretch")

            st.caption(
                "📍 **Thresholds**: "
                "Red line = Schumann resonances requirement (<1Hz freq resolution), "
                "Orange line = Lightning/sprites requirement (<10ms time resolution)"
            )
        except Exception as e:
            st.error(f"Error generating resolution plot: {e}")
    else:
        st.info("Resolution data not available (time_resolution_ms or freq_resolution_hz columns missing)")

# Configuration comparison
st.divider()
st.subheader("⚖️ Configuration Comparison")

if len(filtered_data) >= 2:
    st.markdown("Select two configurations to compare side-by-side:")

    col1, col2 = st.columns(2)

    # Helper function to format config label
    def format_config(i):
        row = filtered_data.iloc[i]
        label = f"NFFT={row['engine_nfft']}, Ch={row['engine_channels']}, Overlap={row['engine_overlap']:.2f}"
        if 'engine_mode' in row:
            label += f", {row['engine_mode'].upper()}"
        return label

    with col1:
        config1_idx = st.selectbox(
            "Configuration 1",
            options=range(len(filtered_data)),
            format_func=format_config,
            key="config1"
        )

    with col2:
        config2_idx = st.selectbox(
            "Configuration 2",
            options=range(len(filtered_data)),
            index=min(1, len(filtered_data) - 1),
            format_func=format_config,
            key="config2"
        )

    if config1_idx != config2_idx:
        config1 = filtered_data.iloc[config1_idx]
        config2 = filtered_data.iloc[config2_idx]

        # Comparison metrics
        metric_cols = ['frames_per_second', 'mean_latency_us', 'rtf', 'pass_rate', 'gb_per_second']
        metric_labels = {
            'frames_per_second': 'Throughput (FPS)',
            'mean_latency_us': 'Latency (μs)',
            'rtf': 'Real-Time Factor',
            'pass_rate': 'Pass Rate (%)',
            'gb_per_second': 'Bandwidth (GB/s)',
        }

        st.markdown("#### Metric Comparison")

        for metric in metric_cols:
            if metric in filtered_data.columns:
                val1 = config1[metric]
                val2 = config2[metric]

                col1, col2, col3 = st.columns(3)

                with col1:
                    if metric == 'pass_rate':
                        st.metric(metric_labels[metric], f"{val1 * 100:.1f}%")
                    else:
                        st.metric(metric_labels[metric], f"{val1:.2f}")

                with col2:
                    if metric == 'pass_rate':
                        st.metric("", f"{val2 * 100:.1f}%")
                    else:
                        st.metric("", f"{val2:.2f}")

                with col3:
                    delta = val2 - val1
                    delta_pct = (delta / val1 * 100) if val1 != 0 else 0

                    # For latency, lower is better, so flip the delta sign for display
                    display_delta = -delta if metric == 'mean_latency_us' else delta

                    st.metric(
                        "Difference",
                        f"{delta:.2f}",
                        delta=f"{delta_pct:+.1f}%",
                        delta_color="normal" if display_delta >= 0 else "inverse"
                    )
    else:
        st.info("Select two different configurations to compare")
else:
    st.info("Need at least 2 configurations to enable comparison")
