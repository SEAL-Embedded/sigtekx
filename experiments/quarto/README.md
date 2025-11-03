# Quarto Reports

Publication-quality static report generation for ionosense benchmarks.

## Status

🚧 **Coming Soon** - Quarto integration planned for future release

This directory provides the skeleton structure for future Quarto-based reporting.

---

## Architecture

Quarto reports will complement the Streamlit dashboard by providing:
- **Publication-ready output**: PDF, HTML, Word formats
- **Professional typesetting**: LaTeX formatting for papers
- **Reproducible templates**: Git-tracked .qmd files
- **Shared analysis**: Reuses modules from `experiments/analysis/`

### Design Philosophy

**No code duplication** - Quarto templates will import existing analysis modules:

```markdown
---
title: "General Performance Report"
format: pdf
---

```{python}
# Import EXISTING modules (no duplication!)
from experiments.analysis.analyzer import AnalysisEngine
from experiments.analysis.visualization import PerformancePlotter
from experiments.streamlit.utils.data_loader import load_benchmark_data

# Load data using EXISTING data loader
data = load_benchmark_data("artifacts/data")

# Generate analysis using EXISTING engine
analyzer = AnalysisEngine()
summary = analyzer.generate_summary(data)

# Use EXISTING plotters
plotter = PerformancePlotter()
fig = plotter.plot_scaling(data, 'engine_nfft', 'frames_per_second')
fig.show()
```
```

---

## Planned Directory Structure

```
experiments/quarto/
├── README.md            # This file
├── templates/           # Quarto markdown templates
│   ├── general_performance.qmd
│   └── ionosphere_research.qmd
├── scripts/             # Generation utilities
│   └── generate_reports.py
└── _quarto.yml          # Quarto project configuration
```

---

## Planned Templates

### 1. General Performance Report

**File:** `templates/general_performance.qmd`

**Content:**
- Executive summary with peak performance metrics
- Throughput analysis (FPS, bandwidth scaling)
- Latency analysis (mean, P95, scaling)
- Accuracy validation (pass rates, error metrics)
- Scaling analysis (NFFT vs performance heatmaps)
- Configuration recommendations

**Output:** `artifacts/reports/general_performance.pdf`

### 2. Ionosphere Research Report

**File:** `templates/ionosphere_research.qmd`

**Content:**
- Introduction to VLF/ULF ionosphere monitoring
- Real-Time Factor (RTF) analysis
- Time vs frequency resolution trade-offs
- Phenomena detection suitability (lightning, SIDs, Schumann, whistlers)
- Dual-channel streaming performance
- Scientific insights and recommendations

**Output:** `artifacts/reports/ionosphere_research.pdf`

---

## Planned Usage

### Via Snakemake (Recommended)

```bash
# Generate all Quarto reports
snakemake quarto_reports --snakefile experiments/Snakefile

# Individual reports
snakemake general_performance_report --snakefile experiments/Snakefile
snakemake ionosphere_research_report --snakefile experiments/Snakefile
```

### Direct Quarto Commands

```bash
# Render single template
quarto render experiments/quarto/templates/general_performance.qmd \
    --output artifacts/reports/general_performance.pdf

# Render to multiple formats
quarto render experiments/quarto/templates/general_performance.qmd \
    --to pdf,html,docx

# Preview in browser
quarto preview experiments/quarto/templates/general_performance.qmd
```

### Programmatic Generation

```bash
# Python wrapper (future)
python experiments/quarto/scripts/generate_reports.py \
    --template general_performance \
    --output artifacts/reports/

# With parameters
python experiments/quarto/scripts/generate_reports.py \
    --template ionosphere_research \
    --experiment ionosphere_resolution \
    --format pdf
```

---

## Integration with Snakemake

### Planned Snakefile Rules

```python
# Generate general performance PDF report
rule general_performance_report:
    input:
        data="artifacts/data/ionosphere_resolution.done",
        template="experiments/quarto/templates/general_performance.qmd"
    output:
        "artifacts/reports/general_performance.pdf"
    shell:
        """
        quarto render {input.template} --output {output}
        """

# Generate ionosphere research PDF report
rule ionosphere_research_report:
    input:
        data="artifacts/data/ionosphere_streaming.done",
        template="experiments/quarto/templates/ionosphere_research.qmd"
    output:
        "artifacts/reports/ionosphere_research.pdf"
    shell:
        """
        quarto render {input.template} --output {output}
        """

# Generate all Quarto reports (optional target)
rule quarto_reports:
    input:
        "artifacts/reports/general_performance.pdf",
        "artifacts/reports/ionosphere_research.pdf"
```

### Workflow

