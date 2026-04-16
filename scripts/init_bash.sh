#!/usr/bin/env bash
# ============================================================================
# sigtekx • Bash Dev Shell Initialization
# Source this file to configure your development session:
#   source scripts/init_bash.sh
#
# Options:
#   --env <name>     Conda environment name (default: sigtekx)
#   --no-conda       Skip conda activation
#   --quiet          Suppress informational output
#   --interactive    Prompt to create env if missing
# ============================================================================

# --- Parse options (safe for sourcing) ----------------------------------------
_SIGX_ENV_NAME="sigtekx"
_SIGX_NO_CONDA=false
_SIGX_QUIET=false
_SIGX_INTERACTIVE=false

for _arg in "$@"; do
  case "$_arg" in
    --env)         _SIGX_ENV_NAME="$2"; shift ;;
    --no-conda)    _SIGX_NO_CONDA=true ;;
    --quiet)       _SIGX_QUIET=true ;;
    --interactive) _SIGX_INTERACTIVE=true ;;
  esac
done

# --- Helper functions (local to init) -----------------------------------------
_sigx_info()  { if ! $_SIGX_QUIET; then echo -e "\033[0;36m$*\033[0m"; fi; }
_sigx_ok()    { if ! $_SIGX_QUIET; then echo -e "\033[0;32m$*\033[0m"; fi; }
_sigx_warn()  { if ! $_SIGX_QUIET; then echo -e "\033[0;33mWARNING: $*\033[0m"; fi; }

# --- Resolve repo root --------------------------------------------------------
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  _SIGX_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  SIGX_ROOT="$(cd "$_SIGX_SCRIPT_DIR/.." && pwd)"
else
  SIGX_ROOT="$(pwd)"
fi
export SIGX_ROOT
export SIGX_CLI="${SIGX_ROOT}/scripts/cli.sh"
export SIGXC_CLI="${SIGX_ROOT}/scripts/cli-cpp.sh"

# --- Conda detection & activation ---------------------------------------------
if ! $_SIGX_NO_CONDA; then
  # Find and source conda.sh
  _conda_found=false

  if command -v conda >/dev/null 2>&1; then
    # conda already on PATH
    _conda_base="$(conda info --base 2>/dev/null)"
    if [[ -f "${_conda_base}/etc/profile.d/conda.sh" ]]; then
      # shellcheck disable=SC1091
      source "${_conda_base}/etc/profile.d/conda.sh"
      _conda_found=true
    fi
  fi

  if ! $_conda_found; then
    for _conda_dir in "$HOME/miniconda3" "$HOME/mambaforge" "$HOME/anaconda3" "/opt/conda"; do
      if [[ -f "${_conda_dir}/etc/profile.d/conda.sh" ]]; then
        # shellcheck disable=SC1091
        source "${_conda_dir}/etc/profile.d/conda.sh"
        _conda_found=true
        _sigx_info "Found conda at: ${_conda_dir}"
        break
      fi
    done
  fi

  if ! $_conda_found; then
    _sigx_warn "conda not found. Install Miniconda or Mambaforge."
  else
    # Ghost environment detection
    if [[ "${CONDA_DEFAULT_ENV:-}" == "$_SIGX_ENV_NAME" ]]; then
      if ! conda env list 2>/dev/null | awk '{print $1}' | grep -qx "$_SIGX_ENV_NAME"; then
        _sigx_warn "Detected ghost environment '$_SIGX_ENV_NAME' - conda doesn't recognize it."
        _sigx_warn "Run: conda deactivate && sigx setup"
      fi
    fi

    # Activate environment
    if [[ "${CONDA_DEFAULT_ENV:-}" != "$_SIGX_ENV_NAME" ]]; then
      if conda env list 2>/dev/null | awk '{print $1}' | grep -qx "$_SIGX_ENV_NAME"; then
        conda activate "$_SIGX_ENV_NAME"
        _sigx_ok "Activated conda env: $_SIGX_ENV_NAME"
      else
        if $_SIGX_INTERACTIVE; then
          echo ""
          echo "Conda environment '$_SIGX_ENV_NAME' does not exist."
          read -r -p "Initialize it now? (Y/n) " _response
          if [[ -z "$_response" || "$_response" =~ ^[Yy] ]]; then
            _sigx_info "Running environment setup..."
            bash "${SIGX_CLI}" setup
            conda activate "$_SIGX_ENV_NAME"
          else
            _sigx_info "Skipping. Use 'sigx setup' manually when ready."
          fi
        else
          _sigx_warn "Environment '$_SIGX_ENV_NAME' not found. Run: sigx setup"
        fi
      fi
    else
      _sigx_info "Conda env '$_SIGX_ENV_NAME' already active."
    fi
  fi
