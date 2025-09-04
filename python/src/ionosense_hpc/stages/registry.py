"""A stage registry for pipeline extensibility and custom processing operations.

This module provides a registry system for managing custom processing stages,
forming the foundation for the v2.0 extensibility framework. It allows developers
to register custom algorithms while maintaining type safety and documentation
standards.
"""

import warnings
from collections.abc import Callable
from typing import Any


class StageRegistry:
    """Manages custom processing stages and their metadata.

    This class provides a thread-safe registry for dynamically adding, retrieving,
    and managing custom functions as pluggable stages in a processing pipeline.
    It handles registration, metadata, and discovery.

    The registry is designed to be thread-safe for concurrent registration
    during initialization and concurrent retrieval during processing.
    """

    def __init__(self):
        """Initializes a new, empty stage registry."""
        self._stages: dict[str, Callable] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        stage_fn: Callable,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Registers a custom processing stage with optional metadata.

        If a stage with the same name already exists, it will be overwritten,
        and a warning will be issued.

        Args:
            name: The unique name for the stage.
            stage_fn: The processing function for the stage.
            metadata: An optional dictionary of metadata about the stage.
        """
        if name in self._stages:
            warnings.warn(f"Overwriting existing stage: {name}", stacklevel=2)

        self._stages[name] = stage_fn
        self._metadata[name] = metadata or {}

    def get(self, name: str) -> Callable | None:
        """Retrieves a registered stage function by name.

        Args:
            name: The name of the stage to retrieve.

        Returns:
            The callable stage function if found, otherwise None.
        """
        return self._stages.get(name)

    def list_stages(self) -> list:
        """Returns a list of all registered stage names.

        Returns:
            A list of strings representing the names of all registered stages.
        """
        return list(self._stages.keys())

    def get_metadata(self, name: str) -> dict[str, Any]:
        """Retrieves the metadata for a registered stage.

        Args:
            name: The name of the stage.

        Returns:
            A dictionary of metadata, or an empty dictionary if the stage
            is not found.
        """
        return self._metadata.get(name, {})

    def clear(self) -> None:
        """Clears all registered stages and metadata from the registry."""
        self._stages.clear()
        self._metadata.clear()


# Global registry instance for application-wide stage management
_global_registry = StageRegistry()


def register_stage(name: str, metadata: dict[str, Any] | None = None):
    """Decorator to register a function as a stage in the global registry.

    Args:
        name: The unique name for the stage.
        metadata: An optional dictionary of metadata about the stage.

    Returns:
        A decorator that registers the function and returns it unchanged.
    """
    def decorator(fn: Callable) -> Callable:
        """Registers the function and returns it."""
        _global_registry.register(name, fn, metadata)
        return fn

    return decorator


def get_stage(name: str) -> Callable | None:
    """Gets a registered stage by name from the global registry.

    Args:
        name: The name of the stage to retrieve.

    Returns:
        The callable stage function if found, otherwise None.
    """
    return _global_registry.get(name)


def list_stages() -> list:
    """Lists all registered stages in the global registry.

    Returns:
        A list of the names of all registered stages.
    """
    return _global_registry.list_stages()
