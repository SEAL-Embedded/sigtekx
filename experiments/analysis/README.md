# Ionosense HPC Analysis System

⚠️ **DEPRECATION NOTICE** ⚠️

**HTML report generation in this module is DEPRECATED.**

For interactive data exploration and reporting, use the **Streamlit dashboard**:
```bash
iono dashboard
# OR: streamlit run experiments/streamlit/app.py
```

The Streamlit dashboard provides all HTML report features plus:
- Interactive filtering and parameter exploration
- Real-time data updates
- Side-by-side configuration comparison
- CSV export capabilities

---

Modern, modular analysis framework for ionosphere research benchmarks.

## Architecture Overview

```
experiments/analysis/
├── __init__.py          # Package exports
├── models.py            # Pydantic data models
├── analyzer.py          # Analysis engine and analyzers
├── metrics.py           # Scientific metrics for ionosphere research
├── visualization.py     # Interactive Plotly + matplotlib plots
├── spectrograms.py      # Spectrogram generation (optional)
├── reporting.py         # Dual HTML report generators
└── cli.py               # Command-line interface
```

## Key Features

### 1. **Scientific Metrics**
- **Real-Time Factor (RTF)**: Processing speed vs signal speed
- **Time Resolution**: Temporal granularity (ms)
- **Frequency Resolution**: Spectral detail (Hz)
- **Hop Size**: Frame advance between STFT windows
- Domain-specific suitability assessment for ionosphere phenomena

### 2. **Reporting System**
⚠️ **HTML reports are DEPRECATED. Use Streamlit dashboard instead.**

- **Streamlit Dashboard** (RECOMMENDED): Interactive web-based analysis
  - General Performance page: Throughput, latency, accuracy, scaling
  - Ionosphere Research page: RTF, resolution trade-offs, phenomena suitability
  - Configuration Explorer: Interactive filtering and comparison
  - Real-time updates and CSV export

- **Legacy HTML Reports** (DEPRECATED): Static HTML generation
  - `reporting.py` module will be removed in future release
  - Use `iono dashboard` for all analysis needs

