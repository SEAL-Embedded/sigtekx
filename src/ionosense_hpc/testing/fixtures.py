"""
Enhanced pytest fixtures for the ionosense-hpc testing framework.

This module provides fixtures for managing test environments, generating
test data, handling hardware dependencies, and supporting the new
benchmark infrastructure following RSE best practices.
"""

from collections.abc import Generator
from pathlib import Path
from typing import cast

import numpy as np
import pytest
import yaml  # type: ignore[import-untyped]

from ionosense_hpc import Engine
from ionosense_hpc.benchmarks.base import (
    BenchmarkConfig,
    BenchmarkContext,
    BenchmarkResult,
)
from ionosense_hpc.config import EngineConfig, get_preset
from ionosense_hpc.utils import (
    make_chirp,
    make_multitone,
    make_noise,
    make_sine,
    make_test_batch,
)
from ionosense_hpc.utils.signals import (
    make_brown_noise,
    make_dc_signal,
    make_impulse,
    make_pink_noise,
    make_pulse_train,
    make_white_noise,
)

# ============================================================================
# Directory Management
# ============================================================================

@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Creates a temporary directory for test data that is cleaned up automatically."""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


@pytest.fixture
def temp_benchmark_dir(tmp_path: Path) -> Path:
    """Creates a temporary directory structure for benchmark results."""
    bench_dir = tmp_path / "benchmark_results"
    bench_dir.mkdir(exist_ok=True)

    # Create subdirectories
    (bench_dir / "results").mkdir(exist_ok=True)
    (bench_dir / "reports").mkdir(exist_ok=True)
    (bench_dir / "experiments").mkdir(exist_ok=True)

    return bench_dir


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def validation_config() -> EngineConfig:
    """Provides a small, controlled configuration for validation and debugging (matches old 'validation' preset)."""
    return EngineConfig(
        nfft=256,
        channels=1,
        overlap=0.0,
        sample_rate_hz=1000,
        warmup_iters=0
    )


@pytest.fixture
def realtime_config() -> EngineConfig:
    """Provides a production-ready configuration for real-time processing tests (matches 'default' preset)."""
    return get_preset('default')


@pytest.fixture
def benchmark_base_config() -> BenchmarkConfig:
    """Provides a base benchmark configuration for testing."""
    return BenchmarkConfig(
        name="test_benchmark",
        iterations=100,
        warmup_iterations=10,
        confidence_level=0.95,
        outlier_threshold=3.0,
        save_raw_data=True,
        verbose=False
    )


@pytest.fixture
def benchmark_config() -> EngineConfig:
    """Provides an EngineConfig tailored for benchmarking."""
    config = get_preset('default')
    config.enable_profiling = True
    config.warmup_iters = 5
    return config

@pytest.fixture
def benchmark_context() -> BenchmarkContext:
    """Provides a mock benchmark context for testing."""
    context = BenchmarkContext()
    # Override some fields for deterministic testing
    context.timestamp = "2025-01-01T00:00:00"
    context.hostname = "test-host"
    context.environment_hash = "test-hash-12345678"
    return context


@pytest.fixture
def sample_benchmark_result(
    benchmark_base_config: BenchmarkConfig,
    benchmark_context: BenchmarkContext
) -> BenchmarkResult:
    """Provides a sample benchmark result for testing."""
    measurements = np.random.randn(100) * 10 + 100  # Mean ~100, std ~10

    return BenchmarkResult(
        name="test_result",
        config=benchmark_base_config.model_dump(),
        context=benchmark_context,
        measurements=measurements,
        passed=True
    )


# ============================================================================
# YAML Configuration Fixtures
# ============================================================================

@pytest.fixture
def yaml_benchmark_config(temp_data_dir: Path) -> Path:
    """Creates a sample YAML benchmark configuration file."""
    config = {
        "name": "test_experiment",
        "iterations": 500,
        "warmup_iterations": 50,
        "engine_config": {
            "nfft": 1024,
            "channels": 2,
            "overlap": 0.5
        },
        "test_signals": [
            {"type": "sine", "frequency": 1000},
            {"type": "noise", "noise_type": "white"}
        ]
    }

    config_path = temp_data_dir / "benchmark_config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config, f)

    return config_path


# ============================================================================
# Engine Fixtures
# ============================================================================

@pytest.fixture
def test_engine(validation_config: EngineConfig) -> Generator[Engine, None, None]:
    """Yields an initialized Engine instance with automatic resource cleanup."""
    engine = Engine(config=validation_config)
    try:
        yield engine
    finally:
        engine.close()


@pytest.fixture
def mock_engine(monkeypatch) -> Engine:
    """Provides a mock Engine that doesn't require GPU."""

    class MockEngine:
        def __init__(self, config=None, **_):
            if config is None:
                default_config = get_preset('default')
                default_config.channels = 1
                self.config = default_config
            else:
                self.config = config
            self.is_initialized = True

        def process(self, data):
            _ = data  # ensure interface compatibility while keeping mock lightweight
            batch = self.config.channels
            bins = self.config.num_output_bins
            return np.random.randn(channels, bins).astype(np.float32)

        def close(self):
            self.is_initialized = False

        def reset(self):
            self.is_initialized = False

    monkeypatch.setattr("ionosense_hpc.Engine", MockEngine)
    return cast(Engine, MockEngine())


# ============================================================================
# Test Data Generation
# ============================================================================

@pytest.fixture
def seeded_rng() -> np.random.Generator:
    """Provides a seeded NumPy random number generator for reproducible tests."""
    return np.random.default_rng(seed=42)


