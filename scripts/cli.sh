#!/usr/bin/env bash
# ============================================================================
# sigtekx • Development CLI (Linux/WSL)
# Essential development tasks - research tools use native CLIs directly
# ============================================================================
set -Eeuo pipefail
IFS=$'\n\t'

# --- Configuration & Paths ---------------------------------------------------
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build"
DEFAULT_PRESET="${BUILD_PRESET:-linux-rel}"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-sigtekx}"

# --- Pretty logging ----------------------------------------------------------
C0='\033[0m'; CRED='\033[0;31m'; CGRN='\033[0;32m'; CYEL='\033[0;33m'; CCYN='\033[0;36m'; CBLD='\033[1m'; CDIM='\033[2m'
log()     { echo -e "${CCYN}[INFO]${C0}  $*"; }
warn()    { echo -e "${CYEL}[WARN]${C0}  $*"; }
err()     { echo -e "${CRED}[ERR ]${C0}  $*" 1>&2; }
ok()      { echo -e "${CGRN}[ OK ]${C0}  $*"; }
section() { echo -e "\n${CBLD}== $* ==${C0}\n"; }
trap 'err "Command failed on line $LINENO"' ERR

# --- Env file selection -------------------------------------------------------
env_file() {
  local f="${PROJECT_ROOT}/environments/environment.linux.yml"
  if [[ -f "$f" ]]; then
    echo "$f"
  else
    err "Environment file not found: $f"
    exit 1
  fi
}

# --- Conda shell (for activation) --------------------------------------------
conda_source() {
  set +u
  # Prefer well-known paths first to avoid picking up a stale conda install
  if [[ -d "$HOME/miniconda3" ]]; then
    # shellcheck disable=SC1091
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
  elif [[ -d "$HOME/mambaforge" ]]; then
    # shellcheck disable=SC1091
    source "$HOME/mambaforge/etc/profile.d/conda.sh"
  elif [[ -d "$HOME/anaconda3" ]]; then
    # shellcheck disable=SC1091
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
  elif command -v conda >/dev/null 2>&1; then
    # shellcheck disable=SC1091
    source "$(conda info --base)/etc/profile.d/conda.sh"
  else
    set -u
    err "Conda shell not found. Install Miniconda/Mambaforge."
    exit 1
  fi
  set -u
}

# --- Solver selection ---------------------------------------------------------
solver() {
  if command -v mamba >/dev/null 2>&1; then
    echo "mamba"
  elif command -v conda >/dev/null 2>&1; then
    warn "mamba not found; falling back to conda."
    echo "conda"
  else
    err "Neither mamba nor conda found."
    exit 1
  fi
}

# --- Helpers ------------------------------------------------------------------
ensure_env_activated() {
  if [[ "${CONDA_DEFAULT_ENV-}" != "$CONDA_ENV_NAME" ]]; then
    err "Conda environment '$CONDA_ENV_NAME' is not activated."
    log "Please run: conda activate $CONDA_ENV_NAME"
    exit 1
  fi
  # When invoked as a subprocess (e.g., bash cli.sh test), the conda env var
  # is inherited but PATH is not, so `python` may resolve to the wrong install.
  # Resolve the correct python from CONDA_PREFIX or known conda paths.
  if [[ -n "${CONDA_PREFIX-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
    SIGX_PYTHON="${CONDA_PREFIX}/bin/python"
  else
    local conda_base
    conda_base="$(conda info --base 2>/dev/null || echo "$HOME/miniconda3")"
    SIGX_PYTHON="${conda_base}/envs/${CONDA_ENV_NAME}/bin/python"
  fi
  if [[ ! -x "$SIGX_PYTHON" ]]; then
    err "Python not found at: $SIGX_PYTHON"
    exit 1
  fi
}

# ============================================================================
# Commands
# ============================================================================

cmd_setup() {
  section "Environment Setup"
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
    "$PKG" env create -f "$FILE"
  fi

  log "Installing sigtekx Python package in development mode..."
  local conda_base env_python
  conda_base="$(conda info --base)"
  env_python="${conda_base}/envs/${CONDA_ENV_NAME}/bin/python"
  if [[ ! -x "$env_python" ]]; then
    err "Python not found at: $env_python"
    err "conda base resolved to: $conda_base"
    exit 1
  fi
  log "Using Python: $env_python"
  "$env_python" -m pip install -e ".[dev]" --no-build-isolation

  ok "Environment ready. Activate with: conda activate $CONDA_ENV_NAME"
}

cmd_build() {
  local preset="$DEFAULT_PRESET"
  local clean=false
  local verbose=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -Preset|--preset) preset="$2"; shift 2 ;;
      -Clean|--clean) clean=true; shift ;;
      -Verbose|--verbose) verbose=true; shift ;;
      --debug) preset="linux-debug"; shift ;;
      --release) preset="linux-rel"; shift ;;
      *) shift ;;
    esac
  done

  section "Building (preset: $preset)"
  ensure_env_activated

  if $clean && [[ -d "${BUILD_DIR}/${preset}" ]]; then
    log "Cleaning build directory: ${BUILD_DIR}/${preset}"
    rm -rf "${BUILD_DIR:?}/${preset}"
  fi

  local configure_args=("--preset" "$preset")
  if $verbose; then configure_args+=("--log-level=VERBOSE"); fi

  log "Configuring with CMake..."
  cmake "${configure_args[@]}"

  local build_args=("--build" "--preset" "$preset")
  if $verbose; then build_args+=("--verbose"); fi

  log "Building..."
  cmake "${build_args[@]}"

  ok "Build completed -> ${BUILD_DIR}/${preset}"
}

