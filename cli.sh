#!/usr/bin/env bash
# ============================================================================
# ionosense-hpc-lib • Linux CLI
# ----------------------------------------------------------------------------
# Modern, portable task runner for building, testing, benchmarking, and
# profiling the CUDA/pybind11 project on Linux/WSL2.
#
# Highlights
# • Ninja + ccache (if available)
# • Clean rebuilds, multi-config builds, configurable CUDA arch list
# • Adds build/ to PYTHONPATH automatically for Python demos/benchmarks
# • Nsight Systems profiling helpers
# • "doctor" diagnostics + Conda dev shell
#
# Reference docs:
#   CMake CLI:        https://cmake.org/cmake/help/latest/manual/cmake.1.html
#   CTest:            https://cmake.org/cmake/help/latest/manual/ctest.1.html
#   CUDA Toolkit:     https://docs.nvidia.com/cuda/
#   pybind11:         https://pybind11.readthedocs.io/
#   Conda envs:       https://conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html
# ============================================================================
set -Eeuo pipefail
IFS=$'
	'

# --- Paths & Defaults --------------------------------------------------------
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR=${BUILD_DIR:-"${PROJECT_ROOT}/build"}
BUILD_TYPE=${BUILD_TYPE:-Release}     # Debug | Release | RelWithDebInfo | MinSizeRel
GENERATOR=${GENERATOR:-auto}          # auto | Ninja | Unix Makefiles
CUDA_ARCHS=${CUDA_ARCHS:-""}         # e.g. "86;89" (empty = CMakeLists default)
CONDA_ENV_NAME=${CONDA_ENV_NAME:-ionosense-hpc}
ENV_FILE=${ENV_FILE:-"${PROJECT_ROOT}/environment.yml"}
PYTHON=${PYTHON:-python3}

# Demo/benchmark scripts
PY_FFT_RT="${PROJECT_ROOT}/python/benchmarks/fft_realtime.py"
PY_FFT_RAW="${PROJECT_ROOT}/python/benchmarks/fft_raw.py"
PY_UTILS="${PROJECT_ROOT}/python/benchmarks/utils.py"
PY_SCALE_A="${PROJECT_ROOT}/python/benchmarks/fft_batch_scaling.py"
PY_SCALE_B="${PROJECT_ROOT}/python/benchmarks/benchmark_scaling.py"
PY_GRAPHS="${PROJECT_ROOT}/python/benchmarks/fft_graphs_comp.py"
PY_VERIFY="${PROJECT_ROOT}/python/benchmarks/verify_accuracy.py"

# Profiles out dir
PROFILE_DIR_NSYS="${PROJECT_ROOT}/build/nsight_reports/nsys_reports"
mkdir -p "${PROFILE_DIR_NSYS}"

