"""
conftest.py - Pytest Fixtures
----------------------------
This file defines shared fixtures for the test suite. Fixtures are a powerful
pytest feature that allows for setting up, sharing, and tearing down resources
(like an initialized CUDA engine) across multiple tests. This avoids redundant
setup code and speeds up the test runs significantly.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
import importlib.machinery as _machinery
import pytest

# Mark all tests in this dir as GPU tests (skip cleanly if engine isn't built)
pytestmark = pytest.mark.gpu


def pytest_configure(config):
    # ensure the marker is registered even without pytest.ini
    config.addinivalue_line(
        "markers",
        "gpu: tests that require the compiled CUDA engine and a working GPU",
    )


def _candidate_core_dirs():
    """
    Yield plausible locations for `ionosense_hpc/core/_engine.*` without
    importing the package (avoids import-time side effects).
    """
    here = Path(__file__).resolve()

    # 1) Editable install path inside repo: python/src/ionosense_hpc/core
    for parent in here.parents:
        maybe = parent / "python" / "src" / "ionosense_hpc" / "core"
        if maybe.is_dir():
            yield maybe
            break

    # 2) Any site-packages / sys.path entry that has ionosense_hpc/core
    for base in map(Path, sys.path):
        core = base / "ionosense_hpc" / "core"
        if core.is_dir():
            yield core


def _locate_engine_file() -> Path | None:
    """
    Look for the compiled extension `_engine` across known dirs using the
    interpreter's extension suffixes (.pyd/.so with ABI tag).
    """
    suffixes = _machinery.EXTENSION_SUFFIXES  # e.g. ['.cp311-win_amd64.pyd', '.pyd', '.so']
    for core_dir in _candidate_core_dirs():
        for suf in suffixes:
            cand = core_dir / f"_engine{suf}"
            if cand.exists():
                return cand
    return None


# ===== Early skip before importing numpy/ionosense_hpc =====
_engine_path = _locate_engine_file()
if _engine_path is None:
    pytest.skip(
        "CUDA engine not built/available; build the extension first "
        "(e.g., ./scripts/cli.sh build && pip install -e .[dev])",
        allow_module_level=True,
    )

# OK, the engine file exists — now it’s safe to import dependencies.
import numpy as np  # noqa: E402
from ionosense_hpc.core.fft_processor import FFTProcessor  # noqa: E402
from ionosense_hpc.core.pipelines import Pipeline  # noqa: E402
from ionosense_hpc.core.config import FFTConfig, PipelineConfig  # noqa: E402


@pytest.fixture(scope="session")
def default_fft_config():
    """Default FFTConfig used across tests."""
    return FFTConfig(nfft=1024, batch_size=4)


@pytest.fixture(scope="session")
def default_pipeline_config(default_fft_config):
    """Default PipelineConfig used across tests."""
    return PipelineConfig(
        num_streams=3,
        enable_profiling=True,
        stage_config=default_fft_config,
    )


@pytest.fixture(scope="session")
def pipeline_instance(default_pipeline_config):
    """
    Session-scoped low-level Pipeline (init CUDA context once).
    """
    pipe = Pipeline(default_pipeline_config)
    pipe.prepare()
    return pipe


@pytest.fixture(scope="session")
def fft_processor_instance():
    """
    Session-scoped high-level FFTProcessor for integration/API tests.
    """
    return FFTProcessor(
        fft_size=2048,
        batch_size=2,
        window="hann",
        num_streams=3,
    )
