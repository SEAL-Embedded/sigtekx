#!/usr/bin/env python
"""
Single-purpose script to run throughput benchmarks.

This script is Hydra-aware and logs results to MLflow.
Communication with other scripts happens through artifact files.
"""

import hydra
import mlflow
import pandas as pd
from omegaconf import DictConfig
from pathlib import Path

from ionosense_hpc import Engine
from ionosense_hpc.benchmarks import ThroughputBenchmark, ThroughputBenchmarkConfig
from ionosense_hpc.config import EngineConfig


@hydra.main(version_base=None, config_path="../experiments/conf", config_name="config")
def run_throughput_benchmark(cfg: DictConfig) -> float:
    """Run throughput benchmark with MLflow tracking and save results.
    
    Returns:
        Frames per second (negative for minimization in Hydra)
    """
    # Convert OmegaConf to Pydantic models for validation
    engine_config = EngineConfig(**cfg.engine)
    benchmark_config = ThroughputBenchmarkConfig(**cfg.benchmark)

    # Setup MLflow

    mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)
    mlflow.set_experiment(cfg.mlflow.experiment_name)
    
    with mlflow.start_run(run_name=f"throughput_{engine_config.nfft}x{engine_config.batch}"):
        # Log configuration
        mlflow.log_params({
            "engine.nfft": engine_config.nfft,
            "engine.batch": engine_config.batch,
            "engine.overlap": engine_config.overlap,
            "benchmark.test_duration_s": benchmark_config.test_duration_s,
        })
        
        # Run benchmark
        benchmark = ThroughputBenchmark(benchmark_config)
        benchmark.engine_config = engine_config  # Set engine config
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
            'engine_batch': engine_config.batch,
            'frames_per_second': fps,
            'gb_per_second': result.statistics.get('gb_per_second', {}).get('mean', 0),
            'gpu_utilization': result.statistics.get('gpu_utilization_mean', 0),
        }
        
        summary_df = pd.DataFrame([summary])
        summary_path = output_dir / f"throughput_summary_{engine_config.nfft}_{engine_config.batch}.csv"
        summary_df.to_csv(summary_path, index=False)
        mlflow.log_artifact(str(summary_path))
        
    # Return negative FPS for minimization (Hydra sweeper minimizes by default)
    return -fps


if __name__ == "__main__":
    run_throughput_benchmark()
