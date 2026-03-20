#!/usr/bin/env bash
# ============================================================================
# sigtekx • GPU Clock Management for Stable Benchmarking (Linux/WSL)
# Provides lock/unlock/query/validate for GPU clocks.
# Requires: nvidia-smi, sudo (for lock/unlock)
# ============================================================================
set -Eeuo pipefail

# --- Configuration -----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOCK_DB="${SCRIPT_DIR}/gpu-clocks.json"

# --- Colors -------------------------------------------------------------------
C0='\033[0m'; CRED='\033[0;31m'; CGRN='\033[0;32m'; CYEL='\033[0;33m'; CCYN='\033[0;36m'; CDIM='\033[2m'

# --- Defaults -----------------------------------------------------------------
ACTION="query"
GPU_INDEX=0
USE_RECOMMENDED=true

# --- Parse args ---------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    lock|Lock)       ACTION="lock"; shift ;;
    unlock|Unlock)   ACTION="unlock"; shift ;;
    query|Query)     ACTION="query"; shift ;;
    validate|Validate) ACTION="validate"; shift ;;
    -Action|--action) ACTION="${2,,}"; shift 2 ;;  # lowercase
    -GpuIndex|--gpu-index) GPU_INDEX="$2"; shift 2 ;;
    --max-clocks)    USE_RECOMMENDED=false; shift ;;
    --recommended)   USE_RECOMMENDED=true; shift ;;
    *) shift ;;
  esac
done

# --- Helper functions ---------------------------------------------------------

check_nvidia_smi() {
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo -e "${CRED}ERROR: nvidia-smi not found. Install NVIDIA drivers.${C0}" >&2
    exit 1
  fi
}

check_sudo() {
  if ! sudo -n true 2>/dev/null; then
    echo -e "${CYEL}WARNING: sudo may require password for GPU clock operations.${C0}"
    echo -e "${CYEL}For passwordless operation, add to /etc/sudoers:${C0}"
    echo -e "${CDIM}  $(whoami) ALL=(ALL) NOPASSWD: /usr/bin/nvidia-smi${C0}"
  fi
}

get_gpu_info() {
  local idx="$1"
  local query="$2"
  nvidia-smi -i "$idx" --query-gpu="$query" --format=csv,noheader,nounits 2>/dev/null | tr -d '[:space:]'
}

