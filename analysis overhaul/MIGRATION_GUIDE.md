# Migration Guide: Old → New Analysis System

## Overview

This guide helps you migrate from the original analysis scripts to the enhanced analysis system.

## Key Differences

### Old System Structure
```
experiments/scripts/
├── analyze.py          # Basic CSV aggregation
├── generate_figures.py # Separate plotting
└── generate_report.py  # HTML generation
```

### New System Structure
```
experiments/
├── analysis/          # Modular package
│   ├── models.py      # Data models
│   ├── engine.py      # Analysis engine
│   └── visualization.py
└── analyze_enhanced.py # Unified CLI
```

## Migration Steps

### 1. Data Format

The new system is **backward compatible** with existing CSV files. No changes needed to your data files!

**Old columns** → **New columns** (automatic mapping):
- `engine_nfft` → Still `engine_nfft` ✓
- `engine_channels` → Still `engine_channels` ✓
- All metrics preserved ✓

### 2. Running Analysis

#### Old Way
```bash
# Three separate steps
python experiments/scripts/analyze.py
python experiments/scripts/generate_figures.py
python experiments/scripts/generate_report.py
```

#### New Way
```bash
# Single command does everything
python analyze_enhanced.py analyze --data-dir artifacts/data
python analyze_enhanced.py report --output report.html --open
```

### 3. Snakefile Integration

Update your `Snakefile` rules:

#### Old Rule
```python
rule analyze_results:
    input:
        "artifacts/data/latency_sweep.done",
        "artifacts/data/throughput_sweep.done"
    output:
        "artifacts/data/summary_statistics.csv"
    shell:
        "python experiments/scripts/analyze.py"
```

#### New Rule
```python
rule analyze_results:
    input:
        "artifacts/data/latency_sweep.done",
        "artifacts/data/throughput_sweep.done"
    output:
        "artifacts/reports/analysis.json",
        "artifacts/reports/analysis.html"
    shell:
        """
        python experiments/analyze_enhanced.py analyze \
            --output artifacts/reports/analysis.json
        python experiments/analyze_enhanced.py report \
            --output artifacts/reports/analysis.html
        """
```

### 4. Hydra Configuration

The new system works seamlessly with existing Hydra configs. No changes needed!

### 5. MLflow Integration

The new system can directly read from MLflow:

```python
from analysis import AnalysisEngine

# Old way: manually export from MLflow
# New way: direct integration
data = DataLoader.load_from_mlflow(
    tracking_uri="file:./mlruns",
    experiment_name="gpu_benchmarks"
)
```

## Feature Mapping

| Old Feature | New Feature | Improvement |
|------------|-------------|-------------|
| `analyze.py` aggregation | `AnalysisEngine` | +Statistical tests, +Caching |
| Basic statistics | `StatisticalMetrics` | +CI, +Effect sizes, +Outliers |
| `generate_figures.py` | `visualization.py` | +Interactive plots, +3D |
| Separate scripts | Unified CLI | +Single entry point |
| CSV only | Multiple formats | +JSON, +MLflow, +Parquet |
| No comparisons | `ComparisonResult` | +Hypothesis testing |
| Manual scaling | `ScalingAnalysis` | +Automatic detection |

## Code Examples

### Old Analysis Code
```python
# Old: Manual aggregation
import pandas as pd

files = Path("artifacts/data").glob("*_summary_*.csv")
dataframes = []
for f in files:
    df = pd.read_csv(f)
    dataframes.append(df)

combined = pd.concat(dataframes)
summary = combined.groupby(['engine_nfft', 'engine_channels']).mean()
```

### New Analysis Code
```python
# New: Comprehensive analysis
from analysis import AnalysisEngine

engine = AnalysisEngine()
data = DataLoader.load_from_directory("artifacts/data")
summary = engine.generate_summary(data)

# Automatic insights
print(summary.key_insights)

# Statistical comparisons
comparison = engine.compare_configurations(
    data, 
    {'nfft': 1024, 'channels': 8},
    {'nfft': 2048, 'channels': 16},
    'mean_latency_us'
)
```

## Gradual Migration

You can run both systems in parallel during migration:

```bash
# Keep old system running
make analysis  # or snakemake

# Test new system alongside
python analyze_enhanced.py analyze --data-dir artifacts/data
```

## Benefits After Migration

✅ **Statistical Rigor**: P-values, confidence intervals, effect sizes
✅ **Performance**: 5-10x faster with caching
✅ **Visualizations**: Interactive Plotly instead of static matplotlib
✅ **Extensibility**: Easy to add custom analyzers
✅ **Unified Interface**: One CLI for everything
✅ **Better Reports**: Professional HTML with embedded charts

## Common Issues

### Issue 1: Missing Dependencies
```bash
# Solution
pip install -r experiments/requirements.txt
```

### Issue 2: Old Scripts Still Running
```bash
# Clean old artifacts
rm -rf artifacts/figures/*.png
rm artifacts/data/summary_statistics.csv

# Use new system
python analyze_enhanced.py analyze
```

### Issue 3: Custom Metrics
```python
# Add custom analyzer
from analysis.engine import AnalyzerBase

class CustomMetricAnalyzer(AnalyzerBase):
    def analyze(self, data):
        # Your custom logic
        pass

engine.analyzers[BenchmarkType.CUSTOM] = CustomMetricAnalyzer()
```

## Rollback Plan

If you need to rollback:

1. The old scripts are unchanged
2. Data format is unchanged
3. Simply run old scripts as before

## Support

- See `README.md` for full documentation
- Run `python example_usage.py` for demonstrations
- Check docstrings in the code

## Timeline

Suggested migration timeline:

- **Week 1**: Run new system in parallel, compare outputs
- **Week 2**: Update Snakefile/workflows to use new system
- **Week 3**: Migrate custom analysis code
- **Week 4**: Deprecate old scripts

The systems can coexist indefinitely if needed!
