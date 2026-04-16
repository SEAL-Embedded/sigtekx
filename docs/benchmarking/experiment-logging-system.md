# Experiment Logging System

**Last Updated**: 2025-01-03
**Purpose**: Explain how SigTekX logs, stores, and tracks benchmark experiments

---

## Executive Summary

SigTekX uses a **three-layer local storage system** for experiment data:

| Layer | Technology | Purpose | Git Tracked? | Size |
|-------|-----------|---------|--------------|------|
| **Experiment Tracking** | MLflow | Queryable metrics, run comparisons, parameter tracking | ❌ No | ~40MB |
| **Analysis Data** | CSV files | Streamlit dashboard, human-readable summaries | ❌ No | ~767KB |
| **Raw Measurements** | Parquet files | Detailed per-iteration data, archival | ❌ No | Included in 767KB |

**Key Point**: Experiment data has **two tiers**:
1. **Ephemeral** (`artifacts/`): Deleted regularly, regenerated from code (~41MB)
2. **Persistent** (`datasets/`): Preserved snapshots for regression tracking (manually managed)

Both are **gitignored** (too large, binary, hardware-specific). Only code and configs are version-controlled.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Benchmark Script (run_latency.py, run_throughput.py, etc.)     │
│ - Runs experiment with Hydra config                             │
│ - Collects measurements (latency, throughput, accuracy)         │
└──────────────────┬──────────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┬──────────────────┬────────────────┐
        ▼                     ▼                  ▼                ▼
┌───────────────┐    ┌────────────────┐   ┌─────────────┐   ┌────────────┐
│   MLflow      │    │  CSV Summary   │   │  Parquet    │   │ .done      │
│  (tracking)   │    │  (dashboard)   │   │ (raw data)  │   │ (markers)  │
├───────────────┤    ├────────────────┤   ├─────────────┤   ├────────────┤
│ Queryable DB  │    │ Human-readable │   │ Columnar    │   │ Snakemake  │
│ Run history   │    │ Streamlit data │   │ Compressed  │   │ completion │
│ Parameters    │    │ Unique per     │   │ Per-config  │   │ tracking   │
│ Metrics       │    │ configuration  │   │ All iters   │   │            │
│ Artifacts     │    │                │   │             │   │            │
└───────┬───────┘    └────────┬───────┘   └──────┬──────┘   └─────┬──────┘
        │                     │                  │                │
        └─────────────────────┴──────────────────┴────────────────┘
                                    │
                            ▼       ▼       ▼
                    ┌─────────────────────────────┐
                    │   artifacts/ (gitignored)   │
                    │   - mlruns/   (~40MB)       │
                    │   - data/     (~767KB)      │
                    └─────────────────────────────┘
```

---

## Layer 1: MLflow Experiment Tracking

### What is MLflow?

MLflow is an open-source platform for tracking ML/research experiments. Think of it as a **local database for experiments** that provides:
- Run history with timestamps
- Parameter tracking (NFFT, channels, overlap, etc.)
- Metric tracking (latency, throughput, RTF, etc.)
- Artifact storage (CSVs, Parquet files)
- Web UI for querying and comparison

### Storage Location

```
artifacts/mlruns/
├── 0/                          # Default experiment ID
│   ├── <run_id_1>/            # Each run gets unique ID
│   │   ├── meta.yaml          # Run metadata
│   │   ├── metrics/           # Timestamped metrics
│   │   ├── params/            # Configuration parameters
│   │   └── artifacts/         # Logged CSV/Parquet files
│   ├── <run_id_2>/
│   └── ...
└── .trash/                     # Deleted runs
```

**Size**: ~40MB (grows over time as you run more experiments)

**Git Status**: ❌ Gitignored (line 65: `mlruns/`)

### What Gets Logged to MLflow

From `benchmarks/run_latency.py` (lines 54-110):

```python
# 1. Set tracking URI (local file storage)
mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)  # "file://./artifacts/mlruns"
mlflow.set_experiment(cfg.mlflow.experiment_name)  # "sigtekx_benchmarks"

