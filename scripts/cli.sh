#!/usr/bin/env bash
# ============================================================================
# ionosense-hpc-lib • Project CLI (Linux/WSL)
# - Mamba-first (conda fallback allowed ONLY on Linux)
# - Professional research-grade build & test orchestration
# - Integrated Python API commands following RSE/RE standards
# ============================================================================
set -Eeuo pipefail
IFS=$'\n\t'

# --- Paths & Defaults --------------------------------------------------------
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build"
PYTHON_DIR="${PROJECT_ROOT}/python"
DEFAULT_PRESET="linux-rel"
DEFAULT_WORKFLOW="linux-rel-workflow"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-ionosense-hpc}"

NSIGHT_DIR="${BUILD_DIR}/nsight_reports"
NSYS_DIR="${NSIGHT_DIR}/nsys_reports"
NCU_DIR="${NSIGHT_DIR}/ncu_reports"
BENCH_RESULTS_DIR="${BUILD_DIR}/benchmark_results"

# --- Pretty logging ----------------------------------------------------------
C0='\033[0m'; CRED='\033[0;31m'; CGRN='\033[0;32m'; CYEL='\033[0;33m'; CCYN='\033[0;36m'; CBLD='\033[1m'
log()     { echo -e "${CCYN}✅ [INFO]${C0}  $*"; }
warn()    { echo -e "${CYEL}⚠️ [WARN]${C0}  $*"; }
err()     { echo -e "${CRED}❌ [ERR ]${C0}  $*" 1>&2; }
ok()      { echo -e "${CGRN}👍 [OK  ]${C0}  $*"; }
section() { echo -e "\n${CBLD}💪 == $* ==${C0}\n"; }
trap 'err "Command failed on line $LINENO"' ERR

# --- Env file selection (Linux) ---------------------------------------------
env_file() {
  if [[ -f "${PROJECT_ROOT}/environment.linux.yml" ]]; then
    echo "${PROJECT_ROOT}/environment.linux.yml"
  elif [[ -f "${PROJECT_ROOT}/environment.win.yml" ]]; then
    # Fallback for WSL users who might only have the windows file
    warn "Using environment.win.yml as environment.linux.yml was not found."
    echo "${PROJECT_ROOT}/environment.win.yml"
  elif [[ -f "${PROJECT_ROOT}/environment.yml" ]]; then
    echo "${PROJECT_ROOT}/environment.yml"
  else
    err "No environment file found (environment.linux.yml, environment.win.yml or environment.yml)."
    exit 1
  fi
}

# --- Conda shell (for activation), safe with set -u --------------------------
conda_source() {
  set +u
  if command -v conda >/dev/null 2>&1; then
    # shellcheck disable=SC1091
    source "$(conda info --base)/etc/profile.d/conda.sh"
  elif [[ -d "$HOME/miniconda3" ]]; then
    # shellcheck disable=SC1091
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
  else
    set -u
    err "Conda shell not found. Install Miniconda/Mambaforge."
    exit 1
  fi
  set -u
}

# --- Solver selection (Linux ONLY allows fallback to conda) ------------------
solver() {
  if command -v mamba >/dev/null 2>&1; then
    echo "mamba"
  elif command -v conda >/dev/null 2>&1; then
    warn "mamba not found; falling back to conda for env ops on Linux."
    echo "conda"
  else
    err "Neither mamba nor conda found."
    exit 1
  fi
}

# --- Helpers -----------------------------------------------------------------
ensure_env_activated() {
  if [[ "${CONDA_DEFAULT_ENV-}" != "$CONDA_ENV_NAME" ]]; then
    err "Conda environment '$CONDA_ENV_NAME' is not activated."
    log "Please run: conda activate $CONDA_ENV_NAME"
    exit 1
  fi
}

with_pythonpath() {
  local old_path="${PYTHONPATH-}"
  export PYTHONPATH="${BUILD_DIR}/${DEFAULT_PRESET}:${PYTHON_DIR}/src:${old_path}"
  "$@"
  export PYTHONPATH="${old_path}"
}

