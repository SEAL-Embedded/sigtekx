"""
python/src/ionosense_hpc/benchmarks/sweep.py
--------------------------------------------------------------------------------
Configuration-driven parameter sweep system for comprehensive benchmarking
following RSE/RE standards for experimental reproducibility.
"""

import itertools
import json
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from pydantic import BaseModel, Field

from ionosense_hpc.benchmarks.base import (
    BaseBenchmark,
    BenchmarkConfig,
    BenchmarkContext,
    BenchmarkResult,
)
from ionosense_hpc.utils import logger
from ionosense_hpc.utils.profiling import (
    ProfileColor,
    ProfilingDomain,
    benchmark_range,
    nvtx_range,
)


class ParameterSpec(BaseModel):
    """Specification for a single parameter to sweep."""

    name: str = Field(description="Parameter name (dotted path for nested)")
    values: list[Any] | None = Field(None, description="Explicit list of values")
    range: dict | None = Field(None, description="Range specification")
    type: str = Field('float', description="Parameter type")

    def generate_values(self) -> list[Any]:
        """Generate parameter values based on specification."""
        if self.values is not None:
            return self.values

        if self.range is not None:
            if self.type == 'int':
                return list(range(
                    self.range['start'],
                    self.range['stop'],
                    self.range.get('step', 1)
                ))
            elif self.type == 'float':
                if 'step' in self.range:
                    values = []
                    current = self.range['start']
                    while current <= self.range['stop']:
                        values.append(current)
                        current += self.range['step']
                    return values
                else:
                    # Logarithmic or linear spacing
                    n_points = self.range.get('n_points', 10)
                    if self.range.get('log_scale', False):
                        return np.logspace(
                            np.log10(self.range['start']),
                            np.log10(self.range['stop']),
                            n_points
                        ).tolist()
                    else:
                        return np.linspace(
                            self.range['start'],
                            self.range['stop'],
                            n_points
                        ).tolist()

        raise ValueError(f"No values or range specified for parameter {self.name}")


class ExperimentConfig(BaseModel):
    """Configuration for a complete parameter sweep experiment."""

    name: str = Field(description="Experiment name")
    description: str = Field("", description="Experiment description")
    benchmark_class: str = Field(description="Fully qualified benchmark class name")

    # Parameter specifications
    parameters: list[ParameterSpec] = Field(default_factory=list)

    # Sweep configuration
    sweep_type: str = Field('grid', description="Sweep type: grid, random, latin_hypercube")
    n_samples: int = Field(100, description="Number of samples for random/LHS sweep")

    # Base configuration
    base_config: dict = Field(default_factory=dict, description="Base benchmark configuration")

    # Execution control
    parallel: bool = Field(False, description="Run experiments in parallel")
    max_workers: int = Field(4, description="Maximum parallel workers")
    continue_on_error: bool = Field(True, description="Continue if individual runs fail")

    # Output control
    output_dir: str = Field('./experiments', description="Output directory")
    save_interval: int = Field(10, description="Save results every N runs")
    aggregate_results: bool = Field(True, description="Generate aggregate analysis")


@dataclass
class ExperimentRun:
    """Single run in a parameter sweep experiment."""

    run_id: str
    parameter_values: dict
    config: BenchmarkConfig
    result: BenchmarkResult | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'run_id': self.run_id,
            'parameters': self.parameter_values,
            'config': self.config.model_dump() if hasattr(self.config, 'model_dump') else dict(self.config),
            'result': self.result.to_dict() if self.result else None,
            'error': self.error
        }


