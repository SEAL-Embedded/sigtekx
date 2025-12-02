"""
Comprehensive NVTX profiling utilities for ionosense-hpc.

Implements layered profiling with domains, colors, categories, decorators,
and convenience helpers. When the `nvtx` package is not installed, everything
behaves as a no-op with minimal overhead.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from contextlib import contextmanager
from enum import Enum
from typing import Any

try:  # Optional dependency
    import nvtx  # type: ignore
    NVTX_AVAILABLE = True
except ImportError:  # pragma: no cover
    NVTX_AVAILABLE = False
    nvtx = None  # type: ignore


# ============================================================================
# NVTX Domains for hierarchical profiling
# ============================================================================

class ProfilingDomain(str, Enum):
    """NVTX domains for different layers of the application."""

    BENCHMARK = "IONOSENSE_BENCHMARK"  # Layer 1: High-level tasks
    CORE = "IONOSENSE_CORE"  # Layer 2: Python API logic
    CPP = "IONOSENSE_CPP"  # Layer 3: C++ implementation (reference)


# ============================================================================
# Color scheme
# ============================================================================

class ProfileColor(str, Enum):
    """Standardized colors for NVTX ranges."""

    NVIDIA_BLUE = "blue"  # Benchmark loops, high-level tasks
    PURPLE = "purple"  # GPU compute (FFT, kernels)
    GREEN = "green"  # Host-to-Device transfers
    ORANGE = "orange"  # Device-to-Host transfers / I/O
    DARK_GRAY = "gray"  # Initialization/allocation
    RED = "red"  # Cleanup/destruction
    YELLOW = "yellow"  # Explicit sync operations
    LIGHT_GRAY = "lightgray"  # Warmup iterations


class ProfileCategory(str, Enum):
    """Categories for organizing profiling data."""

    HIGH_LEVEL = "HighLevel"
    GPU_COMPUTE = "GPUCompute"
    DATA_TRANSFER = "DataTransfer"
    SETUP_TEARDOWN = "SetupTeardown"
    SYNCHRONIZATION = "Synchronization"
    IO_PACING = "IOPacing"
    WARMUP = "Warmup"


# -----------------------------
# Internal helpers (private)
# -----------------------------


def _build_nvtx_attrs(
    message: str,
    color: str | ProfileColor,
    domain: str | ProfilingDomain | None,
    category: str | ProfileCategory | None,
    payload: Any | None,
) -> dict[str, Any]:
    """
    Build the NVTX annotation attributes dict from user-friendly inputs.
    Converts enums to strings and includes optional fields only when provided.
    Numeric payloads (int/float) are kept numeric; others are coerced to str.
    """
    # Convert enums -> strings
    if isinstance(color, ProfileColor):
        color = color.value
    if isinstance(domain, ProfilingDomain):
        domain = domain.value
    if isinstance(category, ProfileCategory):
        category = category.value

    # Base attrs
    attrs: dict[str, Any] = {"message": message, "color": color}

    # Optional fields
    if domain:
        attrs["domain"] = domain
    if category:
        attrs["category"] = category
    if payload is not None:
        attrs["payload"] = payload if isinstance(payload, (int, float)) else str(payload)

    return attrs




# ============================================================================
# Core profiling utilities
# ============================================================================

@contextmanager
def nvtx_range(
    name: str,
    color: str | ProfileColor = ProfileColor.NVIDIA_BLUE,
    domain: str | ProfilingDomain = ProfilingDomain.CORE,
    category: str | ProfileCategory | None = None,
    payload: Any | None = None,
):
    """Create a context-managed NVTX range for detailed profiling."""
    if not NVTX_AVAILABLE:
        # NVTX not present -> no-op but still act like a context manager
        yield
        return

    attrs = _build_nvtx_attrs(name, color, domain, category, payload)
    with nvtx.annotate(**attrs):  # type: ignore[attr-defined]
        yield


def _should_skip_bound_arg(func: Callable[..., Any]) -> bool:
    """Return True when the function's first positional parameter is self/cls."""
    try:
        params = inspect.signature(func).parameters.values()
    except (ValueError, TypeError):
        return False

    for param in params:
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            return param.name in {"self", "cls"}
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            return False

    return False