### 3. **Statistical Rigor**
- Confidence intervals (95% default)
- Hypothesis testing (t-test, Mann-Whitney U)
- Effect sizes (Cohen's d)
- Scaling analysis (linear, logarithmic, power-law, saturation detection)
- MD5-based caching for performance

### 4. **Interactive Visualizations**
- Plotly-based interactive plots
- Scaling curves with log axes
- Performance heatmaps
- RTF vs frequency resolution
- Time vs frequency resolution trade-offs
- Statistical distributions and comparisons

## Usage

### Interactive Dashboard (RECOMMENDED)

```bash
# Launch Streamlit dashboard
iono dashboard

# OR manually
streamlit run experiments/streamlit/app.py
```

**Features:**
- Three interactive pages: General Performance, Ionosphere Research, Configuration Explorer
- Real-time data loading from `artifacts/data/`
- Interactive filtering, comparison, and export
- Access at http://localhost:8501

### Generate Reports (DEPRECATED)

⚠️ **HTML report generation is deprecated. Use Streamlit dashboard instead.**

```bash
# Legacy HTML report generation (will be removed)
python -m experiments.analysis.cli report artifacts/data \
    --output-dir artifacts/reports \
    --generate-plots
```

### Analyze Data

```bash
# Generate analysis summary
python -m experiments.analysis.cli analyze artifacts/data \
    --output artifacts/analysis/summary.json \
    --experiment-name "Ionosphere HPC Analysis"
```

### Compare Configurations

```bash
# Statistical comparison between two configs
python -m experiments.analysis.cli compare artifacts/data \
    "engine_nfft=4096,engine_channels=2" \
    "engine_nfft=8192,engine_channels=2" \
    --metric mean_latency_us
```

**Outputs:**
- Test statistic and p-value
- Effect size (Cohen's d)
- Mean difference and percentage change
- Improvement assessment

### Scaling Analysis

```bash
# Analyze how latency scales with NFFT
python -m experiments.analysis.cli scaling artifacts/data \
    --parameter engine_nfft \
    --metric mean_latency_us
```

**Outputs:**
- Scaling type (linear, log, power-law, saturation)
- Scaling exponent
- Correlation and R² values
- Saturation point (if detected)

## Workflow Integration

### Snakemake Pipeline

```bash
# Run complete benchmark workflow (generates data only)
snakemake --cores 4 --snakefile experiments/Snakefile

# View results in interactive dashboard
iono dashboard

# Individual benchmark steps
snakemake run_ionosphere_resolution  # High-res analysis
snakemake run_ionosphere_temporal    # Temporal characteristics

# NOTE: HTML report generation rules have been removed
# Use Streamlit dashboard for all analysis and reporting
```

### Experiment Configs

- `ionosphere_resolution`: NFFT sweep (4096-32768), overlap study
- `ionosphere_temporal`: Overlap optimization (0.25-0.9375)
- `ionosphere_test`: Quick validation (smaller parameters)

## Data Format

### Input CSV Structure

Benchmark runners now save enriched CSVs with scientific metrics:

```csv
benchmark_type,engine_nfft,engine_channels,engine_overlap,engine_sample_rate_hz,
frames_per_second,mean_latency_us,
sample_rate_hz,overlap,hop_size,time_resolution_ms,freq_resolution_hz,rtf,mode
throughput,4096,2,0.75,48000,1250.5,78.3,48000,0.75,1024,85.33,11.72,26.6,benchmark
latency,8192,2,0.875,48000,...
```

**Key Fields:**
- **Core engine params**: nfft, channels, overlap, sample_rate_hz
- **Performance metrics**: frames_per_second, mean_latency_us, pass_rate
- **Scientific metrics**: time_resolution_ms, freq_resolution_hz, rtf, hop_size

## Architecture Highlights

### DRY Principle
- Imports `EngineConfig` from `ionosense_hpc.config` (no duplication)
- Single source of truth for engine configuration schema

### Modular Design
- Individual analyzers: `LatencyAnalyzer`, `ThroughputAnalyzer`, `AccuracyAnalyzer`
- Orchestrator: `AnalysisEngine` coordinates all analyzers
- Clear separation: GPU processing engine (`ionosense_hpc.Engine`) vs analysis engine

### Caching
- MD5-based result caching for expensive analyses
- Automatic cache invalidation on data changes
- Configurable cache directory

### Extensibility
- Easy to add new analyzers (inherit from `AnalyzerBase`)
- Plugin architecture for custom metrics
- Flexible visualization system

## Migration from Legacy System

### Removed Components
- ❌ `experiments/scripts/analyze.py` (replaced by CLI)
- ❌ `experiments/scripts/generate_figures.py` (replaced by visualization module)
- ❌ `experiments/scripts/generate_report.py` (replaced by dual report system)
- ❌ Legacy Snakemake rules (`analyze_legacy`, `generate_figures_legacy`)

### New Components
- ✅ Modular `experiments/analysis/` package
- ✅ Pydantic data models with validation
- ✅ Statistical rigor (confidence intervals, hypothesis testing)
- ✅ Domain-specific ionosphere metrics
- ✅ Interactive Plotly visualizations
- ✅ Dual report system (general + ionosphere)
- ✅ Comprehensive CLI with subcommands

## Dependencies

Added to `pyproject.toml`:
```toml
benchmark = [
  "scikit-learn>=1.3.0",  # Scaling analysis, metrics (r2_score, RMSE)
  # ... existing deps
]
```

## Terminology

**Consistent terminology throughout:**
- "Channels" (not "Batch Size") - refers to simultaneous data streams
- "NFFT" - FFT window size
- "Overlap" - fraction of window overlap (0.0-1.0)
- "RTF" - Real-Time Factor (processing speed ratio)

## Future Enhancements

### Optional: Spectrogram Support (Phase 3.3)
Requires FFT magnitude data saving:
1. Modify benchmark runners to save FFT output (adds storage overhead)
2. Implement `spectrograms.py` data loading
3. Integrate into reports

**Current Status:** Skeleton implemented, marked optional

### Potential Additions
- MLflow experiment tracking integration
- DVC data versioning workflows
- Automated performance regression detection
- Multi-GPU benchmarking support
- Cloud artifact storage (S3, GCS)

## Testing

Integration tests pending (Phase 6.1):
```bash
# Test analysis pipeline end-to-end
pytest tests/test_analysis_integration.py

# Test report generation
pytest tests/test_reporting.py

# Test CLI commands
pytest tests/test_cli.py
```

## Documentation

- **Architecture Deep Dive**: `docs/analysis/architecture.md` (TODO)
- **Metrics Reference**: `docs/analysis/metrics.md` (TODO)
- **Ionosphere Research Guide**: `docs/analysis/ionosphere.md` (TODO)

## Quick Start Example

```bash
# 1. Run complete benchmark workflow
snakemake --cores 4 --snakefile experiments/Snakefile

# 2. Launch interactive dashboard
iono dashboard

# 3. Explore results interactively
#    - Navigate to General Performance, Ionosphere Research, or Configuration Explorer
#    - Filter by NFFT, channels, overlap
#    - Compare configurations side-by-side
#    - Export filtered data as CSV

# 4. (Optional) Statistical comparison via CLI
python -m experiments.analysis.cli compare artifacts/data \
    "engine_nfft=4096,engine_channels=2" \
    "engine_nfft=8192,engine_channels=2" \
    --metric rtf
```

## Contact

For questions or contributions:
- GitHub Issues: https://github.com/SEAL-Embedded/ionosense-hpc-lib/issues
- Email: rahsaz.kevin@gmail.com

---

**Last Updated**: 2025-10-30
**System Version**: 0.9.4
