#!/usr/bin/env bash
# ============================================================================
# ionosense-hpc-lib • Project CLI (Linux/WSL)
# - Mamba-first (conda fallback allowed ONLY on Linux)
# - Adds `workflow` command using CMake workflow presets (>= 3.25)
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

# --- Pretty logging ----------------------------------------------------------
C0='\033[0m'; CRED='\033[0;31m'; CGRN='\033[0;32m'; CYEL='\033[0;33m'; CCYN='\033[0;36m'; CBLD='\033[1m'
log()     { echo -e "${CCYN}[INFO]${C0}  $*"; }
warn()    { echo -e "${CYEL}[WARN]${C0}  $*"; }
err()     { echo -e "${CRED}[ERR ]${C0}  $*" 1>&2; }
ok()      { echo -e "${CGRN}[OK  ]${C0}  $*"; }
section() { echo -e "\n${CBLD}== $* ==${C0}"; }
trap 'err "Command failed on line $LINENO"' ERR

# --- Env file selection (Linux) ---------------------------------------------
env_file() {
  if [[ -f "${PROJECT_ROOT}/environment.linux.yml" ]]; then
    echo "${PROJECT_ROOT}/environment.linux.yml"
  elif [[ -f "${PROJECT_ROOT}/environment.yml" ]]; then
    echo "${PROJECT_ROOT}/environment.yml"
  else
    err "No environment file found (environment.linux.yml or environment.yml)."
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
env_exists() {
  conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV_NAME"
}

activate_env() {
  conda_source
  if [[ "${CONDA_DEFAULT_ENV-}" != "$CONDA_ENV_NAME" ]]; then
    log "Activating Conda environment: $CONDA_ENV_NAME"
    conda activate "$CONDA_ENV_NAME"
  fi
}

with_pythonpath() {
  export PYTHONPATH="${BUILD_DIR}/${DEFAULT_PRESET}:${PYTHON_DIR}:${PYTHONPATH-}"
  "$@"
}

find_script() {
  local type="$1" dir="$2" name="$3"
  local found_files
  found_files=$(find "$dir" -type f -name "${name}.py" 2>/dev/null || true)
  local count
  count=$(echo "$found_files" | sed '/^\s*$/d' | wc -l)
  if [[ $count -eq 0 ]]; then
    err "$type script not found: ${name}.py"
    log "Use './scripts/cli.sh list benchmarks' to see available scripts."
    exit 1
  elif [[ $count -gt 1 ]]; then
    err "Ambiguous script name: '${name}'. Multiple matches found:"
    echo "$found_files"
    exit 1
  fi
  echo "$found_files"
}

# --- CMake version / workflow support ----------------------------------------
cmake_version() {
  cmake --version | head -n1 | awk '{print $3}'
}
version_ge() {
  # returns 0 (true) if $1 >= $2
  printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1 | grep -qx "$2"
}
cmake_supports_workflow() {
  # Workflow presets are available starting with CMake 3.25
  local have; have="$(cmake_version)"
  version_ge "$have" "3.25.0"
}

# --- Commands ----------------------------------------------------------------
cmd_setup() {
  section "Environment Setup (Linux)"
  conda_source
  local PKG; PKG="$(solver)"
  local FILE; FILE="$(env_file)"
  log "Using solver: $PKG"
  log "Using environment file: $(basename "$FILE")"

  if env_exists; then
    "$PKG" env update -n "$CONDA_ENV_NAME" -f "$FILE" --prune
  else
    "$PKG" env create -n "$CONDA_ENV_NAME" -f "$FILE"
  fi
  ok "Environment ready. Activate with: conda activate $CONDA_ENV_NAME"
}

cmd_build() {
  local preset="${1:-$DEFAULT_PRESET}"
  section "Configuring & Building (preset: ${preset})"
  cmake --preset "$preset"
  cmake --build --preset "$preset" --parallel --verbose
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

cmd_test() {
  section "Running All Tests (Linux)"
  log "Running C++ tests via CTest preset..."
  ctest --preset "linux-tests" --output-on-failure
  if [[ -d "${PYTHON_DIR}/ionosense_hpc/tests" ]]; then
    log "Running Python tests..."
    activate_env
    with_pythonpath python3 -m pytest -q "${PYTHON_DIR}/tests"
  fi
  ok "Tests completed."
}

cmd_list() {
  case "${1-}" in
    benchmarks)
      section "Available Benchmarks"
      find "${PYTHON_DIR}/benchmarks" -type f -name "*.py" ! -name "__init__.py" | \
        sed "s|${PYTHON_DIR}/benchmarks/||; s|.py||" | sort
      ;;
    *) err "Usage: list <benchmarks>" ;;
  esac
}