# --- Pretty logging ----------------------------------------------------------
C0='[0m'; CRED='[0;31m'; CGRN='[0;32m'; CYEL='[0;33m'; CCYN='[0;36m'; CBLD='[1m'
log()       { echo -e "${CCYN}[INFO]${C0}  $*"; }
warn()      { echo -e "${CYEL}[WARN]${C0}  $*"; }
err()       { echo -e "${CRED}[ERR ]${C0}  $*" 1>&2; }
ok()        { echo -e "${CGRN}[OK  ]${C0}  $*"; }
section()   { echo -e "
${CBLD}== $* ==${C0}"; }

trap 'err "Command failed on line $LINENO"' ERR

# --- Helpers -----------------------------------------------------------------
need() { command -v "$1" >/dev/null 2>&1 || { err "Required tool '$1' not found"; exit 127; }; }

choose_generator() {
  if [[ "$GENERATOR" == auto ]]; then
    if command -v ninja >/dev/null 2>&1; then echo Ninja; else echo "Unix Makefiles"; fi
  else
    echo "$GENERATOR"
  fi
}

maybe_ccache_flags() {
  if command -v ccache >/dev/null 2>&1; then
    echo "-DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DCMAKE_CUDA_COMPILER_LAUNCHER=ccache"
  else
    echo ""
  fi
}

cmake_arch_flags() {
  if [[ -n "$CUDA_ARCHS" ]]; then
    echo "-DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCHS}"
  else
    echo ""  # Use project defaults from CMakeLists.txt
  fi
}

ensure_conda_loaded() {
  if command -v conda >/dev/null 2>&1; then
    # shellcheck disable=SC1091
    source "$(conda info --base)/etc/profile.d/conda.sh"
  fi
}

activate_env() {
  ensure_conda_loaded
  if command -v conda >/dev/null 2>&1; then
    # If already in the desired env, don't re-activate (prevents nested-activate bugs)
    if [[ "${CONDA_DEFAULT_ENV-}" == "$CONDA_ENV_NAME" ]]; then
      return 0
    fi
    # Guard against unbound vars in third-party activate/deactivate hooks
    set +u
    conda activate "$CONDA_ENV_NAME"
    set -u
  else
    warn "Conda not found. Using system Python."
  fi
}

with_pythonpath() {
  # Ensure Python can import the freshly built pybind11 module from build dir
  export PYTHONPATH="${BUILD_DIR}:${PYTHONPATH-}"
  "$@"
}

# --- Core actions ------------------------------------------------------------
cmd_doctor() {
  section "Environment Diagnostics"
  for t in gcc g++ nvcc cmake ninja ${PYTHON}; do
    if command -v "$t" >/dev/null 2>&1; then "$t" --version 2>/dev/null | head -n1 || true; else warn "$t not found"; fi
  done
  if command -v nsys >/dev/null 2>&1; then nsys --version | head -n1; else warn "nsys not found"; fi
  if command -v conda >/dev/null 2>&1; then conda info | sed -n '1,12p'; else warn "conda not found"; fi
}

cmd_setup() {
  section "Environment Setup (Conda)"
  ensure_conda_loaded
  if ! command -v conda >/dev/null 2>&1; then
    err "Conda not found. Install Miniconda: https://docs.conda.io/en/latest/miniconda.html"
    exit 1
  fi
  if [[ -f "$ENV_FILE" ]]; then
    if conda env list | grep -q "^${CONDA_ENV_NAME}\s"; then
      log "Updating existing env '${CONDA_ENV_NAME}' from $ENV_FILE ..."
      conda env update -n "$CONDA_ENV_NAME" -f "$ENV_FILE" --prune
    else
      log "Creating env '${CONDA_ENV_NAME}' from $ENV_FILE ..."
      conda env create -n "$CONDA_ENV_NAME" -f "$ENV_FILE"
    fi
    ok "Conda env ready. Launch with: ./cli.sh dev"
  else
    err "Environment file not found: $ENV_FILE"
    exit 2
  fi
}

# Configure + build (no clean)
cmd_build() {
  local bt=${1:-$BUILD_TYPE}
  section "Configuring CMake (${bt})"
  need cmake
  local gen; gen=$(choose_generator)
  mkdir -p "$BUILD_DIR"

  # Build CMake args as an array to avoid launcher quoting bugs
  local -a CMAKE_ARGS
  CMAKE_ARGS=( -S "$PROJECT_ROOT" -B "$BUILD_DIR" -G "$gen" -DCMAKE_BUILD_TYPE="$bt" )

  # ccache launchers if available (each as its own arg)
  if command -v ccache >/dev/null 2>&1; then
    CMAKE_ARGS+=( -DCMAKE_CXX_COMPILER_LAUNCHER=ccache )
    CMAKE_ARGS+=( -DCMAKE_CUDA_COMPILER_LAUNCHER=ccache )
  fi

  # CUDA arch list if provided
  if [[ -n "${CUDA_ARCHS}" ]]; then
    CMAKE_ARGS+=( -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCHS}" )
  fi

  cmake "${CMAKE_ARGS[@]}"

  section "Building"
  # Only pass --config for multi-config generators (VS/Xcode/Ninja Multi-Config)
  if [[ "$gen" == "Ninja" || "$gen" == "Unix Makefiles" ]]; then
    cmake --build "$BUILD_DIR" --parallel --verbose
  else
    cmake --build "$BUILD_DIR" --config "$bt" --parallel --verbose
  fi
  ok "Build finished -> $BUILD_DIR"
}

# Clean build dir then build
cmd_rebuild() {
  local bt=${1:-$BUILD_TYPE}
  section "Rebuilding (${bt})"
  rm -rf "$BUILD_DIR"
  cmd_build "$bt"
}

cmd_clean() {
  section "Cleaning"
  rm -rf "$BUILD_DIR" .pytest_cache **/__pycache__ 2>/dev/null || true
  find "$PROJECT_ROOT" -name "*.pyc" -delete 2>/dev/null || true
  ok "Workspace cleaned"
}

cmd_test() {
  section "Running C++ & Python tests"
  need ctest
  (cd "$BUILD_DIR" && ctest --output-on-failure)
  if [[ -d "${PROJECT_ROOT}/tests" ]]; then
    activate_env
    with_pythonpath "$PYTHON" -m pytest -q "${PROJECT_ROOT}/tests" || true
  else
    warn "No Python tests folder found"
  fi
}

cmd_dev() {
  section "Conda Dev Shell (${CONDA_ENV_NAME})"
  activate_env
  bash -i
}

# --- Benchmarks & Profiling --------------------------------------------------
ensure_bench_scripts_exist() {
  [[ -f "$PY_FFT_RT" ]]  || { err "Missing: $PY_FFT_RT";  exit 3; }
  [[ -f "$PY_FFT_RAW" ]] || { err "Missing: $PY_FFT_RAW"; exit 3; }
  [[ -f "$PY_UTILS" ]]   || { err "Missing: $PY_UTILS";   exit 3; }
}

# Registry (name -> script path). `scale` resolves preferred/fallback names.
declare -A BENCH_SCRIPTS=(
  [rt]="$PY_FFT_RT"
  [raw]="$PY_FFT_RAW"
  [scale]=""       # resolved dynamically (A or B)
  [graphs]="$PY_GRAPHS"
  [verify]="$PY_VERIFY"
)

bench_resolve() {
  local name="$1"; local path="${BENCH_SCRIPTS[$name]:-}"
  if [[ "$name" == scale ]]; then
    if [[ -f "$PY_SCALE_A" ]]; then path="$PY_SCALE_A"; elif [[ -f "$PY_SCALE_B" ]]; then path="$PY_SCALE_B"; fi
  fi
  [[ -n "$path" && -f "$path" ]] && { echo "$path"; return 0; }
  return 1
}

ensure_utils() {
  [[ -f "$PY_UTILS" ]] || { err "Missing: $PY_UTILS"; exit 3; }
}

cmd_bench_list() {
  section "Available benchmarks"
  local k
  for k in "${!BENCH_SCRIPTS[@]}"; do
    if bench_resolve "$k" >/dev/null; then
      printf "  • %-8s %s
" "$k" "$(bench_resolve "$k")"
    else
      printf "  • %-8s %s
" "$k" "(script missing)"
    fi
  done | sort
}

cmd_bench_run() {
  ensure_utils; activate_env
  local name="${1:-}"; shift || true
  [[ -n "$name" ]] || { err "Usage: bench run <name> [args]"; exit 64; }
  local script
  if ! script=$(bench_resolve "$name"); then err "Unknown or missing bench: $name"; cmd_bench_list; exit 66; fi
  section "Benchmark: $name"
  with_pythonpath "$PYTHON" "$script" "$@"
}

# Legacy shorthand wrappers (still supported)
cmd_bench_rt()    { cmd_bench_run rt     "$@"; }
cmd_bench_raw()   { cmd_bench_run raw    "$@"; }
cmd_bench_scale() { cmd_bench_run scale  "$@"; }
cmd_bench_graphs(){ cmd_bench_run graphs "$@"; }
cmd_bench_verify(){ cmd_bench_run verify "$@"; }

nsys_or_die() { command -v nsys >/dev/null 2>&1 || { err "Nsight Systems (nsys) not found"; exit 4; }; }

cmd_profile() {
  nsys_or_die; ensure_utils; activate_env
  local name="${1:-}"; shift || true
  [[ -n "$name" ]] || { err "Usage: profile <name> [args]"; exit 64; }
  local script
  if ! script=$(bench_resolve "$name"); then err "Unknown or missing bench: $name"; cmd_bench_list; exit 66; fi
  local stamp; stamp=$(date +%Y%m%d_%H%M%S)
  local out="${PROFILE_DIR_NSYS}/${name}_${stamp}"
  section "Nsight Systems • $name"
  with_pythonpath nsys profile -o "$out" --trace=cuda,nvtx,osrt --sample=none --cpuctxsw=none \
    "$PYTHON" "$script" "$@"
  ok "Report: ${out}.qdrep"
}

# Back-compat explicit aliases retained
cmd_profile_rt()     { cmd_profile rt     "$@"; }
cmd_profile_raw()    { cmd_profile raw    "$@"; }
cmd_profile_scale()  { cmd_profile scale  "$@"; }
cmd_profile_graphs() { cmd_profile graphs "$@"; }
cmd_profile_verify() { cmd_profile verify "$@"; }
# --- Usage -------------------------------------------------------------------
usage() {
  cat <<EOF
${CBLD}ionosense-hpc-lib CLI${C0}
Usage: ./cli.sh <command> [args]

Core:
  setup                    Create/update Conda env (${CONDA_ENV_NAME}) from environment.yml
  build [TYPE]             Configure & build (TYPE: Debug/Release/RelWithDebInfo)
  rebuild [TYPE]           Clean build/ then build
  clean                    Remove build artifacts & caches
  test                     Run C++ (ctest) and Python tests (pytest if tests/ exists)
  dev                      Open an interactive shell with Conda env activated
  doctor                   Print toolchain diagnostics (cmake/nvcc/nsys/etc.)

Benchmarks (registry):
  bench list               List available benchmarks and their scripts
  bench run <name> [args]  Run a benchmark by name (rt, raw, scale, graphs, verify)

Shortcuts:
  bench:rt [args]          Real-time latency (fft_realtime.py)
  bench:raw [args]         Raw throughput (fft_raw.py)
  bench:scale [args]       Batch-scaling sweep (fft_batch_scaling.py / benchmark_scaling.py)
  bench:graphs [args]      CUDA Graphs vs No-Graphs A/B (fft_graphs_comp.py)
  bench:verify [args]      Numerical accuracy & perf sanity (verify_accuracy.py)

Profiling (Nsight Systems):
  profile <name> [args]    Profile any registered bench -> ${PROFILE_DIR_NSYS}/<name>_<ts>.qdrep
  profile:rt|raw|scale|graphs|verify  Legacy explicit aliases

Env overrides (optional):
  BUILD_TYPE=${BUILD_TYPE}  GENERATOR=${GENERATOR}  CUDA_ARCHS="${CUDA_ARCHS}"
  CONDA_ENV_NAME=${CONDA_ENV_NAME}  BUILD_DIR=${BUILD_DIR}

Examples:
  ./cli.sh build Debug
  CUDA_ARCHS="86;89" ./cli.sh rebuild RelWithDebInfo
  ./cli.sh bench list
  ./cli.sh bench run scale --nfft 4096 --min-batch 2 --max-batch 256 -k 5 -d 3 -o scaling.csv
  ./cli.sh profile graphs -n 4096 -b 8 -i 2000 -d 5
EOF
}

# --- Router ------------------------------------------------------------------
main() {
  cd "$PROJECT_ROOT"
  local cmd=${1:-help}; shift || true
  case "$cmd" in
    help|-h|--help) usage ;;
    doctor)         cmd_doctor ;;
    setup)          cmd_setup ;;
    build)          cmd_build "${1:-$BUILD_TYPE}" ;;
    rebuild)        cmd_rebuild "${1:-$BUILD_TYPE}" ;;
    clean)          cmd_clean ;;
    test)           cmd_test ;;
    dev)            cmd_dev ;;
    # bench registry entrypoints
    bench)          sub=${1:-}; shift || true;
                    case "$sub" in
                      list) cmd_bench_list ;;
                      run)  cmd_bench_run "$@" ;;
                      *)    err "Usage: bench {list|run <name> [args]}"; exit 64 ;;
                    esac ;;
    # shorthand bench aliases
    bench:rt)       cmd_bench_rt "$@" ;;
    bench:raw)      cmd_bench_raw "$@" ;;
    bench:scale)    cmd_bench_scale "$@" ;;
    bench:graphs)   cmd_bench_graphs "$@" ;;
    bench:verify)   cmd_bench_verify "$@" ;;
    # profiler
    profile)        cmd_profile "$@" ;;
    profile:rt)     cmd_profile_rt "$@" ;;
    profile:raw)    cmd_profile_raw "$@" ;;
    profile:scale)  cmd_profile_scale "$@" ;;
    profile:graphs) cmd_profile_graphs "$@" ;;
    profile:verify) cmd_profile_verify "$@" ;;
    *)              err "Unknown command: $cmd"; usage; exit 64 ;;
  esac
}

main "$@"
