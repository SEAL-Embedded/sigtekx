"""Pipeline stages module (placeholder for v2.0 extensibility)."""

from .definitions import StageType, get_stage_info, list_future_stages, list_implemented_stages
from .registry import StageRegistry, get_stage, list_stages, register_stage

# Note: These are kept private as they're not part of the public API yet
__all__ = []