class ParameterSweep:
    """
    Orchestrates parameter sweep experiments with full reproducibility.
    
    This class manages the execution of benchmarks across a parameter space,
    handling result aggregation, failure recovery, and reporting.
    """

    def __init__(self, config: ExperimentConfig | dict | str):
        """
        Initialize sweep from configuration.
        
        Args:
            config: ExperimentConfig, dict, or path to config file
        """
        if isinstance(config, str):
            config = self._load_config(config)
        if isinstance(config, dict):
            config = ExperimentConfig(**config)

        self.config = config
        self.context = BenchmarkContext()
        self.runs = []
        self.results = []

        # Create output directory
        self.output_dir = Path(self.config.output_dir) / self.config.name
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Save experiment configuration
        self._save_config()

    def _load_config(self, path: str) -> dict:
        """Load configuration from file."""
        path = Path(path)
        with open(path) as f:
            if path.suffix in ['.yaml', '.yml']:
                return yaml.safe_load(f)
            else:
                return json.load(f)

    def _save_config(self) -> None:
        """Save experiment configuration for reproducibility."""
        config_path = self.output_dir / 'experiment_config.json'
        with open(config_path, 'w') as f:
            json.dump({
                'config': self.config.model_dump(),
                'context': self.context.to_dict()
            }, f, indent=2, default=str)

    def generate_parameter_grid(self) -> Generator[dict, None, None]:
        """Generate parameter combinations based on sweep type."""
        # Extract parameter names and values
        param_names = [p.name for p in self.config.parameters]
        param_values = [p.generate_values() for p in self.config.parameters]

        if self.config.sweep_type == 'grid':
            # Full factorial grid search
            for combination in itertools.product(*param_values):
                yield dict(zip(param_names, combination, strict=False))

        elif self.config.sweep_type == 'random':
            # Random sampling
            rng = np.random.RandomState(42)  # Deterministic
            for _ in range(self.config.n_samples):
                combination = [rng.choice(vals) for vals in param_values]
                yield dict(zip(param_names, combination, strict=False))

        elif self.config.sweep_type == 'latin_hypercube':
            # Latin Hypercube Sampling for better coverage
            try:
                from scipy.stats import qmc
            except ImportError:
                logger.warning("scipy not available, falling back to random sampling")
                self.config.sweep_type = 'random'
                # Fall back to random sampling
                rng = np.random.RandomState(42)
                for _ in range(self.config.n_samples):
                    combination = [rng.choice(vals) for vals in param_values]
                    yield dict(zip(param_names, combination, strict=False))
                return

            n_params = len(param_names)
            sampler = qmc.LatinHypercube(d=n_params, seed=42)
            sample = sampler.random(n=self.config.n_samples)

            # Scale samples to parameter ranges
            for point in sample:
                combination = []
                for i, (name, values) in enumerate(zip(param_names, param_values, strict=False)):
                    idx = int(point[i] * len(values))
                    idx = min(idx, len(values) - 1)
                    combination.append(values[idx])
                yield dict(zip(param_names, combination, strict=False))

        else:
            raise ValueError(f"Unknown sweep type: {self.config.sweep_type}")

    def create_benchmark_config(self, parameters: dict) -> BenchmarkConfig:
        """Create benchmark configuration with swept parameters."""
        # Start with base configuration
        config_dict = self.config.base_config.copy()

        # Apply swept parameters (handle nested paths)
        for param_path, value in parameters.items():
            if '.' in param_path:
                # Handle nested parameters like 'engine_config.nfft'
                parts = param_path.split('.')
                target = config_dict
                for part in parts[:-1]:
                    if part not in target:
                        target[part] = {}
                    target = target[part]
                target[parts[-1]] = value
            else:
                config_dict[param_path] = value

        # Create appropriate config object
        return BenchmarkConfig(**config_dict)

    def run_single(self, parameters: dict, run_id: str) -> ExperimentRun:
        """Execute a single benchmark run with given parameters."""
        logger.info(f"Running {run_id}: {parameters}")

        # Create configuration
        try:
            config = self.create_benchmark_config(parameters)
            config.name = f"{self.config.name}_{run_id}"
        except Exception as e:
            logger.error(f"Failed to create config for {run_id}: {e}")
            return ExperimentRun(run_id, parameters, None, error=str(e))

        # Get benchmark class
        try:
            benchmark_class = self._get_benchmark_class()
            benchmark = benchmark_class(config)
        except Exception as e:
            logger.error(f"Failed to instantiate benchmark for {run_id}: {e}")
            return ExperimentRun(run_id, parameters, config, error=str(e))

        # Run benchmark
        try:
            result = benchmark.run()
            return ExperimentRun(run_id, parameters, config, result=result)
        except Exception as e:
            logger.error(f"Benchmark failed for {run_id}: {e}")
            return ExperimentRun(run_id, parameters, config, error=str(e))

    def _get_benchmark_class(self) -> type[BaseBenchmark]:
        """Dynamically load benchmark class."""
        module_path, class_name = self.config.benchmark_class.rsplit('.', 1)
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name)

    def run(self) -> list[ExperimentRun]:
        """Execute the complete parameter sweep (NVTX-instrumented)."""
        with benchmark_range(f"ParameterSweep_{self.config.name}"):
            logger.info(f"Starting experiment: {self.config.name}")
            logger.info(f"Output directory: {self.output_dir}")

            # Generate parameter grid
            with nvtx_range("GenerateParameterGrid", color=ProfileColor.YELLOW, domain=ProfilingDomain.BENCHMARK):
                param_grid = list(self.generate_parameter_grid())
            logger.info(f"Parameter grid size: {len(param_grid)}")

            # Execute runs
            if self.config.parallel:
                with nvtx_range("RunParallel", color=ProfileColor.PURPLE, domain=ProfilingDomain.BENCHMARK):
                    results = self._run_parallel(param_grid)
            else:
                with nvtx_range("RunSequential", color=ProfileColor.PURPLE, domain=ProfilingDomain.BENCHMARK):
                    results = self._run_sequential(param_grid)

            # Save final results
            with nvtx_range("SaveResults", color=ProfileColor.ORANGE):
                self._save_results(results)

            # Generate aggregate analysis
            if self.config.aggregate_results:
                with nvtx_range("AggregateAnalysis", color=ProfileColor.ORANGE):
                    self._generate_analysis(results)

            logger.info(f"Experiment complete: {len(results)} runs")
            return results

    def _run_sequential(self, param_grid: list[dict]) -> list[ExperimentRun]:
        """Run benchmarks sequentially."""
        results = []

        for i, parameters in enumerate(param_grid):
            with nvtx_range(f"Run_{i:04d}", color=ProfileColor.PURPLE, domain=ProfilingDomain.BENCHMARK, payload=i):
                run_id = f"run_{i:04d}"
                run = self.run_single(parameters, run_id)
                results.append(run)

                # Periodic saving
                if (i + 1) % self.config.save_interval == 0:
                    with nvtx_range("SaveIntermediate", color=ProfileColor.ORANGE):
                        self._save_results(results)
                    logger.info(f"Progress: {i+1}/{len(param_grid)} runs complete")

                # Check for failures
                if run.error and not self.config.continue_on_error:
                    logger.error(f"Stopping due to error: {run.error}")
                    break

        return results

    def _run_parallel(self, param_grid: list[dict]) -> list[ExperimentRun]:
        """Run benchmarks in parallel."""
        from concurrent.futures import ProcessPoolExecutor, as_completed

        results = []

        with ProcessPoolExecutor(max_workers=self.config.max_workers) as executor:
            # Submit all tasks
            futures = {}
            for i, parameters in enumerate(param_grid):
                run_id = f"run_{i:04d}"
                future = executor.submit(self.run_single, parameters, run_id)
                futures[future] = (run_id, parameters)

            # Collect results as they complete
            for i, future in enumerate(as_completed(futures)):
                run_id, parameters = futures[future]
                try:
                    run = future.result()
                    results.append(run)
                except Exception as e:
                    logger.error(f"Run {run_id} failed: {e}")
                    if not self.config.continue_on_error:
                        executor.shutdown(wait=False)
                        break
                    results.append(ExperimentRun(run_id, parameters, None, error=str(e)))

                # Periodic saving
                if (i + 1) % self.config.save_interval == 0:
                    self._save_results(results)
                    logger.info(f"Progress: {i+1}/{len(param_grid)} runs complete")

        return results

    def _save_results(self, results: list[ExperimentRun]) -> None:
        """Save experiment results to disk."""
        results_path = self.output_dir / 'results.json'

        data = {
            'experiment': self.config.name,
            'timestamp': datetime.now().isoformat(),
            'context': self.context.to_dict(),
            'runs': [r.to_dict() for r in results]
        }

        with open(results_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        # Also save as CSV for easy analysis
        self._save_csv(results)

    def _save_csv(self, results: list[ExperimentRun]) -> None:
        """Save results in CSV format."""
        import csv

        csv_path = self.output_dir / 'results.csv'

        if not results:
            return

        # Collect all unique keys
        rows = []
        for run in results:
            if run.result and run.result.statistics:
                row = {
                    'run_id': run.run_id,
                    **run.parameter_values,
                    **run.result.statistics,
                    'error': run.error or ''
                }
                rows.append(row)

        if rows:
            with open(csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

    def _generate_analysis(self, results: list[ExperimentRun]) -> None:
        """Generate aggregate analysis and visualizations."""
        analysis_dir = self.output_dir / 'analysis'
        analysis_dir.mkdir(exist_ok=True)

        # Separate successful and failed runs
        successful = [r for r in results if r.result is not None]
        failed = [r for r in results if r.error is not None]

        logger.info(f"Analysis: {len(successful)} successful, {len(failed)} failed")

        # Generate parameter importance analysis
        if successful:
            self._analyze_parameter_importance(successful, analysis_dir)

        # Generate performance heatmaps
        if len(self.config.parameters) >= 2:
            self._generate_heatmaps(successful, analysis_dir)

        # Generate summary report
        self._generate_report(results, analysis_dir)

    def _analyze_parameter_importance(
        self,
        runs: list[ExperimentRun],
        output_dir: Path
    ) -> None:
        """Analyze relative importance of parameters on performance."""
        try:
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.inspection import permutation_importance
        except Exception as e:
            logger.warning(f"sklearn not available, skipping importance analysis: {e}")
            return

        # Prepare data
        X = []
        y = []
        param_names = list(runs[0].parameter_values.keys())

        for run in runs:
            if run.result and 'mean' in run.result.statistics:
                X.append([run.parameter_values[p] for p in param_names])
                y.append(run.result.statistics['mean'])

        if len(X) < 10:
            logger.warning("Too few samples for importance analysis")
            return

        X = np.array(X)
        y = np.array(y)

        # Train random forest
        rf = RandomForestRegressor(n_estimators=100, random_state=42)
        rf.fit(X, y)

        # Calculate importance
        importance = permutation_importance(rf, X, y, n_repeats=10, random_state=42)

        # Save importance scores
        importance_data = {
            'parameters': param_names,
            'importance_mean': importance.importances_mean.tolist(),
            'importance_std': importance.importances_std.tolist()
        }

        with open(output_dir / 'parameter_importance.json', 'w') as f:
            json.dump(importance_data, f, indent=2)

        logger.info("Parameter importance analysis saved")

    def _generate_heatmaps(
        self,
        runs: list[ExperimentRun],
        output_dir: Path
    ) -> None:
        """Generate 2D performance heatmaps for parameter pairs."""
        import matplotlib.pyplot as plt

        param_names = list(runs[0].parameter_values.keys())

        if len(param_names) < 2:
            return

        # Generate heatmap for first two parameters
        param1, param2 = param_names[0], param_names[1]

        # Collect unique values
        p1_values = sorted(set(r.parameter_values[param1] for r in runs))
        p2_values = sorted(set(r.parameter_values[param2] for r in runs))

        # Create performance matrix
        perf_matrix = np.full((len(p2_values), len(p1_values)), np.nan)

        for run in runs:
            if run.result and 'mean' in run.result.statistics:
                i = p1_values.index(run.parameter_values[param1])
                j = p2_values.index(run.parameter_values[param2])
                perf_matrix[j, i] = run.result.statistics['mean']

        # Create heatmap
        plt.figure(figsize=(10, 8))
        plt.imshow(perf_matrix, aspect='auto', origin='lower', cmap='viridis')
        plt.colorbar(label='Mean Latency (µs)')
        plt.xlabel(param1)
        plt.ylabel(param2)
        plt.title(f'Performance Heatmap: {param1} vs {param2}')
        plt.xticks(range(len(p1_values)), p1_values, rotation=45)
        plt.yticks(range(len(p2_values)), p2_values)
        plt.tight_layout()
        plt.savefig(output_dir / f'heatmap_{param1}_{param2}.png', dpi=150)
        plt.close()

        logger.info("Performance heatmaps generated")

    def _generate_report(self, results: list[ExperimentRun], output_dir: Path) -> None:
        """Generate markdown summary report."""
        report_path = output_dir / 'report.md'

        successful = [r for r in results if r.result is not None]
        failed = [r for r in results if r.error is not None]

        with open(report_path, 'w') as f:
            f.write(f"# Experiment Report: {self.config.name}\n\n")
            f.write(f"**Generated:** {datetime.now().isoformat()}\n\n")
            f.write(f"**Description:** {self.config.description}\n\n")

            f.write("## Summary\n\n")
            f.write(f"- Total runs: {len(results)}\n")
            f.write(f"- Successful: {len(successful)}\n")
            f.write(f"- Failed: {len(failed)}\n")
            f.write(f"- Success rate: {len(successful)/len(results)*100:.1f}%\n\n")

            f.write("## Configuration\n\n")
            f.write(f"- Sweep type: {self.config.sweep_type}\n")
            f.write(f"- Parameters: {len(self.config.parameters)}\n")
            for param in self.config.parameters:
                f.write(f"  - {param.name}: {len(param.generate_values())} values\n")
            f.write("\n")

            if successful:
                f.write("## Best Configurations\n\n")

                # Sort by mean performance
                best_runs = sorted(
                    successful,
                    key=lambda r: r.result.statistics.get('mean', float('inf'))
                )[:5]

                f.write("### Top 5 by Mean Latency\n\n")
                for i, run in enumerate(best_runs, 1):
                    f.write(f"{i}. **{run.run_id}**\n")
                    f.write(f"   - Parameters: {run.parameter_values}\n")
                    f.write(f"   - Mean: {run.result.statistics.get('mean', 0):.2f} µs\n")
                    f.write(f"   - P99: {run.result.statistics.get('p99', 0):.2f} µs\n\n")

            if failed:
                f.write("## Failed Runs\n\n")
                for run in failed[:10]:  # Show first 10 failures
                    f.write(f"- {run.run_id}: {run.error}\n")

        logger.info(f"Report generated: {report_path}")


# Example configuration file content (save as experiment.yaml)
EXAMPLE_CONFIG = """
name: nfft_batch_sweep
description: Explore FFT size and batch size impact on latency
benchmark_class: ionosense_hpc.benchmarks.latency_enhanced.EnhancedLatencyBenchmark

parameters:
  - name: engine_config.nfft
    type: int
    values: [256, 512, 1024, 2048, 4096]
  
  - name: engine_config.batch
    type: int
    range:
      start: 1
      stop: 32
      step: 1

sweep_type: grid
base_config:
  iterations: 500
  warmup_iterations: 50
  deadline_us: 200
  test_signal_type: sine

output_dir: ./experiments
aggregate_results: true
"""


if __name__ == '__main__':
    # Example: Create and run a parameter sweep
    import tempfile

    # Save example config
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(EXAMPLE_CONFIG)
        config_path = f.name

    # Run sweep
    sweep = ParameterSweep(config_path)
    results = sweep.run()

    print(f"\nExperiment complete: {len(results)} runs")
    print(f"Results saved to: {sweep.output_dir}")