# --- Commands ----------------------------------------------------------------
cmd_setup() {
  section "Environment Setup (Linux/Mamba)"
  conda_source
  local PKG; PKG="$(solver)"
  local FILE; FILE="$(env_file)"
  log "Using solver: $PKG"
  log "Using environment file: $(basename "$FILE")"

  if conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV_NAME"; then
    log "Updating existing environment '$CONDA_ENV_NAME' with $PKG..."
    "$PKG" env update -n "$CONDA_ENV_NAME" -f "$FILE" --prune
  else
    log "Creating new environment '$CONDA_ENV_NAME' with $PKG..."
    log "This may take several minutes..."
    "$PKG" env create -f "$FILE"
  fi
  
  log "Installing ionosense-hpc Python package in development mode..."
  conda run -n "$CONDA_ENV_NAME" python -m pip install -e ".[dev,benchmark,export]"

  ok "Environment ready. Activate with: conda activate $CONDA_ENV_NAME"
}

cmd_build() {
  local preset="${1:-$DEFAULT_PRESET}"
  section "Configuring & Building (preset: ${preset})"
  ensure_env_activated

  cmake --preset "$preset"
  cmake --build --preset "$preset" --parallel --verbose

  log "Verifying Python module..."
  with_pythonpath python -c "import ionosense_hpc; print(f'Module loaded: v{ionosense_hpc.__version__}')" && ok "Python module verified" || warn "Python module import failed - check build output"

  ok "Build finished -> ${BUILD_DIR}/${preset}"
}

cmd_rebuild() {
  local preset="${1:-$DEFAULT_PRESET}"
  section "Clean Rebuild (preset: ${preset})"
  if [[ -d "${BUILD_DIR}/${preset}" ]]; then
    log "Removing ${BUILD_DIR}/${preset}"
    rm -rf "${BUILD_DIR:?}/${preset}"
  fi
  cmd_build "$preset"
}

# --- Test Command Sub-Functions ---
run_cpp_tests() {
  local preset="${1}"
  log "Running C++ tests for preset: $preset"
  
  local build_dir="${BUILD_DIR}/${preset}"

  # 1. Check if the build directory exists. If not, build it.
  if [[ ! -d "$build_dir" ]]; then
      warn "Build directory not found for preset '$preset'."
      log "Attempting to build the preset automatically..."
      # Use the main build command. This will configure and build.
      if ! cmd_build "$preset"; then
          err "Failed to build preset '$preset'. Cannot run C++ tests."
          return 1
      fi
  fi

  # 2. Check if tests were configured for this preset.
  if [[ ! -f "${build_dir}/CTestTestfile.cmake" ]]; then
      err "CTest configuration not found in: $build_dir"
      warn "This means tests were not enabled for the '$preset' preset."
      warn "Please check your CMakeLists.txt and CMakePresets.json."
      return 1 
  fi

  # 3. Run ctest from within the directory.
  log "Executing tests from build directory: $build_dir"
  if (cd "$build_dir" && ctest --output-on-failure); then
    ok "C++ tests passed"
    return 0
  else
    warn "Some C++ tests failed"
    return 1
  fi
}


run_py_tests() {
  log "Running Python tests..."
  if with_pythonpath pytest -v "${PYTHON_DIR}/tests" --tb=short; then
    ok "Python tests passed"
    return 0
  else
    warn "Python tests failed. This could be due to a test error or failing code coverage requirements."
    return 1
  fi
}

cmd_test() {
  local test_type="${1:-all}"
  local preset="${2:-$DEFAULT_PRESET}"
  
  section "Running Tests"
  ensure_env_activated

  local cpp_run=false
  local py_run=false
  local overall_status=0

  case "$test_type" in
    all) cpp_run=true; py_run=true ;;
    cpp) cpp_run=true ;;
    py)  py_run=true ;;
    *)
      err "Unknown test type: '$test_type'. Use 'cpp', 'py', or leave blank for all."
      usage
      exit 1
      ;;
  esac

  if [[ "$cpp_run" == true ]]; then
    if ! run_cpp_tests "$preset"; then
      overall_status=1
    fi
  fi

  if [[ "$py_run" == true ]]; then
    if ! run_py_tests; then
      overall_status=1
    fi
  fi
  
  echo # Add a newline for better formatting before the final status
  if [[ "$overall_status" -eq 0 ]]; then
    ok "Test run finished successfully."
  else
    err "Test run finished with failures."
    exit 1
  fi
}


