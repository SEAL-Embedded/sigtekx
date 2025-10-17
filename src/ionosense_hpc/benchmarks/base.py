"""
src/ionosense_hpc/benchmarks/base.py
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
from typing import TYPE_CHECKING, Any, TypeVar, cast

if TYPE_CHECKING:
    from ionosense_hpc.utils.gpu_clocks import GpuClockManager

import numpy as np
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from ionosense_hpc.utils import logger
from ionosense_hpc.utils.profiling import (
    ProfileColor,
    ProfilingDomain,
    benchmark_range,
    nvtx_range,
    setup_range,
    teardown_range,
    warmup_range,
)

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
    measurements: Any
    statistics: dict[str, Any] = field(default_factory=dict)
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
    require_gpu: bool = Field(default=False, description="Fail validation if no CUDA GPU present")

    # Output control
    save_raw_data: bool = Field(default=True, description="Save raw measurements")
    output_format: str = Field(default="json", description="Output format (json, csv, hdf5)")
    verbose: bool = Field(default=True, description="Verbose output")

    # GPU clock locking (reduces benchmark variability by 50-75%)
    lock_gpu_clocks: bool = Field(default=False, description="Lock GPU clocks for stable benchmarking")
    gpu_index: int = Field(default=0, ge=0, description="GPU index to lock (use with lock_gpu_clocks)")
    use_max_clocks: bool = Field(default=False, description="Use max clocks vs recommended (use with lock_gpu_clocks)")


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
        self.results: list[BenchmarkResult] = []
        self.gpu_clock_manager: GpuClockManager | None = None
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

        # Check GPU availability (only hard-require if configured)
        try:
            from ionosense_hpc.utils import gpu_count
            from ionosense_hpc.utils import logger as _logger
            n_gpu = gpu_count()
            if self.config.require_gpu:
                if n_gpu == 0:
                    issues.append("No CUDA devices available")
            else:
                if n_gpu == 0:
                    # Allow running in CPU/test environments; warn for visibility
                    _logger.warning("No CUDA devices available; proceeding in CPU/test mode")
        except Exception as e:
            # Don't block execution on environment probe errors in baseline validation
            if self.config.require_gpu:
                issues.append(f"Failed to query GPU: {e}")

        # Check minimum driver version (example)
        cuda_ver = self.context.cuda_info.get('cuda_version')
        if cuda_ver:
            try:
                def _vtuple(s: str) -> tuple[int, ...]:
                    parts: list[str] = []
                    for ch in s:
                        if ch.isdigit() or ch == '.':
                            parts.append(ch)
                    clean = ''.join(parts).strip('.') or '0'
                    return tuple(int(p) for p in clean.split('.') if p.isdigit())

                if _vtuple(str(cuda_ver)) < _vtuple('11.0'):
                    issues.append(f"CUDA version {cuda_ver} is below minimum 11.0")
            except Exception:
                # Best-effort only; ignore parsing failures
                pass

        return len(issues) == 0, issues

    def run(self) -> BenchmarkResult:
        """
        Main benchmark execution following standardized phases.

        Returns:
            BenchmarkResult containing all measurements and statistics
        """
        with benchmark_range(f"Benchmark_{self.config.name}"):
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
                    errors=issues,
                )

            measurements: list[float | dict[str, Any]] = []
            errors: list[str] = []
            lock_info: dict[str, Any] | None = None

            # Initialize GPU clock manager if enabled
            if self.config.lock_gpu_clocks:
                try:
                    from ionosense_hpc.utils import GpuClockManager, check_clock_locking_available

                    # Check availability first
                    available, reason = check_clock_locking_available()
                    if not available:
                        logger.warning(f"GPU clock locking not available: {reason}")
                        logger.warning("Proceeding without clock locking")
                    else:
                        self.gpu_clock_manager = GpuClockManager(
                            gpu_index=self.config.gpu_index,
                            use_max_clocks=self.config.use_max_clocks
                        )
                except Exception as e:
                    logger.warning(f"Failed to initialize GPU clock manager: {e}")
                    logger.warning("Proceeding without clock locking")

            try:
                # Lock GPU clocks before setup
                if self.gpu_clock_manager:
                    try:
                        lock_info = self.gpu_clock_manager.lock()
                    except Exception as e:
                        logger.warning(f"Failed to lock GPU clocks: {e}")
                        logger.warning("Proceeding without clock locking")
                        self.gpu_clock_manager = None

                # Setup phase
                with setup_range("Benchmark.setup"):
                    logger.info("Setup phase...")
                    self.setup()

                # Warmup phase
                if self.config.warmup_iterations > 0:
                    with warmup_range(
                        f"Warmup_{self.config.warmup_iterations}_iterations"
                    ):
                        logger.info(
                            f"Running {self.config.warmup_iterations} warmup iterations..."
                        )
                        for w in range(self.config.warmup_iterations):
                            with nvtx_range(
                                f"WarmupIter_{w}",
                                color=ProfileColor.LIGHT_GRAY,
                                domain=ProfilingDomain.BENCHMARK,
                                payload=w,
                            ):
                                _ = self.execute_iteration()

                # Measurement phase
                with nvtx_range(
                    "MeasurementPhase",
                    color=ProfileColor.NVIDIA_BLUE,
                    domain=ProfilingDomain.BENCHMARK,
                ):
                    logger.info(
                        f"Running {self.config.iterations} measurement iterations..."
                    )
                    for i in range(self.config.iterations):
                        try:
                            start_time = time.perf_counter()
                            start_wall = time.time()
                            with nvtx_range(
                                f"Iteration_{i}",
                                color=ProfileColor.PURPLE,
                                domain=ProfilingDomain.BENCHMARK,
                                payload=i,
                            ):
                                iter_result = self.execute_iteration()
                            end_time = time.perf_counter()
                            elapsed = end_time - start_time
                            elapsed_wall = time.time() - start_wall
                            if self.config.timeout_seconds > 0 and (elapsed > self.config.timeout_seconds or elapsed_wall > self.config.timeout_seconds):
                                msg = f"Iteration {i} exceeded timeout"
                                raise TimeoutError(msg)

                            if isinstance(iter_result, dict):
                                measurements.append(iter_result)
                            else:
                                measurements.append(float(iter_result))

                            if self.config.verbose and (i + 1) % max(
                                1, self.config.iterations // 10
                            ) == 0:
                                logger.debug(
                                    f"  Progress: {i + 1}/{self.config.iterations}"
                                )

                        except Exception as e:
                            logger.warning(f"Iteration {i} failed: {e}")
                            errors.append(f"Iteration {i}: {str(e)}")
                            if len(errors) > self.config.iterations * 0.1:
                                raise RuntimeError("Too many iteration failures") from e

            except Exception as e:
                logger.error(f"Benchmark failed: {e}")
                errors.append(f"Fatal: {str(e)}")

            finally:
                with teardown_range("Benchmark.teardown"):
                    logger.info("Teardown phase...")
                    try:
                        self.teardown()
                    except Exception as e:
                        logger.warning(f"Teardown failed: {e}")

                # Always unlock GPU clocks
                if self.gpu_clock_manager and self.gpu_clock_manager.locked:
                    try:
                        self.gpu_clock_manager.unlock()
                    except Exception as e:
                        logger.warning(f"Failed to unlock GPU clocks: {e}")
                        logger.warning("Manual recovery may be needed (see gpu_clocks.py for commands)")

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
        measurements_array: Any
        if isinstance(measurements[0], dict):
            # Multi-metric case
            md = cast(list[dict[str, Any]], measurements)
            metrics_dict: dict[str, np.ndarray] = {}
            for key in md[0]:
                metrics_dict[key] = np.array([d[key] for d in md])
            measurements_array = metrics_dict
        else:
            measurements_array = np.array(measurements)

        # Calculate statistics
        if isinstance(measurements_array, dict):
            statistics = {k: calculate_statistics(v, self.config) for k, v in measurements_array.items()}
        else:
            statistics = calculate_statistics(measurements_array, self.config)

        # Build metadata
        metadata: dict[str, Any] = {}
        if errors:
            metadata['errors'] = errors
        if lock_info:
            metadata['gpu_clock_locking'] = lock_info

        result = BenchmarkResult(
            name=self.config.name,
            config=self.config.model_dump(),
            context=self.context,
            measurements=measurements_array,
            statistics=statistics,
            metadata=metadata,
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
    # Normalize input
    data = np.asarray(data)
    original_size = int(data.size)

    if original_size == 0:
        return {'error': 'No data'}

    config = config or BenchmarkConfig(name="default")

    # Coerce boolean and non-numeric data to float for robust stats
    if data.dtype == np.bool_:
        data = data.astype(np.float32)
    elif data.dtype.kind not in 'iufc':  # not integer/unsigned/float/complex
        try:
            data = data.astype(np.float64)
        except Exception:
            # Best-effort: map truthy/falsy to floats
            data = np.array([float(x) for x in data], dtype=np.float64)

    n_invalid = 0
    if np.issubdtype(data.dtype, np.number):
        finite_mask = np.isfinite(data)
        n_invalid = int(original_size - int(np.count_nonzero(finite_mask)))
        if n_invalid:
            data = data[finite_mask]

    if data.size == 0:
        return {
            'n': 0,
            'n_total': original_size,
            'n_invalid': n_invalid,
            'error': 'No finite data'
        }

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
        'n_total': original_size,
        'n_invalid': n_invalid,
        'n_filtered': len(filtered_data),
        'n_outliers': int(n_outliers),
        'mean': float(np.mean(filtered_data)),
        'std': float(np.std(filtered_data, ddof=1)) if len(filtered_data) > 1 else 0.0,
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
            return cast(dict[str, Any], yaml.safe_load(f))
        elif path.suffix == '.json':
            return cast(dict[str, Any], json.load(f))
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



