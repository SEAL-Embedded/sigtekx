#!/usr/bin/env bash
# ============================================================================
# sigtekx • C++ Benchmarking & Profiling CLI (Linux/WSL)
# Dedicated tool for C++ kernel development and profiling iteration
# ============================================================================
set -Eeuo pipefail

# --- Configuration & Paths ---------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build"
BUILD_PRESET="${BUILD_PRESET:-linux-rel}"
PROFILING_DIR="${PROJECT_ROOT}/artifacts/profiling"
BENCHMARK_EXE="${BUILD_DIR}/${BUILD_PRESET}/sigtekx_benchmark"
BASELINE_CLI="${BUILD_DIR}/${BUILD_PRESET}/sigtekx_baseline_cli"

# --- Colors -------------------------------------------------------------------
C0='\033[0m'; CRED='\033[0;31m'; CGRN='\033[0;32m'; CYEL='\033[0;33m'; CCYN='\033[0;36m'; CDIM='\033[2m'
log()  { echo -e "${CCYN}[INFO]${C0}  $*"; }
err()  { echo -e "${CRED}[ERR ]${C0}  $*" >&2; }
ok()   { echo -e "${CGRN}[ OK ]${C0}  $*"; }

# --- Commands -----------------------------------------------------------------

cmd_bench() {
  if [[ ! -f "$BENCHMARK_EXE" ]]; then
    err "C++ benchmark not found at: $BENCHMARK_EXE"
    echo "Run 'sigx build' to build the benchmark executable."
    exit 1
  fi

  # Parse arguments
  local lock_clocks=false
  local gpu_index=0
  local use_recommended=true
  local filtered_args=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --lock-clocks) lock_clocks=true; shift ;;
      --gpu-index)   gpu_index="$2"; shift 2 ;;
      --max-clocks)  use_recommended=false; shift ;;
      *)             filtered_args+=("$1"); shift ;;
    esac
  done

  if $lock_clocks; then
    local gpu_manager="${SCRIPT_DIR}/gpu-manager.sh"
    if [[ ! -f "$gpu_manager" ]]; then
      err "GPU manager not found: $gpu_manager"
      exit 1
    fi

    echo ""
    log "Benchmarking with locked GPU clocks"
    echo ""

    # Lock clocks
    bash "$gpu_manager" lock --gpu-index "$gpu_index" $(if ! $use_recommended; then echo "--max-clocks"; fi)
    echo ""

    # Auto-unlock on exit (trap)
    trap 'echo ""; bash "'"$gpu_manager"'" unlock --gpu-index '"$gpu_index"'' EXIT

    # Run benchmark
    log "Running C++ benchmark..."
    if [[ ${#filtered_args[@]} -gt 0 ]]; then
      "$BENCHMARK_EXE" "${filtered_args[@]}"
    else
      "$BENCHMARK_EXE"
    fi
    local exit_code=$?

    # Trap will handle unlock
    if [[ $exit_code -eq 0 ]]; then
      ok "Benchmark completed successfully"
    else
      err "Benchmark failed with exit code $exit_code"
      exit $exit_code
    fi
  else
    # Normal benchmark path
    log "Running C++ benchmark..."
    if [[ ${#filtered_args[@]} -gt 0 ]]; then
      "$BENCHMARK_EXE" "${filtered_args[@]}"
    else
      "$BENCHMARK_EXE"
    fi

    if [[ $? -eq 0 ]]; then
      ok "Benchmark completed successfully"
    else
      err "Benchmark failed with exit code $?"
      exit $?
    fi
  fi
}

cmd_profile_nsys() {
  if [[ ! -f "$BENCHMARK_EXE" ]]; then
    err "C++ benchmark not found at: $BENCHMARK_EXE"
    echo "Run 'sigx build' to build the benchmark executable."
    exit 1
  fi

  mkdir -p "$PROFILING_DIR"

  # Parse arguments
  local mode="profile"
  local output_path="${PROFILING_DIR}/cpp_dev"
  local stats=false
  local nsys_args=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --mode)   mode="$2"; shift 2 ;;
      --output) output_path="$2"; shift 2 ;;
      --stats)  stats=true; shift ;;
      *)        nsys_args+=("$1"); shift ;;
    esac
  done

  log "Profiling with Nsight Systems (mode: $mode)..."

  local nsys_cmd=("profile")
  if $stats; then nsys_cmd+=("--stats=true"); fi
  nsys_cmd+=("--force-overwrite" "true")
  nsys_cmd+=("-o" "$output_path")
  nsys_cmd+=("${nsys_args[@]}")
  nsys_cmd+=("$BENCHMARK_EXE" "--${mode}" "--safe-print")

  echo -e "${CDIM}Command: nsys ${nsys_cmd[*]}${C0}"
  nsys "${nsys_cmd[@]}"

  if [[ $? -eq 0 ]]; then
    ok "Profiling completed: ${output_path}.nsys-rep"
    echo "View with: nsys-ui ${output_path}.nsys-rep"
  else
    err "Profiling failed"
    exit 1
  fi
}

cmd_profile_ncu() {
  if [[ ! -f "$BENCHMARK_EXE" ]]; then
    err "C++ benchmark not found at: $BENCHMARK_EXE"
    echo "Run 'sigx build' to build the benchmark executable."
    exit 1
  fi

  mkdir -p "$PROFILING_DIR"

  # Parse arguments
  local mode="profile"
  local output_path="${PROFILING_DIR}/cpp_dev_ncu"
  local metric_set="default"
  local ncu_args=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --mode)   mode="$2"; shift 2 ;;
      --output) output_path="$2"; shift 2 ;;
      --set)    metric_set="$2"; shift 2 ;;
      *)        ncu_args+=("$1"); shift ;;
    esac
  done

  log "Profiling with Nsight Compute (mode: $mode, set: $metric_set)..."
  echo -e "${CYEL}This may take 5-15 minutes depending on metric set...${C0}"

  local ncu_cmd=("--set" "$metric_set" "-o" "$output_path")
  ncu_cmd+=("${ncu_args[@]}")
  ncu_cmd+=("$BENCHMARK_EXE" "--${mode}" "--safe-print")

  echo -e "${CDIM}Command: ncu ${ncu_cmd[*]}${C0}"
  ncu "${ncu_cmd[@]}"

  if [[ $? -eq 0 ]]; then
    ok "Profiling completed: ${output_path}.ncu-rep"
    echo "View with: ncu-ui ${output_path}.ncu-rep"
  else
    err "Profiling failed"
    exit 1
  fi
}

