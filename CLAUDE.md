# SigTekX — Agent Guide

CUDA-accelerated FFT/benchmarking suite for ionospheric research. C++17/CUDA engine
in `cpp/`, Python 3.11+ package in `src/sigtekx/`, Hydra-driven benchmarks in
`benchmarks/` and `experiments/`.

This file holds **rules and invariants an agent cannot infer from the code**.
Reference material lives in `docs/` — see the map at the bottom. Don't duplicate
`docs/` content here; link to it.

## Quick Start

```bash
# Fast realistic workload (~1 min) — best first validation
python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency

# Throughput equivalent
python benchmarks/run_throughput.py experiment=ionosphere_streaming_throughput +benchmark=throughput

# Full suite (30+ min), then view results
snakemake --cores 4 --snakefile experiments/Snakefile
sigx dashboard

# C++-only iteration (no Python dependency)
sigxc bench                      # ~10s dev preset
sigxc bench --preset latency --full --lock-clocks
```

## Critical Invariants

These are real footguns. Violating them fails at runtime or silently produces
the wrong workload.

1. **Always pass an explicit `+benchmark=`.** There is no default; omitting it
   is a config error.
   - `run_latency.py` → `+benchmark=latency`
   - `run_throughput.py` → `+benchmark=throughput`

   ```bash
   # ✅ python benchmarks/run_throughput.py experiment=X +benchmark=throughput
   # ❌ python benchmarks/run_throughput.py experiment=X
   ```

2. **Execution mode comes from the engine config only.** Benchmark configs
   (`latency.yaml`, `throughput.yaml`, …) do *not* override `engine.mode`.
   Choose streaming vs batch by picking the engine — e.g.
   `ionosphere_48k_streaming` vs `ionosphere_48k`, `academic_100k_streaming`
   vs `academic_100k`.

3. **`ionosphere_test` is not a smoke test.** It runs a realistic STREAMING
   workload (4 configs, ~1 min); `ionosphere_test_batch` is the BATCH variant
   (6 configs, ~2 min). The actual minimal sanity check is `smoke_test` (~1s).

4. **Never hand-edit files in `artifacts/`.** They are generated and
   `sigx clean` deletes the tree.

## Two-Tier Result Storage

| Tier | Location | Survives `sigx clean` | Purpose |
|---|---|---|---|
| Ephemeral | `artifacts/` (MLflow + `artifacts/data/*.csv`) | ❌ no | Day-to-day iteration; dashboard's default `live` dataset |
| Persistent | `datasets/` | ✅ yes | Milestones, regression snapshots, cloud runs |

`datasets/<name>/` holds Python snapshots, `datasets/cpp/<name>/` holds C++ ones
(fully decoupled — no Python needed), and `scripts/aws/download_results.sh` writes
`datasets/aws-<timestamp>/` directly without touching `artifacts/data/`.

Snapshot before anything destructive or milestone-worthy:

```bash
sigx dataset save pre-phase1 --tag phase1 --message "Before zero-copy"
sigx dataset compare pre-phase1 post-phase1      # Python
sigxc dataset compare pre_opt post_opt           # C++, exit 1 on regression
```

## CSV Naming (multirun safety)

Each config writes a unique file, so parallel sweeps never collide:

```
{benchmark}_summary_{sample_rate_hz}_{nfft}_{channels}_{overlap}_{mode}.csv
latency_summary_48000_4096_2_0p7500_streaming.csv
realtime_summary_{sample_rate_hz}_{nfft}_{channels}.csv   # always streaming
```

Analysis auto-merges via glob (`*_summary_*.csv`); no file locking involved.
Same config re-run → atomic overwrite (intended). Verified by
[tests/test_csv_multirun_safety.py](tests/test_csv_multirun_safety.py).

## Toolchain

```bash
sigx setup | build | test | lint | format | typecheck | coverage | doctor | clean
sigx dashboard          # streamlit run experiments/streamlit/app.py
sigx dataset ...        # Python snapshots
sigxc bench | profile | dataset ...   # C++ side (scripts/cli-cpp.sh)
sxp nsys|ncu <target>   # Python end-to-end profiling — production path
sxstb | sxsts | sxst    # Per-stage timing (batch | stream | both)
```

Aliases are defined in [scripts/init_bash.sh](scripts/init_bash.sh)
(PowerShell: [scripts/init_pwsh.ps1](scripts/init_pwsh.ps1)). There is **no
`sigx check`** command — run `lint`, `format`, `typecheck` individually.

Quality gates: ruff + mypy (strict) + pytest ≥85% coverage; clang-format
(Google style) and clang-tidy for C++/CUDA. Commit convention is
`type(scope): message` — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Profiling Notes

- Start with `nsys` before `ncu` — nsys is 10–50× faster.
- `sxp <tool> <target>` with no overrides auto-selects the fast `profiling*`
  configs. Adding plain overrides keeps that config; passing `+benchmark=`
  explicitly overrides it entirely.
- Use `ncu --kernel-name <pattern>` to avoid multi-hour full runs.
- `sigxc profile` is for **C++ development iteration only**. Production
  profiling always goes through `sxp` with Python benchmarks.

## Window Symmetry

`StageConfig::window_symmetry` selects endpoint behavior. **PERIODIC**
(denominator `N`, default) for all FFT/STFT/spectrogram and ionosphere work;
**SYMMETRIC** (denominator `N-1`, exact zero endpoints) only for FIR filter
design and time-domain tapering. Do not switch modes in spectral paths.

Full formulas and API docs live in the header:
[cpp/include/sigtekx/core/window_functions.hpp](cpp/include/sigtekx/core/window_functions.hpp).
Tests: [cpp/tests/core/test_window_functions.cpp](cpp/tests/core/test_window_functions.cpp).

## Documentation Map

Read these on demand rather than restating them here.

| Topic | Document |
|---|---|
| All 29 experiments, design rationale, selection guide | [docs/benchmarking/experiment-guide.md](docs/benchmarking/experiment-guide.md) |
| CSV organization design | [docs/benchmarking/csv-file-organization.md](docs/benchmarking/csv-file-organization.md) |
| Warmup methodology / thermal protocol | [docs/benchmarking/warmup-methodology.md](docs/benchmarking/warmup-methodology.md), [thermal-degradation-protocol.md](docs/benchmarking/thermal-degradation-protocol.md) |
| GPU clock locking (CV 20–40% → 5–15%) | [docs/performance/gpu-clock-locking.md](docs/performance/gpu-clock-locking.md) |
| Stability summary | [docs/performance/stability-improvements.md](docs/performance/stability-improvements.md) |
| C++ dataset system | [docs/cpp/dataset-system.md](docs/cpp/dataset-system.md) |
| Architecture, executors, thread safety | [docs/architecture/](docs/architecture/) |
| Repo layout | [docs/architecture/project-structure.md](docs/architecture/project-structure.md) |
| AWS / cloud runs | [docs/aws/](docs/aws/) |
| Dataset & archiving internals | module docstrings in [src/sigtekx/utils/datasets.py](src/sigtekx/utils/datasets.py), [archiving.py](src/sigtekx/utils/archiving.py) |
