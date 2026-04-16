"""
SigTekX Benchmarking Dashboard
===============================

Interactive dashboard for exploring GPU STFT benchmark results with clear
execution mode separation (BATCH vs STREAMING) and objective-focused analysis.

Launch with:
    streamlit run experiments/streamlit/app.py
    OR: sigx dashboard

Navigate between pages using the sidebar.
"""

import sys
from pathlib import Path

import streamlit as st

# Add parent directory to path for imports from experiments.analysis
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from our local utils (not streamlit package utils)
from utils.data_loader import get_data_freshness, load_selected_datasets
from utils.dataset_registry import render_sidebar_picker

# Page configuration
st.set_page_config(
    page_title="SigTekX Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Main page
st.title("🚀 SigTekX Benchmarking Dashboard")

st.markdown("""
Welcome to the **SigTekX interactive dashboard**. This tool provides comprehensive
analysis of GPU STFT benchmark results with clear separation between execution modes
and objective-focused pages.

### 📊 Dashboard Pages

#### Execution Mode Analysis
- **⚡ BATCH Execution**: Discrete frame processing (offline, maximum throughput)
- **🔄 STREAMING Execution**: Continuous real-time processing (ring buffer, deadline compliance)

#### Objective-Focused Analysis
- **🌐 Ionosphere Application**: 48kHz dual-channel VLF/ULF phenomena detection
- **📄 Methods Paper**: 100kHz academic publication positioning (soft real-time capabilities)

#### Exploration
- **⚙️ Configuration Explorer**: Interactive filtering and comparison across all data

### 🎯 Key Features

- **Mode Clarity**: Each analysis page clearly identifies which execution mode (BATCH vs STREAMING)
- **Objective Focus**: Separate pages for ionosphere application and methods paper positioning
- **Interactive Filtering**: Explore parameter space by NFFT, channels, overlap, sample rate
- **Comprehensive Coverage**: 300+ configurations across both execution modes

### 🔄 Data Source

Use the sidebar **Dataset** picker to choose which result set to view. The
default `live` entry points at `artifacts/data/` (your current scratchpad run).
Datasets saved via `sigx dataset save` or downloaded from AWS with
`scripts/aws/download_results.sh` also show up here, and the **Compare with**
selector overlays them on charts and computes deltas.
""")

# Dataset picker (also rendered by every page — harmless to render on main).
primary_entry, compare_entries = render_sidebar_picker()

# Data loading and status
st.divider()

try:
    data = load_selected_datasets()

    # Mode breakdown statistics
    st.subheader("📈 Dataset Statistics")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Configurations", len(data))

    # Execution mode breakdown
    if 'engine_mode' in data.columns:
        batch_count = len(data[data['engine_mode'] == 'batch'])
        streaming_count = len(data[data['engine_mode'] == 'streaming'])
        col2.metric("BATCH Configs", batch_count, help="Discrete frame processing")
        col3.metric("STREAMING Configs", streaming_count, help="Continuous real-time processing")

    # Benchmark types
    if 'benchmark_type' in data.columns:
        benchmark_types = data['benchmark_type'].nunique()
        col4.metric("Benchmark Types", benchmark_types)

    # Data freshness and sample rate breakdown
    col1, col2, col3, col4 = st.columns(4)

    freshness = get_data_freshness(primary_entry.data_path)
    if freshness:
        col1.metric("Last Updated", freshness)

    # Sample rate breakdown
    if 'sample_rate_category' in data.columns:
        iono_48k = len(data[data['sample_rate_category'] == '48kHz'])
        academic_100k = len(data[data['sample_rate_category'] == '100kHz'])
        col2.metric("48kHz (Ionosphere)", iono_48k)
        col3.metric("100kHz (Academic)", academic_100k)

    # Experiment groups
    if 'experiment_group' in data.columns:
        exp_groups = data['experiment_group'].nunique()
        col4.metric("Experiment Groups", exp_groups)

    # Quick performance stats
    st.divider()
    st.subheader("⚡ Performance Highlights")

    col1, col2, col3, col4 = st.columns(4)

    if 'frames_per_second' in data.columns:
        peak_fps = data['frames_per_second'].max()
        peak_config = data.loc[data['frames_per_second'].idxmax()]
        col1.metric(
            "Peak Throughput",
            f"{peak_fps:.1f} FPS",
            help=f"NFFT={peak_config.get('engine_nfft', 'N/A')}, Mode={peak_config.get('engine_mode', 'N/A')}"
        )

    if 'mean_latency_us' in data.columns:
        min_latency = data['mean_latency_us'].min()
        min_config = data.loc[data['mean_latency_us'].idxmin()]
        col2.metric(
            "Lowest Latency",
            f"{min_latency:.1f} μs",
            help=f"NFFT={min_config.get('engine_nfft', 'N/A')}, Mode={min_config.get('engine_mode', 'N/A')}"
        )

    if 'rtf' in data.columns:
        # Real-time capable configs (RTF <= 1.0)
        realtime_capable = len(data[data['rtf'] <= 1.0])
        realtime_pct = (realtime_capable / len(data) * 100) if len(data) > 0 else 0
        col3.metric(
            "Real-Time Capable",
            f"{realtime_pct:.1f}%",
            help="Configurations with RTF ≤ 1.0 (real-time processing)"
        )

    if 'pass_rate' in data.columns:
        accuracy_data = data[data['pass_rate'].notna()]
        if len(accuracy_data) > 0:
            mean_accuracy = accuracy_data['pass_rate'].mean() * 100
            col4.metric(
                "Mean Accuracy",
                f"{mean_accuracy:.1f}%",
                help="Average pass rate across all accuracy tests"
            )

    # Mode comparison
    if 'engine_mode' in data.columns and 'rtf' in data.columns:
        st.divider()
        st.subheader("🔄 BATCH vs STREAMING Comparison")

        col1, col2 = st.columns(2)

        batch_data = data[data['engine_mode'] == 'batch']
        streaming_data = data[data['engine_mode'] == 'streaming']

        with col1:
            st.markdown("**⚡ BATCH Mode**")
            st.markdown("*Discrete frame processing (offline, maximum throughput)*")
            if len(batch_data) > 0:
                if 'frames_per_second' in batch_data.columns:
                    st.metric("Peak FPS", f"{batch_data['frames_per_second'].max():.1f}")
                if 'mean_latency_us' in batch_data.columns:
                    st.metric("Min Latency", f"{batch_data['mean_latency_us'].min():.1f} μs")

        with col2:
            st.markdown("**🔄 STREAMING Mode**")
            st.markdown("*Continuous real-time processing (ring buffer, deadlines)*")
            if len(streaming_data) > 0:
                if 'rtf' in streaming_data.columns:
                    realtime_count = len(streaming_data[streaming_data['rtf'] <= 1.0])
                    realtime_pct = (realtime_count / len(streaming_data) * 100) if len(streaming_data) > 0 else 0
                    st.metric("Real-Time Capable", f"{realtime_pct:.1f}%")
                if 'mean_latency_us' in streaming_data.columns:
                    st.metric("Mean Latency", f"{streaming_data['mean_latency_us'].mean():.1f} μs")

    # Data preview
    st.divider()
    st.subheader("📋 Data Preview")

    with st.expander("Show raw data (first 100 rows)", expanded=False):
        st.dataframe(
            data.head(100),
            use_container_width=True,
            hide_index=True,
        )

    # Navigation guidance
    st.divider()
    st.info(
        "👈 **Navigate using the sidebar** to explore:\n\n"
        "- **Execution Mode Pages**: BATCH (discrete) vs STREAMING (continuous)\n"
        "- **Application Pages**: Ionosphere (48kHz) and Methods Paper (100kHz)\n"
        "- **Configuration Explorer**: Interactive filtering across all data"
    )

except FileNotFoundError as e:
    st.error(
        f"""
        ⚠️ **No benchmark data found for dataset `{primary_entry.name}`**

        {e}

        Options:
        - Run benchmarks locally to populate `artifacts/data/`:
          ```bash
          snakemake --cores 4 --snakefile experiments/Snakefile
          ```
        - Snapshot an existing run: `sigx dataset save <name>`
        - Pull a cloud run: `bash scripts/aws/download_results.sh`
        """
    )
except Exception as e:
    st.error(f"❌ Error loading data: {e}")
    st.exception(e)

# Footer
st.divider()
st.caption(
    "SigTekX • GPU-accelerated STFT for soft real-time signal processing"
)
