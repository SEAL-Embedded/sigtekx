"""
System Health Report
====================

Demonstrates SigTekX's soft real-time capabilities and general applicability
beyond ionosphere research. Highlights the value proposition for methods paper:
filling the gap between NumPy/SciPy (batch) and FPGA/VHDL (hard real-time).

Key Metrics:
- Real-Time Factor (RTF) distribution across all experiments
- Hardware accessibility (gaming GPU performance)
- Soft real-time compliance (RTF <1.0 coverage)
- General applicability (non-domain-specific metrics)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.metrics import classify_rtf
from analysis.visualization import PerformancePlotter, VisualizationConfig
from utils.data_loader import load_benchmark_data
from utils.rtf_helpers import (
    RTF_REALTIME_LIMIT,
    RTF_AGGRESSIVE_TARGET,
    RTF_PRODUCTION_TARGET,
    RTF_HEATMAP_COLORSCALE,
    RTF_HEATMAP_MIDPOINT,
    RTF_HEATMAP_RANGE,
    calculate_rtf_statistics,
    get_rtf_heatmap_interpretation_text,
    add_rtf_threshold_lines
)

# Page configuration
st.set_page_config(page_title="System Health", page_icon="🏥", layout="wide")

st.title("🏥 System Health Report")

# Value proposition banner
st.info("""
**SigTekX Value Proposition:** Soft real-time signal processing in Python

Fills the gap between:
- **Low end:** NumPy/SciPy/CuPy (offline batch processing, no real-time guarantees)
- **High end:** FPGA/VHDL (hard real-time, months of dev time, no Python flexibility)

