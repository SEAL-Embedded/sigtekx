# Ionosense HPC Analysis System

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

### 2. **Dual Report System**
- **General Performance Report**: Comprehensive benchmark analysis
  - Throughput, latency, accuracy statistics
  - Scaling analysis and parameter heatmaps
  - Configuration recommendations
- **Ionosphere Research Report**: Domain-specific analysis
  - RTF vs frequency resolution trade-offs
  - Time/frequency resolution trade-off space
  - Phenomena detection suitability (lightning, SIDs, Schumann, whistlers)
  - Multi-channel performance for direction finding
  - High-resolution configuration analysis

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

### Generate Reports

```bash
# Generate both reports (general + ionosphere)
python -m experiments.analysis.cli report artifacts/data \
    --output-dir artifacts/reports \
    --generate-plots
```

**Outputs:**
- `artifacts/reports/general_performance_report.html`
- `artifacts/reports/ionosphere_research_report.html`
- `artifacts/reports/plots/*.html` (interactive Plotly plots)

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
# Run complete ionosphere analysis workflow
snakemake --cores 4 --snakefile experiments/Snakefile

# Individual steps
snakemake run_ionosphere_resolution  # High-res analysis
snakemake run_ionosphere_temporal    # Temporal characteristics
snakemake analyze_results            # Generate summary
snakemake generate_reports           # Create HTML reports
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
# 1. Run ionosphere experiments
python benchmarks/run_throughput.py --multirun \
    experiment=ionosphere_resolution +benchmark=throughput

python benchmarks/run_latency.py --multirun \
    experiment=ionosphere_resolution +benchmark=latency

# 2. Generate analysis and reports
python -m experiments.analysis.cli analyze artifacts/data
python -m experiments.analysis.cli report artifacts/data \
    --output-dir artifacts/reports --generate-plots

# 3. View reports
# Open artifacts/reports/general_performance_report.html
# Open artifacts/reports/ionosphere_research_report.html

# 4. Compare configurations
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
