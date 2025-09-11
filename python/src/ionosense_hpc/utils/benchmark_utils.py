"""
python/src/ionosense_hpc/utils/benchmark_utils.py
--------------------------------------------------------------------------------
Enhanced utility functions for research-grade benchmarking.
Provides deterministic signal generation, validation helpers, and data analysis.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import DTypeLike


class DeterministicGenerator:
    """
    Deterministic random number generator for reproducible benchmarks.
    
    Uses a combination of seed and context hashing to ensure perfect
    reproducibility across runs while allowing different random streams.
    """

    def __init__(self, base_seed: int = 42, context: str = "default"):
        """
        Initialize generator with base seed and context.
        
        Args:
            base_seed: Base random seed
            context: Context string for generating unique seeds
        """
        self.base_seed = base_seed
        self.context = context
        self._rng_cache: dict[str, np.random.Generator] = {}

    def get_rng(self, stream_id: str = "main") -> np.random.Generator:
        """
        Get a random number generator for a specific stream.
        
        Args:
            stream_id: Unique identifier for the random stream
            
        Returns:
            NumPy random generator with deterministic seed
        """
        if stream_id not in self._rng_cache:
            # Create deterministic seed from context and stream
            seed_str = f"{self.context}:{stream_id}:{self.base_seed}"
            seed_hash = hashlib.sha256(seed_str.encode()).digest()
            seed = int.from_bytes(seed_hash[:4], 'big') % (2**31)
            self._rng_cache[stream_id] = np.random.default_rng(seed)

        return self._rng_cache[stream_id]

    def reset(self) -> None:
        """Reset all cached RNG streams."""
        self._rng_cache.clear()


class SignalGenerator:
    """
    Advanced signal generator for comprehensive testing.
    
    Provides a wide variety of test signals with precise control over
    parameters and ensures bit-exact reproducibility.
    """

    def __init__(self, seed: int = 42):
        """Initialize with seed for reproducibility."""
        self.det_gen = DeterministicGenerator(seed, "signals")

    def generate_test_suite(
        self,
        nfft: int,
        sample_rate: int = 48000,
        dtype: DTypeLike = np.float32
    ) -> dict[str, np.ndarray]:
        """
        Generate comprehensive test signal suite.
        
        Args:
            nfft: FFT size / signal length
            sample_rate: Sample rate in Hz
            dtype: Output data type
            
        Returns:
            Dictionary of test signals
        """
        signals: dict[str, np.ndarray] = {}

        # Time vector
        t = np.arange(nfft) / sample_rate

        # Pure tones at specific frequencies
        test_frequencies = [
            100,    # Low frequency
            1000,   # Mid frequency
            5000,   # High frequency
            sample_rate // 4,  # Quarter Nyquist
            sample_rate // 2 - 1  # Near Nyquist
        ]

        for freq in test_frequencies:
            if freq < sample_rate // 2:
                signals[f'sine_{freq}Hz'] = np.sin(2 * np.pi * freq * t).astype(dtype)

        # Complex signals
        signals['dc'] = np.ones(nfft, dtype=dtype)
        signals['nyquist'] = np.cos(np.pi * np.arange(nfft)).astype(dtype)
        signals['impulse'] = np.zeros(nfft, dtype=dtype)
        signals['impulse'][0] = 1.0

        # Chirps
        signals['chirp_linear'] = self._generate_chirp(
            t, 100, sample_rate // 3, 'linear'
        ).astype(dtype)
        signals['chirp_log'] = self._generate_chirp(
            t, 100, sample_rate // 3, 'logarithmic'
        ).astype(dtype)

        # Noise types
        rng = self.det_gen.get_rng('noise')
        signals['white_noise'] = rng.standard_normal(nfft).astype(dtype)
        signals['pink_noise'] = self._generate_pink_noise(nfft, rng).astype(dtype)
        signals['brown_noise'] = self._generate_brown_noise(nfft, rng).astype(dtype)

        # Modulated signals
        carrier_freq = 5000
        mod_freq = 100
        signals['am_modulated'] = (
            np.sin(2 * np.pi * carrier_freq * t) *
            (1 + 0.5 * np.sin(2 * np.pi * mod_freq * t))
        ).astype(dtype)

        # Pulse trains
        signals['pulse_train'] = self._generate_pulse_train(
            nfft, period=nfft // 10, width=5
        ).astype(dtype)

        # Windowed tone burst
        tone_burst = np.sin(2 * np.pi * 2000 * t)
        window = np.zeros_like(tone_burst)
        window[nfft//4:3*nfft//4] = np.hamming(nfft//2)
        signals['tone_burst'] = (tone_burst * window).astype(dtype)

        return signals

    def _generate_chirp(
        self,
        t: np.ndarray,
        f0: float,
        f1: float,
        method: str
    ) -> np.ndarray:
        """Generate chirp signal."""
        if method == 'linear':
            phase = 2 * np.pi * (f0 * t + (f1 - f0) * t**2 / (2 * t[-1]))
        elif method == 'logarithmic':
            beta = t[-1] / np.log(f1 / f0)
            phase = 2 * np.pi * beta * f0 * (np.power(f1 / f0, t / t[-1]) - 1)
        else:
            phase = 2 * np.pi * f0 * t

        return cast(np.ndarray, np.sin(phase))

    def _generate_pink_noise(self, n: int, rng: np.random.Generator) -> np.ndarray:
        """Generate pink (1/f) noise."""
        # Generate white noise
        white = rng.standard_normal(n)

        # Apply 1/f filter in frequency domain
        fft = np.fft.rfft(white)
        freqs = np.fft.rfftfreq(n)
        freqs[0] = 1.0  # Avoid division by zero

        # Apply 1/sqrt(f) to amplitude (1/f to power)
        fft = fft / np.sqrt(freqs)

        # Convert back to time domain
        pink = np.fft.irfft(fft, n)

        # Normalize
        return cast(np.ndarray, pink / np.std(pink))

    def _generate_brown_noise(self, n: int, rng: np.random.Generator) -> np.ndarray:
        """Generate brown (1/f²) noise via integration."""
        white = rng.standard_normal(n)
        brown = np.cumsum(white)
        return cast(np.ndarray, brown / np.std(brown))

    def _generate_pulse_train(
        self,
        n: int,
        period: int,
        width: int,
        amplitude: float = 1.0
    ) -> np.ndarray:
        """Generate periodic pulse train."""
        signal = np.zeros(n)
        for i in range(0, n, period):
            end = min(i + width, n)
            signal[i:end] = amplitude
        return signal


class ValidationHelper:
    """
    Helper class for validating benchmark results.
    
    Provides statistical tests and validation methods for ensuring
    benchmark quality and detecting anomalies.
    """

    @staticmethod
    def validate_measurements(
        data: np.ndarray,
        name: str = "measurement",
        min_samples: int = 30,
        max_cv: float = 0.5,
        check_outliers: bool = True
    ) -> dict[str, Any]:
        """
        Validate a set of measurements.
        
        Args:
            data: Array of measurements
            name: Name for reporting
            min_samples: Minimum required samples
            max_cv: Maximum coefficient of variation
            check_outliers: Whether to check for outliers
            
        Returns:
            Validation results dictionary
        """
        results: dict[str, Any] = {
            'name': name,
            'valid': True,
            'warnings': [],
            'errors': []
        }

        # Check sample size
        if len(data) < min_samples:
            results['errors'].append(
                f"Insufficient samples: {len(data)} < {min_samples}"
            )
            results['valid'] = False

        # Check for NaN/Inf
        if np.any(np.isnan(data)):
            results['errors'].append("Data contains NaN values")
            results['valid'] = False

        if np.any(np.isinf(data)):
            results['errors'].append("Data contains Inf values")
            results['valid'] = False

        if not results['valid']:
            return results

        # Calculate statistics
        mean = np.mean(data)
        std = np.std(data)
        cv = std / mean if mean != 0 else float('inf')

        # Check coefficient of variation
        if cv > max_cv:
            results['warnings'].append(
                f"High variability: CV={cv:.2f} > {max_cv}"
            )

        # Check for outliers
        if check_outliers:
            z_scores = np.abs((data - mean) / (std + 1e-10))
            n_outliers = np.sum(z_scores > 3)

            if n_outliers > len(data) * 0.05:  # >5% outliers
                results['warnings'].append(
                    f"Many outliers detected: {n_outliers}/{len(data)}"
                )

        # Check for distribution anomalies
        try:
            from scipy import stats

            # Test for normality
            _, p_value = stats.normaltest(data)
            if p_value < 0.01:
                results['warnings'].append(
                    f"Non-normal distribution (p={p_value:.4f})"
                )

            # Check for multimodality
            hist, _ = np.histogram(data, bins='auto')
            peaks = ValidationHelper._find_peaks(hist)
            if len(peaks) > 1:
                results['warnings'].append(
                    f"Multimodal distribution detected ({len(peaks)} peaks)"
                )
        except ImportError:
            pass  # scipy not available

        results['statistics'] = {
            'mean': float(mean),
            'std': float(std),
            'cv': float(cv),
            'min': float(np.min(data)),
            'max': float(np.max(data)),
            'n_samples': len(data)
        }

        return results

    @staticmethod
    def _find_peaks(data: np.ndarray, min_height: float = 0.1) -> list[int]:
        """Simple peak detection."""
        peaks = []
        threshold = np.max(data) * min_height

        for i in range(1, len(data) - 1):
            if data[i] > threshold:
                if data[i] > data[i-1] and data[i] > data[i+1]:
                    peaks.append(i)

        return peaks

    @staticmethod
    def compare_distributions(
        data1: np.ndarray,
        data2: np.ndarray,
        test: str = 'ks'
    ) -> dict[str, Any]:
        """
        Compare two distributions for statistical difference.
        
        Args:
            data1: First dataset
            data2: Second dataset
            test: Statistical test ('ks', 'mw', 'ttest')
            
        Returns:
            Test results dictionary
        """
        try:
            from scipy import stats

            if test == 'ks':
                # Kolmogorov-Smirnov test
                statistic, p_value = stats.ks_2samp(data1, data2)
                test_name = "Kolmogorov-Smirnov"
            elif test == 'mw':
                # Mann-Whitney U test
                statistic, p_value = stats.mannwhitneyu(data1, data2)
                test_name = "Mann-Whitney U"
            elif test == 'ttest':
                # Student's t-test
                statistic, p_value = stats.ttest_ind(data1, data2)
                test_name = "Student's t"
            else:
                raise ValueError(f"Unknown test: {test}")

            return {
                'test': test_name,
                'statistic': float(statistic),
                'p_value': float(p_value),
                'significant': p_value < 0.05,
                'interpretation': "Different" if p_value < 0.05 else "Similar"
            }

        except ImportError:
            # Fallback without scipy
            mean1, mean2 = np.mean(data1), np.mean(data2)
            std1, std2 = np.std(data1), np.std(data2)

            # Simple comparison based on means and stds
            diff = abs(mean1 - mean2)
            pooled_std = np.sqrt((std1**2 + std2**2) / 2)

            return {
                'test': 'mean_comparison',
                'mean_diff': float(diff),
                'pooled_std': float(pooled_std),
                'significant': diff > 2 * pooled_std,
                'interpretation': "Different" if diff > 2 * pooled_std else "Similar"
            }


class DataArchiver:
    """
    Archive and manage benchmark data for reproducibility.
    
    Provides versioned storage of benchmark results with metadata
    for full reproducibility and traceability.
    """

    def __init__(self, base_dir: str | Path = "./benchmark_archive"):
        """Initialize archiver with base directory."""
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def archive_results(
        self,
        results: dict[str, Any],
        experiment_name: str,
        metadata: dict[str, Any] | None = None
    ) -> Path:
        """
        Archive benchmark results with full metadata.
        
        Args:
            results: Benchmark results to archive
            experiment_name: Name of the experiment
            metadata: Additional metadata
            
        Returns:
            Path to archived file
        """
        from datetime import datetime

        # Create versioned filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{experiment_name}_{timestamp}.json"

        # Create experiment directory
        exp_dir = self.base_dir / experiment_name
        exp_dir.mkdir(exist_ok=True)

        # Prepare archive data
        archive = {
            'experiment': experiment_name,
            'timestamp': timestamp,
            'results': results,
            'metadata': metadata or {},
            'environment': self._capture_environment()
        }

        # Save archive
        archive_path = exp_dir / filename
        with open(archive_path, 'w') as f:
            json.dump(archive, f, indent=2, default=str)

        # Update manifest
        self._update_manifest(experiment_name, filename)

        return archive_path

    def load_results(
        self,
        experiment_name: str,
        version: str | None = None
    ) -> dict[str, Any]:
        """
        Load archived results.
        
        Args:
            experiment_name: Name of the experiment
            version: Specific version/timestamp (latest if None)
            
        Returns:
            Archived results dictionary
        """
        exp_dir = self.base_dir / experiment_name

        if not exp_dir.exists():
            raise FileNotFoundError(f"No archive for experiment: {experiment_name}")

        if version is None:
            # Get latest version
            files = sorted(exp_dir.glob("*.json"))
            if not files:
                raise FileNotFoundError(f"No results in archive: {experiment_name}")
            archive_path = files[-1]
        else:
            archive_path = exp_dir / f"{experiment_name}_{version}.json"
            if not archive_path.exists():
                raise FileNotFoundError(f"Version not found: {version}")

        with open(archive_path) as f:
            return cast(dict[str, Any], json.load(f))

    def compare_versions(
        self,
        experiment_name: str,
        version1: str,
        version2: str
    ) -> dict[str, Any]:
        """
        Compare two versions of benchmark results.
        
        Args:
            experiment_name: Name of the experiment
            version1: First version
            version2: Second version
            
        Returns:
            Comparison results
        """
        results1 = self.load_results(experiment_name, version1)
        results2 = self.load_results(experiment_name, version2)

        comparison: dict[str, Any] = {
            'experiment': experiment_name,
            'version1': version1,
            'version2': version2,
            'differences': {}
        }

        # Compare key metrics
        # This is simplified - real implementation would be more sophisticated
        if 'results' in results1 and 'results' in results2:
            r1 = results1['results']
            r2 = results2['results']

            # Find common metrics
            keys1 = set(self._flatten_dict(r1).keys())
            keys2 = set(self._flatten_dict(r2).keys())
            common_keys = keys1 & keys2

            differences: dict[str, dict[str, float]] = {}
            for key in common_keys:
                v1 = self._get_nested_value(r1, key)
                v2 = self._get_nested_value(r2, key)

                if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                    diff = v2 - v1
                    pct_change = (diff / v1 * 100) if v1 != 0 else 0
                    differences[key] = {
                        'v1': v1,
                        'v2': v2,
                        'diff': diff,
                        'pct_change': pct_change
                    }

            comparison['differences'] = differences

        return comparison

    def _capture_environment(self) -> dict[str, Any]:
        """Capture current environment information."""
        import platform
        import sys

        return {
            'platform': platform.platform(),
            'python': sys.version,
            'cwd': str(Path.cwd()),
            'archive_version': '1.0'
        }

    def _update_manifest(self, experiment_name: str, filename: str) -> None:
        """Update experiment manifest."""
        manifest_path = self.base_dir / "manifest.json"

        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
        else:
            manifest = {}

        if experiment_name not in manifest:
            manifest[experiment_name] = []

        manifest[experiment_name].append({
            'filename': filename,
            'timestamp': filename.split('_')[-1].replace('.json', '')
        })

        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

    def _flatten_dict(self, d: dict, parent_key: str = '') -> dict:
        """Flatten nested dictionary."""
        items: list[tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key).items())
            else:
                items.append((new_key, v))
        return dict(items)

    def _get_nested_value(self, d: dict, key: str) -> Any:
        """Get value from nested dictionary using dot notation."""
        keys = key.split('.')
        value = d
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return None
        return value


# Convenience functions
def create_test_signals(
    nfft: int,
    sample_rate: int = 48000,
    seed: int = 42
) -> dict[str, np.ndarray]:
    """Create comprehensive test signal suite."""
    gen = SignalGenerator(seed)
    return gen.generate_test_suite(nfft, sample_rate)


def validate_benchmark_results(
    results: dict[str, Any],
    requirements: dict[str, Any] | None = None
) -> tuple[bool, list[str]]:
    """
    Validate benchmark results against requirements.
    
    Args:
        results: Benchmark results to validate
        requirements: Requirements dictionary
        
    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []

    # Default requirements
    if requirements is None:
        requirements = {
            'min_iterations': 100,
            'max_cv': 0.5,
            'max_error_rate': 0.01
        }

    # Check iteration count
    if 'n_iterations' in results:
        if results['n_iterations'] < requirements.get('min_iterations', 100):
            issues.append(
                f"Too few iterations: {results['n_iterations']} < {requirements['min_iterations']}"
            )

    # Check variability
    if 'cv' in results:
        if results['cv'] > requirements.get('max_cv', 0.5):
            issues.append(
                f"High variability: CV={results['cv']:.2f} > {requirements['max_cv']}"
            )

    # Check error rate
    if 'error_rate' in results:
        if results['error_rate'] > requirements.get('max_error_rate', 0.01):
            issues.append(
                f"High error rate: {results['error_rate']:.2%} > {requirements['max_error_rate']:.2%}"
            )

    return len(issues) == 0, issues