with mlflow.start_run(run_name=f"latency_{nfft}x{channels}"):
    # 2. Log configuration parameters
    mlflow.log_params({
        "engine.nfft": 4096,
        "engine.channels": 2,
        "engine.overlap": 0.75,
        "benchmark.iterations": 5000,
        ...
    })

    # 3. Log metrics
    mlflow.log_metrics({
        "latency.mean": 122.5,    # microseconds
        "latency.p95": 145.2,
        "latency.p99": 167.8,
        "latency.std": 12.3,
    })

    # 4. Log artifacts (CSV/Parquet files)
    mlflow.log_artifact("artifacts/data/latency_summary_4096_2_0p7500_streaming.csv")
```

### How to Query MLflow Data

**Option 1: Web UI**
```bash
# Launch MLflow UI
mlflow ui --backend-store-uri file://./artifacts/mlruns --port 5000

# Open browser to http://localhost:5000
# - View all runs
# - Compare metrics across runs
# - Download artifacts
# - Filter by parameters
```

**Option 2: Python API**
```python
import mlflow
from mlflow.tracking import MlflowClient

# Set tracking URI
mlflow.set_tracking_uri("file://./artifacts/mlruns")

# Get experiment
experiment = mlflow.get_experiment_by_name("sigtekx_benchmarks")

# Search runs
runs = mlflow.search_runs(
    experiment_ids=[experiment.experiment_id],
    filter_string="params.`engine.nfft` = '4096' and metrics.`latency.mean` < 150"
)

print(runs[['params.engine.nfft', 'metrics.latency.mean']])
```

**Option 3: CLI**
```bash
# List experiments
mlflow experiments list --tracking-uri file://./artifacts/mlruns

# Search runs
mlflow runs search \
  --experiment-name sigtekx_benchmarks \
  --filter "metrics.latency.mean < 100"
```

---

## Layer 2: CSV Summary Files (Dashboard Data)

### Purpose

CSV files are **human-readable summaries** designed for:
- Streamlit dashboard visualization
- Quick inspection in Excel/pandas
- Easy diff/comparison between datasets
- Fast loading (no database overhead)

### Storage Location

```
artifacts/data/
├── latency_summary_1024_1_0p5000_batch.csv
├── latency_summary_4096_2_0p7500_streaming.csv
├── latency_summary_8192_4_0p8750_streaming.csv
├── throughput_summary_4096_2_0p7500_streaming.csv
├── accuracy_details_4096_1.csv
├── ...                                          # 266 CSV files total
└── *.done                                       # Snakemake completion markers
```

**Naming Convention** (prevents race conditions in parallel runs):
```
{benchmark}_summary_{nfft}_{channels}_{overlap}_{mode}.csv
                     └──────┬──────┘ └───┬───┘  └─┬──┘
                     Unique config       Execution mode
                     per file            (batch/streaming)
