#!/usr/bin/env python
"""
Single-purpose script to run throughput benchmarks.

This script is Hydra-aware and logs results to MLflow.
Communication with other scripts happens through artifact files.
"""

import warnings
from pathlib import Path

import hydra
import mlflow
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from ionosense_hpc.benchmarks import ThroughputBenchmark, ThroughputBenchmarkConfig
from ionosense_hpc.config import EngineConfig


@hydra.main(version_base=None, config_path="../experiments/conf", config_name="config")
def run_throughput_benchmark(cfg: DictConfig) -> float:
    """Run throughput benchmark with MLflow tracking and save results.

    Returns:
        Frames per second (negative for minimization in Hydra)
    """
    try:
        # ===== ROBUSTNESS FIX: Auto-load default benchmark if missing =====
        if 'benchmark' not in cfg:
            warnings.warn("⚠️  Benchmark config not specified. Defaulting to '+benchmark=throughput'.", stacklevel=2)
            # Get the original config directory to reliably find the default file
            config_dir = f"{hydra.utils.get_original_cwd()}/experiments/conf/benchmark"
            default_benchmark = OmegaConf.load(f"{config_dir}/throughput.yaml")
            # Temporarily disable struct mode to allow adding benchmark key
            OmegaConf.set_struct(cfg, False)
            cfg.benchmark = default_benchmark
            OmegaConf.set_struct(cfg, True)
        # ===== END ROBUSTNESS FIX =====

        # Validate engine parameters
        engine_params = cfg.engine
        nfft = engine_params.get('nfft', 2048)
        batch = engine_params.get('batch', 8)
        overlap = engine_params.get('overlap', 0.5)

        # Import validation (optional - only warn if not available)
        try:
            import sys
            sys.path.append('experiments/conf')
            from validation import validate_engine_parameters
            if not validate_engine_parameters(nfft, batch, overlap):
                warnings.warn("Parameter validation failed - proceeding anyway", stacklevel=2)
        except ImportError:
            pass  # Validation module not available

        # Convert OmegaConf to Pydantic models for validation
        # Filter out metadata fields that aren't part of EngineConfig
        engine_dict = dict(cfg.engine)
        engine_dict.pop("name", None)  # Remove metadata field

        # Merge engine overrides from benchmark config (if present)
        if 'engine' in cfg.benchmark:
            benchmark_engine_overrides = dict(cfg.benchmark.engine)
            engine_dict.update(benchmark_engine_overrides)

        engine_config = EngineConfig(**engine_dict)
        benchmark_config = ThroughputBenchmarkConfig(**cfg.benchmark, engine_config=engine_config.model_dump())

    except Exception as e:
        print(f"❌ Configuration error: {e}")
        print("Check your experiment config and engine parameters")
        raise

    # Setup MLflow

    mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)
    mlflow.set_experiment(cfg.mlflow.experiment_name)

    with mlflow.start_run(run_name=f"throughput_{engine_config.nfft}x{engine_config.channels}"):
        # Log configuration
        mlflow.log_params({
            "engine.nfft": engine_config.nfft,
            "engine.channels": engine_config.channels,
            "engine.overlap": engine_config.overlap,
            "benchmark.test_duration_s": benchmark_config.test_duration_s,
        })

        # Run benchmark
        benchmark = ThroughputBenchmark(benchmark_config)
        result = benchmark.run()

        # Log metrics
        fps = 0.0
        if 'frames_per_second' in result.statistics:
            stats = result.statistics['frames_per_second']
            fps = stats.get('mean', 0) if isinstance(stats, dict) else stats
            mlflow.log_metrics({
                "throughput.fps": fps,
                "throughput.gb_per_second": result.statistics.get('gb_per_second', {}).get('mean', 0),
                "throughput.samples_per_second": result.statistics.get('samples_per_second', {}).get('mean', 0),
            })

        # Save results to parquet (for downstream analysis)
        output_dir = Path(cfg.paths.data)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save summary
        summary = {
            'engine_nfft': engine_config.nfft,
            'engine_channels': engine_config.channels,
            'frames_per_second': fps,
            'gb_per_second': result.statistics.get('gb_per_second', {}).get('mean', 0),
            'gpu_utilization': result.statistics.get('gpu_utilization_mean', 0),
        }

        summary_df = pd.DataFrame([summary])
        summary_path = output_dir / f"throughput_summary_{engine_config.nfft}_{engine_config.channels}.csv"
        summary_df.to_csv(summary_path, index=False)
        mlflow.log_artifact(str(summary_path))

    # Return negative FPS for minimization (Hydra sweeper minimizes by default)
    return -fps


if __name__ == "__main__":
    run_throughput_benchmark()