SigTekX enables:
- ✅ Python prototyping with custom stages (Numba, PyTorch, callbacks)
- ✅ Soft real-time performance (RTF <0.3) for continuous monitoring
- ✅ Accessible hardware (gaming/workstation GPUs, not data centers)
- ✅ Iteration in seconds/minutes, not weeks/months
""")

# Load data
try:
    data = load_benchmark_data("artifacts/data")
except FileNotFoundError:
    st.error("⚠️ No benchmark data found. Please run benchmarks first.")
    st.stop()
except Exception as e:
    st.error(f"❌ Error loading data: {e}")
    st.stop()

# Sidebar filters
st.sidebar.header("🔍 Filters")

# Experiment group filter
if 'experiment_group' in data.columns:
    available_groups = sorted(data['experiment_group'].dropna().astype(str).unique())
    if available_groups:
        selected_groups = st.sidebar.multiselect(
            "Experiment Group",
            options=available_groups,
            default=available_groups,
            help="Filter by experiment category (baseline, scaling, grid, ionosphere, profiling, validation)"
        )
        if selected_groups:
            data = data[data['experiment_group'].astype(str).isin(selected_groups)]

# Sample rate filter
if 'sample_rate_category' in data.columns:
    available_rates = sorted(data['sample_rate_category'].dropna().astype(str).unique())
    if available_rates:
        selected_rates = st.sidebar.multiselect(
            "Sample Rate",
            options=available_rates,
            default=available_rates,
            help="Filter by sampling frequency (100kHz for academic, 48kHz for ionosphere)"
        )
        if selected_rates:
            data = data[data['sample_rate_category'].astype(str).isin(selected_rates)]

# Create tabs
tabs = st.tabs([
    "Executive Summary",
    "Real-Time Performance",
    "Hardware Accessibility",
    "System Reliability",
    "Performance Distribution",
    "Benchmark Coverage"
])

# Initialize plotter
plotter = PerformancePlotter(VisualizationConfig())

# ============================================================================
# TAB 1: EXECUTIVE SUMMARY
# ============================================================================
with tabs[0]:
    st.header("Executive Summary")

    st.markdown("""
    **System Health** provides a high-level view of SigTekX's soft real-time capabilities
    across all experiments, demonstrating general applicability beyond domain-specific use cases.

    This report complements the Ionosphere Research page by showing broader system capabilities.
    """)

    st.divider()

    # Key metrics (4 columns)
    col1, col2, col3, col4 = st.columns(4)

    # 1. Real-Time Capable (RTF ≤1.0) - Academic Convention
    if 'rtf' in data.columns:
        rtf_stats = calculate_rtf_statistics(data)

        col1.metric(
            "Real-Time Capable",
            f"{rtf_stats['realtime_capable_pct']:.1f}%",
            help=f"Percentage of configurations achieving RTF ≤{RTF_REALTIME_LIMIT} (faster than real-time)"
        )

    # 2. High Performance (RTF ≤0.33) - Academic Convention
    if 'rtf' in data.columns:
        col2.metric(
            "High Performance",
            f"{rtf_stats['aggressive_pct']:.1f}%",
            help=f"Percentage achieving RTF ≤{RTF_AGGRESSIVE_TARGET} (3× faster than real-time, production target)"
        )

    # 3. Peak Throughput
    if 'frames_per_second' in data.columns:
        peak_fps = data['frames_per_second'].max()

        col3.metric(
            "Peak Throughput",
            f"{peak_fps:.0f} FPS",
            help="Maximum frames per second across all configurations"
        )

    # 4. Lowest Latency
    if 'mean_latency_us' in data.columns:
        min_latency = data['mean_latency_us'].min()

        col4.metric(
            "Lowest Latency",
            f"{min_latency:.1f} µs",
            help="Minimum mean latency across all configurations"
        )

    st.divider()

    # Value Proposition Highlights
    st.subheader("🎯 Key Capabilities")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        **Soft Real-Time Processing**
        - RTF ≤1.0: Can process real-time data streams
        - RTF ≤0.33: 3× safety margin for burst loads, thermal throttling
        - Continuous processing: hours/days, not just batch jobs

        **Python Flexibility**
        - Custom Numba CUDA kernels (Phase 2, planned)
        - PyTorch model integration (Phase 2, planned)
        - I/O callbacks for databases, APIs (Phase 3, planned)
        """)

    with col2:
        st.markdown("""
        **Accessible Hardware**
        - Gaming GPUs: RTX 3090 Ti, RTX 4090
        - Workstation GPUs: RTX 4000 Ada, RTX 5000 Ada
        - NOT data center cards (A100/H100 - overkill)

        **Rapid Iteration**
        - Prototype in Python (seconds to modify)
        - vs FPGA/VHDL (weeks/months of development)
        - vs offline processing (no real-time guarantees)
        """)

