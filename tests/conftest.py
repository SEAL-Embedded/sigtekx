"""
Project-wide Pytest configuration and fixtures.

This file is automatically discovered by Pytest and is used to define
custom command-line options, hooks, and shared fixtures.

Testing Strategy: GPU-First
- By default, all tests, including those marked 'gpu', will run.
- To skip GPU-dependent tests, run pytest with the --no-gpu flag.
  Example: pytest --no-gpu
"""

# Ensure package is importable when running tests without the CLI/installer.
# Insert `src` at the front of sys.path before importing test plugins.
import sys
from pathlib import Path

import pytest

_tests_dir = Path(__file__).resolve().parent
_src_dir = _tests_dir.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# Make the fixtures from the testing module available to all tests
pytest_plugins = [
    "sigtekx.testing.fixtures",
]

def pytest_addoption(parser):
    """Adds the --no-gpu command-line option to Pytest."""
    parser.addoption(
        "--no-gpu", action="store_true", default=False, help="Skip tests that require a GPU"
    )

def pytest_configure(config):
    """Adds the custom 'gpu' marker to Pytest's configuration."""
    config.addinivalue_line("markers", "gpu: marks tests as requiring a GPU to run")

def pytest_collection_modifyitems(config, items):
    """Reorder collection so engine tests run first and apply GPU skips."""
    engine_prefix = "tests/test_engine.py"
    engine_items = [item for item in items if item.nodeid.startswith(engine_prefix)]
    if engine_items:
        remaining_items = [item for item in items if item not in engine_items]
        items[:] = engine_items + remaining_items

    if not config.getoption("--no-gpu"):
        return

    skip_gpu = pytest.mark.skip(reason="--no-gpu option used to skip GPU-dependent tests")
    for item in items:
        if "gpu" in item.keywords:
            item.add_marker(skip_gpu)

