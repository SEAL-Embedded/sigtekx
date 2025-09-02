"""Accuracy validation benchmarks against reference implementations."""

import json
import argparse
from typing import Dict, Any, Optional, Tuple

import numpy as np
from scipy import signal as scipy_signal
from scipy.fft import rfft

from ..core import Processor
from ..config import EngineConfig, Presets
from ..utils import make_sine, make_multitone, logger


def benchmark_accuracy(
    config: Optional[EngineConfig] = None,
    tolerance: float = 1e-5
) -> Dict[str, Any]:
    """Benchmark FFT accuracy against NumPy/SciPy reference."""
    if config is None:
        config = Presets.validation()
    
    test_signals = [
        {'type': 'sine', 'frequency': 1000, 'amplitude': 1.0},
        {'type': 'multitone', 'frequencies': [1000, 2000, 3000]},
        {'type': 'dc', 'value': 1.0},
    ]
    
    logger.info(f"Starting accuracy benchmark with {len(test_signals)} test signals")
    
    results = {
        'config': { 'nfft': config.nfft, 'batch': config.batch },
        'tolerance': tolerance,
        'tests': []
    }
    
    with Processor(config) as proc:
        for signal_spec in test_signals:
            test_data = _generate_test_signal(signal_spec, config)
            gpu_output = proc.process(test_data)
            ref_output = _compute_reference_fft(test_data, config)
            comparison = _compare_spectra(gpu_output, ref_output, tolerance)
            
            test_result = {
                'signal': signal_spec,
                'passed': comparison['passed'],
                'max_error': comparison['max_error'],
            }
            results['tests'].append(test_result)
            
            logger.info(f"  {signal_spec.get('type')}: {'PASS' if comparison['passed'] else 'FAIL'}")

    n_passed = sum(1 for t in results['tests'] if t['passed'])
    results['summary'] = {
        'total_tests': len(results['tests']),
        'passed': n_passed,
        'pass_rate': n_passed / len(results['tests']) if results['tests'] else 0
    }
    return results

def _generate_test_signal(spec: Dict[str, Any], config: EngineConfig) -> np.ndarray:
    """Generate test signal based on specification."""
    duration = config.nfft / config.sample_rate_hz
    samples = config.nfft * config.batch
    
    if spec['type'] == 'sine':
        signal = make_sine(spec['frequency'], duration, config.sample_rate_hz, spec.get('amplitude', 1.0))
    elif spec['type'] == 'multitone':
        signal = make_multitone(spec['frequencies'], duration, config.sample_rate_hz)
    elif spec['type'] == 'dc':
        signal = np.full(config.nfft, spec['value'], dtype=np.float32)
    else:
        signal = np.zeros(config.nfft, dtype=np.float32)
    
    return np.tile(signal, config.batch)[:samples]

def _compute_reference_fft(data: np.ndarray, config: EngineConfig) -> np.ndarray:
    """Compute reference FFT using SciPy."""
    data = data.reshape(config.batch, config.nfft)
    window = scipy_signal.windows.hann(config.nfft, sym=False)
    data_windowed = data * window
    fft_result = rfft(data_windowed, axis=1)
    return np.abs(fft_result)

def _compare_spectra(gpu: np.ndarray, ref: np.ndarray, tol: float) -> Dict[str, Any]:
    """Compare GPU output with reference."""
    rel_error = np.abs(gpu - ref) / (np.abs(ref) + 1e-10)
    return {
        'passed': np.max(rel_error) < tol,
        'max_error': float(np.max(rel_error)),
    }
    
# (Other functions like benchmark_window_accuracy remain the same)
def benchmark_window_accuracy(
    window_type: str = 'hann',
    nfft_sizes: Optional[list] = None
) -> Dict[str, Any]:
    return {} # Placeholder

def benchmark_numerical_stability(
    config: Optional[EngineConfig] = None,
    n_iterations: int = 1000
) -> Dict[str, Any]:
    return {} # Placeholder

# --- SCRIPT ENTRY POINT ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run accuracy benchmarks.")
    parser.add_argument("--preset", type=str, default="validation", help="Configuration preset to use.")
    parser.add_argument("--tolerance", type=float, default=1e-5, help="Relative error tolerance.")
    args = parser.parse_args()

    try:
        config = getattr(Presets, args.preset)()
    except AttributeError:
        print(f"Error: Preset '{args.preset}' not found.")
        exit(1)
        
    results = benchmark_accuracy(config, tolerance=args.tolerance)
    print(json.dumps(results, indent=2))
