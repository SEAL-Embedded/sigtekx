"""Unified stage registry for core and custom processing stages.

The registry is the single source of truth for stage metadata. It currently
tracks Python-level stages only; Phase 2 will bridge factories into the C++
engine (CustomStage, CUfunction adapters).
"""

import warnings
from collections.abc import Callable
from typing import Any, Literal, Protocol, TypedDict


class StageMetadata(TypedDict):
    """Standardized metadata schema for pipeline stages."""

    description: str
    implemented: bool
    parameters: list[str]
    stage_type: Literal["core", "custom", "experimental"]
    version_added: str


class IStageFactory(Protocol):
    """Protocol for factory callables that instantiate a stage."""

    def __call__(self, config: dict[str, Any]) -> Any:
        ...


class StageRegistry:
    """Unified registry for core + custom stages.

    Phase 0: only metadata is registered for core stages to prepare the extension
    points needed in Phase 2 (Numba/PyTorch custom kernels). Factory attachment
    and C++ bridging remain to be implemented.
    """

    def __init__(self) -> None:
        self._stages: dict[str, IStageFactory] = {}
        self._metadata: dict[str, StageMetadata] = {}
        self._core_stages_registered = False

    def ensure_core_stages(self) -> None:
        """Lazy-load core stage metadata from definitions to avoid import cycles."""
        if self._core_stages_registered:
            return

        from sigtekx.stages.definitions import STAGE_METADATA, StageType

        for stage_type, metadata in STAGE_METADATA.items():
            if metadata.get("implemented", False):
                self.register_core_stage(
                    name=stage_type.value,
                    metadata={
                        "description": metadata["description"],
                        "implemented": True,
                        "parameters": metadata.get("parameters", []),
                        "stage_type": "core",
                        "version_added": "0.9.6",
                    },
                )

        self._core_stages_registered = True

    def register_core_stage(self, name: str, metadata: StageMetadata) -> None:
        """Register a core stage metadata entry (factory binding deferred to Phase 2)."""
        self._metadata[name] = metadata

    def register(
        self,
        name: str,
        stage_fn: IStageFactory,
        metadata: StageMetadata | None = None,
    ) -> None:
        """Register a custom stage factory and optional metadata."""
        self.ensure_core_stages()
        if name in self._stages:
            warnings.warn(f"Overwriting existing stage: {name}", stacklevel=2)

        self._stages[name] = stage_fn
        if metadata:
            self._metadata[name] = metadata

    def get(self, name: str) -> IStageFactory | None:
        """Retrieve a registered stage factory by name."""
        self.ensure_core_stages()
        return self._stages.get(name)

    def list_stages(self) -> list[str]:
        """List all known stages (core metadata + registered factories)."""
        self.ensure_core_stages()
        return sorted(set(self._metadata.keys()) | set(self._stages.keys()))

    def get_metadata(self, name: str) -> StageMetadata:
        """Return metadata for a stage or raise if not registered."""
        self.ensure_core_stages()
        if name not in self._metadata:
            raise ValueError(f"Stage '{name}' not registered")
        return self._metadata[name]

    def validate_stage_exists(self, name: str) -> bool:
        """Check whether a stage name is registered."""
        self.ensure_core_stages()
        return name in self._metadata or name in self._stages

    def get_core_pipeline(self) -> list[str]:
        """Default core pipeline order (Window -> FFT -> Magnitude)."""
        self.ensure_core_stages()
        return ["window", "fft", "magnitude"]

    def clear(self) -> None:
        """Clear all registered stages and metadata (mostly for tests)."""
        self._stages.clear()
        self._metadata.clear()
        self._core_stages_registered = False


# Global registry instance for application-wide stage management
_global_registry = StageRegistry()


def get_global_registry() -> StageRegistry:
    """Return the singleton StageRegistry instance."""
    return _global_registry


def register_stage(name: str, metadata: StageMetadata | None = None):
    """Decorator to register a function as a stage in the global registry."""

    def decorator(fn: Callable) -> Callable:
        _global_registry.register(name, fn, metadata)
        return fn

    return decorator


def get_stage(name: str) -> IStageFactory | None:
    """Retrieve a stage factory from the global registry."""
    return _global_registry.get(name)


def list_stages() -> list[str]:
    """List stage names known to the global registry."""
    return _global_registry.list_stages()
