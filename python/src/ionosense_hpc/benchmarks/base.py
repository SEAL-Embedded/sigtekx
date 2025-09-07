"""
python/src/ionosense_hpc/benchmarks/base.py
--------------------------------------------------------------------------------
Abstract base class and utilities for research-grade benchmarking following
RSE/RE/IEEE standards for reproducibility and statistical rigor.
"""

import abc
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
import yaml
from pydantic import BaseModel, Field

from ionosense_hpc.utils import logger

T = TypeVar('T')


@dataclass
class BenchmarkContext:
    """Immutable context capturing complete execution environment."""

    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    hostname: str = field(default_factory=platform.node)
    platform_info: dict = field(default_factory=lambda: {
        'system': platform.system(),
        'release': platform.release(),
        'version': platform.version(),
        'machine': platform.machine(),
        'processor': platform.processor(),
        'python_version': sys.version,
        'python_implementation': platform.python_implementation()
    })
    cuda_info: dict = field(default_factory=dict)
    git_info: dict = field(default_factory=dict)
    package_versions: dict = field(default_factory=dict)
    environment_hash: str = field(default="")

    def __post_init__(self):
        """Populate context with runtime information."""
        self.cuda_info = self._get_cuda_info()
        self.git_info = self._get_git_info()
        self.package_versions = self._get_package_versions()
        self.environment_hash = self._compute_environment_hash()

    def _get_cuda_info(self) -> dict:
        """Query CUDA runtime and device information."""
        try:
            from ionosense_hpc.utils import device_info, gpu_count
            return {
                'gpu_count': gpu_count(),
                'devices': [device_info(i) for i in range(gpu_count())],
                'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES', 'all')
            }
        except Exception as e:
            logger.warning(f"Failed to get CUDA info: {e}")
            return {'error': str(e)}

    def _get_git_info(self) -> dict:
        """Get Git repository information for reproducibility."""
        try:
            return {
                'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip(),
                'branch': subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).decode().strip(),
                'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain']).decode().strip()),
                'remote': subprocess.check_output(['git', 'remote', 'get-url', 'origin']).decode().strip()
            }
        except Exception:
            return {'available': False}

    def _get_package_versions(self) -> dict:
        """Get versions of key dependencies."""
        packages = {}
        for pkg in ['numpy', 'scipy', 'pydantic', 'ionosense_hpc']:
            try:
                mod = __import__(pkg)
                packages[pkg] = getattr(mod, '__version__', 'unknown')
            except ImportError:
                packages[pkg] = 'not installed'
        return packages

    def _compute_environment_hash(self) -> str:
        """Compute deterministic hash of the environment."""
        env_str = json.dumps({
            'platform': self.platform_info,
            'cuda': self.cuda_info,
            'packages': self.package_versions
        }, sort_keys=True)
        return hashlib.sha256(env_str.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'timestamp': self.timestamp,
            'hostname': self.hostname,
            'platform': self.platform_info,
            'cuda': self.cuda_info,
            'git': self.git_info,
            'packages': self.package_versions,
            'environment_hash': self.environment_hash
        }


@dataclass
class BenchmarkResult:
    """Standardized result container for all benchmarks."""

    name: str
    config: dict
    context: BenchmarkContext
    measurements: np.ndarray
    statistics: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    passed: bool = True
    errors: list = field(default_factory=list)

    def __post_init__(self):
        """Calculate statistics if not provided."""
        if len(self.measurements) > 0 and not self.statistics:
            self.statistics = calculate_statistics(self.measurements)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'config': self.config,
            'context': self.context.to_dict(),
            'measurements': self.measurements.tolist() if isinstance(self.measurements, np.ndarray) else self.measurements,
            'statistics': self.statistics,
            'metadata': self.metadata,
            'passed': self.passed,
            'errors': self.errors
        }


class BenchmarkConfig(BaseModel):
    """Configuration schema for benchmark execution."""

    # Core parameters
    name: str = Field(description="Benchmark name")
    iterations: int = Field(default=1000, gt=0, description="Number of iterations")
    warmup_iterations: int = Field(default=0, ge=0, description="Warmup iterations")
    timeout_seconds: float = Field(default=300.0, gt=0, description="Timeout per iteration")

    # Statistical parameters
    confidence_level: float = Field(default=0.95, gt=0, lt=1, description="Confidence level for intervals")
    outlier_threshold: float = Field(default=3.0, gt=0, description="Z-score threshold for outliers")
    min_samples: int = Field(default=30, gt=0, description="Minimum samples for statistics")

    # Engine configuration
    engine_config: dict = Field(default_factory=dict, description="Engine configuration override")

    # Reproducibility
    seed: int = Field(default=42, description="Random seed for determinism")
    deterministic: bool = Field(default=True, description="Enable deterministic mode")

    # Output control
    save_raw_data: bool = Field(default=True, description="Save raw measurements")
    output_format: str = Field(default="json", description="Output format (json, csv, hdf5)")
    verbose: bool = Field(default=True, description="Verbose output")