```

**Example**: `latency_summary_4096_2_0p7500_streaming.csv`
- Benchmark: `latency`
- NFFT: `4096`
- Channels: `2`
- Overlap: `0.7500` (0.75, but '.' → 'p' to avoid filesystem issues)
- Mode: `streaming`

**Git Status**: ❌ Gitignored (line 11-12: `artifacts/`)

### CSV Contents

Each CSV contains **one row per configuration** with:

```csv
experiment_group,sample_rate_category,engine_nfft,engine_channels,engine_overlap,...
baseline,100kHz,4096,2,0.75,48000,streaming,1024,256,0.042,20.833,...
```

**Columns** (from `run_latency.py` lines 122-143):
- **Metadata**: `experiment_group`, `sample_rate_category`
- **Engine params**: `engine_nfft`, `engine_channels`, `engine_overlap`, `engine_sample_rate_hz`, `engine_mode`
- **Derived params**: `hop_size`, `time_resolution_ms`, `freq_resolution_hz`
- **Metrics**: `mean_latency_us`, `p95_latency_us`, `p99_latency_us`, etc.

### Why Unique Filenames?

**Problem**: Parallel Snakemake/Hydra runs could write to same CSV simultaneously → race condition → data loss

**Solution**: Encode full config in filename
- Different configs → different files → zero collision risk
- Same config re-run → atomic overwrite (desired behavior)
- Dashboard loads ALL CSVs via glob pattern: `artifacts/data/*_summary_*.csv`

**Verified by**: `tests/test_csv_multirun_safety.py` (8/8 tests passing)

**Design Doc**: `docs/benchmarking/csv-file-organization.md`

---

## Layer 3: Parquet Files (Raw Measurements)

### Purpose

Parquet files store **raw per-iteration measurements** for:
- Statistical analysis (distribution, outliers, CV)
- Detailed debugging
- Reproducibility validation
- Long-term archival

### Storage Location

```
artifacts/data/
├── latency_4096_2.parquet           # All iterations for NFFT=4096, channels=2
├── latency_8192_4.parquet
├── throughput_4096_2.parquet
└── ...
```

**Format**: Apache Parquet (columnar, compressed, efficient)

**Git Status**: ❌ Gitignored (same as CSV - line 11-12: `artifacts/`)

### Parquet Contents

Each file contains **one row per iteration**:

```python
import pandas as pd

df = pd.read_parquet("artifacts/data/latency_4096_2.parquet")
print(df.head())

#   latency_us  engine_nfft  engine_channels
# 0     118.42         4096                2
# 1     122.15         4096                2
# 2     119.87         4096                2
# 3     125.03         4096                2
# 4     121.56         4096                2
# ... (5000 rows for 5000 iterations)
```

**Why Parquet?**
- Columnar storage (fast filtering on specific columns)
- Built-in compression (smaller than CSV)
- Type preservation (no CSV parsing ambiguity)
- Fast reading in pandas/polars

---

## Layer 4: Completion Markers (.done files)

### Purpose

Snakemake uses **empty .done files** as completion markers for dependency tracking.

### Storage Location

```
artifacts/data/
├── baseline_batch_100k_latency.done        # Empty file (0 bytes)
├── baseline_streaming_100k_latency.done
├── ionosphere_streaming.done
└── ...
```

**Contents**: Empty (0 bytes) - just a filesystem marker

**Git Status**: ❌ Gitignored (line 11-12: `artifacts/`)

### How Snakemake Uses Them

From `experiments/Snakefile`:

```python
rule run_baseline_streaming_100k_latency:
    output:
        done="artifacts/data/baseline_streaming_100k_latency.done"
    shell:
        """
        python benchmarks/run_latency.py experiment=baseline_streaming_100k_latency +benchmark=latency
        touch {output.done}
        """
```

**Workflow**:
1. Snakemake checks if `.done` file exists
2. If missing → run the benchmark → create `.done` marker
3. If present → skip (already completed)
4. Dependencies: If upstream .done is newer, re-run downstream

---

## Data Flow: From Benchmark to Dashboard

### Step-by-Step Example

**Scenario**: Running ionosphere streaming latency benchmark

```bash
# 1. User runs benchmark
python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency
```

**What Happens**:

```
1. Hydra loads config
   └─> experiments/conf/experiment/ionosphere_streaming.yaml
   └─> experiments/conf/benchmark/latency.yaml

2. Benchmark runs (5000 iterations)
   └─> Collects latency measurements: [118.2, 122.5, 119.8, ...]

3. MLflow logging starts
   └─> Creates new run: artifacts/mlruns/0/<run_id>/
   └─> Logs params: {"engine.nfft": 4096, "engine.channels": 2, ...}
   └─> Logs metrics: {"latency.mean": 122.5, "latency.p95": 145.2, ...}

4. Parquet file written
   └─> artifacts/data/latency_4096_2.parquet
   └─> Contains all 5000 measurements

5. CSV summary written
   └─> artifacts/data/latency_summary_4096_2_0p7500_streaming.csv
   └─> Contains 1 row with aggregated statistics

6. MLflow artifact logging
   └─> Copies CSV/Parquet to: artifacts/mlruns/0/<run_id>/artifacts/

7. Done marker created (if run via Snakemake)
   └─> touch artifacts/data/ionosphere_streaming.done
```

**Result**: Three copies of data
- MLflow tracking database (queryable)
- CSV in `data/` (for dashboard)
- CSV/Parquet in MLflow artifacts (for archival)

---

## Streamlit Dashboard Integration

### How Dashboard Loads Data

From `experiments/streamlit/app.py` (line 71):

```python
# Dashboard reads ALL CSV summary files
data = load_benchmark_data("artifacts/data")
```

**Under the hood** (`experiments/streamlit/utils/data_loader.py`):

```python
def load_benchmark_data(data_dir: str) -> pd.DataFrame:
    """Load all CSV summary files and combine into single DataFrame."""

    # Glob pattern: Match all summary CSVs
    csv_files = Path(data_dir).glob("*_summary_*.csv")

    # Load and concatenate
    dfs = [pd.read_csv(f) for f in csv_files]
    combined = pd.concat(dfs, ignore_index=True)

    return combined
```

**Caching**: Dashboard caches data for 1 hour (reduces disk I/O on page refresh)

**Result**: Dashboard shows unified view of all experiments across all CSV files

---

## Git Tracking Strategy

### What IS Tracked

✅ **Code**
- All Python scripts (`benchmarks/*.py`)
- All C++ source (`cpp/src/`, `cpp/include/`)
- Benchmark configs (`experiments/conf/`)
- Snakefile workflow

✅ **Documentation**
- This doc
- Experiment guides
- Architecture docs

✅ **Tests**
- Test files (`tests/`)
- Test configs

### What is NOT Tracked

❌ **Experiment Data** (`.gitignore` line 11-12: `artifacts/`)
- `artifacts/mlruns/` - MLflow tracking (~40MB)
- `artifacts/data/` - CSV/Parquet/done files (~767KB)
- `artifacts/profiling/` - Nsight profiling reports
- `artifacts/reports/` - Coverage/analysis reports

❌ **Why Not Track Data?**
1. **Size**: Grows unbounded (40MB+ already, will be GB+ after Phase 4)
2. **Binary**: Parquet/SQLite are binary (no useful git diffs)
3. **Regenerable**: All data can be recreated from code + configs
4. **Local-specific**: GPU hardware, timing results not portable
5. **Collaboration**: Data != code - share code, generate data locally

### What About Baselines?

**For important datasets** (like pre-Phase 1), use **timestamped snapshots**:

```bash
# Copy artifacts to timestamped baseline directory
New-Item -ItemType Directory -Force -Path "datasets/v0.9.5_pre-phase1"
Copy-Item -Recurse artifacts/data "datasets/v0.9.5_pre-phase1/data"
Copy-Item -Recurse artifacts/mlruns "datasets/v0.9.5_pre-phase1/mlruns"

# Git tag the CODE state (not data)
git tag -a v0.9.5-pre-phase1 -m "Baseline before Phase 1 optimizations"
git push origin v0.9.5-pre-phase1
```

**Result**:
- Code state: Tracked in git (tag)
- Data state: Local directory (not tracked, but preserved)
- Reproducible: Anyone can checkout tag and regenerate data

---

## Backup and Dataset Strategy

### For Daily Work

**No backup needed** - data is regenerable from code

```bash
# Lost artifacts? Just re-run
snakemake --cores 4 --snakefile experiments/Snakefile
```

### For Phase Milestones

**Use `sigx dataset` command** (see Dataset Management Workflow above):

```bash
# Save baseline at phase boundary
sigx dataset save pre-phase1 --phase 1 --message "Before zero-copy optimization"

# List saved datasets
sigx dataset list --phase 1

# Compare after modifications (Phase 1 feature - coming soon)
sigx dataset compare pre-phase1 post-phase1
```

**Baseline storage**: `datasets/` directory (persists across `sigx clean`)

### For Publication

**Export full baseline** for long-term archival:

```bash
# Save publication baseline with full scope
sigx dataset save methods-paper-v1.0 --scope full --message "IEEE HPEC submission"

# Export for archival (Phase 2 feature - coming soon)
sigx dataset export methods-paper-v1.0 C:\backup --format zip

# Git tag the CODE (not data)
git tag -a v1.0.0 -m "Methods paper publication release"
```

Upload `methods-paper-v1.0.zip` to Zenodo/Figshare for persistent DOI.

---

## Comparison Workflow

### Comparing Two Datasets

**Scenario**: Compare pre-Phase 1 vs post-Phase 1

**Option 1: MLflow UI (Recommended)**

```bash
# Launch two MLflow UIs on different ports
mlflow ui --backend-store-uri file://./datasets/v0.9.5_pre-phase1/mlruns --port 5000 &
mlflow ui --backend-store-uri file://./artifacts/mlruns --port 5001 &

# Open both in browser:
# - http://localhost:5000 (pre-Phase 1)
# - http://localhost:5001 (post-Phase 1)

# Compare side-by-side, download CSVs for diff
```

**Option 2: Python Script**

```python
import pandas as pd

# Load CSV summaries
pre = pd.read_csv("datasets/v0.9.5_pre-phase1/data/latency_summary_4096_2_0p7500_streaming.csv")
post = pd.read_csv("artifacts/data/latency_summary_4096_2_0p7500_streaming.csv")

# Compare
print(f"Pre-Phase 1:  {pre['mean_latency_us'].values[0]:.2f} µs")
print(f"Post-Phase 1: {post['mean_latency_us'].values[0]:.2f} µs")
print(f"Improvement:  {pre['mean_latency_us'].values[0] - post['mean_latency_us'].values[0]:.2f} µs")
```

**Option 3: Dashboard Comparison**

```bash
# Copy baseline CSVs to current data directory (with unique names)
Copy-Item "datasets/v0.9.5_pre-phase1/data/*.csv" "artifacts/data/" -Force

# Rename to distinguish (add prefix)
Get-ChildItem "artifacts/data/*.csv" | Where-Object { $_.Name -notmatch "^v095_" } |
  ForEach-Object { Rename-Item $_ "v095_pre_$($_.Name)" }

# Launch dashboard (shows both datasets)
sigx dashboard
```

---

## Dataset Management Workflow

### When to Save Baselines

**Save datasets at phase boundaries** (methods paper roadmap):
- **Phase 1**: Pre/post memory optimizations (zero-copy ring buffer)
- **Phase 2**: Pre/post custom stage integration (Numba, PyTorch)
- **Phase 3**: Pre/post control plane decoupling (snapshot buffer, event queue)
- **Phase 4**: Final validation baseline (methods paper publication freeze)

**DO NOT** save datasets for every experiment - only for major milestones.

### Typical Workflow

**1. Run baseline experiments**
```bash
snakemake --cores 4 --snakefile experiments/Snakefile
```

**2. Save baseline before modifications**
```bash
sigx dataset save pre-phase1 --phase 1 --message "Before zero-copy optimization"

# Output:
# ✅ Baseline saved: pre-phase1
#    Location: C:\...\sigtekx\datasets\pre-phase1\
#    Size: 41.2 MB
#    Metrics:
#      - streaming_latency_mean_us: 122.5
```

**3. Delete artifacts to free space**
```bash
sigx clean  # Deletes artifacts/ but datasets/ survives
```

**4. Make code changes (e.g., Phase 1 Task 1.1)**
```cpp
// cpp/src/executors/streaming_executor.cpp
// Remove h_batch_staging_ buffer...
```

**5. Rebuild and regenerate data**
```bash
./scripts/cli.ps1 build
snakemake --cores 4 --snakefile experiments/Snakefile
```

**6. Save new baseline**
```bash
sigx dataset save post-phase1 --phase 1 --message "After zero-copy optimization"
```

**7. Compare results** (Phase 1 feature - coming soon)
```bash
sigx dataset compare pre-phase1 post-phase1

# Expected output:
# Dataset Comparison: pre-phase1 vs post-phase1
# ================================================
# Metric                        pre-phase1    post-phase1    Delta
# -----------------------------------------------------------------
# streaming_latency_mean_us     122.5         114.2          -8.3µs  ✅
# Phase 1 Target: -7% ✅ ACHIEVED
```

### Storage Management

**Location**: `datasets/` (repo root, not tracked by git)

**Size management**:
- Minimal scope: ~1MB per baseline
- Standard scope: ~41MB per baseline (default)
- Full scope: ~100MB per baseline

**Cleanup old datasets**:
```bash
sigx dataset list              # Review saved datasets
sigx dataset delete old-test   # Remove unwanted baseline (Phase 2 feature)
```

### Publication Workflow

**For IEEE HPEC / JOSS submissions**:

```bash
# 1. Freeze final state
sigx dataset save methods-paper-v1.0 --scope full --message "Publication freeze"

# 2. Export for archival (Phase 2 feature - coming soon)
sigx dataset export methods-paper-v1.0 C:\backup\publications --format zip

# 3. Upload to Zenodo/Figshare for DOI
# (upload methods-paper-v1.0.zip)

# 4. Git tag the CODE (not data)
git tag -a v1.0.0 -m "Methods paper publication release"
git push origin v1.0.0
```

**Result**:
- Code: Version-controlled in git (v1.0.0 tag)
- Data: Archived with DOI (Zenodo)
- Reproducible: Anyone can checkout v1.0.0 tag and compare results

---

## DVC Integration (Future)

### What is DVC?

**DVC** (Data Version Control) is like git for data:
- Tracks data versions with git-style commands
- Stores actual data remotely (S3, Google Drive, SSH)
- Git only tracks metadata pointers (`.dvc` files)

### Why Not Using DVC Yet?

1. **Data is small** (767KB + 40MB = ~41MB total)
2. **Local development** (single user, no sharing needed)
3. **Regenerable** (can recreate from code)
4. **Phase 0 focus** (infrastructure, not collaboration)

### When to Add DVC?

**Phase 4** (paper preparation) if:
- Data grows >1GB
- Need to share datasets with collaborators
- Want to track data lineage for reproducibility
- Publishing supplementary materials

**Setup** (when ready):

```bash
# Initialize DVC
dvc init

# Add remote storage (e.g., Google Drive)
dvc remote add -d myremote gdrive://<folder_id>

# Track artifacts
dvc add artifacts/data
dvc add artifacts/mlruns

# Commit .dvc metadata files
git add artifacts/data.dvc artifacts/mlruns.dvc .dvc/config
git commit -m "Track experiment data with DVC"

# Push data to remote
dvc push
```

---

## FAQ

### Q: Why isn't experiment data in git?

**A**: Data grows unbounded (will be GB+ after Phase 4), is binary/not diffable, and is regenerable from code. Git is for **code**, not **data outputs**.

### Q: How do I share results with collaborators?

**A**: Share the **code + configs** (git), not the data. Collaborators regenerate results locally. For datasets, use timestamped archives or DVC.

### Q: What if I accidentally delete artifacts/?

**A**: Re-run benchmarks. All data is regenerable:
```bash
snakemake --cores 4 --snakefile experiments/Snakefile
```

### Q: How do I compare two git branches?

**A**:
1. Checkout branch A, run benchmarks, archive to `datasets/branch_a/`
2. Checkout branch B, run benchmarks (stays in `artifacts/`)
3. Compare using MLflow UI or Python script

### Q: Can I use SQLite instead of CSV?

**A**: Technically yes, but CSVs are simpler for now. SQLite is overkill for <1MB data. Consider in Phase 4 if data grows significantly.

### Q: How does Streamlit cache work?

**A**: Dashboard uses `@st.cache_data(ttl=3600)` (1 hour TTL). Data refreshes automatically after 1 hour, or manually via "Clear cache" button.

### Q: What's the total disk usage?

**Current** (as of 2025-01-03):
- `artifacts/data/`: 767KB (266 CSV files)
- `artifacts/mlruns/`: 40MB (MLflow tracking)
- **Total**: ~41MB

**Expected growth** (after Phase 4):
- 10× more experiments → ~500MB total
- Still manageable without database

---

## See Also

- **CSV Organization**: `docs/benchmarking/csv-file-organization.md`
- **Experiment Guide**: `docs/benchmarking/experiment-guide.md`
- **MLflow Docs**: https://mlflow.org/docs/latest/tracking.html
- **Snakemake Docs**: https://snakemake.readthedocs.io/

---

## Summary

**Key Takeaways**:

1. **Three-layer system**: MLflow (tracking) + CSV (dashboard) + Parquet (raw data)
2. **Everything local**: All data in `artifacts/`, gitignored
3. **Code is tracked**: Git tracks code/configs, not data outputs
4. **Regenerable**: Lost data? Re-run benchmarks
5. **Baselines**: Timestamped archives for milestones (e.g., `datasets/v0.9.5_pre-phase1/`)
6. **Comparison**: MLflow UI or Python scripts for before/after analysis
7. **Future**: DVC if data grows >1GB or need collaboration

**Mental Model**: Think of `artifacts/` like a local database that you can delete and regenerate anytime. Git is for preserving the **recipe** (code), not the **output** (data).