def _format_arg_value(value: Any, max_len: int = 30) -> str:
    """Format a single argument for NVTX display with conservative truncation."""
    if isinstance(value, str):
        if len(value) > max_len:
            trimmed = value[: max(max_len - 5, 0)]
            return f'"{trimmed}..."'
        return f'"{value}"'

    if hasattr(value, "shape"):
        shape = value.shape
        return f"{type(value).__name__}{shape}"

    if isinstance(value, (list, tuple)) and len(value) > 3:
        return f"{type(value).__name__}[{len(value)}]"

    text = str(value)
    if len(text) > max_len:
        return f"{text[: max(max_len - 3, 0)]}..."
    return text


def _format_function_args(
    func_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    max_args: int = 2,
    max_length: int = 80,
    skip_first_arg: bool = False,
) -> str:
    """
    Build a readable NVTX range name that includes up to `max_args` inputs overall.

    Examples:
        >>> _format_function_args("process", ("arg1", "arg2"), {"batch": 2}, max_args=3)
        'process("arg1", "arg2", batch=2)'

        >>> class Mock:
        ...     pass
        >>> _format_function_args("method", (Mock(), "value"), {}, skip_first_arg=True)
        'method("value")'
    """
    if not args and not kwargs:
        return func_name

    parts: list[str] = []
    limit = max(0, max_args)
    consumed = 0

    if args and limit:
        start_idx = 1 if skip_first_arg else 0
        for arg in args[start_idx:]:
            if consumed >= limit:
                break
            parts.append(_format_arg_value(arg))
            consumed += 1

    if kwargs and consumed < limit:
        for key, value in kwargs.items():
            if consumed >= limit:
                break
            parts.append(f"{key}={_format_arg_value(value)}")
            consumed += 1

    if not parts:
        return func_name

    range_name = f"{func_name}({', '.join(parts)})"
    if len(range_name) > max_length:
        return f"{range_name[: max(max_length - 3, 0)]}..."
    return range_name


