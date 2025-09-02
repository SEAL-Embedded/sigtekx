"""Shared pytest fixtures for testing."""

from collections.abc import Generator
from pathlib import Path

import numpy as np
import pytest

from ..config import EngineConfig, Presets
from ..core import Processor
from ..utils import make_test_batch


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test data.
    
    Returns:
        Path to temporary directory
    """
    data_dir = tmp_path / "test_data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


@pytest.fixture
def validation_config() -> EngineConfig:
    """Provide a small configuration for validation tests.
    
    Returns:
        EngineConfig for validation
    """
    return Presets.validation()


@pytest.fixture
def realtime_config() -> EngineConfig:
    """Provide realtime configuration for tests.
    
    Returns:
        EngineConfig for realtime processing
    """
    return Presets.realtime()


@pytest.fixture
def test_processor(validation_config: EngineConfig) -> Generator[Processor, None, None]:
    """Create a test processor with cleanup.
    
    Yields:
        Initialized Processor instance
    """
    proc = Processor(validation_config, auto_init=True)
    yield proc
    proc.reset()


@pytest.fixture
def seeded_rng() -> np.random.Generator:
    """Create a seeded random number generator.
    
    Returns:
        Seeded numpy RNG
    """
    return np.random.default_rng(seed=42)


@pytest.fixture
def test_sine_data() -> np.ndarray:
    """Generate test sine wave data.
    
    Returns:
        1D array with 1kHz sine wave
    """
    from ..utils import make_sine
    return make_sine(
        frequency=1000,
        duration=0.1,
        sample_rate=48000,
        amplitude=1.0,
        dtype=np.float32
    )


@pytest.fixture
def test_batch_data() -> np.ndarray:
    """Generate test batch data for dual-channel processing.
    
    Returns:
        Batch data array
    """
    return make_test_batch(
        nfft=1024,
        batch=2,
        signal_type='sine',
        frequency=1000,
        seed=42
    )


@pytest.fixture
def test_noise_data() -> np.ndarray:
    """Generate test noise data.
    
    Returns:
        White noise array
    """
    from ..utils import make_noise
    return make_noise(
        duration=0.1,
        sample_rate=48000,
        noise_type='white',
        seed=42
    )


@pytest.fixture
def mock_device_info() -> dict:
    """Mock device information for testing without GPU.
    
    Returns:
        Mock device info dictionary
    """
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
    """Parametrized fixture for different signal types.
    
    Returns:
        Signal type string
    """
    return request.param


@pytest.fixture(params=[256, 512, 1024, 2048])
def test_nfft_size(request) -> int:
    """Parametrized fixture for different FFT sizes.
    
    Returns:
        FFT size
    """
    return request.param


@pytest.fixture(params=[1, 2, 4, 8])
def test_batch_size(request) -> int:
    """Parametrized fixture for different batch sizes.
    
    Returns:
        Batch size
    """
    return request.param


@pytest.fixture
def gpu_available() -> bool:
    """Check if GPU is available for testing.
    
    Returns:
        True if CUDA GPU is available
    """
    try:
        from ..utils import gpu_count
        return gpu_count() > 0
    except Exception:
        return False


@pytest.fixture
def skip_without_gpu(gpu_available: bool) -> None:
    """Skip test if no GPU is available."""
    if not gpu_available:
        pytest.skip("GPU required for this test")


@pytest.fixture
def benchmark_config() -> EngineConfig:
    """Configuration optimized for benchmarking.
    
    Returns:
        Benchmark-optimized config
    """
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
    """Pre-computed reference FFT output for validation.
    
    Returns:
        Reference magnitude spectrum
    """
    # Simple DC + 1kHz signal reference
    # This would be computed from a known good implementation
    nfft = 256
    bins = nfft // 2 + 1
    reference = np.zeros(bins, dtype=np.float32)
    reference[0] = 0.5  # DC component
    reference[10] = 1.0  # 1kHz bin (approximate)
    return reference
