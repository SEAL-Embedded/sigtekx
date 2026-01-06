"""Tests for the processing stages registry and builder validation."""


import pytest

from sigtekx.core.builder import PipelineBuilder
from sigtekx.stages.definitions import (
    STAGE_METADATA,
    StageType,
    get_stage_metadata_legacy,
)
from sigtekx.stages.registry import get_global_registry


def test_core_stages_registered():
    registry = get_global_registry()

    assert registry.validate_stage_exists("window")
    assert registry.validate_stage_exists("fft")
    assert registry.validate_stage_exists("magnitude")


def test_registry_metadata_matches_definitions():
    registry = get_global_registry()

    for stage_type, static_metadata in STAGE_METADATA.items():
        if not static_metadata.get("implemented", False):
            continue

        registry_metadata = registry.get_metadata(stage_type.value)
        assert registry_metadata["description"] == static_metadata["description"]
        assert set(registry_metadata["parameters"]) == set(
            static_metadata.get("parameters", [])
        )


def test_pipeline_builder_validates_stages():
    builder = PipelineBuilder().add_window().add_fft()
    builder._stages.append({"type": "invalid_stage", "params": {}})

    with pytest.raises(ValueError, match="Stage 'invalid_stage' not registered"):
        builder.build()


def test_add_custom_raises_not_implemented():
    builder = PipelineBuilder()

    with pytest.raises(NotImplementedError, match="Phase 2"):
        builder.add_custom("my_stage", lambda cfg: cfg)


def test_legacy_metadata_access_deprecated():
    with pytest.warns(DeprecationWarning):
        legacy = get_stage_metadata_legacy()

    assert StageType.WINDOW in legacy
    assert legacy[StageType.WINDOW]["stage_type"] == "core"