get_clock_profile() {
  # Use Python to parse the JSON clock database
  local gpu_name="$1"

  if [[ ! -f "$CLOCK_DB" ]]; then
    echo ""
    return
  fi

  python3 -c "
import json, re, sys
with open('$CLOCK_DB') as f:
    db = json.load(f)
gpu_name = '''$gpu_name'''
for rule in db['matching_rules']['rules']:
    if re.search(rule['pattern'], gpu_name):
        profile = db['gpu_models'][rule['profile']]
        print(f\"{profile.get('recommended_graphics_clock_mhz', 0)},{profile.get('recommended_memory_clock_mhz', 0)},{profile.get('max_graphics_clock_mhz', 0)},{profile.get('max_memory_clock_mhz', 0)},{rule['profile']}\")
        sys.exit(0)
print('')
" 2>/dev/null || echo ""
}

# --- Actions ------------------------------------------------------------------

do_query() {
  check_nvidia_smi

  local gpu_name graphics_clock memory_clock max_graphics max_memory persistence
  gpu_name="$(get_gpu_info "$GPU_INDEX" "name")"
  graphics_clock="$(get_gpu_info "$GPU_INDEX" "clocks.current.graphics")"
  memory_clock="$(get_gpu_info "$GPU_INDEX" "clocks.current.memory")"
  max_graphics="$(get_gpu_info "$GPU_INDEX" "clocks.max.graphics")"
  max_memory="$(get_gpu_info "$GPU_INDEX" "clocks.max.memory")"
  persistence="$(get_gpu_info "$GPU_INDEX" "persistence_mode")"

  echo ""
  echo -e "${CCYN}GPU Clock Information${C0}"
  echo "================================================"
  echo ""
  echo "GPU Index       : $GPU_INDEX"
  echo "GPU Name        : $gpu_name"
  echo "Persistence Mode: $persistence"
  echo ""
  echo -e "${CYEL}Current Clocks:${C0}"
  echo "  Graphics      : ${graphics_clock} MHz"
  echo "  Memory        : ${memory_clock} MHz"
  echo ""
  echo -e "${CYEL}Hardware Max:${C0}"
  echo "  Graphics      : ${max_graphics} MHz"
  echo "  Memory        : ${max_memory} MHz"

  # Look up profile
  local profile_info
  profile_info="$(get_clock_profile "$gpu_name")"
  if [[ -n "$profile_info" ]]; then
    IFS=',' read -r rec_g rec_m max_g max_m profile_name <<< "$profile_info"
    echo ""
    echo -e "${CGRN}Profile         : $profile_name${C0}"
    echo ""
    echo -e "${CYEL}Recommended (for stability):${C0}"
    echo "  Graphics      : ${rec_g} MHz"
    echo "  Memory        : ${rec_m} MHz"
    echo ""
    echo -e "${CYEL}Max (for performance):${C0}"
    echo "  Graphics      : ${max_g} MHz"
    echo "  Memory        : ${max_m} MHz"
  else
    echo ""
    echo -e "${CRED}Profile         : [NOT FOUND]${C0}"
    echo "No clock profile for this GPU. You can still lock to hardware max."
  fi
  echo ""
  echo "================================================"
  echo ""
}

do_lock() {
  check_nvidia_smi
  check_sudo

  echo -e "${CCYN}Locking GPU $GPU_INDEX clocks...${C0}"

  local gpu_name
  gpu_name="$(get_gpu_info "$GPU_INDEX" "name")"
  echo "   GPU: $gpu_name"

  local target_g target_m
  local profile_info
  profile_info="$(get_clock_profile "$gpu_name")"

  if [[ -n "$profile_info" ]]; then
    IFS=',' read -r rec_g rec_m max_g max_m profile_name <<< "$profile_info"
    if $USE_RECOMMENDED; then
      target_g="$rec_g"
      target_m="$rec_m"
      echo "   Profile: $profile_name (recommended)"
    else
      target_g="$max_g"
      target_m="$max_m"
      echo "   Profile: $profile_name (max)"
    fi
  else
    echo -e "${CYEL}   No profile found. Using hardware max clocks.${C0}"
    target_g="$(get_gpu_info "$GPU_INDEX" "clocks.max.graphics")"
    target_m="$(get_gpu_info "$GPU_INDEX" "clocks.max.memory")"
  fi

  echo "   Target: Graphics=${target_g} MHz, Memory=${target_m} MHz"

  echo "   [1/4] Enabling persistence mode..."
  sudo nvidia-smi -i "$GPU_INDEX" -pm 1

  echo "   [2/4] Locking graphics clock to ${target_g} MHz..."
  sudo nvidia-smi -i "$GPU_INDEX" -lgc "$target_g"

  echo "   [3/4] Locking memory clock to ${target_m} MHz..."
  sudo nvidia-smi -i "$GPU_INDEX" -lmc "$target_m"

  echo "   [4/4] Validating clock lock..."
  sleep 1

  local new_g new_m
  new_g="$(get_gpu_info "$GPU_INDEX" "clocks.current.graphics")"
  new_m="$(get_gpu_info "$GPU_INDEX" "clocks.current.memory")"
  echo "   Current: Graphics=${new_g} MHz, Memory=${new_m} MHz"

  echo -e "${CGRN}GPU clocks locked successfully${C0}"
}

do_unlock() {
  check_nvidia_smi
  check_sudo

  echo -e "${CCYN}Unlocking GPU $GPU_INDEX clocks...${C0}"

  echo "   [1/3] Resetting graphics clock..."
  sudo nvidia-smi -i "$GPU_INDEX" -rgc 2>/dev/null || true

  echo "   [2/3] Resetting memory clock..."
  sudo nvidia-smi -i "$GPU_INDEX" -rmc 2>/dev/null || true

  echo "   [3/3] Disabling persistence mode..."
  sudo nvidia-smi -i "$GPU_INDEX" -pm 0 2>/dev/null || true

  echo -e "${CGRN}GPU clocks unlocked successfully${C0}"
}

do_validate() {
  echo -e "${CCYN}Validating GPU clock management prerequisites...${C0}"
  echo ""

  local all_good=true

  # Check sudo
  if sudo -n true 2>/dev/null; then
    echo -e "  ${CGRN}OK${C0}  sudo (passwordless)"
  else
    echo -e "  ${CYEL}WARN${C0}  sudo requires password (lock/unlock will prompt)"
    all_good=false
  fi

  # Check nvidia-smi
  if command -v nvidia-smi >/dev/null 2>&1; then
    echo -e "  ${CGRN}OK${C0}  nvidia-smi available"
  else
    echo -e "  ${CRED}FAIL${C0}  nvidia-smi not found"
    all_good=false
  fi

  # Check database
  if [[ -f "$CLOCK_DB" ]]; then
    echo -e "  ${CGRN}OK${C0}  GPU clock database found"
  else
    echo -e "  ${CRED}FAIL${C0}  GPU clock database missing: $CLOCK_DB"
    all_good=false
  fi

  echo ""
  if $all_good; then
    echo -e "  ${CGRN}All prerequisites met${C0}"
    echo ""
    do_query
  else
    echo -e "  ${CRED}Some prerequisites not met${C0}"
    exit 1
  fi
}

# --- Main ---------------------------------------------------------------------
case "$ACTION" in
  lock)     do_lock ;;
  unlock)   do_unlock ;;
  query)    do_query ;;
  validate) do_validate ;;
  *)
    echo "Usage: gpu-manager.sh <lock|unlock|query|validate> [options]"
    echo ""
    echo "Options:"
    echo "  --gpu-index <N>    GPU index (default: 0)"
    echo "  --max-clocks       Use max clocks instead of recommended"
    echo "  --recommended      Use recommended clocks (default)"
    exit 1
    ;;
esac
