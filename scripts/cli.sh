#!/usr/bin/env bash
# ============================================================================
# ionosense-hpc-lib • Project CLI
# ----------------------------------------------------------------------------
# Features smart discovery for benchmarks and other scripts.
# ============================================================================
set -Eeuo pipefail
IFS=$'\n\t'

# --- Paths & Defaults --------------------------------------------------------
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build"
BUILD_PRESET=${BUILD_PRESET:-"linux-rel"}
CONDA_ENV_NAME=${CONDA_ENV_NAME:-ionosense-hpc}
PYTHON_DIR="${PROJECT_ROOT}/python"

# --- Pretty logging ----------------------------------------------------------
C0='\033[0m'; CRED='\033[0;31m'; CGRN='\033[0;32m'; CYEL='\033[0;33m'; CCYN='\033[0;36m'; CBLD='\033[1m'
log()       { echo -e "${CCYN}[INFO]${C0}  $*"; }
warn()      { echo -e "${CYEL}[WARN]${C0}  $*"; }
err()       { echo -e "${CRED}[ERR ]${C0}  $*" 1>&2; }
ok()        { echo -e "${CGRN}[OK  ]${C0}  $*"; }
section()   { echo -e "\n${CBLD}== $* ==${C0}"; }

trap 'err "Command failed on line $LINENO"' ERR

# --- Helpers -----------------------------------------------------------------
activate_env() {
    if [[ "${CONDA_DEFAULT_ENV-}" != "$CONDA_ENV_NAME" ]]; then
        log "Activating Conda environment: $CONDA_ENV_NAME"
        # shellcheck disable=SC1091
        source "$(conda info --base)/etc/profile.d/conda.sh"
        conda activate "$CONDA_ENV_NAME"
    fi
}

with_pythonpath() {
    export PYTHONPATH="${BUILD_DIR}/${BUILD_PRESET}:${PYTHON_DIR}:${PYTHONPATH-}"
    "$@"
}

# Smartly find a script by its name, searching recursively
find_script() {
    local type="$1" # e.g., "Benchmark"
    local dir="$2"  # e.g., "${PYTHON_DIR}/benchmarks"
    local name="$3" # e.g., "raw_throughput"
    local found_files
    
    found_files=$(find "$dir" -type f -name "${name}.py")
    local count
    count=$(echo "$found_files" | wc -l)

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

# --- Core actions ------------------------------------------------------------
cmd_setup() {
    section "Environment Setup (Conda)"
    if ! command -v conda >/dev/null 2>&1; then
        err "Conda not found. Please install it first."
        exit 1
    fi
    # shellcheck disable=SC1091
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda env update -n "$CONDA_ENV_NAME" -f "${PROJECT_ROOT}/environment.yml" --prune
    ok "Conda env ready. Activate with: conda activate $CONDA_ENV_NAME"
}

cmd_build() {
    local preset="${1:-$BUILD_PRESET}"
    section "Configuring & Building (preset: ${preset})"
    cmake --preset "$preset"
    cmake --build --preset "$preset" --parallel --verbose
    ok "Build finished -> ${BUILD_DIR}/${preset}"
}

cmd_rebuild() {
    local preset="${1:-$BUILD_PRESET}"
    section "Clean Rebuild (preset: ${preset})"
    if [[ -d "${BUILD_DIR}/${preset}" ]]; then
        log "Removing ${BUILD_DIR}/${preset}"
        rm -rf "${BUILD_DIR}/${preset}"
    fi
    cmd_build "$preset"
}

cmd_test() {
    section "Running All Tests"
    # C++ Tests
    log "Running C++ tests..."
    ctest --preset "linux-tests" --output-on-failure
    
    # Python Tests
    if [[ -d "${PYTHON_DIR}/tests" ]]; then
        log "Running Python tests..."
        activate_env
        with_pythonpath python3 -m pytest -q "${PYTHON_DIR}/tests"
    fi
    ok "All tests completed."
}

cmd_list() {
    case "$1" in
        benchmarks)
            section "Available Benchmarks"
            find "${PYTHON_DIR}/benchmarks" -type f -name "*.py" ! -name "__init__.py" | \
                sed "s|${PYTHON_DIR}/benchmarks/||; s|.py||" | sort
            ;;
        *)
            err "Usage: list <benchmarks>"
            ;;
    esac
}

cmd_bench() {
    local script_name="${1-}"
    shift || true
    [[ -z "$script_name" ]] && { err "Usage: bench <script_name> [args...]"; exit 1; }
    
    local script_path
    script_path=$(find_script "Benchmark" "${PYTHON_DIR}/benchmarks" "$script_name")
    
    section "Running Benchmark: $script_name"
    activate_env
    with_pythonpath python3 "$script_path" "$@"
}

cmd_profile() {
    local tool="${1-}"
    local script_name="${2-}"
    shift 2 || true
    [[ -z "$tool" || -z "$script_name" ]] && { err "Usage: profile <nsys|ncu> <script_name> [args...]"; exit 1; }

    local script_path
    script_path=$(find_script "Benchmark" "${PYTHON_DIR}/benchmarks" "$script_name")
    local out_dir="${BUILD_DIR}/profiles/${tool}"
    mkdir -p "$out_dir"
    local out_file="${out_dir}/${script_name}_$(date +%Y%m%d_%H%M%S)"
    
    section "Profiling ($tool): $script_name"
    activate_env
    
    case "$tool" in
        nsys)
            with_pythonpath nsys profile -o "$out_file" --trace=cuda,nvtx -f true \
                python3 "$script_path" "$@"
            ok "Nsight Systems report saved to ${out_file}.nsys-rep"
            ;;
        ncu)
            with_pythonpath ncu --set full --target-processes all -o "$out_file" \
                python3 "$script_path" "$@"
            ok "Nsight Compute report saved to ${out_file}.ncu-rep"
            ;;
        *)
            err "Unknown profiler: '$tool'. Use 'nsys' or 'ncu'."
            exit 1
            ;;
    esac
}

# --- Usage & Main ------------------------------------------------------------
usage() {
    cat <<EOF
${CBLD}IONOSENSE-HPC • Scalable Project CLI${C0}
Usage: ./scripts/cli.sh <command> [options]

${CBLD}CORE WORKFLOW${C0}
  setup                    Update Conda environment from environment.yml
  build [preset]           Configure & build the project (default: ${BUILD_PRESET})
  rebuild [preset]         Clean and rebuild
  test                     Run all C++ and Python unit tests
  
${CBLD}BENCHMARKING & PROFILING${C0}
  list benchmarks          Discover and list all available benchmark scripts
  bench <name> [args...]   Run a benchmark by its name (without .py)
  profile <tool> <name>    Profile a benchmark with 'nsys' or 'ncu'

${CBLD}UTILITIES${C0}
  clean                    Remove all build and cache files

${CBLD}EXAMPLES${C0}
  ./scripts/cli.sh test
  ./scripts/cli.sh list benchmarks
  ./scripts/cli.sh bench raw_throughput -n 4096
  ./scripts/cli.sh profile nsys graphs_comparison
EOF
}

main() {
    cd "$PROJECT_ROOT"
    local cmd="${1-help}"; shift || true
    
    case "$cmd" in
        help|-h|--help) usage ;;
        setup|build|rebuild|test|clean|list|bench|profile) "cmd_$cmd" "$@" ;;
        *) err "Unknown command: $cmd"; usage; exit 1 ;;
    esac
}

main "$@"