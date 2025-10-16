#!/usr/bin/env python
"""
Single-purpose script to run latency benchmarks.

This script is Hydra-aware and logs results to MLflow.
Communication with other scripts happens through artifact files.
"""

import warnings
from pathlib import Path

import hydra
import mlflow
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from ionosense_hpc.benchmarks import LatencyBenchmark, LatencyBenchmarkConfig
from ionosense_hpc.config import EngineConfig


@hydra.main(version_base=None, config_path="../experiments/conf", config_name="config")
def run_latency_benchmark(cfg: DictConfig) -> float:
    """Run latency benchmark with MLflow tracking and save results.

    Returns:
        Mean latency in microseconds (for optimization)
    """
    # ===== ROBUSTNESS FIX: Auto-load default benchmark if missing =====
    if 'benchmark' not in cfg:
        warnings.warn("⚠️  Benchmark config not specified. Defaulting to '+benchmark=latency'.")
        # Get the original config directory to reliably find the default file
        config_dir = f"{hydra.utils.get_original_cwd()}/experiments/conf/benchmark"
        default_benchmark = OmegaConf.load(f"{config_dir}/latency.yaml")
        # Temporarily disable struct mode to allow adding benchmark key
        OmegaConf.set_struct(cfg, False)
        cfg.benchmark = default_benchmark
        OmegaConf.set_struct(cfg, True)
    # ===== END ROBUSTNESS FIX =====

    # Convert OmegaConf to Pydantic models for validation
    # Filter out metadata fields that aren't part of EngineConfig
    engine_dict = dict(cfg.engine)
    engine_dict.pop("name", None)  # Remove metadata field
    engine_config = EngineConfig(**engine_dict)
    benchmark_config = LatencyBenchmarkConfig(**cfg.benchmark, engine_config=engine_config.model_dump())

    # Setup MLflow
    mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)
    mlflow.set_experiment(cfg.mlflow.experiment_name)

    with mlflow.start_run(run_name=f"latency_{engine_config.nfft}x{engine_config.batch}"):
        # Log configuration
        mlflow.log_params({
            "engine.nfft": engine_config.nfft,
            "engine.batch": engine_config.batch,
            "engine.overlap": engine_config.overlap,
            "benchmark.iterations": benchmark_config.iterations,
            "benchmark.deadline_us": benchmark_config.deadline_us,
        })

        # Run benchmark
        benchmark = LatencyBenchmark(benchmark_config)
        result = benchmark.run()

        # Log metrics
        if 'latency_us' in result.statistics:
            stats = result.statistics['latency_us']
            mlflow.log_metrics({
                "latency.mean": stats.get('mean', 0),
                "latency.p95": stats.get('p95', 0),
                "latency.p99": stats.get('p99', 0),
                "latency.std": stats.get('std', 0),
            })
            mean_latency = stats.get('mean', float('inf'))
        else:
            mean_latency = float('inf')

        # Save results to parquet (for downstream analysis)
        output_dir = Path(cfg.paths.data)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Convert measurements to DataFrame
        if hasattr(result, 'measurements') and result.measurements is not None:
            df = pd.DataFrame({
                'latency_us': result.measurements.get('latency_us', []),
                'engine_nfft': engine_config.nfft,
                'engine_batch': engine_config.batch,
            })

            output_path = output_dir / f"latency_{engine_config.nfft}_{engine_config.batch}.parquet"
            df.to_parquet(output_path, index=False)

            # Log artifact to MLflow
            mlflow.log_artifact(str(output_path))

        # Also save summary
        summary = {
            'engine_nfft': engine_config.nfft,
            'engine_batch': engine_config.batch,
            'mean_latency_us': mean_latency,
            'p95_latency_us': result.statistics.get('latency_us', {}).get('p95', 0),
            'p99_latency_us': result.statistics.get('latency_us', {}).get('p99', 0),
        }

        summary_df = pd.DataFrame([summary])
        summary_path = output_dir / f"latency_summary_{engine_config.nfft}_{engine_config.batch}.csv"
        summary_df.to_csv(summary_path, index=False)
        mlflow.log_artifact(str(summary_path))

    return mean_latency


if __name__ == "__main__":
    run_latency_benchmark()

