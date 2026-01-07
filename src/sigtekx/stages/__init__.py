"""Stage metadata and registry utilities.

Core stage metadata is lazily loaded into a global registry; Phase 2 will
attach factories and bridge custom kernels into the C++ engine.
"""

from .definitions import (
    StageType,
    get_stage_info,
    get_stage_metadata_legacy,
    list_future_stages,
    list_implemented_stages,
)
from .registry import (
    StageRegistry,
    get_global_registry,
    get_stage,
    list_stages,
    register_stage,
)

__all__ = [
    "StageType",
    "StageRegistry",
    "get_global_registry",
    "get_stage",
    "list_stages",
    "register_stage",
    "get_stage_info",
    "list_future_stages",
    "list_implemented_stages",
    "get_stage_metadata_legacy",
]