@pytest.fixture
def test_sine_data() -> np.ndarray:
    """Generates a standard 1 kHz sine wave for spectral validation."""
    from ionosense_hpc.utils import make_sine
    return cast(
        np.ndarray,
        make_sine(
            sample_rate=48000,
            n_samples=int(0.1 * 48000),
            frequency=1000.0,
            amplitude=1.0,
            dtype=np.float32,
        ),
    )


@pytest.fixture
def test_batch_data(seeded_rng: np.random.Generator) -> np.ndarray:
    """Generates standard dual-channel batch data for testing."""
    config = EngineConfig(nfft=1024, channels=2, sample_rate_hz=48000)
    return cast(
        np.ndarray,
        make_test_batch(
            "sine",
            config,
            rng=seeded_rng,
            frequency=1000.0,
        ),
    )


@pytest.fixture
def test_noise_data() -> np.ndarray:
    """Generates white noise data for validation."""
    rng = np.random.default_rng(seed=42)
    n_samples = int(0.1 * 48000)
    return cast(
        np.ndarray,
        make_noise(
            n_samples=n_samples,
            rng=rng,
            amplitude=1.0,
            dtype=np.float32,
        ),
    )

@pytest.fixture
def test_signal_suite(seeded_rng: np.random.Generator) -> dict[str, np.ndarray]:
    """Provides a comprehensive suite of test signals."""
    sample_rate = 48000
    n_samples = 1024
    suite: dict[str, np.ndarray] = {
        "sine_100Hz": cast(np.ndarray, make_sine(sample_rate, n_samples, 100.0)),
        "sine_1kHz": cast(np.ndarray, make_sine(sample_rate, n_samples, 1000.0)),
        "dc": cast(np.ndarray, make_dc_signal(n_samples, value=1.0)),
        "impulse": cast(np.ndarray, make_impulse(n_samples)),
        "chirp_linear": cast(np.ndarray, make_chirp(sample_rate, n_samples, f_start=100.0, f_end=sample_rate / 3.0)),
        "chirp_log": cast(np.ndarray, make_chirp(sample_rate, n_samples, f_start=100.0, f_end=sample_rate / 3.0, method="logarithmic")),
        "multitone": cast(np.ndarray, make_multitone(sample_rate, n_samples, frequencies=(100.0, 1000.0, 5000.0))),
        "pulse_train": cast(np.ndarray, make_pulse_train(sample_rate, n_samples)),
        "white_noise": cast(np.ndarray, make_white_noise(n_samples, rng=seeded_rng)),
        "pink_noise": cast(np.ndarray, make_pink_noise(n_samples, rng=seeded_rng)),
        "brown_noise": cast(np.ndarray, make_brown_noise(n_samples, rng=seeded_rng)),
    }
    return suite


# ============================================================================
# Mock Data Fixtures
# ============================================================================

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


# ============================================================================
# Parametrized Fixtures
# ============================================================================

@pytest.fixture(params=['sine', 'chirp', 'noise', 'multitone'])
def test_signal_type(request) -> str:
    """Parametrized fixture that provides different signal type names."""
    return cast(str, request.param)


@pytest.fixture(params=[256, 512, 1024, 2048])
def test_nfft_size(request) -> int:
    """Parametrized fixture that provides different FFT sizes."""
    return cast(int, request.param)


@pytest.fixture(params=[1, 2, 4, 8])
def test_batch_size(request) -> int:
    """Parametrized fixture that provides different batch sizes."""
    return cast(int, request.param)


@pytest.fixture(params=['grid', 'random', 'latin_hypercube'])
def sweep_type(request) -> str:
    """Parametrized fixture for different sweep types."""
    return cast(str, request.param)


# ============================================================================
# Hardware Detection
# ============================================================================

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
def require_nsight() -> None:
    """Skip test if NVIDIA Nsight tools are not available."""
    import shutil

    if not shutil.which('nsys') and not shutil.which('ncu'):
        pytest.skip("NVIDIA Nsight tools required")


# ============================================================================
# Benchmark Execution Fixtures
# ============================================================================

@pytest.fixture
def benchmark_runner(temp_benchmark_dir: Path):
    """Provides a configured benchmark runner for testing."""
    _ = temp_benchmark_dir  # trigger fixture side effects (workspace setup)
    from ionosense_hpc.benchmarks.base import BaseBenchmark

    class TestBenchmark(BaseBenchmark):
        data: np.ndarray | None = None
        def setup(self):
            self.data = np.random.randn(100)

        def execute_iteration(self):
            assert self.data is not None
            return float(np.mean(self.data) + np.random.randn() * 0.1)

        def teardown(self):
            self.data = None

    config = BenchmarkConfig(
        name="test_runner",
        iterations=10,
        warmup_iterations=2,
        output_format="json"
    )

    return TestBenchmark(config)


# ============================================================================
# Validation Fixtures
# ============================================================================

@pytest.fixture
def reference_fft_output() -> np.ndarray:
    """Provides a pre-computed reference FFT output for a standard test signal."""
    nfft = 256
    bins = nfft // 2 + 1
    reference = np.zeros(bins, dtype=np.float32)
    reference[0] = 0.5  # DC component
    reference[10] = 1.0  # Peak at specific frequency
    return reference


@pytest.fixture
def validation_helper():
    """Provides a ValidationHelper instance for testing."""
    from ionosense_hpc.utils.validation import ValidationHelper
    return ValidationHelper()


@pytest.fixture
def data_archiver(temp_benchmark_dir: Path):
    """Provides a DataArchiver instance for testing."""
    from ionosense_hpc.utils.archiving import DataArchiver
    return DataArchiver(temp_benchmark_dir / "archive")


# ============================================================================
# Research Workflow Fixtures
# ============================================================================
