"""Version information for ionosense-hpc package.

The canonical version is defined in pyproject.toml under [project.version].
This module reads the installed distribution metadata to avoid duplication.
"""

from importlib.metadata import PackageNotFoundError, version

_NAME = "ionosense-hpc"

try:
    __version__ = version(_NAME)
except PackageNotFoundError:
    # Fallback for source tree without installed metadata
    __version__ = "0.0.0+local"

def _parse_version(v: str) -> tuple:
    parts: list[int] = []
    for segment in v.split("."):
        num = "".join(ch for ch in segment if ch.isdigit())
        if num == "":
            break
        parts.append(int(num))
    return tuple(parts) if parts else (0, 0, 0)

__version_info__ = _parse_version(__version__)