# ============================================================================
# TAB 2: REAL-TIME PERFORMANCE
# ============================================================================
with tabs[1]:
    st.header("Real-Time Performance Analysis")

    st.markdown("""
    **Real-Time Factor (RTF)** is the key metric for soft real-time systems:

    RTF = (Signal Duration) / (Processing Time) = Sample Rate / (FPS × Hop Size)

    **Interpretation (Academic Convention - Lower is Better):**
    - **RTF = 1.0**: Exactly real-time (theoretical limit)
    - **RTF < 1.0**: ✅ Faster than real-time (headroom for burst loads)
    - **RTF ≤ 0.33**: ✅ 3× faster than real-time (production target, 3× safety margin)
    - **RTF > 1.0**: ❌ Cannot keep up (processing slower than data arrival)

    **SigTekX Target:** RTF ≤0.40 for production deployment (ASR industry standard)
    """)

    if 'rtf' in data.columns:
        rtf_data = data[data['rtf'].notna()].copy()

        # RTF Distribution Histogram
        st.subheader("RTF Distribution Across All Configurations")

        fig = px.histogram(
            rtf_data,
            x='rtf',
            nbins=50,
            title="Real-Time Factor Distribution",
            labels={'rtf': 'Real-Time Factor (RTF)', 'count': 'Number of Configurations'},
            color_discrete_sequence=['#636EFA']
        )

        # Add vertical lines for thresholds (Academic Convention: lower is better)
        fig.add_vline(x=RTF_REALTIME_LIMIT, line_dash="dash", line_color="orange",
                     annotation_text=f"Real-Time Limit: RTF={RTF_REALTIME_LIMIT}", annotation_position="top right")
        fig.add_vline(x=RTF_AGGRESSIVE_TARGET, line_dash="dash", line_color="green",
                     annotation_text=f"Target: RTF≤{RTF_AGGRESSIVE_TARGET}", annotation_position="top left")

        st.plotly_chart(fig, use_container_width=True)

        # RTF Statistics
        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Median RTF", f"{rtf_data['rtf'].median():.3f}")
        col2.metric("Mean RTF", f"{rtf_data['rtf'].mean():.3f}")
        col3.metric("Min RTF", f"{rtf_data['rtf'].min():.3f}")
        col4.metric("Max RTF", f"{rtf_data['rtf'].max():.3f}")

        st.divider()

        # RTF by Configuration
        st.subheader("RTF by Configuration Parameter")

        param_options = ['engine_nfft', 'engine_channels', 'engine_overlap', 'engine_mode']
        available_params = [p for p in param_options if p in rtf_data.columns]

        selected_param = st.selectbox(
            "Group by parameter:",
            available_params,
            index=0 if 'engine_nfft' in available_params else 0
        )

        fig = px.box(
            rtf_data,
            x=selected_param,
            y='rtf',
            title=f"RTF Distribution by {selected_param}",
            labels={'rtf': 'Real-Time Factor (RTF)'},
            points='all'
        )

        fig.add_hline(y=RTF_REALTIME_LIMIT, line_dash="dash", line_color="orange",
                     annotation_text=f"Real-Time Limit: {RTF_REALTIME_LIMIT}")
        fig.add_hline(y=RTF_AGGRESSIVE_TARGET, line_dash="dash", line_color="green",
                     annotation_text=f"Target: {RTF_AGGRESSIVE_TARGET}")

        st.plotly_chart(fig, use_container_width=True)

        # Classification Table
        st.subheader("RTF Classification")

        st.markdown("""
        Configurations classified by real-time capability:
        """)

        rtf_data['rtf_class'], rtf_data['rtf_description'] = zip(
            *rtf_data['rtf'].apply(classify_rtf)
        )

        classification_counts = rtf_data['rtf_class'].value_counts()

        classification_df = pd.DataFrame({
            'Classification': classification_counts.index,
            'Count': classification_counts.values,
            'Percentage': (classification_counts.values / len(rtf_data) * 100).round(1)
        })

        st.dataframe(classification_df, use_container_width=True, hide_index=True)

    else:
        st.warning("⚠️ No RTF data available. Run throughput or realtime benchmarks.")