cmd_baseline() {
  if [[ ! -f "$BASELINE_CLI" ]]; then
    err "C++ baseline CLI not found at: $BASELINE_CLI"
    echo "Run 'sigx build' to build the baseline CLI executable."
    exit 1
  fi

  "$BASELINE_CLI" "$@"
}

cmd_clean() {
  log "Cleaning profiling artifacts..."

  if [[ -d "$PROFILING_DIR" ]]; then
    local count
    count="$(find "$PROFILING_DIR" -type f | wc -l)"
    if [[ "$count" -eq 0 ]]; then
      echo "No profiling artifacts to clean."
      return
    fi
    rm -rf "${PROFILING_DIR:?}/"*
    ok "Removed $count profiling artifact(s)"
  else
    echo "Profiling directory does not exist."
  fi
}

cmd_help() {
  cat <<'HELPEOF'
SIGTEKX C++ Benchmarking & Profiling CLI (Linux/WSL)
Dedicated tool for C++ kernel development and profiling iteration

USAGE: sigxc <command> [options]
   OR: ./scripts/cli-cpp.sh <command> [options]

COMMANDS:
  bench [options]               Run C++ benchmark with presets
  baseline <subcommand>         Manage C++ baselines (save, list, compare, delete)
  profile nsys [options]        Profile with Nsight Systems
  profile ncu [options]         Profile with Nsight Compute
  clean                         Clean profiling artifacts
  help                          Show this help

===================================================================

BENCHMARK PRESETS:
  dev (default)   Quick validation (20 iter, ~10s)
  latency         Latency measurement (5000 iter, ~2min)
  throughput      Throughput measurement (10s duration)
  realtime        Real-time streaming (10s duration)
  accuracy        Accuracy validation (10 iter, 8 signals)

RUN MODES:
  --quick         Fast validation (reduced iterations/duration)
  --profile       Profile-ready (moderate iterations/duration)
  --full          Production equivalent (default)

IONOSPHERE VARIANTS:
  --iono          Standard ionosphere (48kHz, 4096/16384 NFFT, 0.75 overlap)
  --ionox         Extreme ionosphere (48kHz, 8192/32768 NFFT, 0.9/0.9375 overlap)

GPU CLOCK CONTROL:
  --lock-clocks   Lock GPU clocks for stable benchmarks (requires sudo)
  --gpu-index <N> Select GPU to lock (default: 0, use with --lock-clocks)
  --max-clocks    Use max clocks instead of recommended (use with --lock-clocks)

BENCHMARK EXAMPLES:
  sigxc bench                                    # Quick dev validation (~10s)
  sigxc bench --preset latency --full            # Production latency benchmark
  sigxc bench --preset realtime --iono --profile # Ionosphere realtime profiling
  sigxc bench --preset throughput --ionox --full  # Extreme ionosphere throughput
  sigxc bench --preset latency --full --lock-clocks  # Stable benchmarking

===================================================================

NSYS PROFILING:
  sigxc profile nsys [options]

  Options:
    --mode <quick|profile|full>  Benchmark mode (default: profile)
    --output <path>              Output file path
    --stats                      Generate statistics
    [nsys flags]                 Any other nsys flags

  Examples:
    sigxc profile nsys                    # Basic profile
    sigxc profile nsys --stats            # With statistics
    sigxc profile nsys --mode quick       # Quick profile

===================================================================

NCU PROFILING:
  sigxc profile ncu [options]

  Options:
    --mode <quick|profile|full>  Benchmark mode (default: profile)
    --output <path>              Output file path
    --set <metric-set>           Metric set (default, roofline, full)
    --kernel-name <pattern>      Filter specific kernels
    [ncu flags]                  Any other ncu flags

  Examples:
    sigxc profile ncu                           # Basic profile
    sigxc profile ncu --set roofline            # Roofline analysis
    sigxc profile ncu --kernel-name "fft_kernel" # Specific kernel

===================================================================

BASELINE MANAGEMENT:
  sigxc baseline save <name> [--message <msg>]
  sigxc baseline list [--preset <name>]
  sigxc baseline compare <name1> <name2>
  sigxc baseline delete <name> [--force]

===================================================================

TYPICAL WORKFLOW:
  1. sigxc bench                           # Quick dev validation (~10s)
  2. sigxc bench --preset latency --profile # Profile-ready run (~30s)
  3. sigxc profile nsys --stats            # Profile with nsys (~1min)
  4. sigxc profile ncu --kernel-name "fft" # Analyze kernel (~10min)
  5. sigxc clean                           # Clean artifacts

FOR PRODUCTION PROFILING:
  Use 'sxp nsys latency' for end-to-end Python workflow validation.
  sigxc is for C++ development iteration only.

ARTIFACTS LOCATION:
  All profiling results: artifacts/profiling/
  Clean with: sigxc clean
HELPEOF
}

# --- Main Execution -----------------------------------------------------------
cd "$PROJECT_ROOT"

CMD="${1:-help}"
shift || true

case "$CMD" in
  bench)    cmd_bench "$@" ;;
  profile)
    if [[ $# -eq 0 ]]; then
      err "Usage: sigxc profile <nsys|ncu> [options]"
      echo "Run 'sigxc help' for examples"
      exit 1
    fi
    tool="${1,,}"  # lowercase
    shift
    case "$tool" in
      nsys) cmd_profile_nsys "$@" ;;
      ncu)  cmd_profile_ncu "$@" ;;
      *)    err "Unknown profiling tool: $tool. Use 'nsys' or 'ncu'."; exit 1 ;;
    esac
    ;;
  baseline) cmd_baseline "$@" ;;
  clean)    cmd_clean ;;
  help|-h|--help) cmd_help ;;
  *)
    err "Unknown command: $CMD"
    echo "Run 'sigxc help' for available commands"
    exit 1
    ;;
esac
