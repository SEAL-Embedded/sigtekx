"""
Unit tests for the low-level Pipeline and PipelineBuilder APIs.
"""
import pytest
import numpy as np
import re
from ionosense_hpc.core.pipelines import Pipeline, PipelineBuilder
from ionosense_hpc.core.config import PipelineConfig, FFTConfig
from ionosense_hpc.core.exceptions import StateError

def test_pipeline_builder(default_fft_config):
    """Tests the fluent builder pattern for creating a Pipeline."""
    builder = PipelineBuilder()
    pipeline = (builder
        .with_streams(2)
        .with_profiling(True)
        .with_fft(default_fft_config.nfft, default_fft_config.batch_size)
        .build())

    assert pipeline is not None
    assert pipeline.num_streams == 2

def test_pipeline_prepare(pipeline_instance: Pipeline):
    """Tests that the pipeline prepares correctly and handles double-prepare."""
    assert pipeline_instance.is_prepared
    with pytest.raises(StateError, match="State Error: Pipeline already prepared."):
        pipeline_instance.prepare()

def test_pipeline_execute_before_prepare():
    """Tests that calling execute before prepare raises a StateError."""
    pipeline = PipelineBuilder().with_fft(1024, 2).build() # Don't call prepare()
    
    expected_error = "State Error: Pipeline not prepared. Call prepare() first."
    with pytest.raises(StateError, match=re.escape(expected_error)):
        pipeline.execute_async(0)

def test_pipeline_buffer_access(pipeline_instance: Pipeline):
    """Tests that buffer accessors return valid NumPy arrays with correct shapes."""
    nfft = pipeline_instance._config.stage_config.nfft
    batch = pipeline_instance._config.stage_config.batch_size
    n_bins = nfft // 2 + 1

    input_buf = pipeline_instance.get_input_buffer(0)
    output_buf = pipeline_instance.get_output_buffer(0)

    assert isinstance(input_buf, np.ndarray)
    assert isinstance(output_buf, np.ndarray)
    assert input_buf.shape == (batch, nfft)
    assert output_buf.shape == (batch, n_bins)
    assert input_buf.dtype == np.float32
    assert output_buf.dtype == np.float32

def test_pipeline_synchronize_all(pipeline_instance: Pipeline):
    """Tests that synchronize_all runs without errors."""
    pipeline_instance.execute_async(0)
    pipeline_instance.synchronize_all()
    # No assert needed, if it doesn't hang or throw, it's working at a basic level.
