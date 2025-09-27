# Claude Code Quick Reference - Direct Toolchain Usage

## Native Tool Commands (Recommended)

### Ionosphere Research Configurations
```bash
# High-resolution analysis (nfft=4096-32768)
python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput

# Temporal characteristics study (overlap optimization)
python benchmarks/run_throughput.py --multirun experiment=ionosphere_temporal +benchmark=throughput

# Comprehensive multi-scale analysis
python benchmarks/run_latency.py experiment=ionosphere_multiscale +benchmark=latency

# Single experiment runs
python benchmarks/run_latency.py experiment=ionosphere_resolution +benchmark=latency
```

### Direct Hydra Usage
```bash
# Native Hydra multirun syntax (IMPORTANT: specify +benchmark=throughput for throughput tests)
python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput
python benchmarks/run_latency.py --multirun engine.nfft=1024,2048,4096,8192 +benchmark=latency

# Single experiments with parameter overrides
python benchmarks/run_latency.py experiment=baseline engine.nfft=8192 +benchmark=latency
python benchmarks/run_throughput.py experiment=ionosphere_temporal +benchmark=throughput

# Quick testing with lightweight config
python benchmarks/run_throughput.py --multirun experiment=ionosphere_test +benchmark=throughput
```

### Complete Research Workflow
```bash
# Run experiments (IMPORTANT: add +benchmark=throughput)
python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput

# Execute analysis pipeline
snakemake --cores 4 --snakefile experiments/Snakefile
snakemake --cores 4 generate_figures --snakefile experiments/Snakefile

# View results
mlflow ui --backend-store-uri file://./artifacts/mlruns

# Data versioning
dvc status
dvc repro
```

## Available Engine Configurations

| Engine | NFFT | Overlap | Batch | Use Case |
|--------|------|---------|-------|----------|
| `ionosphere_realtime` | 2048 | 0.625 | 8 | Real-time processing |
| `ionosphere_hires` | 8192 | 0.75 | 16 | High-resolution analysis |
| `ionosphere_longterm` | 4096 | 0.875 | 64 | Long-duration studies |

## Available Experiment Configurations

| Experiment | Description | Parameter Sweeps |
|------------|-------------|------------------|
| `ionosphere_resolution` | NFFT resolution study | nfft: 4096-32768, overlap: 0.5-0.875 |
| `ionosphere_temporal` | Temporal characteristics | overlap: 0.25-0.9375, batch: 16-128 |
| `ionosphere_multiscale` | Comprehensive analysis | Multi-engine, cross-scale sweeps |

## Essential CLI Commands (Development Only)

```bash
# Environment and build (use CLI for these)
./scripts/cli.ps1 setup                   # Environment setup
./scripts/cli.ps1 build                   # Build project
./scripts/cli.ps1 test                    # Run tests
./scripts/cli.ps1 format                  # Format code
./scripts/cli.ps1 lint                    # Lint code
./scripts/cli.ps1 doctor                  # System health check
```

## Tool-Specific Quick Commands

### MLflow Experiment Tracking
```bash
# Start MLflow UI
mlflow ui --backend-store-uri file://./artifacts/mlruns --port 5000

# List experiments
mlflow experiments list --tracking-uri file://./artifacts/mlruns

# Search runs
mlflow runs search --tracking-uri file://./artifacts/mlruns --filter "metrics.latency < 100"
```

### Snakemake Workflows
```bash
# Run complete pipeline
snakemake --cores 4 --snakefile experiments/Snakefile

# Run specific targets
snakemake --cores 4 generate_figures --snakefile experiments/Snakefile
snakemake --cores 4 analyze_results --snakefile experiments/Snakefile

# Dry run to see what would execute
snakemake --dry-run --snakefile experiments/Snakefile
```

### DVC Data Management
```bash
# Check data status
dvc status

# Reproduce pipeline
dvc repro

# Sync data
dvc push
dvc pull

# View pipeline
dvc dag
```

## System Reliability Notes

### Configuration System
- All ionosphere configurations validated and working
- MLflow integration properly configured
- Direct tool access ensures full feature availability
- No artificial CLI limitations

### Critical Requirements
- **ALWAYS specify `+benchmark=throughput`** when using `run_throughput.py`
- **ALWAYS specify `+benchmark=latency`** when using `run_latency.py`
- **No default benchmark** - must be explicitly specified to prevent config conflicts
- **Use `experiment=ionosphere_test`** for quick testing with smaller parameters

### Working Command Templates
```bash
# ✅ CORRECT - includes +benchmark=throughput
python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput

# ✅ CORRECT - includes +benchmark=latency
python benchmarks/run_latency.py experiment=ionosphere_multiscale +benchmark=latency

# ❌ WRONG - no benchmark specified (will fail)
python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution
```

Last updated: 2025-09-27 (Fixed benchmark config override issue)