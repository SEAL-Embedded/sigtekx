"""Accuracy validation benchmarks against reference implementations."""

from typing import Dict, Any, Optional
import json
import numpy as np
from scipy import signal as scipy_signal
from scipy.fft import rfft

from ..core import Processor
from ..config import EngineConfig, Presets
from ..utils import make_sine, make_multitone, logger


def benchmark_accuracy(
    config: Optional[EngineConfig] = None,
    test_signals: Optional[list] = None,
    tolerance: float = 1e-5
) -> Dict[str, Any]:
    """Benchmark FFT accuracy against NumPy/SciPy reference."""
    if config is None:
        config = Presets.validation()
    
    if test_signals is None:
        test_signals = [
            {'type': 'sine', 'frequency': 1000, 'amplitude': 1.0},
            {'type': 'multitone', 'frequencies': [1000, 2000, 3000]},
            {'type': 'dc', 'value': 1.0},
        ]
    
    logger.info(f"Starting accuracy benchmark with {len(test_signals)} test signals")
    
    results = {'config': config.model_dump(), 'tolerance': tolerance, 'tests': []}
    
    with Processor(config) as proc:
        for signal_spec in test_signals:
            test_data = _generate_test_signal(signal_spec, config)
            gpu_output = proc.process(test_data)
            ref_output = _compute_reference_fft(test_data, config)
            comparison = _compare_spectra(gpu_output, ref_output, tolerance)
            
            test_result = {'signal': signal_spec, **comparison}
            results['tests'].append(test_result)
            logger.info(f"  {signal_spec.get('type')}: {'PASS' if comparison['passed'] else 'FAIL'}")

    n_passed = sum(1 for t in results['tests'] if t['passed'])
    results['summary'] = {
        'total_tests': len(results['tests']),
        'passed': n_passed,
        'failed': len(results['tests']) - n_passed,
        'pass_rate': n_passed / len(results['tests']) if results['tests'] else 0.0
    }
    return results


def benchmark_window_accuracy(
    window_type: str = 'hann',
    nfft_sizes: Optional[list] = None
) -> Dict[str, Any]:
    """Validate window function implementation."""
    if nfft_sizes is None:
        nfft_sizes = [256, 1024, 4096]
    
    logger.info(f"Validating {window_type} window implementation")
    results = {'window_type': window_type, 'tests': []}
    
    for nfft in nfft_sizes:
        if window_type == 'hann':
            ref_window = scipy_signal.windows.hann(nfft, sym=False)
        else:
            raise ValueError(f"Unknown window type: {window_type}")
        
        test_signal = np.ones(nfft, dtype=np.float32)
        config = EngineConfig(nfft=nfft, batch=1, warmup_iters=0)
        
        with Processor(config) as proc:
            output = proc.process(test_signal)
            
            expected_dc_from_sum = np.sum(ref_window)
            actual_dc_from_fft = output[0, 0] * nfft  # Reverse cuFFT scaling
            
            error = abs(actual_dc_from_fft - expected_dc_from_sum) / expected_dc_from_sum
            
            test_result = {
                'nfft': nfft,
                'relative_error': float(error),
                'passed': error < 1e-4
            }
            results['tests'].append(test_result)
            logger.info(f"  nfft={nfft}: {'PASS' if test_result['passed'] else 'FAIL'} (error={error:.2e})")
    
    return results


def benchmark_numerical_stability(
    config: Optional[EngineConfig] = None,
    n_iterations: int = 100
) -> Dict[str, Any]:
    """Test numerical stability with edge cases."""
    if config is None:
        config = Presets.validation()
    
    logger.info("Testing numerical stability")
    edge_cases = {
        'zeros': np.zeros(config.nfft * config.batch, dtype=np.float32),
        'ones': np.ones(config.nfft * config.batch, dtype=np.float32),
    }
    
    results = {'config': config.model_dump(), 'edge_cases': []}
    
    with Processor(config) as proc:
        for case_name, test_data in edge_cases.items():
            outputs = [proc.process(test_data.copy()) for _ in range(n_iterations)]
            outputs_arr = np.array(outputs)
            
            max_std = np.max(np.std(outputs_arr, axis=0))
            stable = max_std < 1e-6
            
            results['edge_cases'].append({'case': case_name, 'stable': stable, 'max_std_dev': float(max_std)})
            logger.info(f"  Case '{case_name}': {'STABLE' if stable else 'UNSTABLE'}")
            
    results['all_stable'] = all(c['stable'] for c in results['edge_cases'])
    return results


def _generate_test_signal(spec: Dict[str, Any], config: EngineConfig) -> np.ndarray:
    duration = config.nfft / config.sample_rate_hz
    if spec['type'] == 'sine':
        signal = make_sine(spec['frequency'], duration, config.sample_rate_hz, spec.get('amplitude', 1.0))
    elif spec['type'] == 'multitone':
        signal = make_multitone(spec['frequencies'], duration, config.sample_rate_hz)
    elif spec['type'] == 'dc':
        signal = np.full(config.nfft, spec['value'], dtype=np.float32)
    else:
        signal = np.zeros(config.nfft, dtype=np.float32)
    return np.tile(signal, config.batch)


def _compute_reference_fft(data: np.ndarray, config: EngineConfig) -> np.ndarray:
    data = data.reshape(config.batch, config.nfft)

    window = scipy_signal.windows.hann(config.nfft, sym=False)
    data_windowed = data * window
    fft_result = rfft(data_windowed, axis=1)
    
    fft_result_scaled = np.abs(fft_result) / config.nfft
    return fft_result_scaled


def _compare_spectra(gpu_output: np.ndarray, ref_output: np.ndarray, tolerance: float) -> Dict[str, Any]:
    assert gpu_output.shape == ref_output.shape
    abs_error = np.abs(gpu_output - ref_output)
    rel_error = abs_error / (np.abs(ref_output) + 1e-10)
    signal_power = np.mean(ref_output**2)
    noise_power = np.mean(abs_error**2)
    snr_db = 10 * np.log10(signal_power / (noise_power + 1e-12))
    passed = np.max(rel_error) < tolerance
    return {
        'passed': bool(passed),
        'max_error': float(np.max(rel_error)),
        'mean_error': float(np.mean(abs_error)),
        'snr_db': float(snr_db)
    }

if __name__ == '__main__':
    print("Running Accuracy Benchmark...")
    acc_results = benchmark_accuracy()
    print(json.dumps(acc_results, indent=2, default=str))

    print("\nRunning Window Accuracy Benchmark...")
    win_results = benchmark_window_accuracy()
    print(json.dumps(win_results, indent=2, default=str))

    print("\nRunning Numerical Stability Benchmark...")
    stab_results = benchmark_numerical_stability()
    print(json.dumps(stab_results, indent=2, default=str))
