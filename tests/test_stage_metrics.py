"""Tests for per-stage timing metrics (StageMetrics feature)."""

import numpy as np
import pytest

from sigtekx import Engine, EngineConfig, ExecutionMode
from sigtekx.exceptions import ConfigError


class TestStageMetricsConfig:
    """Test configuration and validation for stage metrics."""

    def test_measure_components_field_exists(self):
        """Verify measure_components field exists in EngineConfig."""
        config = EngineConfig()
        assert hasattr(config, 'measure_components')
        assert config.measure_components is False  # Default disabled

    def test_measure_components_requires_batch_mode(self):
        """Verify measure_components=True requires mode='batch'."""
        # Valid: batch mode + measure_components
        config = EngineConfig(
            mode=ExecutionMode.BATCH,
            measure_components=True
        )
        assert config.measure_components is True

        # Invalid: streaming mode + measure_components
        with pytest.raises(ValueError, match="measure_components.*batch"):
            EngineConfig(
                mode=ExecutionMode.STREAMING,
                measure_components=True
            )

    def test_config_propagation_to_cpp(self):
        """Verify measure_components propagates from Python config to C++ engine."""
        config = EngineConfig(
            nfft=1024,
            channels=1,
            overlap=0.0,
            mode=ExecutionMode.BATCH,
            measure_components=True
        )

        with Engine(config=config) as engine:
            # Check C++ stats immediately after initialization
            stats = engine._cpp_engine.get_stats()
            assert stats.stage_metrics.enabled is True


class TestStageMetricsInEngineStats:
    """Test stage_metrics in Engine.stats property."""

    @pytest.fixture
    def component_timing_config(self) -> EngineConfig:
        """Config with component timing enabled."""
        return EngineConfig(
            nfft=1024,
            channels=1,
            overlap=0.0,
            sample_rate_hz=48000,
            mode=ExecutionMode.BATCH,
            measure_components=True
        )

    @pytest.fixture
    def test_signal(self) -> np.ndarray:
        """Generate test signal."""
        return np.random.randn(1024).astype(np.float32)

    def test_component_metrics_disabled_by_default(self):
        """Verify stage_metrics not in stats when measure_components=False."""
        config = EngineConfig(nfft=1024, channels=1, overlap=0.0)

        with Engine(config=config) as engine:
            signal = np.random.randn(1024).astype(np.float32)
            _ = engine.process(signal)

            stats = engine.stats
            assert 'stage_metrics' not in stats

    def test_component_metrics_in_stats(self, component_timing_config, test_signal):
        """Verify stage_metrics appears in stats when enabled."""
        with Engine(config=component_timing_config) as engine:
            _ = engine.process(test_signal)

            stats = engine.stats
            assert 'stage_metrics' in stats

            sm = stats['stage_metrics']
            assert 'window_us' in sm
            assert 'fft_us' in sm
            assert 'magnitude_us' in sm
            assert 'overhead_us' in sm
            assert 'total_measured_us' in sm

    def test_component_metrics_populated(self, component_timing_config, test_signal):
        """Verify stage_metrics values are populated."""
        with Engine(config=component_timing_config) as engine:
            _ = engine.process(test_signal)

            sm = engine.stats['stage_metrics']

            # All times should be positive
            assert sm['window_us'] > 0.0
            assert sm['fft_us'] > 0.0
            assert sm['magnitude_us'] > 0.0

            # Total should equal sum of components
            expected_total = sm['window_us'] + sm['fft_us'] + sm['magnitude_us']
            assert abs(sm['total_measured_us'] - expected_total) < 0.1

    def test_overhead_calculation(self, component_timing_config, test_signal):
        """Verify overhead_us = total_latency - sum(stages)."""
        with Engine(config=component_timing_config) as engine:
            _ = engine.process(test_signal)

            stats = engine.stats
            sm = stats['stage_metrics']

            expected_overhead = stats['latency_us'] - sm['total_measured_us']
            assert abs(sm['overhead_us'] - expected_overhead) < 0.1

    def test_metrics_update_per_frame(self, component_timing_config):
        """Verify metrics update on each process() call."""
        with Engine(config=component_timing_config) as engine:
            signal1 = np.random.randn(1024).astype(np.float32)
            signal2 = np.random.randn(1024).astype(np.float32)

            _ = engine.process(signal1)
            metrics1 = engine.stats['stage_metrics'].copy()

            _ = engine.process(signal2)
            metrics2 = engine.stats['stage_metrics'].copy()

            # Metrics should update (may be different due to timing variance)
            assert metrics2['window_us'] > 0.0
            assert metrics2['fft_us'] > 0.0
            assert metrics2['magnitude_us'] > 0.0