cmd_list() {
  local list_type="${1-}"
  if [[ -z "$list_type" ]]; then err "Usage: list <benchmarks|presets|devices>"; exit 1; fi
  
  ensure_env_activated
  case "$list_type" in
    benchmarks)
      section "Available Benchmarks"
      find "${PYTHON_DIR}/src/ionosense_hpc/benchmarks" -type f -name "*.py" ! -name "__init__.py" | \
        sed "s|.*/||; s|.py||" | sort
      ;;
    presets)
      section "Available Configuration Presets"
      with_pythonpath python -c "from ionosense_hpc import Presets; [print(f'  {n:12s}: nfft={c.nfft:5d}, batch={c.batch:3d}') for n, c in Presets.list_presets().items()]"
      ;;
    devices)
      section "Available CUDA Devices"
      with_pythonpath python -c "from ionosense_hpc import gpu_count, device_info; n=gpu_count(); print(f'Found {n} CUDA device(s)'); [print(f'  [{i}] {d[\"name\"]} - {d[\"memory_free_mb\"]}/{d[\"memory_total_mb\"]} MB free') for i in range(n) for d in [device_info(i)]]"
      ;;
    *) err "Unknown list type: '$list_type'. Use benchmarks, presets, or devices." ;;
  esac
}

cmd_bench() {
  [[ $# -lt 1 ]] && { err "Usage: bench <script_name|suite> [args...]"; exit 1; }
  ensure_env_activated
  mkdir -p "$BENCH_RESULTS_DIR"

  local script_name="$1"; shift
  local module_base="ionosense_hpc.benchmarks"

  if [[ "$script_name" == "suite" ]]; then
    section "Running Full Benchmark Suite"
    local preset="${1:-realtime}"
    local timestamp; timestamp=$(date +%Y%m%d_%H%M%S)
    local output_dir="${BENCH_RESULTS_DIR}/${timestamp}_${preset}"
    with_pythonpath python -m "${module_base}.suite" --preset "$preset" --output "$output_dir" --log-level INFO
    ok "Results saved to: $output_dir"
  else
    local module_name="${module_base}.${script_name}"
    section "Running Benchmark: $module_name"
    with_pythonpath python -m "$module_name" "$@"
  fi
}

cmd_profile() {
  [[ $# -lt 2 ]] && { err "Usage: profile <nsys|ncu> <script_name> [args...]"; exit 1; }
  ensure_env_activated

  local tool="$1"; shift
  local script_name="$1"; shift
  local module_base="ionosense_hpc.benchmarks"
  local module_name="${module_base}.${script_name}"

  mkdir -p "$NSYS_DIR" "$NCU_DIR"
  local stamp; stamp="$(date +%Y%m%d_%H%M%S)"
  local base_name; base_name="${script_name//\//_}_${stamp}"

  section "Profiling ($tool): $module_name"
  case "$tool" in
    nsys)
      local report_path="${NSYS_DIR}/${base_name}"
      with_pythonpath nsys profile -o "${report_path}" --trace=cuda,nvtx,osrt -f true --wait=all \
        python -m "$module_name" "$@"
      ok "Nsight Systems report -> ${report_path}.nsys-rep"
      ;;
    ncu)
      local report_path="${NCU_DIR}/${base_name}"
      with_pythonpath ncu --set full -o "${report_path}" \
        python -m "$module_name" "$@"
      ok "Nsight Compute report -> ${report_path}.ncu-rep"
      ;;
    *)
      err "Unknown profiler: '$tool'. Use 'nsys' or 'ncu'."
      ;;
  esac
}

cmd_validate() {
    section "Running Validation Suite"
    ensure_env_activated
    
    log "Running accuracy and stability validation..."
    local validation_script="from ionosense_hpc.benchmarks import benchmark_accuracy, benchmark_numerical_stability; import json; acc_results = benchmark_accuracy(); print(f\"Accuracy: {acc_results['summary']['pass_rate']:.0%} tests passed\"); stab_results = benchmark_numerical_stability(); print(f\"Stability: {'PASS' if stab_results['all_stable'] else 'FAIL'}\"); f_path = r'$BUILD_DIR/validation_results.json'; open(f_path, 'w').write(json.dumps({'accuracy': acc_results, 'stability': stab_results}, indent=2)); print(f\"Results saved to: {f_path}\")"
    with_pythonpath python -c "$validation_script"

    ok "Validation complete"
}

cmd_monitor() {
    section "GPU Monitoring"
    ensure_env_activated
    
    log "Starting GPU monitor (Ctrl+C to stop)..."
    local monitor_script="import time, os; from ionosense_hpc import monitor_device; try: [ (os.system('clear'), print('=== GPU Monitor ==='), print(monitor_device()), time.sleep(1)) for _ in iter(int, 1)]; except KeyboardInterrupt: print('\nDone.')"
    with_pythonpath python -c "$monitor_script"
}

cmd_info() {
    section "System Information"
    ensure_env_activated
    
    with_pythonpath python -c "from ionosense_hpc import show_versions; print('=== Environment ==='); show_versions(verbose=True)"
}

cmd_clean() {
  section "Cleaning Workspace"
  if [[ -d "${BUILD_DIR}" ]]; then
    log "Removing build directory: ${BUILD_DIR}"
    rm -rf "${BUILD_DIR}"
  fi
  
  log "Cleaning Python artifacts..."
  find "$PROJECT_ROOT" -type d \( -name "__pycache__" -o -name ".pytest_cache" -o -name "*.egg-info" \) -exec rm -rf {} +
  find "$PROJECT_ROOT" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete

  ok "Workspace cleaned."
}

cmd_workflow() {
  local have; have="$(cmake --version | head -n1 | awk '{print $3}')"
  local min_ver="3.25.0"
  # version_ge check
  if ! printf '%s\n' "$min_ver" "$have" | sort -V -C; then
      err "CMake workflow presets require CMake >= $min_ver. Detected: $have"
      exit 1
  fi
  
  local wf="${1:-$DEFAULT_WORKFLOW}"
  section "CMake Workflow (preset: ${wf})"
  cmake --workflow --preset "$wf"
  ok "Workflow completed."
}

usage() {
  cat <<EOF
${CBLD}IONOSENSE-HPC • Research-Grade Signal Processing CLI (Linux/WSL)${C0}
Usage: ./scripts/cli.sh <command> [options]

${CBLD}CORE WORKFLOW${C0}
  setup                      Create/update environment & install Python package
  build [preset]             Configure & build (default: ${DEFAULT_PRESET})
  rebuild [preset]           Clean & rebuild
  test [cpp|py] [preset]     Run tests for cpp, py, or all (default)
  workflow [preset]          Run a full CMake workflow (default: ${DEFAULT_WORKFLOW}, requires CMake>=3.25)

${CBLD}BENCHMARKING & PROFILING${C0}
  list <type>                List available items (benchmarks, presets, devices)
  bench suite [preset]       Run full benchmark suite with report
  bench <name> [args...]     Run specific benchmark
  profile <tool> <name>      Profile with Nsight Systems (nsys) or Compute (ncu)
  validate                   Run numerical validation suite

${CBLD}UTILITIES${C0}
  monitor                    Real-time GPU monitoring
  info                       Show system & build information
  clean                      Remove all build outputs & caches

${CBLD}EXAMPLES${C0}
  ./scripts/cli.sh setup
  ./scripts/cli.sh build
  ./scripts/cli.sh test py
  ./scripts/cli.sh test cpp linux-debug
EOF
}

main() {
  cd "$PROJECT_ROOT"
  local cmd="${1-help}"; shift || true
  case "$cmd" in
    help|-h|--help) usage ;;
    setup|build|rebuild|clean|list|bench|profile|workflow|validate|monitor|info) "cmd_$cmd" "$@" ;;
    test) cmd_test "$@" ;;
    *) err "Unknown command: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"

