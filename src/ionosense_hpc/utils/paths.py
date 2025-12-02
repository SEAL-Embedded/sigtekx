"""
Centralized paths for outputs and artifacts.

Policy:
- Default derived artifacts under <repo>/artifacts so routine cleans preserve results.
- Allow overrides via env vars for research workflows and CI.
"""
from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import shutil
from typing import Iterable


def _repo_root() -> Path:

    """Find project root by searching for pyproject.toml"""

    path = Path(__file__).resolve()

    for parent in [path] + list(path.parents):
        if (parent / "pyproject.toml").exists():
            return parent

    raise FileNotFoundError(
        f"Project root not found: no project.toml in {path} or any parent directory. "
        f"Set IONO_OUTPUT_ROOT environment  variable to override"
    )

def _sanitize_component(name: str) -> str:
    """Return a filesystem safe name limited to simple characters."""
    cleaned = ''.join(ch if (ch.isalnum() or ch in ('-', '_')) else '-' for ch in name.strip())
    cleaned = cleaned.strip('-_')
    return cleaned or 'benchmark'


def _ensure(path: Path) -> Path:
    """Create path if missing and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_benchmark_name(name: str) -> str:
    """Return a sanitized benchmark name for filesystem usage."""
    return _sanitize_component(name)


ARTIFACTS_ROOT_NAME = "artifacts"


def get_artifacts_root() -> Path:
    """Root directory for long-lived artifacts."""
    env_root = os.environ.get("IONO_OUTPUT_ROOT")
    if env_root:
        return _ensure(Path(env_root))

    root = _repo_root()
    return _ensure(root / ARTIFACTS_ROOT_NAME)


def get_output_root() -> Path:
    """Alias for artifact root for backwards compatibility."""
    return get_artifacts_root()

def _get_path_with_env_override(env_var: str, default_subdir: str) -> Path:
    """Get path with environment variable override report.
    
    Args: Environment variable name to check
    default_subdir: Subdirectory name under output root if env var not set
    
    Returns:
        Path object - either from env var or default location
    """
    env_path = os.environ.get(env_var)
    if env_path:
        return Path(env_path)
    return get_output_root() / default_subdir

def get_benchmarks_root() -> Path:
    """Root for benchmark result directories."""
    return _get_path_with_env_override("IONO_BENCH_DIR", "benchmark_results")


def get_benchmark_run_dir(name: str) -> Path:
    """Directory for a specific benchmark name (sanitized)."""
    safe = normalize_benchmark_name(name)
    return _ensure(get_benchmarks_root() / safe)


def get_benchmark_result_path(
    name: str,
    *,
    timestamp: datetime | None = None,
    suffix: str = "json",
) -> Path:
    """Standardized path for benchmark outputs."""
    ts = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
    safe = normalize_benchmark_name(name)
    ext = suffix.lstrip('.')
    run_dir = get_benchmark_run_dir(safe)
    return run_dir / f"{safe}_{ts}.{ext}"


def get_experiments_root() -> Path:
    """Root for research workflow experiment directories."""
    return _get_path_with_env_override("IONO_EXPERIMENTS_DIR", "experiments")


def get_reports_root() -> Path:
    """Root for top-level reports (test, lint, etc.)."""
    return _get_path_with_env_override("IONO_REPORTS_DIR", "reports")


# =============================================================================
# Nsight tool discovery
# =============================================================================

_NSIGHT_INSTALL_PATTERNS = {
    "nsys": ("Nsight Systems*", "nsight-systems*"),
    "ncu": ("Nsight Compute*", "nsight-compute*"),
}

_NSIGHT_ENV_OVERRIDES = {
    "cli": {"nsys": "IONO_NSYS_BIN", "ncu": "IONO_NCU_BIN"},
    "gui": {"nsys": "IONO_NSYS_GUI", "ncu": "IONO_NCU_GUI"},
}

_NSIGHT_RELATIVE_PATHS = {
    "nsys": {
        "cli": (
            Path("nsys"),
            Path("nsys.exe"),
            Path("nsys.bat"),
            Path("bin") / "nsys",
            Path("bin") / "nsys.exe",
            Path("target-windows-x64") / "nsys.exe",
            Path("target-linux-x64") / "nsys",
        ),
        "gui": (
            Path("nsys-ui"),
            Path("nsys-ui.exe"),
            Path("host-windows-x64") / "nsys-ui.exe",
            Path("host") / "windows-x64" / "nsys-ui.exe",
            Path("host") / "nsys-ui.exe",
        ),
    },
    "ncu": {
        "cli": (
            Path("ncu"),
            Path("ncu.exe"),
            Path("ncu.bat"),
            Path("bin") / "ncu",
            Path("bin") / "ncu.exe",
            Path("target-windows-x64") / "ncu.exe",
            Path("target-linux-x64") / "ncu",
        ),
        "gui": (
            Path("ncu-ui"),
            Path("ncu-ui.exe"),
            Path("ncu-ui.bat"),
            Path("host") / "windows-desktop-win7-x64" / "ncu-ui.exe",
            Path("host") / "windows-x64" / "ncu-ui.exe",
        ),
    },
}

_NSIGHT_COMMAND_NAMES = {
    "nsys": {
        "cli": ("nsys", "nsys.exe"),
        "gui": ("nsys-ui", "nsys-ui.exe"),
    },
    "ncu": {
        "cli": ("ncu", "ncu.exe"),
        "gui": ("ncu-ui", "ncu-ui.exe", "ncu-ui.bat"),
    },
}

_NSIGHT_ROOT_HINTS = {
    "nsys": ("target-windows-x64", "target-linux-x64", "bin"),
    "ncu": ("target-windows-x64", "target-linux-x64", "bin"),
}

_LOCAL_NSIGHT_DIRS = (
    Path("tools") / "nsight",
    Path("vendor") / "nsight",
    Path("deps") / "nsight",
)


def _path_if_exists(path_value: str | os.PathLike[str] | None) -> Path | None:
    """Return the Path when it exists on disk."""
    if not path_value:
        return None
    candidate = Path(path_value).expanduser()
    try:
        if candidate.exists():
            return candidate
    except OSError:
        return None
    return None


def _nsight_install_roots(tool: str) -> list[Path]:
    """Return candidate installation roots for a Nsight tool."""
    tool = tool.lower()
    if tool not in _NSIGHT_INSTALL_PATTERNS:
        raise ValueError(f"Unsupported Nsight tool '{tool}'")

    candidates: list[Path] = []
    # Env-configured roots
    for env_name in ("IONO_NSIGHT_ROOT", f"IONO_{tool.upper()}_ROOT"):
        env_value = os.environ.get(env_name)
        env_path = _path_if_exists(env_value)
        if env_path:
            candidates.append(env_path)
            if env_path.is_dir():
                for pattern in _NSIGHT_INSTALL_PATTERNS[tool]:
                    candidates.extend(env_path.glob(pattern))

    # Local repo directories
    try:
        repo_root = _repo_root()
    except FileNotFoundError:
        repo_root = Path.cwd()
    for rel in _LOCAL_NSIGHT_DIRS:
        candidate = repo_root / rel
        if candidate.exists():
            candidates.append(candidate)

    # Platform-specific global installs
    if os.name == "nt":
        pf_vars = ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)")
        for var in pf_vars:
            pf_value = os.environ.get(var)
            if not pf_value:
                continue
            corp_root = Path(pf_value) / "NVIDIA Corporation"
            if not corp_root.exists():
                continue
            for pattern in _NSIGHT_INSTALL_PATTERNS[tool]:
                candidates.extend(corp_root.glob(pattern))
    else:
        linux_bases = [
            Path("/opt/nvidia"),
            Path("/opt/nvidia/nsight"),
            Path("/usr/local/NVIDIA-Nsight"),
            Path("/usr/local/nvidia"),
            Path("/usr/local/cuda"),
        ]
        for base in linux_bases:
            if not base.exists():
                continue
            candidates.append(base)
            for pattern in _NSIGHT_INSTALL_PATTERNS[tool]:
                candidates.extend(base.glob(pattern))

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            if not candidate.exists():
                continue
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _match_nsight_relative(root: Path, tool: str, kind: str) -> Path | None:
    """Look for Nsight binaries under an installation root."""
    rel_paths = _NSIGHT_RELATIVE_PATHS.get(tool, {}).get(kind, ())
    for rel in rel_paths:
        candidate = (root / rel).expanduser()
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def _resolve_nsight_tool(
    tool: str,
    kind: str,
    *,
    extra_roots: Iterable[Path] | None = None,
) -> Path | None:
    """Resolve Nsight binary path via env overrides, PATH, or install search."""
    tool = tool.lower()
    if tool not in _NSIGHT_INSTALL_PATTERNS:
        raise ValueError(f"Unsupported Nsight tool '{tool}'")

    env_name = _NSIGHT_ENV_OVERRIDES[kind][tool]
    env_override = _path_if_exists(os.environ.get(env_name))
    if env_override:
        return env_override

    for cmd_name in _NSIGHT_COMMAND_NAMES[tool][kind]:
        resolved = shutil.which(cmd_name)
        if resolved:
            cmd_path = _path_if_exists(resolved)
            if cmd_path:
                return cmd_path

    candidate_roots: list[Path] = []
    if extra_roots:
        for root in extra_roots:
            if root:
                existing = _path_if_exists(root)
                if existing:
                    candidate_roots.append(existing)

    candidate_roots.extend(_nsight_install_roots(tool))
    for root in candidate_roots:
        matched = _match_nsight_relative(root, tool, kind)
        if matched:
            return matched

    return None


@lru_cache(maxsize=None)
def get_nsight_cli(tool: str) -> Path | None:
    """Return the absolute CLI path for the requested Nsight tool if present."""
    return _resolve_nsight_tool(tool, "cli")


@lru_cache(maxsize=None)
def get_nsight_gui(tool: str) -> Path | None:
    """Return the GUI executable path for the requested Nsight tool if present."""
    cli_path = get_nsight_cli(tool)
    extra_roots: list[Path] = []
    if cli_path:
        try:
            resolved_cli = cli_path.resolve()
        except OSError:
            resolved_cli = cli_path
        parent = resolved_cli.parent
        extra_roots.append(parent)
        if parent.name in _NSIGHT_ROOT_HINTS.get(tool, ()):
            extra_roots.append(parent.parent)
    return _resolve_nsight_tool(tool, "gui", extra_roots=extra_roots)