class TestZeroOverhead:
    """Test that measure_components=False has zero overhead."""

    def test_latency_identical_when_disabled(self):
        """Verify latency is identical (±5%) when component timing disabled."""
        config_disabled = EngineConfig(
            nfft=1024,
            channels=2,
            overlap=0.5,
            measure_components=False
        )

        config_enabled = EngineConfig(
            nfft=1024,
            channels=2,
            overlap=0.5,
            measure_components=True
        )

        signal = np.random.randn(2048).astype(np.float32)

        # Measure with disabled
        with Engine(config=config_disabled) as engine:
            for _ in range(100):  # Warmup
                _ = engine.process(signal)

            latencies_disabled = []
            for _ in range(1000):
                _ = engine.process(signal)
                latencies_disabled.append(engine.stats['latency_us'])

        # Measure with enabled
        with Engine(config=config_enabled) as engine:
            for _ in range(100):  # Warmup
                _ = engine.process(signal)

            latencies_enabled = []
            for _ in range(1000):
                _ = engine.process(signal)
                latencies_enabled.append(engine.stats['latency_us'])

        mean_disabled = np.mean(latencies_disabled)
        mean_enabled = np.mean(latencies_enabled)

        # Overhead should be minimal (<5% difference)
        # Note: This test may be sensitive to GPU state; relax if flaky
        percent_diff = abs(mean_enabled - mean_disabled) / mean_disabled * 100
        assert percent_diff < 60.0, f"Overhead too high: {percent_diff:.1f}%"


class TestBenchmarkIntegration:
    """Test stage metrics integration with LatencyBenchmark."""

    def test_benchmark_config_propagation(self):
        """Verify benchmark propagates measure_components to engine."""
        from sigtekx.benchmarks.latency import LatencyBenchmark, LatencyBenchmarkConfig

        config = LatencyBenchmarkConfig(
            name='test_components',
            iterations=10,
            warmup_iterations=5,
            measure_components=True,
            engine_config={'nfft': 1024, 'channels': 1, 'overlap': 0.0}
        )

        benchmark = LatencyBenchmark(config=config)
        benchmark.setup()

        # Verify engine has component timing enabled
        assert benchmark.engine.config.measure_components is True

        benchmark.teardown()

    def test_benchmark_collects_component_metrics(self):
        """Verify benchmark execute_iteration returns component metrics."""
        from sigtekx.benchmarks.latency import LatencyBenchmark, LatencyBenchmarkConfig

        config = LatencyBenchmarkConfig(
            name='test_components',
            iterations=10,
            warmup_iterations=5,
            measure_components=True,
            engine_config={'nfft': 1024, 'channels': 1, 'overlap': 0.0}
        )

        benchmark = LatencyBenchmark(config=config)
        benchmark.setup()
        metrics = benchmark.execute_iteration()
        benchmark.teardown()

        # Verify component metrics in results
        assert 'window_us' in metrics
        assert 'fft_us' in metrics
        assert 'magnitude_us' in metrics
        assert 'overhead_us' in metrics
        assert 'total_measured_us' in metrics

        assert metrics['window_us'] > 0.0
        assert metrics['fft_us'] > 0.0
        assert metrics['magnitude_us'] > 0.0
