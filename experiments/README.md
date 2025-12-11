# Experiments Directory

Benchmark execution and reporting for sigtekx.

## Directory Structure

```
experiments/
├── analysis/         # Shared analysis modules (core logic)
│   ├── analyzer.py   # Statistical analysis engine
│   ├── visualization.py  # Plotly charts
│   ├── metrics.py    # Scientific metrics
│   └── models.py     # Data models
│
├── streamlit/        # Interactive dashboard (PRIMARY)
│   ├── app.py        # Main dashboard entry point
│   ├── pages/        # Three interactive pages
│   └── utils/        # Data loading utilities
│
├── quarto/           # Static reports (FUTURE)
│   └── templates/    # Publication templates
│
├── conf/             # Hydra configuration
│   ├── benchmark/    # Benchmark configs (latency, throughput, etc.)
│   ├── engine/       # Engine configs (ionosphere_realtime, etc.)
│   └── experiment/   # Experiment sweeps (ionosphere_resolution, etc.)
│
└── Snakefile         # Workflow orchestration
```

## 🎯 Two Reporting Solutions

Ionosense uses two complementary approaches for presenting benchmark results:

### 1. Streamlit Dashboard 🚀 (PRIMARY)

**Interactive exploration and analysis**

```bash
# Launch dashboard
sigx dashboard

# OR manually
streamlit run experiments/streamlit/app.py

# Access at http://localhost:8501
```

**Three Interactive Pages:**
1. **General Performance** - Throughput, latency, accuracy, scaling (6 tabs)
2. **Ionosphere Research** - VLF/ULF phenomena, RTF analysis, resolution trade-offs (7 tabs)
3. **Configuration Explorer** - Interactive filtering and comparison

**When to use:**
- Daily benchmark analysis
- Parameter tuning and optimization
- Interactive exploration of results
- Quick comparisons between configurations
- Exporting filtered data

### 2. Quarto Reports 📄 (FUTURE)

**Publication-quality static reports**

```bash
# Generate publication reports (coming soon)
snakemake quarto_reports

# Outputs PDF/HTML/Word documents
```

**Features:**
- LaTeX typesetting for papers
- Cross-references and bibliographies
- Git-tracked reproducible templates
- PDF, HTML, and Word output

**When to use:**
- Publication submissions
- Technical presentations
- Archival documentation
- Sharing results offline

---

## Quick Start

### Run Benchmarks

```bash
# Full ionosphere benchmark suite
snakemake --cores 4 --snakefile experiments/Snakefile

# Quick test run
snakemake test --snakefile experiments/Snakefile

# Individual experiments
snakemake run_ionosphere_resolution --snakefile experiments/Snakefile
snakemake run_ionosphere_temporal --snakefile experiments/Snakefile
```

### View Results

```bash
# Launch interactive dashboard (primary method)
sigx dashboard

# Statistical analysis via CLI
python -m experiments.analysis.cli analyze artifacts/data

# Configuration comparison
python -m experiments.analysis.cli compare artifacts/data \
    "engine_nfft=4096,engine_channels=2" \
    "engine_nfft=8192,engine_channels=2" \
    --metric mean_latency_us
```

---

## Workflow

### Complete Research Workflow

```bash
# 1. Run benchmarks (generates data in artifacts/data/)
snakemake --cores 4 --snakefile experiments/Snakefile

# 2. Explore results interactively
sigx dashboard

# 3. (Optional) Generate publication reports (future)
snakemake quarto_reports

# 4. (Optional) View experiment tracking
mlflow ui --backend-store-uri file://./artifacts/mlruns
```

### Data Flow

```
Hydra Configs → Benchmark Runners → CSV Data → Reporting
(conf/)         (benchmarks/)        (artifacts/data/)  (streamlit/ + quarto/)
                                                          ↓
                                              Shared Analysis Modules
                                              (experiments/analysis/)
```

---

## Configuration System

### Benchmark Configurations

**Location:** `experiments/conf/benchmark/`

- `latency.yaml` - Latency measurement (5000 iterations)
- `throughput.yaml` - Throughput measurement (10s duration)
- `realtime.yaml` - Real-time streaming (10s duration)
- `accuracy.yaml` - Accuracy validation vs NumPy

### Engine Configurations

**Location:** `experiments/conf/engine/`

Pre-configured settings for common use cases:

| Engine | NFFT | Overlap | Channels | Use Case |
|--------|------|---------|----------|----------|
| `ionosphere_realtime` | 2048 | 0.625 | 2 | Real-time processing |
| `ionosphere_hires` | 8192 | 0.75 | 2 | High-resolution analysis |
| `ionosphere_longterm` | 4096 | 0.875 | 2 | Long-duration studies |