# ============================================================================
# TAB 3: HARDWARE ACCESSIBILITY
# ============================================================================
with tabs[2]:
    st.header("Hardware Accessibility")

    st.markdown("""
    **SigTekX targets accessible hardware**, not expensive data center GPUs.

    This demonstrates that researchers can achieve soft real-time performance
    with consumer/workstation GPUs, enabling wider adoption.
    """)

    # Hardware tier comparison
    st.subheader("Target Hardware Tiers")

    hardware_tiers = pd.DataFrame({
        'Tier': ['Consumer', 'Workstation', 'Data Center', 'Embedded'],
        'Example GPUs': [
            'RTX 3090 Ti, RTX 4090',
            'RTX 4000 Ada, RTX 5000 Ada',
            'A100, H100 (NOT targeted)',
            'Jetson Orin (future work)'
        ],
        'TDP (W)': ['350-450', '70-150', '300-700', '15-60'],
        'Price Range': ['$1000-2000', '$1500-4000', '$10,000-40,000', '$500-2000'],
        'SigTekX Status': ['✅ Primary', '✅ Validated', '❌ Overkill', '📅 Planned']
    })

    st.dataframe(hardware_tiers, use_container_width=True, hide_index=True)

    st.divider()

    # Performance/Watt Analysis
    st.subheader("Performance vs Power Efficiency")

    st.markdown("""
    **Key Insight:** Consumer/workstation GPUs provide excellent performance/watt ratio
    compared to data center cards, making them ideal for:
    - Field deployment (antenna systems)
    - Remote monitoring stations
    - Budget-conscious research labs

    **Future Work:** Jetson deployment for embedded real-time processing (15-30W budget).
    """)

    # Memory footprint
    st.subheader("Memory Footprint (Accessible)")

    st.markdown("""
    **Typical Memory Usage** (NFFT=4096, 2 channels):
    - Ring buffers: ~98 KB
    - Device input buffers: ~64 KB
    - Device output buffers: ~32 KB
    - Snapshot buffer: ~16 KB
    - **Total:** ~210 KB per pipeline instance

    **Scalability:**
    - Consumer GPUs (24 GB): Can run ~100,000+ concurrent pipelines (impractical but shows minimal footprint)
    - Workstation GPUs (12-16 GB): Ample headroom for multi-channel, high-NFFT configurations
    - Embedded (8 GB shared): Can run dozens of pipelines with careful memory management
    """)

# ============================================================================
# TAB 4: SYSTEM RELIABILITY
# ============================================================================
with tabs[3]:
    st.header("System Reliability Metrics")

    st.markdown("""
    **Reliability** is critical for production soft real-time systems:
    - Low jitter (coefficient of variation)
    - High accuracy (vs reference implementations)
    - Stable performance under load
    """)

    # Jitter Analysis
    st.subheader("Performance Stability (Jitter)")

    if 'cv' in data.columns:
        cv_data = data[data['cv'].notna()]

        fig = px.histogram(
            cv_data,
            x='cv',
            nbins=30,
            title="Coefficient of Variation (CV) Distribution",
            labels={'cv': 'CV (%)', 'count': 'Number of Configurations'},
            color_discrete_sequence=['#EF553B']
        )

        fig.add_vline(x=10, line_dash="dash", line_color="green",
                     annotation_text="Target: CV<10%", annotation_position="top right")

        st.plotly_chart(fig, use_container_width=True)

        col1, col2, col3 = st.columns(3)

        col1.metric("Median CV", f"{cv_data['cv'].median():.1f}%")
        col2.metric("Low Jitter (<10% CV)",
                   f"{(cv_data['cv'] < 10).sum() / len(cv_data) * 100:.1f}%")
        col3.metric("High Jitter (>20% CV)",
                   f"{(cv_data['cv'] > 20).sum() / len(cv_data) * 100:.1f}%")

        st.markdown("""
        **GPU Clock Locking** reduces CV from 20-40% → 5-15% (see `docs/performance/gpu-clock-locking.md`)
        """)
    else:
        st.info("ℹ️ CV data not available. Run benchmarks with statistical analysis enabled.")

    st.divider()

    # Accuracy Analysis
    st.subheader("Numerical Accuracy")

    if 'pass_rate' in data.columns:
        accuracy_data = data[data['pass_rate'].notna()]

        col1, col2, col3 = st.columns(3)

        col1.metric("Mean Pass Rate", f"{accuracy_data['pass_rate'].mean() * 100:.2f}%")
        col2.metric("Min Pass Rate", f"{accuracy_data['pass_rate'].min() * 100:.2f}%")
        col3.metric("Configs >99% Pass",
                   f"{(accuracy_data['pass_rate'] > 0.99).sum() / len(accuracy_data) * 100:.1f}%")

        st.markdown("""
        **Accuracy Validation:** All configurations tested against NumPy reference (double precision).

        Pass criteria: Relative error <1e-4 (0.01%) per FFT bin.
        """)
    else:
        st.info("ℹ️ Accuracy data not available. Run accuracy benchmarks.")

