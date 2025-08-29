# python/tests/test_pipeline.py
"""
Integration tests for the FFTPipeline.

These tests verify that the pipeline correctly orchestrates the C++ engine,
buffer management, and signal processing to produce valid results.
"""
import numpy as np
import pytest

from ionosense_hpc.core.config import ProcessingConfig
from ionosense_hpc.core.pipeline import FFTPipeline
from ionosense_hpc.utils.signals import generate_test_signal, SignalParameters

# Mark all tests in this file as belonging to the 'pipeline' suite
pytestmark = pytest.mark.pipeline


@pytest.fixture(scope="module")
def pipeline_instance() -> FFTPipeline:
    """
    Pytest fixture that creates a reusable FFTPipeline instance.

    This is scoped to the module to avoid the overhead of re-initializing
    the CUDA engine and capturing graphs for every single test function.
    """
    config = ProcessingConfig(
        fft_size=4096,
        batch_size=8,
        window='hann',
        use_graphs=False  # CUDA graphs are incompatible with Python's runtime memory modification
    )
    return FFTPipeline(config)


def test_pipeline_execution(pipeline_instance: FFTPipeline):
    """
    Tests a single, successful execution of the pipeline with random data.
    Verifies output shape, type, and metadata.
    """
    config = pipeline_instance.config
    
    # 1. Create a batch of random data matching the pipeline's config
    test_data = np.random.randn(config.batch_size, config.fft_size).astype(np.float32)

    # 2. Process the batch
    result = pipeline_instance.process_batch(test_data)

    # 3. Validate the results
    assert result.output.shape == (config.batch_size, config.fft_size // 2 + 1)
    assert result.output.dtype == np.float32
    assert result.latency_ms > 0
    assert 0 <= result.stream_id < pipeline_instance.engine.num_streams
    assert result.metadata['fft_size'] == config.fft_size
    assert result.metadata['window'] == config.window


def test_pipeline_incorrect_input_shape(pipeline_instance: FFTPipeline):
    """Tests that the pipeline correctly raises a ValueError for mismatched input."""
    wrong_shape_data = np.zeros((4, 1024), dtype=np.float32) # Incorrect shape

    with pytest.raises(ValueError, match="Input data has shape"):
        pipeline_instance.process_batch(wrong_shape_data)


def test_pipeline_accuracy(pipeline_instance: FFTPipeline):
    """
    Tests the numerical accuracy of the pipeline using a known signal.
    """
    config = pipeline_instance.config
    sample_rate = 100_000 # A typical sample rate

    # 1. Generate a known signal: a 7kHz sine wave
    params = SignalParameters(
        sample_rate=sample_rate,
        duration=1.0, # Long enough to get many frames
        frequencies=(7000.0, 1000.0), # We only care about the first channel
        noise_level=0.0
    )
    signals = generate_test_signal(params)
    single_frame = signals['ch1'][:config.fft_size]

    # 2. Create a full batch, with our known signal in the first slot
    #    and zeros everywhere else.
    batch_data = np.zeros((config.batch_size, config.fft_size), dtype=np.float32)
    batch_data[0, :] = single_frame
    
    # 3. Process the batch
    result = pipeline_instance.process_batch(batch_data)
    
    # 4. Analyze the output for our known signal
    spectrum = result.output[0] # Extract the first FFT result from the batch

    # 5. Verify the peak frequency
    # The expected frequency bin is calculated as: (frequency * fft_size / sample_rate)
    expected_bin = int(params.frequencies[0] * config.fft_size / sample_rate)
    found_bin = np.argmax(spectrum)

    # Allow for a small tolerance (e.g., 1 bin) due to windowing effects
    assert abs(found_bin - expected_bin) <= 1, f"Peak at bin {found_bin}, expected {expected_bin}±1"