"""
Unit tests for the configuration classes in `ionosense_hpc.core.config`.
"""
import pytest
from ionosense_hpc.core.config import FFTConfig, PipelineConfig
from ionosense_hpc.core.exceptions import ConfigurationError

def test_fft_config_valid():
    """Tests creation of a valid FFTConfig."""
    config = FFTConfig(nfft=4096, batch_size=8)
    assert config.nfft == 4096
    assert config.batch_size == 8

def test_fft_config_invalid_nfft():
    """Tests that non-power-of-2 FFT sizes raise ConfigurationError."""
    with pytest.raises(ConfigurationError, match="FFT size must be a positive power of 2"):
        FFTConfig(nfft=1000)

def test_fft_config_invalid_batch_size():
    """Tests that non-positive batch sizes raise ConfigurationError."""
    with pytest.raises(ConfigurationError, match="Batch size must be at least 1"):
        FFTConfig(nfft=1024, batch_size=0)

def test_pipeline_config_valid(default_fft_config):
    """Tests creation of a valid PipelineConfig."""
    config = PipelineConfig(
        num_streams=4,
        use_graphs=False,
        stage_config=default_fft_config
    )
    assert config.num_streams == 4
    assert not config.use_graphs
    assert config.stage_config == default_fft_config

def test_pipeline_config_invalid_streams():
    """Tests that an invalid number of streams raises ConfigurationError."""
    with pytest.raises(ConfigurationError, match="Number of streams must be 1-16"):
        PipelineConfig(num_streams=0)
    with pytest.raises(ConfigurationError, match="Number of streams must be 1-16"):
        PipelineConfig(num_streams=17)

def test_pipeline_config_with_dict_stage_config():
    """Tests that a dict passed for stage_config is converted to FFTConfig."""
    config = PipelineConfig(stage_config={'nfft': 2048, 'batch_size': 2})
    assert isinstance(config.stage_config, FFTConfig)
    assert config.stage_config.nfft == 2048