# ============================================================================
# TAB 5: PERFORMANCE DISTRIBUTION
# ============================================================================
with tabs[4]:
    st.header("Performance Distribution Analysis")

    st.markdown("""
    **Distribution analysis** reveals performance characteristics across parameter space.

    This helps identify:
    - Sweet spots (optimal configurations)
    - Performance scaling patterns
    - Outliers requiring investigation
    """)

    # Latency vs Throughput Scatter
    st.subheader("Latency vs Throughput Trade-off")

    if 'mean_latency_us' in data.columns and 'frames_per_second' in data.columns:
        scatter_data = data[
            data['mean_latency_us'].notna() &
            data['frames_per_second'].notna()
        ].copy()

        color_param = st.selectbox(
            "Color by parameter:",
            ['engine_nfft', 'engine_channels', 'engine_overlap', 'engine_mode'],
            index=0
        )

        fig = px.scatter(
            scatter_data,
            x='mean_latency_us',
            y='frames_per_second',
            color=color_param,
            title="Latency vs Throughput (color by parameter)",
            labels={
                'mean_latency_us': 'Mean Latency (µs)',
                'frames_per_second': 'Throughput (FPS)'
            },
            hover_data=['engine_nfft', 'engine_channels', 'engine_overlap']
        )

        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # RTF Heatmaps (if grid data available)
    st.subheader("Performance Heatmaps")

    # Common NFFT range selector for both heatmaps
    if 'engine_nfft' in data.columns and 'rtf' in data.columns:
        nfft_values = sorted(data['engine_nfft'].unique())

        # Define preset ranges
        nfft_range_options = {
            "Standard (≤16384)": 16384,
            "High-Res (≤32768)": 32768,
            "Extended (≤65536)": 65536,
            "All (includes 131k)": max(nfft_values)
        }

        selected_range = st.selectbox(
            "NFFT Range",
            options=list(nfft_range_options.keys()),
            index=1,  # Default to High-Res (≤32768)
            help="Filter NFFT values to prevent extreme values from compressing the heatmap scale"
        )

        max_nfft = nfft_range_options[selected_range]
        filtered_data = data[data['engine_nfft'] <= max_nfft].copy()

        # Heatmap 1: RTF vs Channels and NFFT (Channel Scaling)
        if 'engine_channels' in filtered_data.columns:
            st.markdown("### RTF vs Channels × NFFT (Channel Scaling)")

            fig = plotter.plot_heatmap(
                filtered_data,
                x_col='engine_nfft',
                y_col='engine_channels',
                z_col='rtf',
                title=f"RTF Heatmap: Channels × NFFT (≤{max_nfft:,}) - Academic Convention",
                colorscale=RTF_HEATMAP_COLORSCALE,
                color_midpoint=RTF_HEATMAP_MIDPOINT,
                color_range=RTF_HEATMAP_RANGE
            )

            st.plotly_chart(fig, use_container_width=True)

            st.markdown(get_rtf_heatmap_interpretation_text())
            st.markdown("This heatmap shows how channel count affects RTF across NFFT sizes.")

        # Heatmap 2: RTF vs Overlap and NFFT (Overlap Scaling - Non-Linear)
        if 'engine_overlap' in filtered_data.columns:
            st.divider()
            st.markdown("### RTF vs Overlap × NFFT (Overlap Scaling - Non-Linear)")

            # Filter to data with overlap information
            overlap_data = filtered_data[filtered_data['engine_overlap'].notna()].copy()

            if len(overlap_data) > 0:
                fig = plotter.plot_heatmap(
                    overlap_data,
                    x_col='engine_nfft',
                    y_col='engine_overlap',
                    z_col='rtf',
                    title=f"RTF Heatmap: Overlap × NFFT (≤{max_nfft:,}) - Academic Convention",
                    colorscale=RTF_HEATMAP_COLORSCALE,
                    color_midpoint=RTF_HEATMAP_MIDPOINT,
                    color_range=RTF_HEATMAP_RANGE
                )

                st.plotly_chart(fig, use_container_width=True)

                st.markdown("""
                **Interpretation (Non-Linear Overlap Scaling):**
                - **Overlap scaling is non-linear**: 50% → 75% (2× load), 90% → 95% (2× load)
                - **Green regions**: RTF ≤0.33 even at high overlap (GPU parallelism advantage)
                - **Yellow/Red progression**: Shows computational load increasing with overlap
                - **Scientific necessity**: VLF ionosphere monitoring requires 90-95% overlap for fine temporal structure

                **Key Insight**: GPU maintains real-time performance (RTF <1.0) even at extreme overlap where CPU would fail.
                This demonstrates the GPU parallelism advantage for high-overlap STFT processing.
                """)
            else:
                st.info("ℹ️ No overlap sweep data available. Run ionosphere_specialized experiment for overlap analysis.")
        else:
            st.info("ℹ️ No overlap data available in this dataset.")
    else:
        st.info("ℹ️ RTF heatmaps require throughput/realtime benchmark data with NFFT sweeps.")

