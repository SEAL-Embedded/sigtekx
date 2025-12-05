"""Tests for the processing stages and registry."""


import pytest

# Import the global registry instance that the application uses
from sigtekx.stages.registry import _global_registry


# Mock some stages for testing, since the tests depend on them being registered.
# In a real scenario, you might import the modules where they are defined.
class MockStage:
    def __init__(self, name, key, description):
        self.name = name
        self.key = key
        self.description = description
    def __call__(self, *args, **kwargs):
        pass

# Register mock stages to the global registry for the tests to find
_global_registry.register("fft", MockStage("FFT", "fft", "Calculates the Fast Fourier Transform"))
_global_registry.register("magnitude", MockStage("Magnitude", "magnitude", "Computes the magnitude"))
_global_registry.register("db", MockStage("dB Conversion", "db", "Converts the magnitude spectrum to decibels"))


@pytest.fixture(scope="module")
def stage_registry():
    """Provides the singleton instance of the StageRegistry."""
    return _global_registry


class TestStageDefinitions:
    """Test individual processing stage definitions obtained from the registry."""

    def test_fft_stage_properties(self, stage_registry):
        """Test the properties of the FFT stage."""
        stage = stage_registry.get("fft")
        assert stage.name == "FFT"
        assert stage.key == "fft"
        assert "Calculates the Fast Fourier Transform" in stage.description

    def test_magnitude_stage_properties(self, stage_registry):
        """Test the properties of the Magnitude stage."""
        stage = stage_registry.get("magnitude")
        assert stage.name == "Magnitude"
        assert stage.key == "magnitude"
        assert "Computes the magnitude" in stage.description

    def test_converttodb_stage_properties(self, stage_registry):
        """Test the properties of the ConvertToDB stage."""
        stage = stage_registry.get("db")
        assert stage.name == "dB Conversion"
        assert stage.key == "db"
        assert "Converts the magnitude spectrum to decibels" in stage.description


class TestStageRegistry:
    """Test the StageRegistry functionality."""

    def test_singleton_pattern(self, stage_registry):
        """Test that the StageRegistry uses a singleton pattern via its global instance."""
        # Importing the global registry again should yield the same object
        from sigtekx.stages.registry import _global_registry as registry2
        assert stage_registry is registry2

    def test_stage_retrieval(self, stage_registry):
        """Test retrieving registered stages."""
        # Check that stages registered at the start of the file are retrievable
        assert len(stage_registry.list_stages()) >= 3

        fft_stage = stage_registry.get("fft")
        assert fft_stage.key == "fft"

    def test_get_invalid_stage(self, stage_registry):
        """Test retrieving a non-existent stage returns None without error."""
        # The .get() method returns None for a missing key, it does not raise KeyError
        assert stage_registry.get("non_existent_stage") is None

    def test_list_available_stages(self, stage_registry):
        """Test that listing available stages returns a list of keys."""
        available_stages = stage_registry.list_stages()

        assert isinstance(available_stages, list)
        assert "fft" in available_stages
        assert "magnitude" in available_stages
        assert "db" in available_stages

