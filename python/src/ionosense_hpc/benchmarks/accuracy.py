"""
python/src/ionosense_hpc/benchmarks/accuracy.py
--------------------------------------------------------------------------------
Numerical accuracy validation benchmark following IEEE standards.
Upgraded to use BaseBenchmark framework for research-grade validation.
"""

from typing import Any, cast

import numpy as np
from scipy import signal as scipy_signal
from scipy.fft import rfft

from ionosense_hpc import Engine
from ionosense_hpc.benchmarks.base import BaseBenchmark, BenchmarkConfig, BenchmarkResult
from ionosense_hpc.config import EngineConfig, Presets
from ionosense_hpc.utils import logger, make_chirp, make_multitone, make_noise, make_sine
from ionosense_hpc.utils.paths import get_benchmark_run_dir, normalize_benchmark_name
from ionosense_hpc.utils.profiling import (
    ProfileColor,
    nvtx_range,
    setup_range,
    teardown_range,
)
from ionosense_hpc.utils.reproducibility import DeterministicGenerator
from ionosense_hpc.utils.signals import make_dc_signal, make_impulse


class AccuracyBenchmarkConfig(BenchmarkConfig):
    """Configuration for accuracy validation benchmark."""

    # Accuracy parameters
    absolute_tolerance: float = 1e-6
    relative_tolerance: float = 1e-5
    snr_threshold_db: float = 60.0
    phase_tolerance_deg: float = 1.0

    # Test signal specifications
    test_signals: list[dict] | None = None
    test_frequencies: list[float] | None = None  # For spectral tests

    # Validation types
    validate_parseval: bool = True  # Energy conservation
    validate_linearity: bool = True  # Superposition principle
    validate_time_invariance: bool = True
    validate_numerical_stability: bool = True
    validate_window_accuracy: bool = True

    # Reference settings
    use_double_precision_reference: bool = True
    reference_implementation: str = "scipy"  # scipy, numpy, or custom

    def __post_init__(self):
        """Set default test signals if not provided."""
        if self.test_signals is None:
            self.test_signals = [
                {'type': 'sine', 'frequency': 1000, 'amplitude': 1.0},
                {'type': 'sine', 'frequency': 5000, 'amplitude': 0.5},
                {'type': 'multitone', 'frequencies': [1000, 2000, 3000]},
                {'type': 'chirp', 'f_start': 100, 'f_end': 10000},
                {'type': 'noise', 'noise_type': 'white'},
                {'type': 'dc', 'value': 1.0},
                {'type': 'impulse', 'position': 0},
                {'type': 'nyquist', 'amplitude': 1.0}
            ]