```bash
# 1. Run benchmarks (generates data)
snakemake --cores 4 --snakefile experiments/Snakefile

# 2. (Optional) Generate Quarto reports
snakemake quarto_reports --snakefile experiments/Snakefile

# Data flow:
# benchmarks → artifacts/data/ → Quarto templates → artifacts/reports/
```

---

## Dependencies

### System Requirements

```bash
# Install Quarto (system-level)
# macOS: brew install quarto
# Windows: choco install quarto
# Linux: Download from https://quarto.org/docs/get-started/

# Verify installation
quarto check
```

### Python Requirements

```toml
# Already included in pyproject.toml
[project.optional-dependencies]
visualization = [
    "plotly>=5.18",
    "jupyter>=1.0",      # For Quarto Python integration
    # ... other deps
]
```

---

## Design Decisions

### Why Quarto?

1. **Native Python Integration**: Execute Python code in .qmd documents
2. **Multiple Output Formats**: PDF, HTML, Word from single template
3. **Professional Typesetting**: LaTeX for publication-quality PDFs
4. **Reproducibility**: Git-trackable markdown templates
5. **Cross-references**: Automatic figure/table/section numbering
6. **Bibliographies**: BibTeX integration for citations

### Streamlit vs Quarto

| Feature | Streamlit | Quarto |
|---------|-----------|--------|
| **Type** | Interactive web app | Static document |
| **Use Case** | Daily exploration | Publications/archival |
| **Output** | Browser (real-time) | PDF/HTML/Word |
| **Interactivity** | High (filters, dropdowns) | None (frozen output) |
| **Sharing** | Requires running server | Standalone files |
| **Version Control** | Code only | Templates + output |
| **Professional Look** | Dashboard style | LaTeX typesetting |

Both solutions **complement** each other - use both!

### Code Reuse Strategy

**Shared Modules:**
- `experiments/analysis/analyzer.py` → Statistical analysis
- `experiments/analysis/visualization.py` → Plotly charts
- `experiments/analysis/metrics.py` → Scientific metrics
- `experiments/streamlit/utils/data_loader.py` → CSV loading

**Benefits:**
- ✅ Update analysis logic once, both reports benefit
- ✅ Consistent metrics across platforms
- ✅ No code duplication
- ✅ Easy maintenance

---

## Future Enhancements

### Short Term
- [ ] Create `general_performance.qmd` template
- [ ] Create `ionosphere_research.qmd` template
- [ ] Add Snakemake rules for Quarto generation
- [ ] Write `generate_reports.py` CLI wrapper

### Medium Term
- [ ] Add parametrized templates (experiment-specific reports)
- [ ] Implement multi-format output (PDF + HTML + Word)
- [ ] Add custom Quarto extensions for ionosphere visualizations
- [ ] Create reusable template components (_quarto-includes/)

### Long Term
- [ ] Automated report generation in CI/CD
- [ ] Interactive HTML reports with Plotly widgets
- [ ] RevealJS presentations from templates
- [ ] Integration with MLflow for experiment tracking

---

## Examples

### Basic Quarto Template Structure

```markdown
---
title: "General Performance Report"
subtitle: "GPU Benchmark Analysis"
author: "Ionosense HPC System"
date: today
format:
  pdf:
    toc: true
    toc-depth: 2
    number-sections: true
    colorlinks: true
  html:
    toc: true
    code-fold: true
    theme: cosmo
execute:
  echo: false    # Hide code, show results only
  warning: false
---

# Executive Summary

```{python}
#| label: load-data
#| include: false

# Import EXISTING modules
from experiments.analysis.analyzer import AnalysisEngine
from experiments.streamlit.utils.data_loader import load_benchmark_data

# Load and analyze
data = load_benchmark_data("artifacts/data")
analyzer = AnalysisEngine()
summary = analyzer.generate_summary(data)
```

This report analyzes `{python} len(data)` measurements across
`{python} len(summary.configurations_tested)` configurations.

Peak throughput: **`{python} f"{summary.peak_throughput:.1f}"` FPS**

# Throughput Analysis

```{python}
#| label: fig-throughput
#| fig-cap: "Throughput scaling with NFFT size"

from experiments.analysis.visualization import PerformancePlotter

plotter = PerformancePlotter()
throughput_data = data[data['benchmark_type'] == 'throughput']

fig = plotter.plot_scaling(
    throughput_data,
    x_col='engine_nfft',
    y_col='frames_per_second',
    group_by='engine_channels'
)
fig.show()
```

As shown in @fig-throughput, throughput scales ...
```

---

## Contact

For questions about Quarto integration:
- GitHub Issues: https://github.com/SEAL-Embedded/ionosense-hpc-lib/issues
- Email: rahsaz.kevin@gmail.com

---

**Status**: Placeholder structure ready
**Next Steps**: Implement templates when ready for publication workflows
**Last Updated**: 2025-11-03