cmd_test() {
  local suite="all"
  local pattern=""
  local coverage=false
  local verbose=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      python|py|p) suite="python"; shift ;;
      cpp|c++|cxx) suite="cpp"; shift ;;
      all) suite="all"; shift ;;
      -Pattern|--pattern) pattern="$2"; shift 2 ;;
      -Coverage|--coverage) coverage=true; shift ;;
      -Verbose|--verbose) verbose=true; shift ;;
      *) shift ;;
    esac
  done

  section "Running Tests"
  ensure_env_activated

  local py_args=()
  if $coverage; then py_args+=("--cov=sigtekx"); fi
  if $verbose; then py_args+=("-v"); fi
  if [[ -n "$pattern" ]]; then py_args+=("-k" "$pattern"); fi

  case "$suite" in
    python)
      log "Running Python tests..."
      "$SIGX_PYTHON" -m pytest tests/ "${py_args[@]}"
      ;;
    cpp)
      if $coverage; then
        cmd_coverage
      else
        log "Running C++ tests..."
        local test_exe="${BUILD_DIR}/${DEFAULT_PRESET}/sigtekx_tests"
        if [[ -f "$test_exe" ]]; then
          "$test_exe"
        else
          err "C++ test executable not found at: $test_exe"
          log "Run 'build' first."
          exit 1
        fi
      fi
      ;;
    all)
      log "Running Python tests..."
      "$SIGX_PYTHON" -m pytest tests/ "${py_args[@]}" || true

      log "Running C++ tests..."
      local test_exe="${BUILD_DIR}/${DEFAULT_PRESET}/sigtekx_tests"
      if [[ -f "$test_exe" ]]; then
        "$test_exe"
      else
        log "C++ tests skipped (executable not found)"
      fi
      ;;
    *)
      err "Unknown test suite: $suite. Use: all, python, cpp"
      exit 1
      ;;
  esac

  ok "Tests completed"
}

