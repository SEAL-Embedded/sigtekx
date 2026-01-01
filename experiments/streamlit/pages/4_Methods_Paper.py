"""
Methods Paper Analysis
======================

100kHz academic publication positioning (soft real-time capabilities, general applicability).
"""

import sys
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.data_loader import load_benchmark_data

# Page configuration
st.set_page_config(page_title="Methods Paper", page_icon="📄", layout="wide")

# Badge
st.markdown("""
<div style="background-color: #9467bd; color: white; padding: 10px; border-radius: 5px; text-align: center; margin-bottom: 20px;">
    <h3 style="margin: 0;">📄 METHODS PAPER - 100kHz Academic Analysis</h3>
    <p style="margin: 5px 0 0 0; font-size: 14px;">Soft Real-Time Capabilities • General Applicability • Publication Positioning</p>
</div>
""", unsafe_allow_html=True)

st.title("📄 Methods Paper Analysis")

# Load and filter data
try:
    data = load_benchmark_data("artifacts/data")

    # AUTOMATIC FILTER: 100kHz sample rate (academic/general-purpose)
    # Defensive: check if column exists before filtering
    if 'sample_rate_category' in data.columns:
        methods_data = data[data['sample_rate_category'] == '100kHz'].copy()
    else:
        st.warning("⚠️ sample_rate_category column missing. Showing all data. Please re-run benchmarks to get proper categorization.")
        methods_data = data.copy()

    if len(methods_data) == 0:
        st.warning("No 100kHz data found. Please run academic baseline experiments.")
        st.stop()

    st.info(f"📊 Analyzing **{len(methods_data)} academic configurations** at 100kHz (filtered from {len(data)} total)")

    # Create tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🎯 Value Proposition",
        "⚡ BATCH vs STREAMING",
        "⏱️ Real-Time Capability",
        "🖥️ Hardware Accessibility",
        "📊 General Applicability"
    ])

    with tab1:
        st.header("Value Proposition")

        st.subheader("Positioning: Soft Real-Time GPU STFT in Python")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("""
            **NumPy/SciPy**
            - ❌ Offline only
            - ❌ CPU-bound
            - ✅ Easy to use
            - ✅ Ubiquitous
            """)

        with col2:
            st.markdown("""
            **SigTekX (This Work)**
            - ✅ Soft real-time
            - ✅ GPU-accelerated
            - ✅ Python interface
            - ✅ Consumer hardware
            """)

        with col3:
            st.markdown("""
            **FPGA/VHDL**
            - ✅ Hard real-time
            - ✅ Ultra-low latency
            - ❌ Complex development
            - ❌ Specialized hardware
            """)

        st.divider()

        st.subheader("Key Capabilities")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("""
            **Technical Capabilities:**
            - GPU-accelerated STFT processing
            - Soft real-time performance (RTF ≤ 1.0)
            - Python interface for rapid development
            - BATCH and STREAMING execution modes
            - Consumer/workstation GPU support
            - Parameter space: NFFT 256-131072, channels 1-128
            """)

        with col2:
            st.markdown("""
            **Target Audience:**
            - Researchers (signal processing, acoustics, geophysics)
            - Engineers (real-time monitoring, analysis)
            - Educators (teaching DSP concepts)
            - Prototypers (rapid development cycles)
            """)

        # Summary statistics
        st.subheader("Dataset Overview (100kHz Academic)")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Configs", len(methods_data))

        with col2:
            if 'engine_mode' in methods_data.columns:
                batch_count = len(methods_data[methods_data['engine_mode'] == 'batch'])
                st.metric("BATCH Configs", batch_count)

        with col3:
            if 'engine_mode' in methods_data.columns:
                streaming_count = len(methods_data[methods_data['engine_mode'] == 'streaming'])
                st.metric("STREAMING Configs", streaming_count)

        with col4:
            if 'rtf' in methods_data.columns:
                realtime_capable = len(methods_data[methods_data['rtf'] <= 1.0])
                st.metric("Real-Time Capable", realtime_capable)

    with tab2:
        st.header("BATCH vs STREAMING Comparison")

        if 'engine_mode' in methods_data.columns:
            batch_data = methods_data[methods_data['engine_mode'] == 'batch']
            streaming_data = methods_data[methods_data['engine_mode'] == 'streaming']

            st.subheader("Mode Overhead Analysis")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### ⚡ BATCH Mode")
                st.markdown("*Discrete frame processing*")

                if len(batch_data) > 0:
                    if 'frames_per_second' in batch_data.columns:
                        st.metric("Peak FPS", f"{batch_data['frames_per_second'].max():.1f}")
                    # Use mean for batch (less jitter-sensitive)
                    if 'mean_latency_us' in batch_data.columns:
                        st.metric("Mean Latency", f"{batch_data['mean_latency_us'].mean():.1f} μs")
                    if 'gb_per_second' in batch_data.columns:
                        st.metric("Peak Bandwidth", f"{batch_data['gb_per_second'].max():.1f} GB/s")
                else:
                    st.info("No BATCH mode data at 100kHz")

            with col2:
                st.markdown("### 🔄 STREAMING Mode")
                st.markdown("*Continuous real-time processing*")

                if len(streaming_data) > 0:
                    if 'rtf' in streaming_data.columns:
                        realtime_pct = (len(streaming_data[streaming_data['rtf'] <= 1.0]) / len(streaming_data) * 100)
                        st.metric("Real-Time %", f"{realtime_pct:.1f}%")

                    # Use p99 for streaming (critical for jitter/real-time)
                    p99_displayed = False
                    if 'p99_latency_us' in streaming_data.columns:
                        p99_values = streaming_data['p99_latency_us'].dropna()
                        if len(p99_values) > 0:
                            st.metric("P99 Latency", f"{p99_values.median():.1f} μs",
                                     help="99th percentile latency - critical for real-time jitter analysis")
                            p99_displayed = True

                    if not p99_displayed and 'mean_latency_us' in streaming_data.columns:
                        mean_values = streaming_data['mean_latency_us'].dropna()
                        if len(mean_values) > 0:
                            st.metric("Mean Latency", f"{mean_values.mean():.1f} μs",
                                     help="Fallback: p99_latency_us not available")

                    # Calculate FPS from realtime data if frames_per_second is missing/NaN
                    if 'frames_per_second' in streaming_data.columns:
                        fps_values = streaming_data['frames_per_second'].dropna()
                        if len(fps_values) > 0:
                            st.metric("Sustained FPS", f"{fps_values.max():.1f}")
                        elif 'frames_processed' in streaming_data.columns and 'stream_duration_s' in streaming_data.columns:
                            # Calculate from realtime benchmark data
                            fps_calc = streaming_data['frames_processed'] / streaming_data['stream_duration_s']
                            fps_calc = fps_calc.dropna()
                            if len(fps_calc) > 0:
                                st.metric("Sustained FPS", f"{fps_calc.max():.1f}",
                                         help="Calculated from frames_processed / stream_duration_s")
                    elif 'frames_processed' in streaming_data.columns and 'stream_duration_s' in streaming_data.columns:
                        # Calculate from realtime benchmark data
                        fps_calc = streaming_data['frames_processed'] / streaming_data['stream_duration_s']
                        fps_calc = fps_calc.dropna()
                        if len(fps_calc) > 0:
                            st.metric("Sustained FPS", f"{fps_calc.max():.1f}",
                                     help="Calculated from frames_processed / stream_duration_s")
                else:
                    st.warning(f"⚠️ No STREAMING mode data at 100kHz (found {len(streaming_data)} rows after filtering)")
                    st.info(f"Debug: methods_data has {len(methods_data)} total rows, {len(methods_data[methods_data['engine_mode']=='streaming']) if 'engine_mode' in methods_data.columns else 0} streaming")

            # Latency comparison (use p99 for streaming, mean for batch)
            if len(batch_data) > 0 and len(streaming_data) > 0:
                st.subheader("Latency Overhead: BATCH vs STREAMING")

                # Determine which latency metric to use for streaming
                streaming_latency_col = 'p99_latency_us' if 'p99_latency_us' in streaming_data.columns else 'mean_latency_us'
                streaming_label = 'P99 Latency' if streaming_latency_col == 'p99_latency_us' else 'Mean Latency'

                if 'mean_latency_us' in batch_data.columns and streaming_latency_col in streaming_data.columns:
                    fig = go.Figure()

                    fig.add_trace(go.Box(
                        y=batch_data['mean_latency_us'],
                        name='BATCH (mean)',
                        marker_color='#1f77b4'
                    ))

                    fig.add_trace(go.Box(
                        y=streaming_data[streaming_latency_col],
                        name=f'STREAMING ({streaming_label.lower()})',
                        marker_color='#2ca02c'
                    ))

                    fig.update_layout(
                        title=f"Latency Distribution by Execution Mode (100kHz)<br><sub>BATCH: mean latency | STREAMING: {streaming_label.lower()} (jitter-critical)</sub>",
                        yaxis_title="Latency (μs)",
                        yaxis_type="log",
                        height=500
                    )

                    st.plotly_chart(fig, use_container_width=True)

                    # Overhead calculation (comparing medians)
                    batch_median = batch_data['mean_latency_us'].median()
                    streaming_median = streaming_data[streaming_latency_col].median()
                    overhead_pct = ((streaming_median - batch_median) / batch_median * 100) if batch_median > 0 else 0

                    st.metric("STREAMING Overhead", f"{overhead_pct:.1f}%",
                             help=f"Median latency increase: BATCH (mean)={batch_median:.1f}μs → STREAMING ({streaming_label.lower()})={streaming_median:.1f}μs")

            # Decision tree
            st.divider()
            st.subheader("Execution Mode Decision Tree")

            st.markdown("""
            **When to use BATCH mode:**
            - Offline file processing
            - Maximum throughput required
            - Post-processing recorded data
            - Benchmarking peak performance

            **When to use STREAMING mode:**
            - Live monitoring or real-time analysis
            - Continuous data streams
            - Deadline-critical applications
            - Real-time visualization or alerts
            """)

        else:
            st.info("No execution mode data available")

    with tab3:
        st.header("Real-Time Capability")

        if 'rtf' in methods_data.columns:
            st.subheader("Real-Time Factor (RTF) Distribution")

            # RTF histogram
            fig = px.histogram(
                methods_data,
                x='rtf',
                nbins=50,
                title="RTF Distribution (100kHz Academic)",
                labels={'rtf': 'Real-Time Factor', 'count': 'Configuration Count'}
            )

            # Threshold lines
            fig.add_vline(x=1.0, line_dash="dash", line_color="red",
                         annotation_text="Real-Time (RTF=1.0)")
            fig.add_vline(x=0.33, line_dash="dash", line_color="green",
                         annotation_text="Soft Real-Time (RTF=0.33)")

            st.plotly_chart(fig, use_container_width=True)

            # Real-time capability breakdown
            st.subheader("Real-Time Capability Breakdown")

            col1, col2, col3, col4 = st.columns(4)

            soft_rt = len(methods_data[methods_data['rtf'] <= 0.33])
            rt = len(methods_data[(methods_data['rtf'] > 0.33) & (methods_data['rtf'] <= 1.0)])
            near_rt = len(methods_data[(methods_data['rtf'] > 1.0) & (methods_data['rtf'] <= 2.0)])
            not_rt = len(methods_data[methods_data['rtf'] > 2.0])

            total = len(methods_data)

            with col1:
                pct = (soft_rt / total * 100) if total > 0 else 0
                st.metric("Soft RT (≤0.33)", f"{soft_rt} ({pct:.0f}%)")

            with col2:
                pct = (rt / total * 100) if total > 0 else 0
                st.metric("RT (0.33-1.0)", f"{rt} ({pct:.0f}%)")

            with col3:
                pct = (near_rt / total * 100) if total > 0 else 0
                st.metric("Near RT (1.0-2.0)", f"{near_rt} ({pct:.0f}%)")

            with col4:
                pct = (not_rt / total * 100) if total > 0 else 0
                st.metric("Not RT (>2.0)", f"{not_rt} ({pct:.0f}%)")

            # RTF by NFFT and mode
            if 'engine_nfft' in methods_data.columns and 'engine_mode' in methods_data.columns:
                st.subheader("RTF Scaling by NFFT and Mode")

                fig = px.box(
                    methods_data,
                    x='engine_nfft',
                    y='rtf',
                    color='engine_mode',
                    title="RTF Distribution by NFFT and Execution Mode",
                    labels={'engine_nfft': 'NFFT Size', 'rtf': 'Real-Time Factor', 'engine_mode': 'Mode'},
                    log_x=True
                )

                fig.add_hline(y=1.0, line_dash="dash", line_color="red")
                fig.add_hline(y=0.33, line_dash="dash", line_color="green")

                st.plotly_chart(fig, use_container_width=True)

        else:
            st.info("No RTF data available")

    with tab4:
        st.header("Hardware Accessibility")

        st.subheader("Consumer/Workstation GPU Performance")

        st.markdown("""
        **Hardware Philosophy:**
        - ✅ Consumer GPUs (RTX 3090 Ti, RTX 4090, etc.)
        - ✅ Workstation GPUs (Professional series)
        - ❌ **NOT** data center GPUs (A100, H100)
        - ❌ **NOT** specialized hardware requirements

        **Rationale:**
        - Accessible to researchers and engineers
        - Cost-effective for laboratories and institutions
        - Rapid prototyping and development
        - Easy deployment and scaling
        """)

        # Performance/watt and memory analysis
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Performance Metrics:**")
            if 'frames_per_second' in methods_data.columns:
                st.write(f"- Peak Throughput: {methods_data['frames_per_second'].max():.1f} FPS")
            if 'mean_latency_us' in methods_data.columns:
                st.write(f"- Min Latency: {methods_data['mean_latency_us'].min():.1f} μs")
            if 'gb_per_second' in methods_data.columns:
                st.write(f"- Peak Bandwidth: {methods_data['gb_per_second'].max():.1f} GB/s")

        with col2:
            st.markdown("**Resource Requirements:**")
            st.write("- GPU Memory: <8GB for most configs")
            st.write("- CUDA Compute: SM 8.0+ (Ampere+)")
            st.write("- CPU: Any modern x86_64")
            st.write("- RAM: 16GB recommended")

        # Hardware tier comparison (if multiple GPUs tested)
        st.divider()
        st.subheader("GPU Performance Comparison")

        st.markdown("""
        **Target Hardware Tiers:**
        1. **Entry**: RTX 3070, RTX 4070 (8-12GB VRAM)
        2. **Standard**: RTX 3080, RTX 4080 (10-16GB VRAM)
        3. **Performance**: RTX 3090 Ti, RTX 4090 (24GB VRAM)

        All tiers capable of soft real-time processing for typical configurations.
        """)

    with tab5:
        st.header("General Applicability")

        st.subheader("Parameter Space Coverage")

        col1, col2, col3 = st.columns(3)

        with col1:
            if 'engine_nfft' in methods_data.columns:
                nfft_values = sorted(methods_data['engine_nfft'].unique())
                st.markdown("**NFFT Range:**")
                st.write(f"{min(nfft_values)} - {max(nfft_values)}")
                st.write(f"({len(nfft_values)} values)")

        with col2:
            if 'engine_channels' in methods_data.columns:
                channel_values = sorted(methods_data['engine_channels'].unique())
                st.markdown("**Channel Range:**")
                st.write(f"{min(channel_values)} - {max(channel_values)}")
                st.write(f"({len(channel_values)} values)")

        with col3:
            if 'engine_overlap' in methods_data.columns:
                overlap_values = sorted(methods_data['engine_overlap'].unique())
                st.markdown("**Overlap Range:**")
                st.write(f"{min(overlap_values):.3f} - {max(overlap_values):.3f}")
                st.write(f"({len(overlap_values)} values)")

        # Parameter space heatmap (NFFT x Channels)
        if all(col in methods_data.columns for col in ['engine_nfft', 'engine_channels', 'rtf']):
            st.subheader("Parameter Space Coverage Heatmap (NFFT × Channels)")

            pivot = methods_data.pivot_table(
                values='rtf',
                index='engine_channels',
                columns='engine_nfft',
                aggfunc='mean'
            )

            # Convert to string labels for categorical (evenly spaced) axes
            x_labels = [str(int(x)) for x in pivot.columns]
            y_labels = [str(int(y)) for y in pivot.index]

            fig = go.Figure(data=go.Heatmap(
                z=pivot.values,
                x=x_labels,
                y=y_labels,
                colorscale='RdYlGn_r',
                text=pivot.values,
                texttemplate='%{text:.2f}',
                textfont={"size": 10},
                colorbar=dict(title="Mean RTF")
            ))

            fig.update_layout(
                title="Mean RTF across Parameter Space (100kHz)",
                xaxis_title="NFFT Size",
                yaxis_title="Channel Count",
                xaxis=dict(type='category'),  # Evenly spaced
                yaxis=dict(type='category'),  # Evenly spaced
                height=600
            )

            st.plotly_chart(fig, use_container_width=True)

        # Parameter space heatmap (NFFT x Overlap)
        if all(col in methods_data.columns for col in ['engine_nfft', 'engine_overlap', 'rtf']):
            st.subheader("RTF Heatmap by NFFT × Overlap")

            pivot_overlap = methods_data.pivot_table(
                values='rtf',
                index='engine_overlap',
                columns='engine_nfft',
                aggfunc='mean'
            )

            # Convert to string labels for categorical (evenly spaced) axes
            x_labels_overlap = [str(int(x)) for x in pivot_overlap.columns]
            y_labels_overlap = [f"{y:.3f}" for y in pivot_overlap.index]

            fig_overlap = go.Figure(data=go.Heatmap(
                z=pivot_overlap.values,
                x=x_labels_overlap,
                y=y_labels_overlap,
                colorscale='RdYlGn_r',
                text=pivot_overlap.values,
                texttemplate='%{text:.2f}',
                textfont={"size": 10},
                colorbar=dict(title="Mean RTF")
            ))

            fig_overlap.update_layout(
                title="Mean RTF by NFFT and Overlap (100kHz)",
                xaxis_title="NFFT Size",
                yaxis_title="Overlap Fraction",
                xaxis=dict(type='category'),  # Evenly spaced
                yaxis=dict(type='category'),  # Evenly spaced
                height=600
            )

            st.plotly_chart(fig_overlap, use_container_width=True)

        # Extensibility
        st.divider()
        st.subheader("Extensibility to Other Use Cases")

        st.markdown("""
        **Demonstrated Applicability:**
        - ✅ Ionosphere monitoring (VLF/ULF, 48kHz)
        - ✅ Academic signal processing (100kHz baseline)
        - ✅ Multi-channel arrays (1-128 channels)
        - ✅ Variable resolution (NFFT 256-131072)

        **Potential Extensions:**
        - Audio processing (music, speech, environmental)
        - Biomedical signals (EEG, ECG, EMG)
        - Seismic monitoring
        - Radio/RF signal analysis
        - Acoustic monitoring (marine, wildlife)
        - Vibration analysis
        - Power systems monitoring
        """)

except FileNotFoundError:
    st.error("No benchmark data found. Please run benchmarks first.")
except Exception as e:
    st.error(f"Error loading data: {e}")
    st.exception(e)
