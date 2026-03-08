# Experiment Workflow Guide

This guide covers the supported paths for running end-to-end benchmark studies. The workflow uses direct Python entry points for individual experiments and Snakemake for full pipeline orchestration.

**Version:** v0.9.5+
**See also:** `docs/benchmarking/experiment-guide.md` for the complete experiment taxonomy, `CLAUDE.md` for the full command reference.

---

## Quick Start

### Full Pipeline (Snakemake)

Run all benchmark experiments and generate data for the dashboard:

```bash
snakemake --cores 4 --snakefile experiments/Snakefile
```

- Executes all configured benchmark sweeps and writes CSVs to `artifacts/data/`
- Preview steps without executing: `snakemake --dry-run --snakefile experiments/Snakefile`
- View results interactively: `sigx dashboard`

### Single Experiment (Direct)

```bash
# Quick validation (~5 min)
python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency

# Standard streaming latency study
python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency

# Streaming throughput
python benchmarks/run_throughput.py experiment=ionosphere_streaming_throughput +benchmark=throughput
```

**Critical:** Always specify `+benchmark=latency` or `+benchmark=throughput` — no default is set.

---

## Experiment Reference

Experiment configs live in `experiments/conf/experiment/`. Select one with `experiment=<name>`:

### Ionosphere Research (48 kHz, 2-channel)

| Experiment | Mode | Purpose | Command |
|------------|------|---------|---------|
| `ionosphere_test` | Mixed | Quick sanity check | `run_latency.py experiment=ionosphere_test +benchmark=latency` |
| `ionosphere_streaming` | STREAMING | Standard real-time VLF/ULF | `run_latency.py experiment=ionosphere_streaming +benchmark=latency` |
| `ionosphere_streaming_hires` | STREAMING | High frequency resolution | `run_latency.py experiment=ionosphere_streaming_hires +benchmark=latency` |
| `ionosphere_streaming_latency` | STREAMING | Latency-optimised | `run_latency.py experiment=ionosphere_streaming_latency +benchmark=latency` |
| `ionosphere_streaming_throughput` | STREAMING | Max throughput | `run_throughput.py experiment=ionosphere_streaming_throughput +benchmark=throughput` |
| `ionosphere_batch_throughput` | BATCH | Offline max throughput | `run_throughput.py experiment=ionosphere_batch_throughput +benchmark=throughput` |

### Baseline Performance (General)

| Experiment | Mode | Purpose |
|------------|------|---------|
| `baseline_100k` | Mixed | Quick 100 kHz coverage |
| `baseline_batch_100k_latency` | BATCH | Detailed batch latency (45 configs) |
| `baseline_streaming_100k_latency` | STREAMING | Detailed streaming latency (45 configs) |
| `baseline_streaming_100k_realtime` | STREAMING | Real-time factor validation |
| `baseline_48k` | Mixed | Quick 48 kHz coverage |

### Analysis & Validation

| Experiment | Purpose |
|------------|---------|
| `execution_mode_comparison` | BATCH vs STREAMING comparison |
| `full_parameter_grid_100k` | Exhaustive 100 kHz sweep (~60 min) |
| `accuracy_validation` | Correctness vs SciPy reference |
| `low_nfft_scaling` | Low-latency NFFT study |

For the complete list and selection guide, see `docs/benchmarking/experiment-guide.md`.

---

## Direct Benchmark Commands

Each benchmark script is a Hydra application. The Snakemake rules call these same commands under the hood.

```bash
# Latency sweep across NFFT values
python benchmarks/run_latency.py --multirun \
    experiment=baseline_streaming_100k_latency \
    +benchmark=latency \
    "engine.nfft=1024,2048,4096,8192"

# Throughput sweep across channel counts
python benchmarks/run_throughput.py --multirun \
    experiment=baseline_batch_100k_throughput \
    +benchmark=throughput \
    "engine.channels=1,2,4,8"

# Accuracy validation
python benchmarks/run_accuracy.py \
    experiment=accuracy_validation \
    +benchmark=accuracy
```

Outputs land in `artifacts/data/` as unique per-configuration CSVs and `artifacts/mlruns/` for MLflow tracking.

---

## Custom Experiments

1. Create `experiments/conf/experiment/my_study.yaml`:

    ```yaml
    # @package _global_
    defaults:
      - override /engine: ionosphere_streaming

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
    ```

2. Run directly:

    ```bash
    python benchmarks/run_latency.py --multirun \
        experiment=my_study \
        +benchmark=latency
    ```

3. To include in Snakemake, add a rule to `experiments/Snakefile` following the existing pattern.

---

## Viewing Results

### Streamlit Dashboard (Recommended)

```bash
sigx dashboard        # Opens at http://localhost:8501
```

The dashboard automatically loads all CSV files from `artifacts/data/` and provides interactive filtering, comparison, and export.

### MLflow UI (Run History)

```bash
mlflow ui --backend-store-uri file://./artifacts/mlruns --port 5000
# Opens at http://localhost:5000
```

Useful for querying specific runs by parameter, comparing metrics across runs, and downloading artifacts.

### Targeted Snakemake Runs

```bash
# Run a single specific experiment
snakemake --cores 4 --snakefile experiments/Snakefile run_baseline_streaming_100k_latency

# Run all streaming baseline experiments
snakemake --cores 4 --snakefile experiments/Snakefile \
  run_baseline_streaming_100k_latency \
  run_baseline_streaming_100k_throughput \
  run_baseline_streaming_100k_realtime
```

---

## Troubleshooting

- **Hydra config not found**: confirm you're in the repo root, and the experiment YAML exists in `experiments/conf/experiment/`.
- **Missing `+benchmark=` error**: always specify `+benchmark=latency` or `+benchmark=throughput` — there is no default.
- **Dry-run to preview**: `snakemake --dry-run --snakefile experiments/Snakefile`
- **Config validation**: `python experiments/conf/validation.py experiments/conf/experiment/<name>.yaml`
- **MLflow port conflict**: `mlflow ui --backend-store-uri file://./artifacts/mlruns --port 5001`
- **Environment issues**: run `./scripts/cli.ps1 doctor` to check system health.

---

## Typical Journeys

| Goal | Command |
|------|---------|
| Quick sanity check | `python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency` |
| Full pipeline + dashboard | `snakemake --cores 4 --snakefile experiments/Snakefile && sigx dashboard` |
| Streaming real-time study | `python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency` |
| Comprehensive sweep | `snakemake --cores 8 --snakefile experiments/Snakefile run_full_parameter_grid_100k` |
| Accuracy verification | `python benchmarks/run_accuracy.py experiment=accuracy_validation +benchmark=accuracy` |

---

## Next Steps

1. Run `ionosphere_test` to confirm the environment is healthy.
2. Run `sigx dashboard` to explore results.
3. Use targeted experiment commands to study specific parameters.
4. Commit your experiment configs to version control for reproducibility.

For debugging, check `artifacts/logs/` for run logs, or open an issue with the exact command and config details.
