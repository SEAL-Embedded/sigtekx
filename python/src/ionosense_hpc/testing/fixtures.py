"""
Enhanced pytest fixtures for the ionosense-hpc testing framework.

This module provides fixtures for managing test environments, generating
test data, handling hardware dependencies, and supporting the new
benchmark infrastructure following RSE best practices.
"""

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
import yaml  # type: ignore[import-untyped]

from ionosense_hpc.benchmarks.base import (
    BenchmarkConfig,
    BenchmarkContext,
    BenchmarkResult,
)
from ionosense_hpc.config import EngineConfig, Presets
from ionosense_hpc.core import Processor
from ionosense_hpc.utils import make_test_batch

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
    """Provides a small, controlled configuration for validation and debugging."""
    return Presets.validation()


@pytest.fixture
def realtime_config() -> EngineConfig:
    """Provides a production-ready configuration for real-time processing tests."""
    return Presets.realtime()


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
            "batch": 2,
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


@pytest.fixture
def yaml_sweep_config(temp_data_dir: Path) -> Path:
    """Creates a sample parameter sweep configuration file."""
    config = {
        "name": "test_sweep",
        "description": "Test parameter sweep",
        "benchmark_class": "ionosense_hpc.benchmarks.latency.LatencyBenchmark",
        "parameters": [
            {
                "name": "engine_config.nfft",
                "type": "int",
                "values": [256, 512, 1024]
            },
            {
                "name": "engine_config.batch",
                "type": "int",
                "range": {"start": 1, "stop": 4, "step": 1}
            }
        ],
        "sweep_type": "grid",
        "base_config": {
            "iterations": 10,
            "warmup_iterations": 2
        }
    }

    config_path = temp_data_dir / "sweep_config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config, f)

    return config_path


# ============================================================================
# Processor and Engine Fixtures
# ============================================================================

@pytest.fixture
def test_processor(validation_config: EngineConfig) -> Generator[Processor, None, None]:
    """Yields an initialized Processor instance with automatic resource cleanup."""
    proc = Processor(validation_config, auto_init=True)
    try:
        yield proc
    finally:
        proc.reset()


@pytest.fixture
def mock_processor(monkeypatch) -> Processor:
    """Provides a mock processor that doesn't require GPU."""

    class MockProcessor:
        def __init__(self, config=None):
            self.config = config or Presets.validation()
            self._initialized = False

        def initialize(self):
            self._initialized = True

        def process(self, data):
            # Return mock FFT output
            batch = self.config.batch
            bins = self.config.num_output_bins
            return np.random.randn(batch, bins).astype(np.float32)

        def reset(self):
            self._initialized = False

        @property
        def is_initialized(self):
            return self._initialized

    monkeypatch.setattr("ionosense_hpc.core.Processor", MockProcessor)
    return cast(Processor, MockProcessor())


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
    return cast(np.ndarray, make_sine(
        frequency=1000,
        duration=0.1,
        sample_rate=48000,
        amplitude=1.0,
        dtype=np.float32
    ))


@pytest.fixture
def test_batch_data() -> np.ndarray:
    """Generates standard dual-channel batch data for testing."""
    return cast(np.ndarray, make_test_batch(nfft=1024, batch=2, signal_type='sine', frequency=1000, seed=42))


@pytest.fixture
def test_signal_suite(seeded_rng: np.random.Generator) -> dict[str, np.ndarray]:
    """Provides a comprehensive suite of test signals."""
    from ionosense_hpc.utils.benchmark_utils import SignalGenerator

    gen = SignalGenerator(seed=42)
    return gen.generate_test_suite(nfft=1024, sample_rate=48000)


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


@pytest.fixture
def mock_benchmark_results(temp_benchmark_dir: Path) -> list[Path]:
    """Creates mock benchmark result files for testing reporting."""
    results = []

    for i in range(3):
        result = {
            "name": f"benchmark_{i}",
            "config": {"iterations": 1000},
            "context": {"hostname": "test-host"},
            "measurements": np.random.randn(100).tolist(),
            "statistics": {
                "mean": 100 + i * 10,
                "std": 5,
                "p99": 120 + i * 10
            },
            "passed": True
        }

        result_path = temp_benchmark_dir / "results" / f"result_{i}.json"
        with open(result_path, 'w') as f:
            json.dump(result, f)

        results.append(result_path)

    return results


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
    from ionosense_hpc.benchmarks.base import BaseBenchmark

    class TestBenchmark(BaseBenchmark):
        data: np.ndarray | None = None
        def setup(self):
            self.data = np.random.randn(100)

        def execute_iteration(self):
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


@pytest.fixture
def parameter_sweep_runner(yaml_sweep_config: Path, temp_benchmark_dir: Path):
    """Provides a configured parameter sweep for testing."""
    from ionosense_hpc.benchmarks.sweep import ParameterSweep

    sweep = ParameterSweep(str(yaml_sweep_config))
    sweep.config.output_dir = str(temp_benchmark_dir / "experiments")
    return sweep


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
    from ionosense_hpc.utils.benchmark_utils import ValidationHelper
    return ValidationHelper()


@pytest.fixture
def data_archiver(temp_benchmark_dir: Path):
    """Provides a DataArchiver instance for testing."""
    from ionosense_hpc.utils.benchmark_utils import DataArchiver
    return DataArchiver(temp_benchmark_dir / "archive")


# ============================================================================
# Research Workflow Fixtures
# ============================================================================

@pytest.fixture
def research_metadata() -> dict[str, Any]:
    """Provides standard research metadata for experiments."""
    return {
        "experiment_id": "exp_20250101_000000",
        "researcher": "Test User",
        "project": "ionosense-hpc",
        "tags": ["test", "validation"],
        "standards": ["RSE", "RE", "IEEE"],
        "version": "2.0.0"
    }


@pytest.fixture
def experiment_config(research_metadata: dict[str, Any], temp_benchmark_dir: Path):
    """Provides a complete experiment configuration."""
    return {
        "metadata": research_metadata,
        "output_dir": str(temp_benchmark_dir),
        "benchmarks": ["latency", "throughput", "accuracy"],
        "presets": ["realtime", "throughput"],
        "parameter_sweeps": [
            {
                "parameter": "nfft",
                "values": [512, 1024, 2048]
            }
        ],
        "reporting": {
            "format": "pdf",
            "include_raw_data": False
        }
    }


