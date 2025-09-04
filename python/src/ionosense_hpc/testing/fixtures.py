"""Shared pytest fixtures for the ionosense-hpc testing framework.

This module provides fixtures for managing test environments, generating
test data, and handling hardware dependencies, following RSE best practices
for scientific computing validation.
"""

from collections.abc import Generator
from pathlib import Path

import numpy as np
import pytest

from ionosense_hpc.config import EngineConfig, Presets
from ionosense_hpc.core import Processor
from ionosense_hpc.utils import make_test_batch


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Creates a temporary directory for test data that is cleaned up automatically."""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


@pytest.fixture
def validation_config() -> EngineConfig:
    """Provides a small, controlled configuration for validation and debugging."""
    return Presets.validation()


@pytest.fixture
def realtime_config() -> EngineConfig:
    """Provides a production-ready configuration for real-time processing tests."""
    return Presets.realtime()


@pytest.fixture
def test_processor(validation_config: EngineConfig) -> Generator[Processor, None, None]:
    """Yields an initialized Processor instance with automatic resource cleanup."""
    proc = Processor(validation_config, auto_init=True)
    try:
        yield proc
    finally:
        proc.reset()


@pytest.fixture
def seeded_rng() -> np.random.Generator:
    """Provides a seeded NumPy random number generator for reproducible tests."""
    return np.random.default_rng(seed=42)


@pytest.fixture
def test_sine_data() -> np.ndarray:
    """Generates a standard 1 kHz sine wave for spectral validation."""
    from ionosense_hpc.utils import make_sine
    return make_sine(
        frequency=1000,
        duration=0.1,
        sample_rate=48000,
        amplitude=1.0,
        dtype=np.float32
    )


@pytest.fixture
def test_batch_data() -> np.ndarray:
    """Generates standard dual-channel batch data for testing."""
    return make_test_batch(nfft=1024, batch=2, signal_type='sine', frequency=1000, seed=42)


@pytest.fixture
def test_noise_data() -> np.ndarray:
    """Generates standard white Gaussian noise for robustness testing."""
    from ionosense_hpc.utils import make_noise
    return make_noise(duration=0.1, sample_rate=48000, noise_type='white', seed=42)


@pytest.fixture
def mock_device_info() -> dict:
    """Provides mock GPU device info for testing without actual hardware."""
    return {
        'id': 0,
        'name': 'Mock GPU',
        'memory_total_mb': 8192,
        'memory_free_mb': 7000,
        'compute_capability': (8, 0),
        'temperature_c': 45,
        'power_w': 75.0,
        'utilization_gpu': 15,
        'utilization_memory': 10
    }


@pytest.fixture(params=['sine', 'chirp', 'noise', 'multitone'])
def test_signal_type(request) -> str:
    """Parametrized fixture that provides different signal type names."""
    return request.param


@pytest.fixture(params=[256, 512, 1024, 2048])
def test_nfft_size(request) -> int:
    """Parametrized fixture that provides different FFT sizes."""
    return request.param


@pytest.fixture(params=[1, 2, 4, 8])
def test_batch_size(request) -> int:
    """Parametrized fixture that provides different batch sizes."""
    return request.param


@pytest.fixture
def gpu_available() -> bool:
    """Returns True if a CUDA-capable GPU is available, otherwise False."""
    try:
        from ionosense_hpc.utils import gpu_count
        return gpu_count() > 0
    except Exception:
        return False


@pytest.fixture
def skip_without_gpu(gpu_available: bool) -> None:
    """A fixture that skips a test if no GPU is available."""
    if not gpu_available:
        pytest.skip("GPU required for this test")


@pytest.fixture
def benchmark_config() -> EngineConfig:
    """Provides a configuration optimized for performance benchmarking."""
    return EngineConfig(
        nfft=2048,
        batch=8,
        overlap=0.5,
        sample_rate_hz=48000,
        warmup_iters=10,
        enable_profiling=True
    )


@pytest.fixture
def reference_fft_output() -> np.ndarray:
    """Provides a pre-computed reference FFT output for a standard test signal."""
    nfft = 256
    bins = nfft // 2 + 1
    reference = np.zeros(bins, dtype=np.float32)
    reference[0] = 0.5
    reference[10] = 1.0
    return reference