cmd_coverage() {
  local verbose=false
  local no_open=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -NoOpen|--no-open) no_open=true; shift ;;
      -Verbose|--verbose) verbose=true; shift ;;
      *) shift ;;
    esac
  done

  section "C++ Coverage (GCC/gcovr)"
  ensure_env_activated

  # Step 1: Build with coverage preset
  log "Building with coverage instrumentation..."
  local configure_args=("--preset" "linux-coverage")
  if $verbose; then configure_args+=("--log-level=VERBOSE"); fi
  cmake "${configure_args[@]}"
  cmake --build --preset linux-coverage

  # Step 2: Run tests
  local test_exe="${BUILD_DIR}/linux-coverage/sigtekx_tests"
  if [[ ! -f "$test_exe" ]]; then
    err "Test executable not found at: $test_exe"
    exit 1
  fi

  log "Running tests with coverage analysis..."
  local test_args=()
  if ! $verbose; then test_args+=("--gtest_brief=1"); fi
  "$test_exe" "${test_args[@]}" || true

  # Step 3: Generate coverage reports
  local reports_dir="${PROJECT_ROOT}/artifacts/reports"
  local coverage_dir="${reports_dir}/coverage-cpp"
  mkdir -p "$coverage_dir"

  local src_dir="${PROJECT_ROOT}/cpp"
  local root_path="${PROJECT_ROOT}"
  local src_filter="${src_dir}/.*"

  log "Generating coverage report..."

  # Terminal summary
  gcovr \
    --root "$root_path" \
    --filter "$src_filter" \
    --exclude ".*test.*" \
    --exclude ".*_deps.*" \
    --print-summary

  # HTML report
  gcovr \
    --root "$root_path" \
    --filter "$src_filter" \
    --exclude ".*test.*" \
    --exclude ".*_deps.*" \
    --html-details "${coverage_dir}/index.html"

  if [[ -f "${coverage_dir}/index.html" ]]; then
    ok "Coverage report generated: ${coverage_dir}/index.html"
    if ! $no_open && command -v xdg-open >/dev/null 2>&1; then
      xdg-open "${coverage_dir}/index.html" 2>/dev/null || true
    fi
  else
    err "Coverage report generation failed"
  fi
}

cmd_lint() {
  local target="all"
  local fix=false
  local verbose=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      python|py) target="python"; shift ;;
      cpp|c++) target="cpp"; shift ;;
      all) target="all"; shift ;;
      -Fix|--fix) fix=true; shift ;;
      -Verbose|--verbose) verbose=true; shift ;;
      *) shift ;;
    esac
  done

  section "Linting"
  ensure_env_activated

  local args=()
  if $fix; then args+=("--fix"); fi
  if $verbose; then args+=("--verbose"); fi

  case "$target" in
    python|all)
      log "Linting Python code with ruff..."
      "$SIGX_PYTHON" -m ruff check . "${args[@]}"
      ;;
    cpp)
      log "C++ linting not yet implemented"
      ;;
    *)
      err "Unknown lint target: $target. Use: all, python, cpp"
      exit 1
      ;;
  esac

  ok "Linting completed"
}

cmd_format() {
  local check=false
  local verbose=false
  local paths=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -Check|--check) check=true; shift ;;
      -Verbose|--verbose) verbose=true; shift ;;
      -*) shift ;;
      *) paths+=("$1"); shift ;;
    esac
  done

  section "Formatting C++ Code"
  ensure_env_activated

  if [[ ${#paths[@]} -eq 0 ]]; then
    paths=("cpp/src" "cpp/tests" "cpp/include" "cpp/bindings" "examples")
  fi

  local fmt_args=()
  if $check; then fmt_args+=("--dry-run" "--Werror"); fi
  if $verbose; then fmt_args+=("--verbose"); fi

  for p in "${paths[@]}"; do
    if [[ -d "${PROJECT_ROOT}/${p}" ]]; then
      find "${PROJECT_ROOT}/${p}" -type f \( -name "*.cpp" -o -name "*.hpp" -o -name "*.h" \) \
        -exec clang-format -i "${fmt_args[@]}" --style=file {} +
    fi
  done

  ok "Formatting completed"
}

cmd_typecheck() {
  local strict=false
  local verbose=false
  local paths=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -Strict|--strict) strict=true; shift ;;
      -Verbose|--verbose) verbose=true; shift ;;
      -*) shift ;;
      *) paths+=("$1"); shift ;;
    esac
  done

  section "Type Checking (mypy)"
  ensure_env_activated

  if [[ ${#paths[@]} -eq 0 ]]; then
    paths=("src/sigtekx")
  fi

  local args=()
  if $verbose; then args+=("-v"); fi
  if $strict; then args+=("--strict"); fi
  args+=("${paths[@]}")

  mypy "${args[@]}"

  ok "Type checking completed"
}

cmd_clean() {
  local all=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -All|--all) all=true; shift ;;
      *) shift ;;
    esac
  done

  section "Cleaning Artifacts"

  local artifacts_dir="${PROJECT_ROOT}/artifacts"
  if [[ -d "$artifacts_dir" ]]; then
    log "Removing artifacts directory..."
    rm -rf "$artifacts_dir"
  fi

  if $all; then
    if [[ -d "$BUILD_DIR" ]]; then
      log "Removing build directory..."
      rm -rf "$BUILD_DIR"
    fi
  fi

  # Clean Python artifacts
  find "$PROJECT_ROOT" -type d \( -name "__pycache__" -o -name ".pytest_cache" -o -name "*.egg-info" \) -exec rm -rf {} + 2>/dev/null || true
  find "$PROJECT_ROOT" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>/dev/null || true

  ok "Cleanup completed"
}