def nvtx_decorate(
    message: str | None = None,
    color: str | ProfileColor = ProfileColor.NVIDIA_BLUE,
    domain: str | ProfilingDomain = ProfilingDomain.CORE,
    category: str | ProfileCategory | None = None,
    include_args: bool = False,
    max_args: int = 2,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for automatically profiling function calls."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if not NVTX_AVAILABLE:  # Fast path when nvtx isn't installed
            return func

        skip_bound_arg = _should_skip_bound_arg(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any):
            base_name = message or func.__name__
            if include_args:
                range_name = _format_function_args(
                    base_name,
                    args,
                    kwargs,
                    max_args=max_args,
                    skip_first_arg=skip_bound_arg,
                )
            else:
                range_name = base_name

            with nvtx_range(range_name, color=color, domain=domain, category=category):
                return func(*args, **kwargs)

        return wrapper

    return decorator


# ============================================================================
# Specialized profiling contexts
# ============================================================================

@contextmanager
def benchmark_range(name: str, iteration: int | None = None):
    payload = iteration if iteration is not None else None
    with nvtx_range(
        name,
        color=ProfileColor.NVIDIA_BLUE,
        domain=ProfilingDomain.BENCHMARK,
        category=ProfileCategory.HIGH_LEVEL,
        payload=payload,
    ):
        yield


@contextmanager
def compute_range(name: str):
    with nvtx_range(
        name,
        color=ProfileColor.PURPLE,
        domain=ProfilingDomain.CORE,
        category=ProfileCategory.GPU_COMPUTE,
    ):
        yield


@contextmanager
def transfer_range(name: str, direction: str = "H2D"):
    color = ProfileColor.GREEN if direction == "H2D" else ProfileColor.ORANGE
    with nvtx_range(
        name,
        color=color,
        domain=ProfilingDomain.CORE,
        category=ProfileCategory.DATA_TRANSFER,
    ):
        yield


@contextmanager
def setup_range(name: str):
    with nvtx_range(
        name,
        color=ProfileColor.DARK_GRAY,
        domain=ProfilingDomain.CORE,
        category=ProfileCategory.SETUP_TEARDOWN,
    ):
        yield


@contextmanager
def teardown_range(name: str):
    with nvtx_range(
        name,
        color=ProfileColor.RED,
        domain=ProfilingDomain.CORE,
        category=ProfileCategory.SETUP_TEARDOWN,
    ):
        yield


@contextmanager
def sync_range(name: str = "Synchronize"):
    with nvtx_range(
        name,
        color=ProfileColor.YELLOW,
        domain=ProfilingDomain.CORE,
        category=ProfileCategory.SYNCHRONIZATION,
    ):
        yield


@contextmanager
def warmup_range(name: str = "Warmup", iteration: int | None = None):
    with nvtx_range(
        name,
        color=ProfileColor.LIGHT_GRAY,
        domain=ProfilingDomain.BENCHMARK,
        category=ProfileCategory.WARMUP,
        payload=iteration,
    ):
        yield


# ============================================================================
# Profiling utilities
# ============================================================================

def mark_event(
    message: str,
    color: str | ProfileColor = ProfileColor.NVIDIA_BLUE,
    domain: str | ProfilingDomain | None = None,
    category: str | ProfileCategory | None = None,
    payload: Any | None = None,
) -> None:
    """Insert a point event into the NVTX timeline."""
    if not NVTX_AVAILABLE:
        return

    attrs = _build_nvtx_attrs(message, color, domain, category, payload)
    # Implement as zero-duration range for compatibility
    with nvtx.annotate(**attrs):  # type: ignore[attr-defined]
        pass


def set_thread_name(name: str) -> None:
    """Set thread name to appear in profiler (best-effort)."""

    if not NVTX_AVAILABLE:
        return

    try:
        import threading

        threading.current_thread().name = name
    except Exception:
        pass


# ============================================================================
# Profiling control
# ============================================================================

class ProfilingContext:
    """Global profiling context for enabling/disabling features."""

    _enabled = True
    _verbose = False

    @classmethod
    def enable(cls) -> None:
        cls._enabled = True

    @classmethod
    def disable(cls) -> None:
        cls._enabled = False

    @classmethod
    def is_enabled(cls) -> bool:
        return cls._enabled and NVTX_AVAILABLE

    @classmethod
    def set_verbose(cls, verbose: bool) -> None:
        cls._verbose = verbose


# ============================================================================
# Convenience functions
# ============================================================================

def profile_iterator(
    iterator: Any,
    name: str = "Iteration",
    domain: ProfilingDomain = ProfilingDomain.BENCHMARK,
):
    """Yield items from iterator with NVTX ranges per iteration."""

    for i, item in enumerate(iterator):
        with nvtx_range(f"{name}_{i}", domain=domain.value if isinstance(domain, ProfilingDomain) else domain, payload=i):
            yield item


def initialize_profiling(verbose: bool = False) -> str:
    """Initialize profiling system and return a status string."""

    ProfilingContext.set_verbose(verbose)
    if NVTX_AVAILABLE:
        return "NVTX profiling enabled" + (" (verbose mode)" if verbose else "")
    return "NVTX not available - profiling disabled"


__all__ = [
    # Core functions
    "nvtx_range",
    "nvtx_decorate",
    "mark_event",
    # Specialized ranges
    "benchmark_range",
    "compute_range",
    "transfer_range",
    "setup_range",
    "teardown_range",
    "sync_range",
    "warmup_range",
    # Utilities
    "profile_iterator",
    "ProfilingContext",
    "initialize_profiling",
    # Enums
    "ProfilingDomain",
    "ProfileColor",
    "ProfileCategory",
    # Status
    "NVTX_AVAILABLE",
]