class BaseBenchmark(abc.ABC):
    """
    Abstract base class for all benchmarks following RSE/RE standards.
    
    This class enforces a standardized structure and provides common
    functionality for reproducibility, statistics, and reporting.
    """

    def __init__(self, config: BenchmarkConfig | dict | None = None):
        """Initialize benchmark with configuration."""
        if isinstance(config, dict):
            config = BenchmarkConfig(**config)
        self.config = config or BenchmarkConfig(name=self.__class__.__name__)
        self.context = BenchmarkContext()
        self.results = []
        self._setup_reproducibility()

    def _setup_reproducibility(self) -> None:
        """Configure environment for reproducible results."""
        np.random.seed(self.config.seed)

        if self.config.deterministic:
            # Set environment variables for deterministic GPU operations
            import os
            os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'
            # Note: Full determinism may require PyTorch settings if used

    @abc.abstractmethod
    def setup(self) -> None:
        """Setup phase - allocate resources, initialize engine."""
        pass

    @abc.abstractmethod
    def execute_iteration(self) -> float | dict:
        """
        Execute a single benchmark iteration.
        
        Returns:
            Either a single metric value (float) or dict of metrics
        """
        pass

    @abc.abstractmethod
    def teardown(self) -> None:
        """Cleanup phase - release resources."""
        pass

    def validate_environment(self) -> tuple[bool, list[str]]:
        """
        Validate that the environment meets benchmark requirements.
        
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        # Check GPU availability
        try:
            from ionosense_hpc.utils import gpu_count
            if gpu_count() == 0:
                issues.append("No CUDA devices available")
        except Exception as e:
            issues.append(f"Failed to query GPU: {e}")

        # Check minimum driver version (example)
        if 'cuda_version' in self.context.cuda_info:
            cuda_ver = self.context.cuda_info.get('cuda_version', '')
            if cuda_ver and cuda_ver < '11.0':
                issues.append(f"CUDA version {cuda_ver} is below minimum 11.0")

        return len(issues) == 0, issues

    def run(self) -> BenchmarkResult:
        """
        Main benchmark execution following standardized phases.
        
        Returns:
            BenchmarkResult containing all measurements and statistics
        """
        logger.info(f"Starting benchmark: {self.config.name}")
        logger.info(f"Environment: {self.context.environment_hash}")

        # Validate environment
        is_valid, issues = self.validate_environment()
        if not is_valid:
            logger.error(f"Environment validation failed: {issues}")
            return BenchmarkResult(
                name=self.config.name,
                config=self.config.model_dump(),
                context=self.context,
                measurements=np.array([]),
                passed=False,
                errors=issues
            )

        measurements = []
        errors = []

        try:
            # Setup phase
            logger.info("Setup phase...")
            self.setup()

            # Warmup phase
            if self.config.warmup_iterations > 0:
                logger.info(f"Running {self.config.warmup_iterations} warmup iterations...")
                for _ in range(self.config.warmup_iterations):
                    _ = self.execute_iteration()

            # Measurement phase
            logger.info(f"Running {self.config.iterations} measurement iterations...")
            for i in range(self.config.iterations):
                try:
                    # Add timeout protection
                    start_time = time.perf_counter()
                    result = self.execute_iteration()
                    elapsed = time.perf_counter() - start_time

                    if elapsed > self.config.timeout_seconds:
                        raise TimeoutError(f"Iteration {i} exceeded timeout")

                    if isinstance(result, dict):
                        measurements.append(result)
                    else:
                        measurements.append(float(result))

                    # Progress reporting
                    if self.config.verbose and (i + 1) % max(1, self.config.iterations // 10) == 0:
                        logger.debug(f"  Progress: {i + 1}/{self.config.iterations}")

                except Exception as e:
                    logger.warning(f"Iteration {i} failed: {e}")
                    errors.append(f"Iteration {i}: {str(e)}")
                    if len(errors) > self.config.iterations * 0.1:  # Fail if >10% errors
                        raise RuntimeError("Too many iteration failures")

        except Exception as e:
            logger.error(f"Benchmark failed: {e}")
            errors.append(f"Fatal: {str(e)}")

        finally:
            # Teardown phase
            logger.info("Teardown phase...")
            try:
                self.teardown()
            except Exception as e:
                logger.warning(f"Teardown failed: {e}")

        # Process results
        if not measurements:
            return BenchmarkResult(
                name=self.config.name,
                config=self.config.model_dump(),
                context=self.context,
                measurements=np.array([]),
                passed=False,
                errors=errors or ["No measurements collected"]
            )

        # Convert to numpy array
        if isinstance(measurements[0], dict):
            # Multi-metric case
            metrics = {}
            for key in measurements[0].keys():
                metrics[key] = np.array([m[key] for m in measurements])
            measurements_array = metrics
        else:
            measurements_array = np.array(measurements)

        # Calculate statistics
        if isinstance(measurements_array, dict):
            statistics = {k: calculate_statistics(v, self.config) for k, v in measurements_array.items()}
        else:
            statistics = calculate_statistics(measurements_array, self.config)

        result = BenchmarkResult(
            name=self.config.name,
            config=self.config.model_dump(),
            context=self.context,
            measurements=measurements_array,
            statistics=statistics,
            metadata={'errors': errors} if errors else {},
            passed=len(errors) == 0
        )

        logger.info(f"Benchmark complete: {'PASSED' if result.passed else 'FAILED'}")
        return result


def calculate_statistics(
    data: np.ndarray,
    config: BenchmarkConfig | None = None
) -> dict[str, Any]:
    """
    Calculate comprehensive statistics with outlier detection.
    
    Args:
        data: Array of measurements
        config: Benchmark configuration for statistical parameters
        
    Returns:
        Dictionary of statistical metrics
    """
    if len(data) == 0:
        return {'error': 'No data'}

    config = config or BenchmarkConfig(name="default")

    # Remove outliers using Z-score method
    z_scores = np.abs((data - np.mean(data)) / (np.std(data) + 1e-10))
    mask = z_scores < config.outlier_threshold
    filtered_data = data[mask]
    n_outliers = len(data) - len(filtered_data)

    if len(filtered_data) == 0:
        filtered_data = data  # Fallback if all are outliers

    # Basic statistics
    stats = {
        'n': len(data),
        'n_filtered': len(filtered_data),
        'n_outliers': n_outliers,
        'mean': float(np.mean(filtered_data)),
        'std': float(np.std(filtered_data, ddof=1) if len(filtered_data) > 1 else 0),
        'min': float(np.min(filtered_data)),
        'max': float(np.max(filtered_data)),
        'median': float(np.median(filtered_data))
    }

    # Percentiles
    for p in [1, 5, 25, 50, 75, 90, 95, 99]:
        stats[f'p{p}'] = float(np.percentile(filtered_data, p))

    # Confidence interval
    if len(filtered_data) >= config.min_samples:
        try:
            from scipy import stats as scipy_stats
            confidence = config.confidence_level
            sem = scipy_stats.sem(filtered_data)
            margin = sem * scipy_stats.t.ppf((1 + confidence) / 2, len(filtered_data) - 1)
            stats['ci_lower'] = float(stats['mean'] - margin)
            stats['ci_upper'] = float(stats['mean'] + margin)
            stats['ci_margin'] = float(margin)
        except ImportError:
            # Fallback to simple standard error without t-distribution
            sem = stats['std'] / np.sqrt(len(filtered_data))
            margin = sem * 1.96  # Approximate 95% confidence
            stats['ci_lower'] = float(stats['mean'] - margin)
            stats['ci_upper'] = float(stats['mean'] + margin)
            stats['ci_margin'] = float(margin)

    # Coefficient of variation
    if stats['mean'] != 0:
        stats['cv'] = stats['std'] / abs(stats['mean'])

    # Additional metrics
    stats['iqr'] = stats['p75'] - stats['p25']
    stats['range'] = stats['max'] - stats['min']

    return stats


def load_benchmark_config(path: Path | str) -> dict[str, Any]:
    """Load benchmark configuration from YAML or JSON file."""
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        if path.suffix in ['.yaml', '.yml']:
            return yaml.safe_load(f)
        elif path.suffix == '.json':
            return json.load(f)
        else:
            raise ValueError(f"Unsupported config format: {path.suffix}")


def save_benchmark_results(
    results: BenchmarkResult | list[BenchmarkResult],
    output_path: Path | str,
    format: str = 'json'
) -> None:
    """Save benchmark results in specified format."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(results, BenchmarkResult):
        results = [results]

    data = [r.to_dict() for r in results]

    if format == 'json':
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    elif format == 'yaml':
        with open(output_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
    elif format == 'csv':
        import csv
        # Flatten results for CSV
        rows = []
        for r in results:
            base = {
                'name': r.name,
                'timestamp': r.context.timestamp,
                'environment': r.context.environment_hash
            }
            base.update(r.statistics)
            rows.append(base)

        with open(output_path, 'w', newline='') as f:
            if rows:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
    else:
        raise ValueError(f"Unsupported format: {format}")

    logger.info(f"Results saved to {output_path}")


