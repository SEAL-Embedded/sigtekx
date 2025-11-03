# Ionosense HPC Analysis System

Core analysis modules shared by **two primary reporting solutions**.

## 🎯 Reporting Solutions

Ionosense uses two complementary approaches for presenting benchmark results:

### 1. Streamlit Dashboard (Interactive)
**Location:** `experiments/streamlit/`
**Purpose:** Daily exploration, parameter tuning, interactive analysis
**Launch:** `iono dashboard`

**Features:**
- Three interactive pages: General Performance, Ionosphere Research, Configuration Explorer
- Real-time data loading from `artifacts/data/`
- Interactive filtering, sorting, and comparison
- CSV export capabilities
- Dynamic visualizations with user-selectable axes

### 2. Quarto Reports (Static)
**Location:** `experiments/quarto/` (coming soon)
**Purpose:** Publication-quality reports, archival, presentations
**Launch:** `snakemake quarto_reports`

**Features:**
- PDF/HTML/Word output with LaTeX typesetting
- Cross-references and bibliographies
- Professional formatting for papers and presentations
- Git-tracked templates for reproducibility

---

## 📦 Shared Analysis Modules

Both reporting solutions import from `experiments/analysis/`:

### Core Modules

```
experiments/analysis/
├── analyzer.py          # Statistical analysis engine
│   └── AnalysisEngine   # Orchestrator for all analyzers
│       ├── LatencyAnalyzer
│       ├── ThroughputAnalyzer
│       ├── AccuracyAnalyzer
│       ├── RealtimeAnalyzer
│       └── ScientificMetricsAnalyzer
│
├── visualization.py     # Plotly charts
│   ├── PerformancePlotter
│   └── StatisticalPlotter
│
├── metrics.py           # Scientific metrics
│   └── assess_ionosphere_suitability()
│
├── models.py            # Pydantic data models
│   ├── BenchmarkResult
│   ├── ExperimentSummary
│   └── ComparisonResult
│
└── cli.py               # Command-line interface
    ├── analyze
    ├── compare
    └── scaling
```

### Key Features

**Scientific Metrics:**
- **Real-Time Factor (RTF)**: Processing speed vs signal speed
- **Time Resolution**: Temporal granularity (ms)
- **Frequency Resolution**: Spectral detail (Hz)
- **Hop Size**: Frame advance between STFT windows
- Domain-specific suitability for ionosphere phenomena

**Statistical Rigor:**
- Confidence intervals (95% default)
- Hypothesis testing (t-test, Mann-Whitney U)
- Effect sizes (Cohen's d)
- Scaling analysis (linear, logarithmic, power-law, saturation detection)

**Performance:**
- MD5-based caching for expensive analyses
- Automatic cache invalidation on data changes
- Configurable cache directory

---

## Usage

### Interactive Dashboard (Primary Method)

```bash
# Launch Streamlit dashboard
iono dashboard

# OR manually
streamlit run experiments/streamlit/app.py
```

Access at http://localhost:8501

### Statistical Analysis (CLI)

```bash
# Generate analysis summary
python -m experiments.analysis.cli analyze artifacts/data \
    --output artifacts/analysis/summary.json \
    --experiment-name "Ionosphere HPC Analysis"
```

### Configuration Comparison

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

---

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
```

### Experiment Configs

- `ionosphere_resolution`: NFFT sweep (4096-32768), overlap study
- `ionosphere_temporal`: Overlap optimization (0.25-0.9375)
- `ionosphere_test`: Quick validation (smaller parameters)

---

## Data Format

### Input CSV Structure

Benchmark runners save enriched CSVs with scientific metrics:

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

---

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

---

## Dependencies

Added to `pyproject.toml`:
```toml
benchmark = [
  "scikit-learn>=1.3.0",  # Scaling analysis, metrics (r2_score, RMSE)
  # ... existing deps
]

visualization = [
  "streamlit>=1.30.0",    # Interactive dashboard
  "watchdog>=3.0",        # Auto-reload support
  # ... existing deps
]
```

---

## Terminology

**Consistent terminology throughout:**
- "Channels" - refers to simultaneous data streams
- "NFFT" - FFT window size
- "Overlap" - fraction of window overlap (0.0-1.0)
- "RTF" - Real-Time Factor (processing speed ratio)

---

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

---

## Contact

For questions or contributions:
- GitHub Issues: https://github.com/SEAL-Embedded/ionosense-hpc-lib/issues
- Email: rahsaz.kevin@gmail.com

---

**Last Updated**: 2025-11-03
**System Version**: 0.9.5