### Experiment Configurations

**Location:** `experiments/conf/experiment/`

Parameter sweeps for comprehensive analysis:

| Experiment | Description | Parameters |
|------------|-------------|------------|
| `ionosphere_resolution` | NFFT sweep | 4096-32768, overlap 0.5-0.875 |
| `ionosphere_temporal` | Overlap study | 0.25-0.9375, channels 16-128 |
| `ionosphere_multiscale` | Cross-scale | Multiple engine configs |
| `ionosphere_test` | Quick validation | Smaller parameters |

---

## Shared Analysis Core

Both Streamlit and Quarto import from `experiments/analysis/`:

**Key Modules:**
- **analyzer.py** - `AnalysisEngine`, statistical analyzers
- **visualization.py** - `PerformancePlotter`, `StatisticalPlotter`
- **metrics.py** - `assess_ionosphere_suitability()`
- **models.py** - Pydantic data models
- **cli.py** - Command-line tools (analyze, compare, scaling)

**Benefits:**
- ✅ No code duplication
- ✅ Update once, both reports benefit
- ✅ Consistent metrics across platforms
- ✅ Shared caching and optimization

---

## Data Output

### Benchmark Data

**Location:** `artifacts/data/`

**Format:** Enriched CSV with scientific metrics

```csv
benchmark_type,engine_nfft,engine_channels,engine_overlap,
frames_per_second,mean_latency_us,
time_resolution_ms,freq_resolution_hz,rtf
```

**Consumed by:**
- Streamlit dashboard (real-time loading)
- Quarto reports (template rendering)
- CLI analysis tools

---

## Dependencies

### Core Requirements

```toml
# Scientific computing
numpy>=1.24
pandas>=2.0
scipy>=1.10

# Visualization
plotly>=5.18

# Reporting
streamlit>=1.30.0      # Interactive dashboard
watchdog>=3.0          # Auto-reload

# (Future) Quarto via system install
# pip install jupyterlab  # Optional: for Quarto integration
```

### Development Requirements

```bash
# Install with benchmark dependencies
pip install -e ".[benchmark,visualization]"
```

---

## Examples

### Run Specific Experiment

```bash
# High-resolution analysis
python benchmarks/run_throughput.py --multirun \
    experiment=ionosphere_resolution +benchmark=throughput

# Temporal characteristics study
python benchmarks/run_throughput.py --multirun \
    experiment=ionosphere_temporal +benchmark=throughput

# Multi-scale comprehensive analysis
python benchmarks/run_latency.py \
    experiment=ionosphere_multiscale +benchmark=latency
```

### Interactive Exploration

```bash
# Launch dashboard
sigx dashboard

# Navigate to pages:
# - General Performance: Overall benchmark metrics
# - Ionosphere Research: Domain-specific analysis
# - Configuration Explorer: Filter and compare

# Use sidebar filters:
# - NFFT size, channels, overlap, mode
# - Real-time filtering updates all charts
# - Side-by-side configuration comparison
# - Export filtered data as CSV
```

### Statistical Analysis

```bash
# Generate comprehensive summary
python -m experiments.analysis.cli analyze artifacts/data \
    --output artifacts/analysis/summary.json

# Compare two configurations
python -m experiments.analysis.cli compare artifacts/data \
    "engine_nfft=4096,engine_channels=2" \
    "engine_nfft=8192,engine_channels=2" \
    --metric rtf

# Analyze scaling patterns
python -m experiments.analysis.cli scaling artifacts/data \
    --parameter engine_nfft \
    --metric mean_latency_us
```

---

## Troubleshooting

### No Data Found

```
⚠️ No benchmark data found. Please run benchmarks first.
```

**Solution:**
```bash
# Run at least one benchmark
snakemake run_ionosphere_resolution --snakefile experiments/Snakefile
```

### Streamlit Import Errors

**Problem:** `ModuleNotFoundError: No module named 'streamlit'`

**Solution:**
```bash
# Install visualization dependencies
pip install -e ".[visualization]"
```

### Hydra Configuration Errors

**Problem:** `MissingMandatoryValue: Missing mandatory value: benchmark`

**Solution:** Always specify `+benchmark=<type>` when running benchmarks:
```bash
# ✅ CORRECT
python benchmarks/run_throughput.py +benchmark=throughput

# ❌ WRONG (missing +benchmark)
python benchmarks/run_throughput.py
```

---

## Contact

For questions or contributions:
- GitHub Issues: https://github.com/SEAL-Embedded/sigtekx/issues
- Email: rahsaz.kevin@gmail.com

---

**Last Updated**: 2025-11-03
**Version**: 0.9.5
