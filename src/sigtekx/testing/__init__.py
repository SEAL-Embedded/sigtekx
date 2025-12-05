"""Testing utilities for sigtekx.

This package intentionally avoids importing fixtures or validators at package
import time to keep pytest plugin loading lightweight and robust. Tests should
import from `sigtekx.testing.fixtures` and `sigtekx.testing.validators`
directly as needed.
"""

__all__: list[str] = []