# ============================================================================
# TAB 6: BENCHMARK COVERAGE
# ============================================================================
with tabs[5]:
    st.header("Benchmark Coverage Report")

    st.markdown("""
    **Coverage analysis** shows which configurations have been tested across benchmark types.

    This ensures comprehensive validation for the methods paper.
    """)

    # Benchmark type coverage
    st.subheader("Benchmark Types Executed")

    if 'benchmark_type' in data.columns:
        benchmark_counts = data['benchmark_type'].value_counts()

        fig = px.bar(
            x=benchmark_counts.index,
            y=benchmark_counts.values,
            title="Measurements per Benchmark Type",
            labels={'x': 'Benchmark Type', 'y': 'Number of Measurements'},
            color=benchmark_counts.index
        )

        st.plotly_chart(fig, use_container_width=True)

        # Breakdown table
        benchmark_df = pd.DataFrame({
            'Benchmark Type': benchmark_counts.index,
            'Measurements': benchmark_counts.values,
            'Percentage': (benchmark_counts.values / len(data) * 100).round(1)
        })

        st.dataframe(benchmark_df, use_container_width=True, hide_index=True)

    st.divider()

    # Parameter coverage
    st.subheader("Parameter Space Coverage")

    param_coverage = {}

    for param in ['engine_nfft', 'engine_channels', 'engine_overlap', 'engine_mode']:
        if param in data.columns:
            param_coverage[param] = data[param].nunique()

    if param_coverage:
        coverage_df = pd.DataFrame({
            'Parameter': list(param_coverage.keys()),
            'Unique Values Tested': list(param_coverage.values())
        })

        st.dataframe(coverage_df, use_container_width=True, hide_index=True)

        st.markdown("""
        **Interpretation:**
        - High coverage: Comprehensive testing across parameter range
        - Low coverage: May need additional sweeps for paper
        """)

    st.divider()

    # Configuration matrix
    st.subheader("Configuration Testing Matrix")

    if 'engine_nfft' in data.columns and 'benchmark_type' in data.columns:
        # Count unique configs per benchmark type
        matrix = data.groupby(['benchmark_type', 'engine_nfft']).size().unstack(fill_value=0)

        st.markdown("**Measurements per NFFT × Benchmark Type:**")
        st.dataframe(matrix, use_container_width=True)

        st.markdown("""
        **Usage:** Identify gaps in testing (zeros in matrix) that may need additional experiments.
        """)

# Footer
st.divider()
st.caption(
    "System Health Report • Phase 0 → 1 baseline tracking • Soft real-time capabilities"
)