cmd_doctor() {
  section "Environment Health Check"

  _doctor_check() {
    local name="$1"
    local cmd="$2"
    if command -v "$cmd" >/dev/null 2>&1; then
      local ver=""
      case "$cmd" in
        python) ver="$(python --version 2>&1)" ;;
        cmake)  ver="$(cmake --version 2>&1 | head -1)" ;;
        gcc)    ver="$(gcc --version 2>&1 | head -1)" ;;
        g++)    ver="$(g++ --version 2>&1 | head -1)" ;;
        nvcc)   ver="$(nvcc --version 2>&1 | tail -1)" ;;
      esac
      if [[ -n "$ver" ]]; then
        echo -e "  ${CGRN}OK${C0}  ${name}: ${CDIM}${ver}${C0}"
      else
        echo -e "  ${CGRN}OK${C0}  ${name}"
      fi
    else
      echo -e "  ${CRED}MISSING${C0}  ${name} (${cmd})"
    fi
  }

  # Core tools
  _doctor_check "Conda" "conda"
  _doctor_check "CMake" "cmake"
  _doctor_check "Python" "python"
  _doctor_check "GCC" "gcc"
  _doctor_check "G++" "g++"
  _doctor_check "NVCC" "nvcc"

  # Python tools
  _doctor_check "Ruff" "ruff"
  _doctor_check "Pytest" "pytest"
  _doctor_check "Mypy" "mypy"

  # C++ tools
  _doctor_check "clang-format" "clang-format"
  _doctor_check "gcovr" "gcovr"

  # Research tools
  _doctor_check "Streamlit" "streamlit"
  _doctor_check "MLflow" "mlflow"

  # Conda env
  echo ""
  if conda env list 2>/dev/null | awk '{print $1}' | grep -qx "$CONDA_ENV_NAME"; then
    echo -e "  ${CGRN}OK${C0}  Conda env '${CONDA_ENV_NAME}' exists"
  else
    echo -e "  ${CRED}MISSING${C0}  Conda env '${CONDA_ENV_NAME}'"
  fi

  # Build dir
  if [[ -d "$BUILD_DIR" ]]; then
    echo -e "  ${CGRN}OK${C0}  Build directory exists"
  else
    echo -e "  ${CYEL}WARN${C0}  Build directory not found (run build)"
  fi

  # NVIDIA GPU
  if command -v nvidia-smi >/dev/null 2>&1; then
    local gpu_name
    gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits 2>/dev/null | head -1)" || gpu_name=""
    if [[ -n "$gpu_name" ]]; then
      echo -e "  ${CGRN}OK${C0}  GPU: ${CDIM}${gpu_name}${C0}"
    fi
  else
    echo -e "  ${CYEL}WARN${C0}  nvidia-smi not found"
  fi

  echo ""
}

cmd_dashboard() {
  local port=8501

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -Port|--port) port="$2"; shift 2 ;;
      *) shift ;;
    esac
  done

  section "Streamlit Dashboard"
  ensure_env_activated

  log "Launching on port $port..."
  log "URL: http://localhost:$port"
  streamlit run experiments/streamlit/app.py --server.port "$port"
}

