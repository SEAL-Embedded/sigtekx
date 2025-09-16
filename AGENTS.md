# Agent Operations Guide

## Purpose
- Align autonomous and human contributors with repository guardrails before making changes.
- Capture project specific expectations derived from RSE and RE practice plus IEEE 1074 life cycle control.
- Preserve numerical integrity and reproducibility targets that rely on IEEE 754 floating point behaviour.

## Repository Snapshot
- Domain: CUDA accelerated FFT and benchmarking suite exposed to Python.
- Primary languages: C++17 and CUDA in `cpp/`, Python 3.11+ package under `python/src/`.
- Command interface: cross platform CLI wrappers in `scripts/cli.sh` and `scripts/cli.ps1`, plus enhanced PowerShell shell `scripts/open_dev_pwsh.ps1`.
- Key docs: `README.md`, `PROJECT_STRUCTURE.md`, `docs/DEVELOPMENT.md`, `CONTRIBUTING.md`.

## Standards and Guardrails
### RSE and Requirements Engineering
- Start every task by restating requirements and acceptance criteria; ensure traceability to issues, specs, or benchmarking targets.
- Prefer automation and scripted workflows; never hand edit generated artefacts or bypass CLI orchestration.
- Preserve reproducibility: configuration lives in versioned YAML or TOML, raw data remains immutable, derived artefacts go in `build/` or configured outputs.

### IEEE 1074 Software Life Cycle Alignment
- Initiate: confirm scope, stakeholders, and affected subsystems before coding.
- Plan: produce an explicit task plan, identify risks, and schedule validation steps.
- Develop: implement minimal, reviewable increments; keep code modular with traceable requirement references in comments or commit messages when needed.
- Integrate and Test: use provided CLI targets for builds and tests; document deviations or skipped checks.
- Release and Maintenance: update docs, changelogs, and benchmarks when behaviour changes; capture lessons learned for continuous improvement.

### IEEE 754 Numerical Expectations
- Preserve precision choices used by the engine (float32 and float64); do not mix precisions without explicit reasoning.
- Avoid undefined behaviour around denormals, NaNs, and infinities; handle them deliberately in both C++ and Python layers.
- Document any algorithm that may alter rounding, accumulation order, or parallel reductions.
- When touching benchmarks or validation, record tolerances and compare against reference traces.

### Code Quality Gates
- Python: `ruff` linting (see `pyproject.toml`), `mypy` strict type checks, pytest with coverage at least 85 percent.
- C++ and CUDA: `clang-format` (Google style), `clang-tidy` via CLI, CTest presets managed by CMake.
- Use `./scripts/cli.sh check` or `iono check` (Windows shell) to run the default convergence of format, lint, typecheck, and quick tests.
- Never commit failing lint, format, or typecheck results; sync with CI expectations defined in `.github/` workflows.

## Operational Playbook
1. Intake
   - Read existing issue or story plus relevant docs; capture assumptions.
   - Locate affected modules using `PROJECT_STRUCTURE.md` and `pyproject.toml`.
2. Plan
   - Outline steps in comments or work log before changing files (minimum two steps, update as work progresses).
   - Identify data dependencies, tests to run, and metrics to collect.
3. Execute
   - Use repo CLI for builds, formatting, linting, and type checking.
   - Keep changes minimal; update or add unit tests or benchmarks alongside code.
4. Validate
   - Run targeted tests (`./scripts/cli.sh test py`, `ctest --preset <name>`, etc.).
   - For numerical work, compare outputs against reference baselines and record tolerances inline or in docs.
5. Document and Handover
   - Update relevant README, changelog, or benchmark notes.
   - Summarise changes, tests, and outstanding risks in PR or session report.

## Toolchain Quick Reference
- `./scripts/cli.sh setup` or `.\scripts\cli.ps1 setup`: provision conda environment, compilers, CUDA dependencies.
- `./scripts/cli.sh build [preset]` or `iono build`: configure and build via CMake presets.
- `./scripts/cli.sh format` or `iono format`: run clang-format checks (Google style).
- `./scripts/cli.sh lint` or `iono lint`: run Python lint plus C++ static analysis.
- `./scripts/cli.sh typecheck`: strict mypy across `python/src/` and `python/tests/`.
- `./scripts/cli.sh test`, `./scripts/cli.sh test py`, `./scripts/cli.sh test cpp`: run unit and integration suites.
- `./scripts/cli.sh bench suite`, `./scripts/cli.sh profile nsys <target>`: benchmarking and profiling flows.

## Toolchain Baselines (2025-09)
- **CUDA toolkit**: 13.0 (nvcc + dev libs via conda packages `cuda-compiler=13.0`, `cuda-libraries-dev=13.0`).
- **CUDA driver**: >= 550 to match toolkit 13 runtime on host GPUs.
- **Nsight Systems**: CLI 2024.3.x (`nsys` 3.2) with matching GUI; reports land in `build/nsight_reports/nsys_reports/`.
- **Nsight Compute**: CLI 2024.3.x (`ncu` 3.0) with GUI optional for kernel deep dives.
- **Python**: 3.11.x via the `ionosense-hpc` conda environment.
- **CMake**: >= 3.26 (see `CMakePresets.json` minimum).
- **Build tools**: Ninja (conda), GCC 14.* on Linux (`gxx_linux-64=14.*`), MSVC 2022 via `vs2022_win-64` on Windows.
- **Core Python deps**: `numpy==1.26.4`, `scipy==1.13.0`, `pydantic>=2.0`, `pynvml>=11.5` (see `pyproject.toml`).
- **Conda channels**: `nvidia`, `conda-forge` with strict priority; environment specs live in `environments/`.

## Data, Artefacts, and Environment
- Outputs belong under `build/` (default via `IONO_OUTPUT_ROOT`); do not commit generated results.
- Research artefacts live in `research/` with raw versus processed data separation; respect immutability of `research/data/raw/` inputs.
- GPU profiling requires Nsight tools; gate GPU heavy tests with the `--gpu` pytest marker.
- Watch for cache directories (`.mypy_cache/`, `.ruff_cache/`); clear via CLI if stale.

## Collaboration Notes
- Follow commit convention `type(scope): message` (see `CONTRIBUTING.md`).
- Reference issues and requirements in commit or PR descriptions for traceability (RE practice).
- Coordinate cross language changes (Python to C++ bindings) within a single review to keep interfaces consistent.
- When introducing new public APIs, update stubs, type hints, and documentation simultaneously.

## Pending Knowledge and TODOs
- Local development shell recipe: use the non-interactive bootstrap above when automation is needed; interactive shell remains `.\\scripts\\open_dev_pwsh.ps1` for manual sessions.
- Track further agent specific friction points and document mitigation strategies here.

## References
- Internal docs: `docs/DEVELOPMENT.md`, `docs/BENCHMARKS.md`.
- Standards primers: RSE UK guidelines, IEEE Std 1074 2006, IEEE Std 754 2019.
- External tooling docs: CUDA Programming Guide, CUDA Best Practices Guide, pybind11 docs, pytest, ruff, mypy.