fi

# --- Environment variables ----------------------------------------------------
export SIGX_LOG_COLOR="${SIGX_LOG_COLOR:-1}"

# --- Shell functions (session-scoped) -----------------------------------------

sigx() {
  if [[ ! -f "$SIGX_CLI" ]]; then
    echo "ERROR: cli.sh not found at $SIGX_CLI" >&2
    return 1
  fi

  local valid_commands="setup build test coverage lint format clean doctor help profile typecheck diagrams dev dataset dashboard"

  if [[ $# -gt 0 ]]; then
    local cmd="$1"
    if ! echo "$valid_commands" | tr ' ' '\n' | grep -qx "$cmd"; then
      echo "Command '$cmd' not available. Use 'sigx help' for available commands."
      echo "For research workflows, use direct tools:"
      echo "  python benchmarks/run_latency.py experiment=baseline +benchmark=latency"
      echo "  snakemake --cores 4 --snakefile experiments/Snakefile"
      echo "For C++ benchmarking/profiling:"
      echo "  sigxc bench"
      echo "  sigxc profile nsys --stats"
      return 1
    fi
  fi

  bash "$SIGX_CLI" "$@"
}

sigxc() {
  if [[ ! -f "$SIGXC_CLI" ]]; then
    echo "ERROR: cli-cpp.sh not found at $SIGXC_CLI" >&2
    return 1
  fi

  if [[ $# -eq 0 ]]; then
    bash "$SIGXC_CLI" help
    return
  fi

  bash "$SIGXC_CLI" "$@"
}

# Essential CLI shortcuts
sxb()  { sigx build "$@"; }
sxt()  { sigx test "$@"; }
sxl()  { sigx lint "$@"; }
sxf()  { sigx format "$@"; }
sxc()  { sigx clean "$@"; }
sxh()  { sigx help; }
sxtp() { sxt python "$@"; }
sxtc() { sxt cpp "$@"; }
sxpc() { sigxc profile "$@"; }

# Dashboard shortcut
sxdash() { sigx dashboard "$@"; }

# Dev workflow shortcut
sxd() { sigx dev "$@"; }

# Stage timing shortcuts
sxstb() { python scripts/helpers/stage_timing_helper.py batch "$@"; }
sxsts() { python scripts/helpers/stage_timing_helper.py stream "$@"; }
sxst()  { python scripts/helpers/stage_timing_helper.py both "$@"; }

# Profiling shortcut with Hydra arg classification
sxp() {
  if [[ $# -eq 0 ]]; then
    echo "Usage: sxp <tool> <target> [--flags] [hydra=configs]"
    echo "Example: sxp nsys latency --mode full engine.nfft=8192"
    return 1
  fi

  # Pattern-based argument classification
  local tool_args=()
  local hydra_args=()

  while [[ $# -gt 0 ]]; do
    local arg="$1"
    shift

    # Hydra config patterns: key=value, +key=value, ++key=value, ~key, ~key=value
    if [[ "$arg" =~ ^[+~]{0,2}[a-zA-Z0-9_./-]+= ]] || [[ "$arg" =~ ^~[a-zA-Z0-9_./-]+$ ]]; then
      hydra_args+=("$arg")
    elif [[ "$arg" =~ ^--[a-zA-Z] ]]; then
      tool_args+=("$arg")
      # Check if next arg is a value (not another flag or Hydra config)
      if [[ $# -gt 0 ]]; then
        local next="$1"
        if [[ ! "$next" =~ ^-- ]] && [[ ! "$next" =~ ^[+~]{0,2}[a-zA-Z0-9_./-]+= ]]; then
          tool_args+=("$next")
          shift
        fi
      fi
    else
      # Positional argument (tool name, target name)
      tool_args+=("$arg")
    fi
  done

  # Build command
  local sigx_args=("profile" "${tool_args[@]}")
  if [[ ${#hydra_args[@]} -gt 0 ]]; then
    sigx_args+=("${hydra_args[@]}")
  fi

  sigx "${sigx_args[@]}"
}

# Reload sigx functions
sxreload() {
  _sigx_info "Reloading sigx functions..."
  # shellcheck disable=SC1091
  source "${SIGX_ROOT}/scripts/init_bash.sh" --quiet
  _sigx_ok "Functions reloaded. Try: sxp nsys latency"
}

# --- Bash completion ----------------------------------------------------------
_sigx_complete() {
  local cur="${COMP_WORDS[COMP_CWORD]}"
  local prev="${COMP_WORDS[COMP_CWORD-1]}"

  local commands="setup build test coverage lint format clean doctor help profile typecheck diagrams dev dataset dashboard"
  local targets="python cpp all py sys nsys ncu latency throughput accuracy realtime --clean --verbose --debug --release --fix --check --coverage --pattern --strict --all --force --format --layout --port --no-open --mode"

  if [[ $COMP_CWORD -eq 1 ]] || { [[ $COMP_CWORD -eq 2 ]] && [[ "${COMP_WORDS[0]}" != "sigx" ]]; }; then
    COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
  else
    COMPREPLY=( $(compgen -W "$targets $commands" -- "$cur") )
  fi
}

_sigxc_complete() {
  local cur="${COMP_WORDS[COMP_CWORD]}"
  local commands="bench profile dataset clean help"
  local targets="nsys ncu --mode --output --stats --trace --set --kernel-name --preset --iono --ionox --full --quick --profile --lock-clocks --gpu-index --max-clocks --save-dataset save list compare delete"

  if [[ $COMP_CWORD -eq 1 ]] || { [[ $COMP_CWORD -eq 2 ]] && [[ "${COMP_WORDS[0]}" != "sigxc" ]]; }; then
    COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
  else
    COMPREPLY=( $(compgen -W "$targets $commands" -- "$cur") )
  fi
}

complete -F _sigx_complete sigx sxb sxt sxl sxf sxc sxtp sxtc sxh sxp sxd sxdash
complete -F _sigxc_complete sigxc sxpc

# --- Prompt -------------------------------------------------------------------
if ! $_SIGX_QUIET; then
  # Set a session-aware prompt
  _sigx_prompt() {
    local env_prefix=""
    if [[ -n "${CONDA_DEFAULT_ENV:-}" ]]; then
      env_prefix="(${CONDA_DEFAULT_ENV}) "
    fi
    PS1="${env_prefix}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ "
  }
  _sigx_prompt
fi

# --- Change to repo root ------------------------------------------------------
if [[ -d "$SIGX_ROOT" ]]; then
  cd "$SIGX_ROOT" || true
  if ! $_SIGX_QUIET; then
    _sigx_info "Changed directory to $SIGX_ROOT"
  fi
fi

# --- Session info -------------------------------------------------------------
if ! $_SIGX_QUIET; then
  echo ""
  _sigx_ok "Dev shell ready (bash ${BASH_VERSION})"

  if command -v gcc >/dev/null 2>&1; then
    echo -e "\033[2mgcc    : $(gcc --version 2>&1 | head -1)\033[0m"
  fi
  if command -v nvcc >/dev/null 2>&1; then
    echo -e "\033[2mnvcc   : $(nvcc --version 2>&1 | tail -1)\033[0m"
  fi
  if [[ -n "${CONDA_DEFAULT_ENV:-}" ]]; then
    echo -e "\033[2menv    : ${CONDA_DEFAULT_ENV}\033[0m"
  fi
  echo ""
fi

# --- Cleanup temp variables ---------------------------------------------------
unset _SIGX_ENV_NAME _SIGX_NO_CONDA _SIGX_QUIET _SIGX_INTERACTIVE
unset _SIGX_SCRIPT_DIR _conda_found _conda_base _conda_dir _arg _response