cmd_profile() {
  ensure_env_activated

  local prof_helper="${PROJECT_ROOT}/scripts/helpers/prof_helper.py"
  if [[ ! -f "$prof_helper" ]]; then
    err "prof_helper.py not found at: $prof_helper"
    exit 1
  fi

  # Separate tool/profile args from Hydra args
  local hydra_args=()
  local tool=""
  local target=""
  local mode="quick"
  local kernel=""
  local duration=0
  local positional_count=0

  local all_args=("$@")
  local i=0
  while [[ $i -lt ${#all_args[@]} ]]; do
    local arg="${all_args[$i]}"

    # Hydra config patterns: key=value, +key=value, ++key=value, ~key, ~key=value
    if [[ "$arg" =~ ^[+~]{0,2}[a-zA-Z0-9_./-]+= ]] || [[ "$arg" =~ ^~[a-zA-Z0-9_./-]+$ ]]; then
      hydra_args+=("$arg")
    elif [[ "$arg" == "--mode" ]]; then
      i=$((i + 1)); mode="${all_args[$i]}"
    elif [[ "$arg" == "--kernel" || "$arg" == "-Kernel" ]]; then
      i=$((i + 1)); kernel="${all_args[$i]}"
    elif [[ "$arg" == "--duration" || "$arg" == "-Duration" ]]; then
      i=$((i + 1)); duration="${all_args[$i]}"
    elif [[ "$arg" == "-Full" || "$arg" == "--full" ]]; then
      mode="full"
    elif [[ "$arg" == "-NoOpen" || "$arg" == "--no-open" ]]; then
      : # no-op on Linux
    elif [[ "$arg" =~ ^- ]]; then
      : # skip unknown flags
    else
      if [[ $positional_count -eq 0 ]]; then
        tool="$arg"
      elif [[ $positional_count -eq 1 ]]; then
        target="$arg"
      fi
      positional_count=$((positional_count + 1))
    fi
    i=$((i + 1))
  done

  if [[ -z "$tool" || -z "$target" ]]; then
    echo "Usage: profile <tool> <target> [--mode quick|full] [hydra=configs]"
    echo "  Tools:   nsys, ncu"
    echo "  Targets: latency, throughput, accuracy, realtime, custom"
    echo "Example: profile nsys latency engine.nfft=8192"
    return 1
  fi

  # Build prof_helper command
  local args=()
  args+=("--mode" "$mode")
  if [[ -n "$kernel" ]]; then args+=("--kernel" "$kernel"); fi
  if [[ "$duration" -gt 0 ]]; then args+=("--duration" "$duration"); fi
  args+=("$tool" "$target")

  # Add profiling config for preset benchmarks
  if [[ "$target" =~ ^(latency|throughput|accuracy|realtime)$ ]]; then
    if [[ ${#hydra_args[@]} -eq 0 ]]; then
      local benchmark_config
      case "$target" in
        latency)    benchmark_config="profiling" ;;
        throughput) benchmark_config="profiling_throughput" ;;
        realtime)   benchmark_config="profiling_realtime" ;;
        accuracy)   benchmark_config="profiling_accuracy" ;;
      esac
      args+=("--" "experiment=profiling" "+benchmark=$benchmark_config")
    else
      args+=("--" "${hydra_args[@]}")
    fi
  fi

  log "Executing: $SIGX_PYTHON $prof_helper ${args[*]}"
  "$SIGX_PYTHON" "$prof_helper" "${args[@]}"
}

cmd_baseline() {
  ensure_env_activated

  local baseline_helper="${PROJECT_ROOT}/scripts/helpers/baseline_helper.py"
  if [[ ! -f "$baseline_helper" ]]; then
    err "Baseline helper not found: $baseline_helper"
    exit 1
  fi

  if [[ $# -eq 0 ]]; then
    err "Missing subcommand. Use: save, list, compare, delete, export"
    echo "Examples:"
    echo "  sigx baseline save pre-phase1 --phase 1"
    echo "  sigx baseline list"
    exit 1
  fi

  "$SIGX_PYTHON" "$baseline_helper" "$@"
}

cmd_diagrams() {
  local target="all"
  local format="svg"
  local layout=""
  local force=false
  local verbose=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --format) format="$2"; shift 2 ;;
      --layout) layout="$2"; shift 2 ;;
      --force) force=true; shift ;;
      --verbose) verbose=true; shift ;;
      -*) shift ;;
      *) target="$1"; shift ;;
    esac
  done

  section "Generating Diagrams"
  ensure_env_activated

  if ! command -v d2 >/dev/null 2>&1; then
    err "d2 not found. Install via: https://d2lang.com/"
    exit 1
  fi

  local src_dir="${PROJECT_ROOT}/docs/diagrams/src"
  local out_dir="${PROJECT_ROOT}/docs/diagrams/generated"

  if [[ ! -d "$src_dir" ]]; then
    err "Diagram source directory not found: $src_dir"
    exit 1
  fi

  mkdir -p "$out_dir"

  # Find all .d2 files, excluding common/
  local diagrams=()
  while IFS= read -r -d '' f; do
    local rel="${f#"$src_dir/"}"
    if [[ ! "$rel" =~ ^common/ ]]; then
      diagrams+=("$f")
    fi
  done < <(find "$src_dir" -name "*.d2" -print0)

  if [[ ${#diagrams[@]} -eq 0 ]]; then
    err "No diagram files found in: $src_dir"
    exit 1
  fi

  local success=0 skip=0 errors=0

  for src_file in "${diagrams[@]}"; do
    local basename
    basename="$(basename "$src_file" .d2)"

    # Filter by target
    if [[ "$target" != "all" ]]; then
      if [[ ! "$basename" =~ ^${target} ]]; then
        continue
      fi
    fi

    local out_file="${out_dir}/${basename}.${format}"

    # Smart regeneration
    if ! $force && [[ -f "$out_file" ]] && [[ "$out_file" -nt "$src_file" ]]; then
      if $verbose; then echo -e "  ${CDIM}Skipped: ${basename} (up to date)${C0}"; fi
      skip=$((skip + 1))
      continue
    fi

    local engine="${layout:-dagre}"
    log "Rendering: ${basename} -> ${format} (layout: ${engine})"

    if (cd "$src_dir" && d2 --layout "$engine" "$src_file" "$out_file" 2>/dev/null); then
      ok "  ${basename}.${format}"
      success=$((success + 1))
    else
      err "  Failed: ${basename}"
      errors=$((errors + 1))
    fi
  done

  ok "Diagrams: ${success} generated, ${skip} skipped, ${errors} errors"
  if [[ $errors -gt 0 ]]; then exit 1; fi
}

cmd_dev() {
  section "Development Workflow Quick Reference"
  ensure_env_activated

  # Dynamic experiment discovery
  local exp_dir="${PROJECT_ROOT}/experiments/conf/experiment"
  local experiments=()
  if [[ -d "$exp_dir" ]]; then
    while IFS= read -r -d '' f; do
      experiments+=("$(basename "$f" .yaml)")
    done < <(find "$exp_dir" -maxdepth 1 -name "*.yaml" -print0 | sort -z)
  fi

  echo -e "${CBLD}PYTHON SINGLE EXPERIMENTS${C0}"
  echo "  python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency"
  echo "  python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency"
  echo "  python benchmarks/run_throughput.py experiment=ionosphere_streaming_throughput +benchmark=throughput"
  echo "  python benchmarks/run_latency.py experiment=baseline_streaming_100k_latency +benchmark=latency"
  echo ""

  echo -e "${CBLD}PYTHON MULTI-RUN EXPERIMENTS${C0}"
  echo "  python benchmarks/run_latency.py --multirun experiment=full_parameter_grid_48k +benchmark=latency"
  echo "  python benchmarks/run_throughput.py --multirun experiment=full_parameter_grid_100k +benchmark=throughput"
  echo ""

  echo -e "${CBLD}SNAKEMAKE WORKFLOWS${C0}"
  echo "  snakemake --cores 4 --snakefile experiments/Snakefile"
  echo "  snakemake --dry-run --snakefile experiments/Snakefile"
  echo ""

  echo -e "${CBLD}ANALYSIS & VISUALIZATION${C0}"
  echo "  sigx dashboard                                      # Streamlit"
  echo "  mlflow ui --backend-store-uri file://./artifacts/mlruns  # Experiment tracking"
  echo ""

  echo -e "${CBLD}AVAILABLE EXPERIMENTS (${#experiments[@]})${C0}"
  if [[ ${#experiments[@]} -gt 0 ]]; then
    for exp in "${experiments[@]}"; do
      echo "  - $exp"
    done
  else
    echo "  No experiments found in experiments/conf/experiment/"
  fi
  echo ""

  echo "Tip: Use 'sigx help' for full CLI reference"
  echo "     See CLAUDE.md for detailed workflow documentation"
}

cmd_help() {
  cat <<'HELPEOF'
SIGTEKX DEVELOPMENT CLI (Linux/WSL)
Custom tooling for C++ builds, profiling, and development workflows

USAGE: ./scripts/cli.sh <command> [options]
   OR: sigx <command> [options]  (via init_bash.sh aliases)

===================================================================
CORE DEVELOPMENT COMMANDS
===================================================================

  setup                      Create/update conda environment & install package
  build [--preset <name>] [--clean] [--debug|--release] [--verbose]
                             Configure and build C++ project with CMake
  test [all|python|cpp] [--pattern <pat>] [--coverage] [--verbose]
                             Run Python and/or C++ test suites
  dashboard [--port <n>]     Launch Streamlit interactive dashboard
  coverage [--no-open]       Run C++ tests with code coverage report (gcovr)
  clean [--all]              Remove artifacts/ (use --all to also remove build/)
  doctor                     Check development environment health

===================================================================
CODE QUALITY
===================================================================

  format [paths] [--check]       Format C++ code with clang-format
  lint [all|python|cpp] [--fix]  Lint code with ruff (Python)
  typecheck [--strict]           Run mypy type checking on Python code

===================================================================
GPU PROFILING & PERFORMANCE
===================================================================

  profile <tool> <target> [--mode quick|full] [hydra=configs]
      Tools:   nsys (Nsight Systems), ncu (Nsight Compute)
      Targets: latency, throughput, accuracy, realtime, custom

  Quick Examples:
    sigx profile nsys latency
    sigx profile ncu latency engine.nfft=8192

===================================================================
BASELINE MANAGEMENT
===================================================================

  baseline save <name> [--phase <n>] [--message <msg>]
  baseline list [--phase <n>] [--verbose]
  baseline compare <name1> <name2>
  baseline delete <name> [--force]

===================================================================
DOCUMENTATION & DIAGRAMS
===================================================================

  diagrams [target] [--format svg|png|pdf] [--layout <engine>] [--force]

===================================================================
DEVELOPMENT WORKFLOWS
===================================================================

  dev [--verbose]      Show workflow quick reference with experiment list
  help                 Show this help

===================================================================
TYPICAL WORKFLOWS
===================================================================

  Development Setup:
    sigx setup && sigx build && sigx test

  Code Quality:
    sigx format && sigx lint && sigx typecheck

  Research & Benchmarking:
    python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency
    snakemake --cores 4 --snakefile experiments/Snakefile
    sigx dashboard

  C++ Development:
    sigxc bench                          # Quick validation (~10s)
    sigxc bench --preset latency --full  # Production benchmark
    sigxc profile nsys --stats           # Profile C++ directly
    sigxc help                           # Full sigxc documentation

===================================================================
ADDITIONAL RESOURCES
===================================================================

  CLAUDE.md                              Complete development & research guide
  docs/performance/gpu-clock-locking.md  GPU stability optimization
  For C++ benchmarking: sigxc help
  For Python profiling: sxp --help
HELPEOF
}

# --- Main Execution -----------------------------------------------------------
main() {
  cd "$PROJECT_ROOT"
  local cmd="${1:-help}"; shift || true
  case "$cmd" in
    help|-h|--help) cmd_help ;;
    setup)     cmd_setup "$@" ;;
    build)     cmd_build "$@" ;;
    test)      cmd_test "$@" ;;
    coverage)  cmd_coverage "$@" ;;
    lint)      cmd_lint "$@" ;;
    format)    cmd_format "$@" ;;
    typecheck) cmd_typecheck "$@" ;;
    clean)     cmd_clean "$@" ;;
    doctor)    cmd_doctor ;;
    dashboard) cmd_dashboard "$@" ;;
    profile)   cmd_profile "$@" ;;
    baseline)  cmd_baseline "$@" ;;
    diagrams)  cmd_diagrams "$@" ;;
    dev)       cmd_dev "$@" ;;
    *)
      err "Unknown command: $cmd"
      echo "Run './scripts/cli.sh help' for available commands"
      exit 1
      ;;
  esac
}

main "$@"
