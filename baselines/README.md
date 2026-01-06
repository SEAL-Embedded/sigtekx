# Baselines Directory

This directory contains saved experiment baselines for regression tracking and phase comparisons.

## What are Baselines?

Baselines are snapshots of experiment results saved at important milestones (e.g., before/after major optimizations). They enable:
- **Regression tracking**: Compare current performance vs past baselines
- **Phase validation**: Verify optimization targets are met (e.g., Phase 1: -7% latency)
- **Publication archival**: Preserve experiment states for paper submissions

## Storage and Lifecycle

- **Location**: `baselines/` (repo root, NOT gitignored)
- **Persistence**: Survives `sigx clean` (unlike ephemeral `artifacts/`)
- **Management**: Manually managed via `sigx baseline` commands
- **Size**: ~1MB (minimal) to ~100MB+ (full scope)

## Directory Structure

Each baseline is a directory containing:

```
baselines/
├── pre-phase1/                      # Example baseline
│   ├── metadata.json                # Baseline metadata + metrics
│   ├── data/                        # CSV summaries (always included)
│   ├── mlruns/                      # MLflow tracking (scope: standard/full)
│   └── README.md                    # Human-readable summary
├── post-phase1/
├── methods-paper-v1.0/              # Publication baseline
└── .baseline_manifest.json          # Global baseline index
```

## Usage

### Save a Baseline

```bash
# Before making changes
snakemake --cores 4 --snakefile experiments/Snakefile
sigx baseline save pre-phase1 --phase 1 --message "Before zero-copy optimization"
```

### List Baselines

```bash
# List all baselines
sigx baseline list

# Filter by phase
sigx baseline list --phase 1 --verbose
```

### Compare Baselines

```bash
sigx baseline compare pre-phase1 post-phase1
```

### Typical Workflow

```bash
# 1. Run experiments and save baseline
snakemake --cores 4 --snakefile experiments/Snakefile
sigx baseline save pre-phase1 --phase 1

# 2. Clean artifacts to free space (baselines/ survives)
sigx clean

# 3. Modify code, rebuild, regenerate
sigx build --release
snakemake --cores 4 --snakefile experiments/Snakefile

# 4. Save new baseline and compare
sigx baseline save post-phase1 --phase 1
sigx baseline compare pre-phase1 post-phase1
```

## Roadmap Alignment

Baselines are aligned with the methods paper roadmap phases:

| Phase | Baselines | Purpose |
|-------|-----------|---------|
| **Phase 1** | `pre-phase1`, `post-phase1` | Validate zero-copy optimization (-7% latency) |
| **Phase 2** | `pre-phase2`, `post-phase2-numba`, `post-phase2-pytorch` | Validate custom stage overhead (<10µs) |
| **Phase 3** | `pre-phase3`, `post-phase3` | Validate control plane decoupling |
| **Phase 4** | `phase4-validation`, `methods-paper-v1.0` | Publication freeze |

## Scope Options

When saving baselines, you can control what's archived:

- **minimal** (~1MB): CSV summaries only - fast, small
- **standard** (~41MB): CSV + MLflow tracking - default, recommended
- **full** (~100MB+): CSV + MLflow + Parquet + profiling - publication-ready

Example:
```bash
sigx baseline save methods-paper-v1.0 --scope full
```

## Storage Management

### Cleanup

Baselines are NOT automatically deleted. To remove old baselines:

```bash
# List baselines
sigx baseline list

# Delete unwanted baseline (with confirmation)
sigx baseline delete old-test-baseline

# Or force delete without confirmation
sigx baseline delete old-test-baseline --force
```

### Manual Cleanup

You can also manually delete baseline directories:

```bash
# Windows
Remove-Item -Recurse -Force baselines/old-baseline/

# Linux/Mac
rm -rf baselines/old-baseline/
```

### Size Management

Monitor baseline storage:

```bash
# Windows PowerShell
Get-ChildItem baselines -Directory | ForEach-Object {
    $size = (Get-ChildItem $_.FullName -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
    [PSCustomObject]@{Name=$_.Name; SizeMB=[math]::Round($size, 1)}
} | Format-Table
```

## Git Tracking

**Important**: This directory is NOT gitignored. Baselines are stored locally and manually managed.

- **Code**: Version-controlled in git (tags like v0.9.5, v1.0.0)
- **Data**: Stored in baselines/ (local only, not in git)
- **Reproducibility**: Anyone can checkout a git tag and regenerate data

## Publication Workflow

For IEEE HPEC / JOSS / Radio Science submissions:

```bash
# 1. Freeze final state
sigx baseline save methods-paper-v1.0 --scope full \\
    --message "IEEE HPEC submission freeze (2025-07-14)"

# 2. Export for archival (Phase 2 feature - coming soon)
sigx baseline export methods-paper-v1.0 C:\\backup --format zip

# 3. Upload to Zenodo/Figshare for DOI
# (upload methods-paper-v1.0.zip)

# 4. Git tag the CODE (not data)
git tag -a v1.0.0 -m "Methods paper publication release"
git push origin v1.0.0
```

## See Also

- **Full documentation**: `docs/benchmarking/experiment-logging-system.md`
- **Experiment guide**: `docs/benchmarking/experiment-guide.md`
- **Methods roadmap**: `docs/development/methods-paper-roadmap.md`

---
*Generated by SigTekX Baseline Management System*
