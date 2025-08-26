"""
Unit tests for the Python RtFftEngine wrapper.
"""
import pytest
import numpy as np
from ionosense_hpc.core.engine import RtFftEngine, RtFftConfig

@pytest.fixture
def default_config():
    """Provides a default configuration for the FFT engine."""
    return RtFftConfig(nfft=1024, batch=4)

def test_engine_construction(default_config):
    """Tests that the engine can be created with a config."""
    try:
        engine = RtFftEngine(default_config)
        assert engine.fft_size == default_config.nfft
        assert engine.batch_size == default_config.batch
    except Exception as e:
        pytest.fail(f"Engine construction failed: {e}")

def test_runtime_graph_toggle(default_config):
    """
    Verifies that the use_graphs property can be changed at runtime.
    (Migrated from C++ test: RuntimeGraphToggleTest)
    """
    config = default_config
    config.use_graphs = True
    engine = RtFftEngine(config)

    assert engine.use_graphs is True, "Graph usage should be True initially"

    # Disable graphs and check
    engine.use_graphs = False
    assert engine.use_graphs is False, "Graph usage should be False after setting"

    # Re-enable graphs and check
    engine.use_graphs = True
    assert engine.use_graphs is True, "Graph usage should be True after re-enabling"

def test_set_window_function(default_config):
    """
    Tests that a custom window can be set from Python.
    (Migrated from C++ test: WindowFunctionTest)
    """
    engine = RtFftEngine(default_config)
    
    # Create a Hann window using NumPy
    window = np.hanning(default_config.nfft).astype(np.float32)
    
    try:
        engine.set_window(window)
    except Exception as e:
        pytest.fail(f"set_window should not raise an exception: {e}")

    # Verify the window data has the correct length
    assert len(window) == engine.fft_size