cmd_bench() {
  local script_name="${1-}"; shift || true
  [[ -z "$script_name" ]] && { err "Usage: bench <script_name> [args...]"; exit 1; }
  local script_path; script_path=$(find_script "Benchmark" "${PYTHON_DIR}/benchmarks" "$script_name")
  section "Running Benchmark: $script_name"
  activate_env
  with_pythonpath python3 "$script_path" "$@"
}

cmd_profile() {
  local tool="${1-}" script_name="${2-}"; shift 2 || true
  [[ -z "$tool" || -z "$script_name" ]] && { err "Usage: profile <nsys|ncu> <script_name> [args...]"; exit 1; }
  local script_path; script_path=$(find_script "Benchmark" "${PYTHON_DIR}/benchmarks" "$script_name")
  mkdir -p "$NSYS_DIR" "$NCU_DIR"
  local stamp; stamp="$(date +%Y%m%d_%H%M%S)"
  local base="${script_name}_${stamp}"

  section "Profiling ($tool): $script_name"
  activate_env
  case "$tool" in
    nsys)
      with_pythonpath nsys profile -o "${NSYS_DIR}/${base}" --trace=cuda,nvtx -f true \
        python3 "$script_path" "$@"
      ok "Nsight Systems report -> ${NSYS_DIR}/${base}.nsys-rep"
      ;;
    ncu)
      with_pythonpath ncu --set full --target-processes all -o "${NCU_DIR}/${base}" \
        python3 "$script_path" "$@"
      ok "Nsight Compute report -> ${NCU_DIR}/${base}.ncu-rep"
      ;;
    *)
      err "Unknown profiler: '$tool'. Use 'nsys' or 'ncu'."
      ;;
  esac
}

cmd_clean() {
  section "Cleaning Workspace"
  if [[ -d "${BUILD_DIR}" ]]; then
    log "Removing build directory: ${BUILD_DIR}"
    rm -rf "${BUILD_DIR}"
  fi
  ok "Workspace cleaned."
}

cmd_workflow() {
  local wf="${1:-$DEFAULT_WORKFLOW}"
  section "CMake Workflow (preset: ${wf})"
  if ! cmake_supports_workflow; then
    err "CMake workflow presets require CMake >= 3.25 (project min is 3.26). Detected: $(cmake_version)"
    exit 1
  fi
  cmake --workflow --preset "$wf"
  ok "Workflow completed."
}

usage() {
  cat <<EOF
${CBLD}IONOSENSE-HPC • Linux CLI${C0}
Usage: ./scripts/cli.sh <command> [options]

CORE
  setup                      Create/update env from environment.linux.yml (or environment.yml)
  build [preset]             Configure & build (default: ${DEFAULT_PRESET})
  rebuild [preset]           Clean & rebuild
  test                       Run C++ & Python tests
  workflow [preset]          Run a full CMake workflow (default: ${DEFAULT_WORKFLOW})

BENCH & PROFILING
  list benchmarks            List benchmark scripts
  bench <name> [args...]     Run benchmark by name
  profile <nsys|ncu> <name>  Profile a benchmark; outputs under build/nsight_reports/{nsys,ncu}_reports

UTIL
  clean                      Remove all build outputs
EOF
}

main() {
  cd "$PROJECT_ROOT"
  local cmd="${1-help}"; shift || true
  case "$cmd" in
    help|-h|--help) usage ;;
    setup|build|rebuild|test|clean|list|bench|profile|workflow) "cmd_$cmd" "$@" ;;
    *) err "Unknown command: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
