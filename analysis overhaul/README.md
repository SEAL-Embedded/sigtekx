# Enhanced GPU Pipeline Analysis System

## Overview

A complete ground-up rebuild of the GPU benchmark analysis pipeline with:

- 🔬 **Statistical Rigor** - Proper hypothesis testing, confidence intervals, effect sizes
- 📊 **Advanced Visualizations** - Interactive Plotly charts, publication-quality figures
- ⚡ **Performance** - Caching, incremental computation, optimized data handling
- 🔧 **Modularity** - Extensible analyzer framework, plug-in architecture
- 📈 **Scaling Analysis** - Automatic detection of scaling patterns and saturation points
- 📝 **Comprehensive Reports** - HTML reports with embedded visualizations

## Architecture

```
experiments/
├── analysis/
│   ├── __init__.py         # Package initialization
│   ├── models.py           # Data models (Pydantic)
│   ├── engine.py           # Core analysis engine
│   └── visualization.py    # Plotting and reports
├── analyze_enhanced.py     # CLI interface
├── requirements.txt        # Dependencies
└── README.md              # This file
```

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Basic Usage

```bash
# Run full analysis
python analyze_enhanced.py analyze --data-dir artifacts/data

# Generate HTML report
python analyze_enhanced.py report --output report.html --open

# Compare configurations
python analyze_enhanced.py compare \
    --config1 "nfft=1024,channels=8" \
    --config2 "nfft=2048,channels=16" \
    --plot comparison.html

# Analyze scaling patterns
python analyze_enhanced.py scaling \
    --parameter engine_nfft \
    --metric mean_latency_us \
    --plot

# Watch mode (real-time monitoring)
python analyze_enhanced.py watch \
    --interval 10 \
    --auto-report live_report.html
```

## Features

### 1. Statistical Analysis

- **Hypothesis Testing**: Automatic selection of appropriate tests (t-test, Mann-Whitney U)
- **Confidence Intervals**: 95% CI for all metrics
- **Effect Sizes**: Cohen's d for meaningful comparisons
- **Outlier Detection**: IQR-based outlier identification
- **Distribution Analysis**: Normality testing, skewness, kurtosis

### 2. Modular Analyzers

Each benchmark type has a specialized analyzer:

- **LatencyAnalyzer**: Jitter, stability scores, tail latencies
- **ThroughputAnalyzer**: Memory efficiency, GPU utilization
- **AccuracyAnalyzer**: Reliability scores, SNR analysis  
- **RealtimeAnalyzer**: Compliance rates, deadline analysis

### 3. Scaling Analysis

Automatically detects:
- Linear vs sublinear vs superlinear scaling
- Saturation points
- Optimal configurations
- Efficiency degradation

### 4. Caching System

- Automatic result caching
- Incremental computation
- Cache invalidation on data changes

### 5. Visualization

Interactive Plotly visualizations:
- Distribution comparisons
- Confidence interval plots
- Scaling curves with model fits
- 3D performance surfaces
- Heatmaps and correlation matrices

## Data Format

Expected CSV columns:
- `engine_nfft`: FFT size
- `engine_channels`: Batch/channel count
- `benchmark_type`: Type of benchmark (optional)
- Metric columns: `mean_latency_us`, `frames_per_second`, etc.

## Programmatic Usage

```python
from analysis import AnalysisEngine
from analysis.visualization import ReportGenerator
from pathlib import Path
import pandas as pd

# Load data
data = pd.read_csv("artifacts/data/summary_statistics.csv")

# Create engine
engine = AnalysisEngine()

# Run analysis
summary = engine.generate_summary(data, "My Experiment")

# Generate specific analysis
scaling = engine.analyze_scaling(
    data,
    parameters=['engine_nfft'],
    metrics=['mean_latency_us']
)

# Statistical comparison
comparison = engine.compare_configurations(
    data,
    config1={'engine_nfft': 1024, 'engine_channels': 8},
    config2={'engine_nfft': 2048, 'engine_channels': 16},
    metric='mean_latency_us'
)

# Generate report
report_gen = ReportGenerator()
report_gen.generate_full_report(summary, Path("report.html"))
```

## Extending the System

### Adding a New Analyzer

```python
from analysis.engine import AnalyzerBase

class CustomAnalyzer(AnalyzerBase):
    def get_metrics(self) -> List[str]:
        return ['custom_metric1', 'custom_metric2']
    
    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        # Your analysis logic here
        results = {}
        for config, group in data.groupby(['engine_nfft', 'engine_channels']):
            # Compute custom metrics
            results[f"{config[0]}_{config[1]}"] = {
                'custom_metric1': compute_metric1(group),
                'custom_metric2': compute_metric2(group)
            }
        return results

# Register analyzer
engine.analyzers[BenchmarkType.CUSTOM] = CustomAnalyzer()
```

### Adding Custom Visualizations

```python
from analysis.visualization import VisualizationConfig
import plotly.graph_objects as go

def plot_custom_analysis(data: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    
    # Add your traces
    fig.add_trace(go.Scatter(
        x=data['engine_nfft'],
        y=data['custom_metric'],
        mode='lines+markers'
    ))
    
    fig.update_layout(
        title="Custom Analysis",
        xaxis_title="NFFT",
        yaxis_title="Custom Metric"
    )
    
    return fig
```

## Key Improvements Over Original

### Original System Issues
- Basic CSV aggregation only
- No statistical testing
- Simple matplotlib plots
- No caching
- Limited extensibility
- Separate scripts for each task

### New System Benefits
- ✅ Full statistical analysis pipeline
- ✅ Modular, extensible architecture
- ✅ Interactive visualizations
- ✅ Unified CLI and API
- ✅ Caching and incremental computation
- ✅ Comprehensive HTML reports
- ✅ Real-time monitoring mode
- ✅ MLflow integration support

## Performance Considerations

### Memory Usage
- Incremental data loading for large datasets
- Efficient pandas operations
- Caching to reduce recomputation

### Computation
- Vectorized numpy operations
- Parallel analysis where possible
- Smart caching of expensive computations

### Scalability
- Designed for datasets up to 100k measurements
- Can be extended with Dask for larger datasets
- Database backend support possible

## Roadmap

Future enhancements:
- [ ] Database backend (PostgreSQL/ClickHouse)
- [ ] Distributed analysis with Dask
- [ ] ML-based anomaly detection
- [ ] Automated performance regression detection
- [ ] Integration with CI/CD pipelines
- [ ] REST API for remote analysis
- [ ] Real-time streaming analysis

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! The modular design makes it easy to add:
- New analyzers for different metrics
- Additional statistical tests
- Custom visualizations
- Data format adapters

## Support

For issues or questions:
1. Check the examples in this README
2. Review the docstrings in the code
3. Open an issue on GitHub
