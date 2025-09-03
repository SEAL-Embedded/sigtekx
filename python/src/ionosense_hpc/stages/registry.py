"""Stage registry for pipeline extensibility."""

import warnings
from collections.abc import Callable
from typing import Any


class StageRegistry:
    """Registry for custom processing stages.

    This is a placeholder for v2.0 extensibility. Currently,
    the pipeline stages are hardcoded in C++.
    """

    def __init__(self):
        self._stages: dict[str, Callable] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        stage_fn: Callable,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Register a custom stage.

        Args:
            name: Unique stage identifier
            stage_fn: Stage processing function
            metadata: Optional stage metadata
        """
        if name in self._stages:
            warnings.warn(f"Overwriting existing stage: {name}")

        self._stages[name] = stage_fn
        self._metadata[name] = metadata or {}

    def get(self, name: str) -> Callable | None:
        """Get a registered stage.

        Args:
            name: Stage identifier

        Returns:
            Stage function or None
        """
        return self._stages.get(name)

    def list_stages(self) -> list:
        """List all registered stages.

        Returns:
            List of stage names
        """
        return list(self._stages.keys())

    def get_metadata(self, name: str) -> dict[str, Any]:
        """Get stage metadata.

        Args:
            name: Stage identifier

        Returns:
            Stage metadata dictionary
        """
        return self._metadata.get(name, {})

    def clear(self) -> None:
        """Clear all registered stages."""
        self._stages.clear()
        self._metadata.clear()


# Global registry instance
_global_registry = StageRegistry()


def register_stage(name: str, metadata: dict[str, Any] | None = None):
    """Decorator for registering stages.

    Example:
        >>> @register_stage("custom_filter")
        ... def my_filter(data, config):
        ...     return filtered_data
    """
    def decorator(fn: Callable) -> Callable:
        _global_registry.register(name, fn, metadata)
        return fn
    return decorator


def get_stage(name: str) -> Callable | None:
    """Get a registered stage by name."""
    return _global_registry.get(name)


def list_stages() -> list:
    """List all registered stages."""
    return _global_registry.list_stages()