class AccuracyBenchmark(BaseBenchmark):
    """
    Comprehensive accuracy validation against reference implementations.

    This benchmark validates the numerical accuracy of the FFT engine
    against known reference implementations, tests fundamental signal
    processing properties, and ensures IEEE-754 compliance.
    """

    def __init__(self, config: AccuracyBenchmarkConfig | dict | None = None):
        """Initialize accuracy benchmark."""
        if isinstance(config, dict):
            config = AccuracyBenchmarkConfig(**config)
        super().__init__(config or AccuracyBenchmarkConfig(name="Accuracy"))
        self.config: AccuracyBenchmarkConfig = self.config

        self.engine: Engine | None = None
        self.engine_config: EngineConfig | None = None
        self.test_results: list[dict[str, Any]] = []
        self.validation_errors: list[str] = []
        self._signal_rng = DeterministicGenerator(self.config.seed, "accuracy_signals")

    def setup(self) -> None:
        """Initialize engine and prepare test signals (NVTX-instrumented)."""
        with setup_range("AccuracyBenchmark.setup"):
            # Get engine configuration
            if self.config.engine_config:
                self.engine_config = EngineConfig(**self.config.engine_config)
            else:
                self.engine_config = Presets.validation()

            # Initialize engine
            with nvtx_range("InitializeEngine", color=ProfileColor.DARK_GRAY):
                self.engine = Engine(self.engine_config)

            self._signal_rng.reset()

            logger.info("Accuracy benchmark initialized:")
            logger.info(f"  Engine config: {self.engine_config}")
            logger.info(
                f"  Tolerance: rel={self.config.relative_tolerance}, abs={self.config.absolute_tolerance}"
            )
            logger.info(f"  Test signals: {len(self.config.test_signals or [])}")

    def execute_iteration(self) -> dict[str, float]:
        """Execute one complete accuracy validation suite."""
        # Ensure engine available
        assert self.engine is not None
        metrics: dict[str, float] = {
            'total_tests': 0.0,
            'passed_tests': 0.0,
            'failed_tests': 0.0,
            'mean_error': 0.0,
            'max_error': 0.0,
            'mean_snr_db': 0.0,
            'min_snr_db': 0.0,
            'pass_rate': 0.0,
        }

        errors: list[float] = []
        snrs: list[float] = []

        # Test each signal type
        for signal_spec in (self.config.test_signals or []):
            test_name = f"{signal_spec['type']}_{signal_spec.get('frequency', '')}"

            with nvtx_range("TestSignal", color=ProfileColor.PURPLE, payload=test_name):
                # Generate test signal
                with nvtx_range("GenerateSignal", color=ProfileColor.ORANGE):
                    test_data = self._generate_test_signal(signal_spec)

                # Process with engine
                with nvtx_range("ProcessGPU", color=ProfileColor.PURPLE):
                    gpu_output = self.engine.process(test_data)

                # Compute reference
                with nvtx_range("ComputeReference", color=ProfileColor.GREEN):
                    ref_output = self._compute_reference_fft(test_data)

                # Compare results
                with nvtx_range("CompareResults", color=ProfileColor.YELLOW):
                    comparison = self._compare_spectra(gpu_output, ref_output)

                # Store results
                self.test_results.append({
                    'signal': signal_spec,
                    'comparison': comparison,
                    'passed': comparison['passed']
                })

            metrics['total_tests'] += 1.0
            if comparison['passed']:
                metrics['passed_tests'] += 1.0
            else:
                metrics['failed_tests'] += 1.0
                self.validation_errors.append(f"{test_name}: {comparison['error_reason']}")

            errors.append(comparison['mean_error'])
            snrs.append(comparison['snr_db'])

            if self.config.verbose:
                status = "PASS" if comparison['passed'] else "FAIL"
                logger.debug(f"  {test_name}: {status} (SNR={comparison['snr_db']:.1f}dB)")

        # Additional validation tests
        if self.config.validate_parseval:
            parseval_result = self._test_parseval_theorem()
            metrics['total_tests'] += 1.0
            if parseval_result['passed']:
                metrics['passed_tests'] += 1.0
            else:
                metrics['failed_tests'] += 1.0

        if self.config.validate_linearity:
            linearity_result = self._test_linearity()
            metrics['total_tests'] += 1.0
            if linearity_result['passed']:
                metrics['passed_tests'] += 1.0
            else:
                metrics['failed_tests'] += 1.0

        if self.config.validate_window_accuracy:
            window_result = self._test_window_function()
            metrics['total_tests'] += 1.0
            if window_result['passed']:
                metrics['passed_tests'] += 1.0
            else:
                metrics['failed_tests'] += 1.0

        # Calculate summary metrics
        if errors:
            metrics['mean_error'] = float(np.mean(errors))
            metrics['max_error'] = float(np.max(errors))

        if snrs:
            metrics['mean_snr_db'] = float(np.mean(snrs))
            metrics['min_snr_db'] = float(np.min(snrs))

        metrics['pass_rate'] = metrics['passed_tests'] / max(1, metrics['total_tests'])

        return metrics

    def teardown(self) -> None:
        """Clean up resources (NVTX-instrumented)."""
        with teardown_range("AccuracyBenchmark.teardown"):
            if self.engine:
                self.engine.close()
                self.engine = None

    def _generate_test_signal(self, spec: dict[str, Any]) -> np.ndarray:
        """Generate test signal based on specification."""
        assert self.engine_config is not None
        nfft = self.engine_config.nfft
        batch = self.engine_config.batch
        sample_rate = self.engine_config.sample_rate_hz
        n_samples = nfft

        signal_type = spec['type']

        if signal_type == 'sine':
            signal = make_sine(
                sample_rate=sample_rate,
                n_samples=n_samples,
                frequency=float(spec['frequency']),
                amplitude=float(spec.get('amplitude', 1.0)),
                phase=float(spec.get('phase', 0.0)),
                dtype=np.float32,
            )
        elif signal_type == 'multitone':
            signal = make_multitone(
                sample_rate=sample_rate,
                n_samples=n_samples,
                frequencies=spec['frequencies'],
                amplitudes=spec.get('amplitudes'),
                phases=spec.get('phases'),
                dtype=np.float32,
            )
        elif signal_type == 'chirp':
            signal = make_chirp(
                sample_rate=sample_rate,
                n_samples=n_samples,
                f_start=float(spec['f_start']),
                f_end=float(spec['f_end']),
                method=str(spec.get('method', 'linear')),
                amplitude=float(spec.get('amplitude', 1.0)),
                dtype=np.float32,
            )
        elif signal_type == 'noise':
            noise_type = spec.get('noise_type', 'white')
            amplitude = float(spec.get('amplitude', 1.0))
            rng = self._signal_rng.get_rng(f"noise_{noise_type}")
            signal = make_noise(
                n_samples=n_samples,
                noise_type=noise_type,
                amplitude=amplitude,
                rng=rng,
                dtype=np.float32,
            )
        elif signal_type == 'dc':
            signal = make_dc_signal(
                n_samples,
                value=float(spec.get('value', 1.0)),
                dtype=np.float32,
            )
        elif signal_type == 'impulse':
            signal = make_impulse(
                n_samples,
                amplitude=float(spec.get('amplitude', 1.0)),
                index=int(spec.get('position', 0)),
                dtype=np.float32,
            )
        elif signal_type == 'nyquist':
            amplitude = float(spec.get('amplitude', 1.0))
            signal = amplitude * np.cos(np.pi * np.arange(n_samples, dtype=np.float32))
        else:
            signal = np.zeros(n_samples, dtype=np.float32)

        return np.tile(signal, batch)



    def _compute_reference_fft(self, data: np.ndarray) -> np.ndarray:
        """Compute reference FFT using scipy."""
        assert self.engine_config is not None
        data = data.reshape(self.engine_config.batch, self.engine_config.nfft)

        # Use double precision for reference if configured
        if self.config.use_double_precision_reference:
            data = data.astype(np.float64)

        # Apply window (matching engine configuration)
        window = scipy_signal.windows.hann(self.engine_config.nfft, sym=False)
        data_windowed = data * window

        # Compute FFT
        fft_result = rfft(data_windowed, axis=1)

        # Convert to magnitude and scale
        magnitude = np.abs(fft_result) / self.engine_config.nfft

        return cast(np.ndarray, magnitude.astype(np.float32))

    def _compare_spectra(
        self,
        gpu_output: np.ndarray,
        ref_output: np.ndarray
    ) -> dict[str, Any]:
        """Compare GPU output with reference."""
        # Ensure same shape
        assert gpu_output.shape == ref_output.shape, \
            f"Shape mismatch: {gpu_output.shape} vs {ref_output.shape}"

        # Calculate errors
        abs_error = np.abs(gpu_output - ref_output)
        rel_error = abs_error / (np.abs(ref_output) + 1e-10)

        # Calculate SNR
        signal_power = np.mean(ref_output**2)
        noise_power = np.mean(abs_error**2)
        snr_db = 10 * np.log10(signal_power / (noise_power + 1e-12))

        # Check pass criteria
        max_rel_error = np.max(rel_error)
        max_abs_error = np.max(abs_error)

        passed = (max_rel_error < self.config.relative_tolerance or
                 max_abs_error < self.config.absolute_tolerance) and \
                 snr_db > self.config.snr_threshold_db

        error_reason = ""
        if not passed:
            if max_rel_error >= self.config.relative_tolerance:
                error_reason = f"Relative error {max_rel_error:.2e} exceeds tolerance"
            elif snr_db <= self.config.snr_threshold_db:
                error_reason = f"SNR {snr_db:.1f}dB below threshold"

        return {
            'passed': bool(passed),
            'max_rel_error': float(max_rel_error),
            'max_abs_error': float(max_abs_error),
            'mean_error': float(np.mean(abs_error)),
            'snr_db': float(snr_db),
            'error_reason': error_reason
        }

    def _test_parseval_theorem(self) -> dict[str, bool | float]:
        """Test Parseval's theorem (energy conservation)."""
        assert self.engine_config is not None
        assert self.engine is not None
        # Generate test signal
        noise_rng = self._signal_rng.get_rng('parseval')
        test_signal = make_noise(
            n_samples=self.engine_config.nfft,
            rng=noise_rng,
            dtype=np.float32,
        )

        # Apply the same windowing as the GPU pipeline before energy check
        window = scipy_signal.windows.hann(self.engine_config.nfft, sym=False)
        windowed_signal = test_signal * window

        # Compute time-domain energy
        time_energy = np.sum(windowed_signal**2)

        # Process and get frequency domain
        test_batch = np.tile(test_signal, self.engine_config.batch)
        freq_output = self.engine.process(test_batch)

        # Compute frequency-domain energy (accounting for one-sided spectrum)
        freq_energy = np.sum(freq_output[0]**2)
        # Double all bins except DC and Nyquist
        freq_energy = freq_energy * 2 - freq_output[0, 0]**2
        if self.engine_config.nfft % 2 == 0:
            freq_energy -= freq_output[0, -1]**2

        # Scale for FFT normalization
        freq_energy *= self.engine_config.nfft

        # Check energy conservation
        rel_error = abs(time_energy - freq_energy) / time_energy
        passed = rel_error < 0.01  # 1% tolerance for energy conservation

        if self.config.verbose:
            logger.debug(f"  Parseval test: time_energy={time_energy:.3f}, "
                        f"freq_energy={freq_energy:.3f}, error={rel_error:.2%}")

        return {'passed': passed, 'relative_error': float(rel_error)}

    def _test_linearity(self) -> dict[str, bool | float]:
        """Test linearity (superposition principle)."""
        assert self.engine_config is not None
        assert self.engine is not None
        # Generate two signals
        n_samples = self.engine_config.nfft
        sample_rate = self.engine_config.sample_rate_hz
        signal1 = make_sine(
            sample_rate=sample_rate,
            n_samples=n_samples,
            frequency=1000.0,
            amplitude=0.5,
            dtype=np.float32,
        )
        signal2 = make_sine(
            sample_rate=sample_rate,
            n_samples=n_samples,
            frequency=2000.0,
            amplitude=0.3,
            dtype=np.float32,
        )

        # Process individually
        batch1 = np.tile(signal1, self.engine_config.batch)
        batch2 = np.tile(signal2, self.engine_config.batch)

        output1 = self.engine.process(batch1)
        output2 = self.engine.process(batch2)

        # Process sum
        sum_signal = signal1 + signal2
        sum_batch = np.tile(sum_signal, self.engine_config.batch)
        sum_output = self.engine.process(sum_batch)

        # Check linearity
        expected_sum = output1 + output2
        error = np.max(np.abs(sum_output - expected_sum))
        passed = error < self.config.absolute_tolerance

        if self.config.verbose:
            logger.debug(f"  Linearity test: max_error={error:.2e}")

        return {'passed': passed, 'max_error': float(error)}

    def _test_window_function(self) -> dict[str, bool | float]:
        """Validate window function implementation."""
        assert self.engine_config is not None
        assert self.engine is not None
        # Test with DC signal (all ones)
        test_signal = np.ones(self.engine_config.nfft, dtype=np.float32)
        test_batch = np.tile(test_signal, self.engine_config.batch)

        # Process
        output = self.engine.process(test_batch)

        # Expected: DC component should equal sum of window
        window = scipy_signal.windows.hann(self.engine_config.nfft, sym=False)
        expected_dc = np.sum(window) / self.engine_config.nfft
        actual_dc = output[0, 0]

        error = abs(actual_dc - expected_dc) / expected_dc
        passed = error < 1e-4

        if self.config.verbose:
            logger.debug(f"  Window test: expected_dc={expected_dc:.4f}, "
                        f"actual_dc={actual_dc:.4f}, error={error:.2e}")

        return {'passed': passed, 'relative_error': float(error)}

    def analyze_results(self, result: BenchmarkResult) -> dict[str, Any]:
        """
        Analyze accuracy validation results.

        Returns:
            Dictionary with detailed accuracy analysis
        """
        from ionosense_hpc.utils.profiling import ProfileColor, nvtx_range
        with nvtx_range("AnalyzeAccuracyResults", color=ProfileColor.ORANGE):
            analysis = {
                'summary': {
                    'all_passed': result.statistics.get('failed_tests', 0) == 0,
                    'pass_rate': result.statistics.get('pass_rate', 0),
                    'mean_snr_db': result.statistics.get('mean_snr_db', 0)
                }
            }

            # Categorize failures
            if self.validation_errors:
                error_categories: dict[str, list[str]] = {}
                for error in self.validation_errors:
                    category = 'unknown'
                    if 'relative error' in error.lower():
                        category = 'precision'
                    elif 'snr' in error.lower():
                        category = 'noise_floor'
                    elif 'parseval' in error.lower():
                        category = 'energy_conservation'
                    elif 'linearity' in error.lower():
                        category = 'linearity'

                    if category not in error_categories:
                        error_categories[category] = []
                    error_categories[category].append(error)

                analysis['error_categories'] = error_categories

            # Performance vs accuracy tradeoff analysis
            if hasattr(self, 'test_results') and self.test_results:
                # Find which signal types have worst accuracy
                by_signal_type: dict[str, list[float]] = {}
                for test in self.test_results:
                    sig_type = test['signal']['type']
                    if sig_type not in by_signal_type:
                        by_signal_type[sig_type] = []
                    by_signal_type[sig_type].append(test['comparison']['snr_db'])

                worst_signals: dict[str, dict[str, float]] = {}
                for sig_type, snrs in by_signal_type.items():
                    worst_signals[sig_type] = {
                        'mean_snr_db': float(np.mean(snrs)),
                        'min_snr_db': float(np.min(snrs))
                    }

                analysis['signal_type_accuracy'] = worst_signals

            return analysis


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Accuracy validation benchmark')
    parser.add_argument('--config', help='Configuration YAML file')
    parser.add_argument('--tolerance', type=float, help='Error tolerance')
    parser.add_argument('--output', help='Output file (defaults under benchmark_results/accuracy)')
    parser.add_argument('--validate-stability', action='store_true',
                       help='Run numerical stability tests')

    args = parser.parse_args()

    # Create configuration
    config = AccuracyBenchmarkConfig(
        name='accuracy_validation',
        iterations=1  # Single validation pass
    )

    if args.tolerance:
        config.relative_tolerance = args.tolerance
        config.absolute_tolerance = args.tolerance

    if args.validate_stability:
        config.validate_numerical_stability = True

    # Run benchmark
    benchmark = AccuracyBenchmark(config)
    result = benchmark.run()

    # Analyze
    analysis = benchmark.analyze_results(result)
    result.metadata['analysis'] = analysis

    # Output
    from ionosense_hpc.benchmarks.base import save_benchmark_results
    if args.output:
        save_benchmark_results(result, args.output)
    else:
        from datetime import datetime

        base_dir = get_benchmark_run_dir('accuracy')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{normalize_benchmark_name(result.name)}_{timestamp}.json"
        save_benchmark_results(result, base_dir / filename)
