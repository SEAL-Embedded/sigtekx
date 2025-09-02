"""
Project-wide Pytest configuration and fixtures.

This file is automatically discovered by Pytest and is used to define
custom command-line options, hooks, and shared fixtures.

Testing Strategy: GPU-First
- By default, all tests, including those marked 'gpu', will run.
- To skip GPU-dependent tests, run pytest with the --no-gpu flag.
  Example: pytest --no-gpu
"""

import pytest

# Make the fixtures from the testing module available to all tests
pytest_plugins = [
   "ionosense_hpc.testing.fixtures"
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
    """
    Skips tests marked with 'gpu' if the --no-gpu flag is provided.
    """
    if not config.getoption("--no-gpu"):
        # --no-gpu flag is NOT set, so run all tests.
        return

    # --no-gpu flag IS set, so skip all tests marked with 'gpu'.
    skip_gpu = pytest.mark.skip(reason="--no-gpu option used to skip GPU-dependent tests")
    for item in items:
        if "gpu" in item.keywords:
            item.add_marker(skip_gpu)
