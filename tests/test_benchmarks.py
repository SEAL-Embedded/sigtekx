"""
Regression tests for the benchmarking core primitives.

Legacy orchestration (suite/sweep/workflow) has been retired in favour of the
Hydra/Snakemake toolchain; these tests now focus solely on the reusable
building blocks that remain in the library.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from omegaconf import OmegaConf

from sigtekx.benchmarks import (
    BaseBenchmark,
    BenchmarkConfig,
    BenchmarkContext,
    BenchmarkResult,
    calculate_statistics,
    load_benchmark_config,
    save_benchmark_results,
)


class TestBaseBenchmark:
    """Validate the base benchmarking abstractions."""

    def test_benchmark_config_validation(self):
        config = BenchmarkConfig(name="test", iterations=100)
        assert config.name == "test"
        assert config.iterations == 100
        assert config.confidence_level == 0.95

        with pytest.raises(ValueError):
            BenchmarkConfig(name="test", iterations=-1)

        with pytest.raises(ValueError):
            BenchmarkConfig(name="test", confidence_level=1.5)

    def test_benchmark_context_creation(self):
        context = BenchmarkContext()

        assert context.timestamp
        assert context.hostname
        assert 'python_version' in context.platform_info
        assert context.environment_hash

        context_dict = context.to_dict()
        assert isinstance(context_dict, dict)
        assert 'timestamp' in context_dict

    def test_benchmark_result_statistics(self):
        measurements = np.random.randn(100) * 10 + 50

        result = BenchmarkResult(
            name="test",
            config={},
            context=BenchmarkContext(),
            measurements=measurements,
        )

        assert 'mean' in result.statistics
        assert 'std' in result.statistics
        assert 'p99' in result.statistics
        assert abs(result.statistics['mean'] - 50) < 5

    def test_calculate_statistics(self):
        data = np.concatenate([
            np.random.randn(95) * 5 + 100,
            [1000, 2000, 3000, -1000, -2000],
        ])

        config = BenchmarkConfig(name="test", outlier_threshold=3.0)
        stats = calculate_statistics(data, config)

        assert stats['n'] == 100
        assert stats['n_outliers'] > 0
        assert abs(stats['mean'] - 100) < 10
        assert 'ci_lower' in stats
        assert 'ci_upper' in stats

    def test_benchmark_implementation(self, benchmark_runner):
        result = benchmark_runner.run()

        assert result.passed
        assert result.name == "test_runner"
        assert len(result.measurements) == 10
        assert result.statistics['n'] == 10

    def test_benchmark_validation(self):
        class TestBenchmark(BaseBenchmark):
            def setup(self):
                pass

            def execute_iteration(self):
                return 1.0

            def teardown(self):
                pass

            def validate_environment(self):
                return False, ["Test validation failure"]

        config = BenchmarkConfig(name="test", iterations=1)
        benchmark = TestBenchmark(config)

        result = benchmark.run()
        assert not result.passed
        assert "Test validation failure" in result.errors

    def test_save_and_load_results(self, sample_benchmark_result, temp_data_dir):
        result_path = temp_data_dir / "test_result.json"
        save_benchmark_results(sample_benchmark_result, result_path)

        assert result_path.exists()

        with open(result_path) as handle:
            loaded = json.load(handle)

        assert loaded[0]['name'] == sample_benchmark_result.name
        assert 'measurements' in loaded[0]
        assert 'statistics' in loaded[0]

    def test_load_benchmark_config_yaml(self, yaml_benchmark_config):
        config_dict = load_benchmark_config(yaml_benchmark_config)

        assert config_dict['name'] == "test_experiment"
        assert config_dict['iterations'] == 500
        assert 'engine_config' in config_dict


class TestBenchmarkWarmupConfiguration:
    """Ensure benchmark configs include warmup defaults and allow overrides."""

    def test_throughput_config_has_warmup(self):
        config = OmegaConf.load(Path("experiments/conf/benchmark/throughput.yaml"))

        assert 'warmup_iterations' in config
        assert int(config.warmup_iterations) >= 1
        assert float(config.warmup_duration_s) >= 1.0

    def test_accuracy_config_has_warmup(self):
        config = OmegaConf.load(Path("experiments/conf/benchmark/accuracy.yaml"))

        assert 'warmup_iterations' in config
        assert int(config.warmup_iterations) >= 1

    def test_warmup_override_allows_zero(self):
        config = OmegaConf.create({
            "warmup_iterations": 0,
            "iterations": 10,
        })

        assert config.warmup_iterations == 0
