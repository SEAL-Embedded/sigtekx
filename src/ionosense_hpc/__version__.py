"""Version information for ionosense-hpc package.

The canonical version is defined in pyproject.toml under [project.version].
This module reads the installed distribution metadata to avoid duplication.
"""

from importlib.metadata import PackageNotFoundError, version

_NAME = "ionosense-hpc"

# Start with a safe, default fallback version.
__version__ = "0.0.0+local"

try:
    # Attempt to get the version from installed package metadata.
    installed_version = version(_NAME)
    # Only overwrite the fallback if a valid version string is found.
    if installed_version:
        __version__ = installed_version
except PackageNotFoundError:
    # This is expected if the package is not installed, so we just
    # proceed with the fallback version.
    pass

def _parse_version(v: str) -> tuple:
    """Parses a version string into a tuple of integers."""
    parts: list[int] = []
    # Handles version strings like "0.9.1" or "0.9.1.dev0"
    for segment in v.split("."):
        # Extract only the numeric part of the segment
        num = "".join(ch for ch in segment if ch.isdigit())
        if not num:
            break
        parts.append(int(num))
    return tuple(parts) if parts else (0, 0, 0)

# Parse the final version string into a tuple for easy comparison.
__version_info__ = _parse_version(__version__)
