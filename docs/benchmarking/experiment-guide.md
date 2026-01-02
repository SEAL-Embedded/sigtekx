# Experiment Configuration Guide

**Comprehensive guide to the SigTekX experiment taxonomy, design principles, and selection criteria.**

## Table of Contents

- [Overview](#overview)
- [Design Principles](#design-principles)
- [Experiment Taxonomy](#experiment-taxonomy)
- [Selection Guide](#selection-guide)
- [Experiment Details](#experiment-details)
- [Quick Reference](#quick-reference)
- [Best Practices](#best-practices)

---

## Overview

SigTekX provides **26 carefully designed experiments** organized into 4 categories, each serving distinct purposes with zero redundancy. This guide explains the taxonomy, selection criteria, and design rationale.

### Why Multiple Experiments?

Each experiment is purpose-built for specific research objectives:

1. **Quick Validation** - Lightweight configs for fast sanity checks (~5-10 min)
2. **Deep Analysis** - Comprehensive parameter sweeps for thorough studies (~30-60 min)
3. **Mode Separation** - Distinct configs for BATCH vs STREAMING execution
4. **Objective Focus** - Optimized for latency, throughput, or real-time performance
5. **Domain Specificity** - Tailored for ionosphere research or general academic use

**Key Insight:** Experiments are complementary, not redundant. Quick experiments provide fast feedback; comprehensive experiments provide publishable results.

---

## Design Principles

### 1. Clean Mode Separation (BATCH vs STREAMING)

**BATCH Mode** (discrete frame processing):
- Includes zero overlap (0.0) for discrete frame analysis
- Focus: per-frame latency without ring buffer overhead
- Use case: Offline processing, maximum throughput

**STREAMING Mode** (continuous real-time):
- Excludes zero overlap (minimum 0.5) - streaming requires temporal continuity
- Focus: Real-Time Factor (RTF), ring buffer overhead, deadline compliance
- Use case: Real-time monitoring, low-latency applications

**Example:**
```yaml
# BATCH experiment - includes zero overlap
baseline_batch_100k_latency:
  overlap: 0.0, 0.5, 0.75  # Zero overlap valid for discrete frames

# STREAMING experiment - no zero overlap
baseline_streaming_100k_latency:
  overlap: 0.5, 0.75, 0.875  # Streaming requires temporal continuity
```

### 2. Complementary Coverage (Quick vs Deep)

**Quick Experiments** (~5-10 configurations):
- Broad parameter sweep with coarse granularity
- Fast execution for iterative development
- Sanity checks and regression testing

**Deep Experiments** (~45-100 configurations):
- Fine-grained parameter sweeps
- Statistical rigor for publications
- Comprehensive performance characterization

**Example:**
```yaml
# Quick: 9 configurations (3×3×1)
baseline_100k:
  nfft: 2048, 4096, 8192
  channels: 2, 8, 32
  overlap: 0.5

# Deep: 45 configurations (5×3×3)
baseline_batch_100k_latency:
  nfft: 1024, 2048, 4096, 8192, 16384
  channels: 1, 2, 8
  overlap: 0.0, 0.5, 0.75
```

### 3. Sample Rate Separation (100kHz vs 48kHz)

**100kHz Experiments** (Methods Paper positioning):
- Academic soft real-time capabilities
- General-purpose benchmarking
- Comparison against NumPy/SciPy baselines
- Publication target: methods papers, performance studies

**48kHz Experiments** (Ionosphere application):
- Real-world VLF/ULF phenomena detection
- Dual-channel (E-W + N-S dipoles)
- Application-specific performance validation
- Publication target: domain science papers

### 4. Objective-Focused Metrics

**Latency Experiments:**
- Mean, median, percentiles (p50, p95, p99)
- Coefficient of Variation (CV) for stability
- Jitter analysis
- Threshold: <10ms per-frame for soft real-time

**Throughput Experiments:**
- Frames per second
- GPU utilization
- Memory bandwidth
- Scaling efficiency

**Real-Time Experiments:**
- Real-Time Factor (RTF ≤ 0.33 target)
- Deadline miss rate
- Frame time consistency
- Buffer overflow monitoring

---

## Experiment Taxonomy

### Category 1: Ionosphere Research (7 experiments)

**Purpose:** 48kHz dual-channel VLF/ULF phenomena detection

| Experiment | Mode | Configs | Purpose | Duration |
|------------|------|---------|---------|----------|
| `ionosphere_test` | Mixed | ~5 | Quick validation, CI/CD | ~5 min |
| `ionosphere_streaming` | STREAMING | ~15 | Standard real-time monitoring | ~15 min |
| `ionosphere_streaming_hires` | STREAMING | ~10 | High frequency resolution | ~10 min |
| `ionosphere_streaming_latency` | STREAMING | ~20 | Latency-optimized real-time | ~20 min |
| `ionosphere_streaming_throughput` | STREAMING | ~15 | Max throughput real-time | ~15 min |
| `ionosphere_batch_throughput` | BATCH | ~20 | Offline processing max speed | ~20 min |
| `ionosphere_specialized` | Mixed | ~8 | Custom specialized parameters | ~10 min |

**When to use:**
- Developing ionosphere monitoring applications
- Validating real-time VLF/ULF detection
- Optimizing 48kHz dual-channel performance
- Quick test: `ionosphere_test`
- Production: `ionosphere_streaming` or `ionosphere_streaming_hires`

### Category 2: Baseline Performance (11 experiments)

**Purpose:** General-purpose academic benchmarking at 100kHz and 48kHz

#### 100kHz Baselines (Methods Paper)

| Experiment | Mode | Configs | NFFT Range | Overlap | Purpose |
|------------|------|---------|------------|---------|---------|
| `baseline_100k` | Mixed | 9 | 2048-8192 | 0.5 | Quick general coverage |
| `baseline_batch_100k_latency` | BATCH | 45 | 1024-16384 | 0.0-0.75 | Detailed batch latency |
| `baseline_batch_100k_throughput` | BATCH | 45 | 1024-16384 | 0.0-0.75 | Detailed batch throughput |
| `baseline_streaming_100k_latency` | STREAMING | 45 | 1024-16384 | 0.5-0.875 | Detailed streaming latency |
| `baseline_streaming_100k_throughput` | STREAMING | 45 | 1024-16384 | 0.5-0.875 | Detailed streaming throughput |
| `baseline_streaming_100k_realtime` | STREAMING | 30 | 2048-8192 | 0.5-0.875 | Real-time factor validation |

#### 48kHz Baselines (Ionosphere)

| Experiment | Mode | Configs | Purpose |
|------------|------|---------|---------|
| `baseline_48k` | Mixed | 9 | Quick 48kHz coverage |
| `baseline_batch_48k_latency` | BATCH | 45 | Detailed 48kHz batch latency |
| `baseline_batch_48k_throughput` | BATCH | 45 | Detailed 48kHz batch throughput |
| `baseline_streaming_48k_latency` | STREAMING | 45 | Detailed 48kHz streaming latency |
| `baseline_streaming_48k_realtime` | STREAMING | 30 | 48kHz real-time validation |

#### Special Baseline

| Experiment | Purpose |
|------------|---------|
| `baseline_batch_high_nfft_throughput` | High NFFT (8192-32768) throughput study |

**When to use:**
- Methods paper performance data
- Comparing against NumPy/SciPy baselines
- Academic publication benchmarks
- Quick test: `baseline_100k` or `baseline_48k` (~5 min)
- Full study: `baseline_batch_100k_latency` + `baseline_streaming_100k_latency` (~60 min)

### Category 3: Analysis & Validation (6 experiments)

| Experiment | Configs | Purpose | Duration |
|------------|---------|---------|----------|
| `execution_mode_comparison` | ~40 | BATCH vs STREAMING comparison | ~30 min |
| `full_parameter_grid_100k` | ~100 | Exhaustive 100kHz parameter sweep | ~60 min |
| `full_parameter_grid_48k` | ~100 | Exhaustive 48kHz parameter sweep | ~60 min |
| `low_nfft_scaling` | ~20 | Low-latency optimization (256-2048 NFFT) | ~15 min |
| `accuracy_validation` | ~10 | Correctness verification vs SciPy | ~10 min |
| `stress_test` | ~5 | Stability and limits testing | ~20 min |

**When to use:**
- Comprehensive performance characterization
- Mode selection analysis (BATCH vs STREAMING)
- Accuracy validation
- Extreme parameter testing

### Category 4: Profiling (1 experiment)

| Experiment | Purpose | Duration |
|------------|---------|----------|
| `profiling` | GPU profiling with Nsight (lightweight config) | ~5 min |

**When to use:**
- GPU kernel profiling with Nsight Systems/Compute
- Performance bottleneck identification
- Development iteration (used with `sxp nsys` or `sxp ncu`)

---

## Selection Guide

### Decision Tree

```
START: What is your goal?
│
├─ Quick validation / CI/CD?
│  ├─ Ionosphere → ionosphere_test
│  ├─ 100kHz → baseline_100k
│  └─ 48kHz → baseline_48k
│
├─ Methods paper benchmarks?
│  ├─ BATCH latency → baseline_batch_100k_latency
│  ├─ STREAMING latency → baseline_streaming_100k_latency
│  ├─ Throughput → baseline_batch_100k_throughput
│  └─ Comprehensive → full_parameter_grid_100k
│
├─ Ionosphere application?
│  ├─ Real-time monitoring → ionosphere_streaming
│  ├─ High resolution → ionosphere_streaming_hires
│  ├─ Low latency → ionosphere_streaming_latency
│  └─ Max throughput → ionosphere_batch_throughput
│
├─ Mode comparison?
│  └─ execution_mode_comparison
│
├─ Accuracy validation?
│  └─ accuracy_validation
│
└─ GPU profiling?
   └─ profiling (with sxp nsys/ncu)
```

### By Time Budget

| Time Available | Recommended Experiments |
|----------------|-------------------------|
| **5-10 minutes** | `ionosphere_test`, `baseline_100k`, `baseline_48k`, `profiling` |
| **15-30 minutes** | `ionosphere_streaming`, `execution_mode_comparison`, `low_nfft_scaling` |
| **30-60 minutes** | `baseline_batch_100k_latency`, `baseline_streaming_100k_latency`, `full_parameter_grid_48k` |
| **1-2 hours** | `full_parameter_grid_100k`, Multiple baseline experiments |
| **Full suite** | Run Snakefile (~4-6 hours) |

### By Research Objective

| Objective | Experiments |
|-----------|-------------|
| **Soft real-time validation** | `baseline_streaming_100k_latency`, `baseline_streaming_100k_realtime` |
| **Maximum throughput** | `baseline_batch_100k_throughput`, `ionosphere_batch_throughput` |
| **Low-latency optimization** | `low_nfft_scaling`, `ionosphere_streaming_latency` |
| **Accuracy verification** | `accuracy_validation` |
| **Comprehensive characterization** | `full_parameter_grid_100k`, `full_parameter_grid_48k` |
| **Mode selection** | `execution_mode_comparison` |

---

## Experiment Details

### Ionosphere Experiments (48kHz, 2-channel)

#### `ionosphere_test`
**Purpose:** Lightweight quick validation
- **Configs:** ~5
- **NFFT:** 2048, 4096
- **Channels:** 2
- **Overlap:** 0.5, 0.75
- **Use case:** CI/CD, quick sanity checks
- **Command:** `python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency`

#### `ionosphere_streaming`
**Purpose:** Standard real-time VLF/ULF monitoring
- **Configs:** ~15
- **Mode:** STREAMING
- **NFFT:** 2048, 4096, 8192
- **Overlap:** 0.625, 0.75, 0.875
- **Focus:** Balanced real-time performance
- **Command:** `python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency`

#### `ionosphere_streaming_hires`
**Purpose:** High frequency resolution real-time monitoring
- **Configs:** ~10
- **Mode:** STREAMING
- **NFFT:** 8192, 16384
- **Overlap:** 0.75, 0.875
- **Focus:** Maximum frequency resolution while maintaining real-time
- **Command:** `python benchmarks/run_latency.py experiment=ionosphere_streaming_hires +benchmark=latency`

### Baseline Experiments

#### Why Multiple Baselines?

**Quick baseline** (`baseline_100k`):
- 9 configurations (3 NFFT × 3 channels × 1 overlap)
- Fast execution (~5 min)
- Broad coverage for sanity checks

**Detailed baselines** (`baseline_batch_100k_latency`, etc.):
- 45 configurations (5 NFFT × 3 channels × 3 overlap)
- Mode-specific (BATCH or STREAMING)
- Metric-specific (latency or throughput)
- Statistical rigor for publications

**Example comparison:**
```yaml
# Quick: baseline_100k (9 configs, ~5 min)
nfft: [2048, 4096, 8192]
channels: [2, 8, 32]
overlap: [0.5]

# Deep: baseline_batch_100k_latency (45 configs, ~30 min)
nfft: [1024, 2048, 4096, 8192, 16384]
channels: [1, 2, 8]
overlap: [0.0, 0.5, 0.75]
mode: batch  # Explicit mode
```

---

## Quick Reference

### Most Common Commands

```bash
# Quick testing (5-10 min)
python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency

# Ionosphere production (15-20 min)
python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency
python benchmarks/run_throughput.py experiment=ionosphere_streaming_throughput +benchmark=throughput

# Methods paper baseline (30-60 min)
python benchmarks/run_latency.py experiment=baseline_streaming_100k_latency +benchmark=latency
python benchmarks/run_throughput.py experiment=baseline_batch_100k_throughput +benchmark=throughput

# Comprehensive analysis (60 min)
python benchmarks/run_latency.py --multirun experiment=full_parameter_grid_48k +benchmark=latency

# Full benchmark suite (4-6 hours)
snakemake --cores 4 --snakefile experiments/Snakefile
```

### Experiment Summary Table

| Category | Count | Sample Rate | Mode | Time Budget | Use Case |
|----------|-------|-------------|------|-------------|----------|
| **Ionosphere** | 7 | 48kHz | Mixed | 5-20 min | VLF/ULF real-time monitoring |
| **Baseline** | 11 | 100kHz/48kHz | Split | 5-60 min | Academic benchmarking |
| **Analysis** | 6 | Mixed | Mixed | 10-60 min | Comprehensive studies |
| **Profiling** | 1 | Configurable | Mixed | 5 min | GPU profiling |
| **Total** | 26 | - | - | Variable | All research objectives |

---

## Best Practices

### 1. Start Small, Scale Up

```bash
# Step 1: Quick validation (5 min)
python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency

# Step 2: If results look good, run production config (15 min)
python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency

# Step 3: If needed, run comprehensive sweep (60 min)
python benchmarks/run_latency.py --multirun experiment=full_parameter_grid_48k +benchmark=latency
```

### 2. Match Mode to Use Case

- **BATCH mode**: Offline processing, maximum throughput, zero overlap allowed
- **STREAMING mode**: Real-time monitoring, low latency, continuous processing

### 3. Use Appropriate Sample Rate

- **100kHz**: Methods papers, academic benchmarking, soft real-time positioning
- **48kHz**: Ionosphere application, domain science, real-world validation

### 4. Leverage Quick Experiments for Development

During iterative development:
```bash
# Fast iteration loop (~5 min each)
1. Modify code
2. python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency
3. Check results
4. Repeat
```

Before committing:
```bash
# Full validation (~30 min)
python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency
```

### 5. GPU Clock Locking for Stability

For production benchmarks, use GPU clock locking to reduce variance:

```bash
# With clock locking (5-10% CV)
python benchmarks/run_latency.py experiment=baseline_streaming_100k_latency +benchmark=latency benchmark.lock_gpu_clocks=true

# Without clock locking (20-40% CV)
python benchmarks/run_latency.py experiment=baseline_streaming_100k_latency +benchmark=latency
```

See `docs/performance/gpu-clock-locking.md` for details.

### 6. View Results with Dashboard

After running experiments:
```bash
sigx dashboard
# OR
streamlit run experiments/streamlit/app.py
```

The dashboard automatically loads all results from `artifacts/data/` and provides:
- Interactive filtering by NFFT, channels, overlap, mode
- Side-by-side configuration comparison
- Execution mode analysis (BATCH vs STREAMING)
- Ionosphere-specific analysis (VLF/ULF phenomena detection)

---

## Design Rationale

### Why Not a Single Configurable Experiment?

**Considered:** One experiment with all parameters configurable via command line.

**Rejected because:**
1. **Error-prone**: Easy to forget mode-specific constraints (e.g., zero overlap invalid for streaming)
2. **No defaults**: Users must specify all parameters explicitly
3. **Metric mismatch**: Latency vs throughput vs real-time require different analysis
4. **Documentation burden**: Users must learn all valid parameter combinations

**Current approach:**
- **Self-documenting**: Experiment name indicates purpose
- **Validated constraints**: Each experiment enforces valid parameter combinations
- **Metric alignment**: Experiments paired with appropriate benchmark configs
- **Quick discovery**: `sigx dev` shows all available experiments

### Why Separate BATCH and STREAMING Baselines?

**Key difference:** Overlap ranges

- **BATCH**: Allows zero overlap (0.0) for discrete frame analysis
- **STREAMING**: Minimum 0.5 overlap (temporal continuity required)

**Why this matters:**
- Zero overlap invalid for streaming (no temporal continuity)
- Different focus metrics (BATCH: discrete latency, STREAMING: RTF + ring buffer overhead)
- Different use cases (offline vs real-time)

**Example mistake if combined:**
```yaml
# BAD: Single experiment with all overlaps
overlap: [0.0, 0.5, 0.75, 0.875]
mode: [batch, streaming]

# Problem: streaming + zero overlap = invalid config!
```

**Solution:** Separate experiments with appropriate constraints:
```yaml
# baseline_batch_100k_latency
overlap: [0.0, 0.5, 0.75]
mode: batch

# baseline_streaming_100k_latency
overlap: [0.5, 0.75, 0.875]
mode: streaming
```

### Why Quick + Deep Coverage?

**Quick experiments** (9 configs, ~5 min):
- Fast feedback during development
- CI/CD integration
- Regression testing
- Sanity checks

**Deep experiments** (45-100 configs, ~30-60 min):
- Statistical rigor (larger N)
- Fine-grained parameter exploration
- Publication-quality data
- Comprehensive characterization

**Both needed:**
- Quick experiments enable iterative development
- Deep experiments provide publishable results
- Different time budgets, different purposes

---

## Related Documentation

- **Quick commands**: `CLAUDE.md` - Copy-paste ready commands
- **CLI reference**: `sigx dev` - Dynamic experiment discovery
- **Benchmark configs**: `experiments/conf/benchmark/` - Benchmark-specific settings
- **Engine configs**: `experiments/conf/engine/` - Engine preset configurations
- **GPU stability**: `docs/performance/gpu-clock-locking.md` - Reduce benchmark variance
- **Analysis guide**: `experiments/streamlit/` - Interactive dashboard for results

---

## FAQ

### Q: Which experiment should I run first?

**A:** Start with the quick test for your use case:
- Ionosphere: `ionosphere_test` (~5 min)
- 100kHz: `baseline_100k` (~5 min)
- 48kHz: `baseline_48k` (~5 min)

### Q: Why are there so many baseline experiments?

**A:** Each serves a distinct purpose:
- **Quick baselines** (9 configs): Fast sanity checks
- **BATCH baselines** (45 configs): Offline processing analysis
- **STREAMING baselines** (45 configs): Real-time performance analysis
- **Mode-specific metrics**: BATCH vs STREAMING have different focus areas

### Q: Can I customize an experiment?

**A:** Yes, use Hydra overrides:
```bash
# Override NFFT values
python benchmarks/run_latency.py --multirun experiment=ionosphere_streaming +benchmark=latency engine.nfft=2048,4096,8192

# Override specific parameter
python benchmarks/run_latency.py experiment=baseline_100k +benchmark=latency engine.channels=16
```

### Q: How do I add a new experiment?

**A:** Create a new YAML file in `experiments/conf/experiment/`:
1. Copy an existing experiment as template
2. Modify parameters for your use case
3. Set appropriate defaults and sweeps
4. Test with: `python benchmarks/run_latency.py experiment=your_new_experiment +benchmark=latency`

### Q: What's the fastest way to validate code changes?

**A:**
```bash
# Fastest: ionosphere_test (~5 min, 5 configs)
python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency

# If passed, validate production config (~15 min, 15 configs)
python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency
```

### Q: Which experiments feed the Streamlit dashboard?

**A:** All experiments! The dashboard loads all CSV files from `artifacts/data/` and filters them by:
- Sample rate (100kHz vs 48kHz)
- Execution mode (BATCH vs STREAMING)
- Channels (e.g., 2-channel for ionosphere)
- Other parameters (NFFT, overlap, etc.)

No need to run specific experiments for the dashboard - it adapts to whatever data you generate.

---

**Last updated:** 2026-01-01
**Version:** 2.0.0
