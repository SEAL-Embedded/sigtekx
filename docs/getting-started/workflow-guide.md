# 🧪 Complete Ionosphere Experiment Workflow Guide

**From Config → Experiments → Analysis → Charts → Reports**

This guide shows you exactly how to run complete ionosphere experiments without needing to understand the complex configuration system.

## 🚀 Quick Start (Recommended)

The easiest way to run a complete study:

```bash
# Show available experiment presets
python run_complete_study.py --list-presets

# Run a complete ionosphere resolution study (config → charts → report)
python run_complete_study.py --preset ionosphere_resolution

# Run a quick test to validate your setup
python run_complete_study.py --preset quick_test
```

That's it! The script will:
1. ✅ Validate your environment and configuration
2. 🧪 Run the experiments with proper parameters
3. 📊 Analyze the results and generate statistics
4. 📈 Create charts and visualizations
5. 📋 Generate a final HTML report
6. 🌐 Tell you where to find everything

## 📋 Available Experiment Presets

| Preset | Purpose | Runtime | Output Focus |
|--------|---------|---------|--------------|
| `ionosphere_resolution` | High-resolution frequency analysis | 20-30 min | Frequency resolution vs computational cost |
| `ionosphere_temporal` | Temporal characteristics optimization | 30-45 min | Temporal resolution and scintillation detection |
| `ionosphere_multiscale` | Comprehensive multi-scale analysis | 60+ min | Complete performance characterization |
| `quick_test` | Fast validation test | 5-10 min | System validation and basic functionality |
| `baseline` | Standard performance baseline | 15-25 min | Baseline metrics across parameter ranges |

## 🛠️ Manual Workflow (Advanced)

If you want to run steps manually or customize the process:

### Step 1: Run Individual Experiments

```bash
# Throughput analysis
python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput

# Latency analysis
python benchmarks/run_latency.py --multirun experiment=ionosphere_temporal +benchmark=latency

# Accuracy analysis
python benchmarks/run_accuracy.py --multirun experiment=baseline +benchmark=accuracy
```

### Step 2: Run Analysis Pipeline

```bash
# Generate analysis and figures using Snakemake
snakemake --cores 4 --snakefile experiments/Snakefile

# Or run individual analysis steps
python experiments/scripts/analyze.py
python experiments/scripts/generate_figures.py
python experiments/scripts/generate_report.py
```

### Step 3: View Results

```bash
# Interactive MLflow tracking UI
mlflow ui --backend-store-uri file://./artifacts/mlruns

# Open the final HTML report
start artifacts/reports/final_report.html  # Windows
open artifacts/reports/final_report.html   # macOS
```

## 📊 Understanding Your Results

After running an experiment, you'll find:

### 📁 **artifacts/mlruns/**
- Interactive MLflow experiment tracking
- Compare different parameter combinations
- Drill down into individual runs

### 📁 **artifacts/data/**
- Raw experimental data (CSV/Parquet files)
- Summary statistics
- Performance metrics

### 📁 **artifacts/figures/**
- `latency_vs_nfft.png` - Latency scaling with FFT size
- `throughput_scaling.png` - Throughput vs batch size
- `accuracy_heatmap.png` - Accuracy across parameter space
- `combined_analysis.png` - Multi-metric overview

### 📁 **artifacts/reports/**
- `final_report.html` - Complete analysis report
- Includes all figures, statistics, and recommendations

## ⚙️ Configuration System (Optional Deep Dive)

If you want to understand or customize the configuration system:

### Configuration Structure
```
experiments/conf/
├── config.yaml              # Main configuration
├── engine/                  # Engine configurations
│   ├── ionosphere_realtime.yaml
│   ├── ionosphere_hires.yaml
│   └── ionosphere_longterm.yaml
├── experiment/              # Experiment definitions
│   ├── ionosphere_resolution.yaml
│   ├── ionosphere_temporal.yaml
│   └── ionosphere_multiscale.yaml
└── benchmark/               # Benchmark settings
    ├── throughput.yaml
    ├── latency.yaml
    └── accuracy.yaml
```

### Creating Custom Experiments

Create a new file in `experiments/conf/experiment/my_custom.yaml`:

```yaml
# @package _global_
defaults:
  - override /engine: ionosphere_hires

experiment:
  name: my_custom_study
  description: Custom ionosphere analysis
  tags: [custom, ionosphere]

hydra:
  mode: MULTIRUN
  sweeper:
    params:
      engine.nfft: 2048,4096,8192
      engine.overlap: 0.5,0.75
      engine.batch: 8,16,32
```

Then run it:
```bash
python run_complete_study.py --preset my_custom_study
```

## 🔧 Troubleshooting

### Environment Issues
```bash
# Check if everything is properly installed
python run_complete_study.py --list-presets
```

### Configuration Validation
```bash
# Validate a specific config file
python experiments/conf/validation.py experiments/conf/experiment/ionosphere_resolution.yaml
```

### MLflow Issues
```bash
# If MLflow UI won't start, check the tracking URI
mlflow ui --backend-store-uri file://./artifacts/mlruns --port 5000
```

### Missing Dependencies
```bash
# Install missing packages
pip install hydra-core mlflow snakemake pandas matplotlib seaborn plotly
```

## 🎯 Common Use Cases

### "I want to find the best parameters for real-time ionosphere monitoring"
```bash
python run_complete_study.py --preset ionosphere_temporal
```
→ Focus on temporal resolution and latency optimization

### "I need comprehensive performance characterization"
```bash
python run_complete_study.py --preset ionosphere_multiscale
```
→ Complete analysis across all engines and parameter ranges

### "I want to validate my setup quickly"
```bash
python run_complete_study.py --preset quick_test
```
→ Fast validation with minimal parameters

### "I want to compare different FFT sizes for frequency resolution"
```bash
python run_complete_study.py --preset ionosphere_resolution
```
→ High-resolution frequency analysis study

## 💡 Tips & Best Practices

### Performance Tips
- Start with `quick_test` to validate your setup
- Use `baseline` for standard comparisons
- Reserve `ionosphere_multiscale` for comprehensive studies

### Resource Management
- Large experiments can take 1+ hours
- Monitor GPU memory usage with large NFFT values
- Use smaller parameter ranges for initial exploration

### Analysis Tips
- Always check the HTML report first for overview
- Use MLflow UI for detailed parameter exploration
- Look at individual figures for specific insights

### Reproducibility
- All experiments are automatically seeded for reproducibility
- Config files are version controlled
- MLflow tracks all parameters and metrics

## 📈 Next Steps

1. **Start Simple**: Run `python run_complete_study.py --preset quick_test`
2. **Explore Results**: Open the HTML report and MLflow UI
3. **Scale Up**: Try `ionosphere_resolution` or `ionosphere_temporal`
4. **Customize**: Create your own experiment configs
5. **Analyze**: Use the generated data for your research

## 🆘 Need Help?

- Check the validation output for parameter issues
- Look at the HTML report for automated recommendations
- Use MLflow UI to compare different experiments
- Examine individual figures in `artifacts/figures/`

---

**Remember**: You don't need to understand the complex config system to get great results. Just use the presets and focus on your research! 🚀