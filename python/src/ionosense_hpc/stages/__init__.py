"""Pipeline stages module (placeholder for v2.0 extensibility)."""

from .registry import (
    StageRegistry,
    register_stage,
    get_stage,
    list_stages
)

from .definitions import (
    StageType,
    get_stage_info,
    list_implemented_stages,
    list_future_stages
)

# Note: These are kept private as they're not part of the public API yet
__all__ = []