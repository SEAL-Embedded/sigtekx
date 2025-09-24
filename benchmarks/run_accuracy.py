#!/usr/bin/env python
"""
Single-purpose script to run accuracy benchmarks.

This script is Hydra-aware and logs results to MLflow.
Communication with other scripts happens through artifact files.
"""

import hydra
import mlflow
import pandas as pd
from omegaconf import DictConfig
from pathlib import Path

from ionosense_hpc import Engine
from ionosense_hpc.benchmarks import AccuracyBenchmark
from ionosense_hpc.benchmarks.base import AccuracyBenchmarkConfig
from ionosense_hpc.config import EngineConfig


@hydra.main(version_base=None, config_path="../conf", config_name="config")
def run_accuracy_benchmark(cfg: DictConfig) -> float:
    """Run accuracy benchmark with MLflow tracking and save results.
    
    Returns:
        Error rate (1 - pass_rate) for optimization
    """
    # Convert OmegaConf to Pydantic models for validation
    engine_config = EngineConfig(**cfg.engine)
    benchmark_config = AccuracyBenchmarkConfig(
        name="accuracy",
        **cfg.benchmark
    )
    
    # Setup MLflow
    mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)
    mlflow.set_experiment(cfg.mlflow.experiment_name)
    
    with mlflow.start_run(run_name=f"accuracy_{engine_config.nfft}x{engine_config.batch}"):
        # Log configuration
        mlflow.log_params({
            "engine.nfft": engine_config.nfft,
            "engine.batch": engine_config.batch,
            "benchmark.absolute_tolerance": benchmark_config.absolute_tolerance,
            "benchmark.relative_tolerance": benchmark_config.relative_tolerance,
            "benchmark.snr_threshold_db": benchmark_config.snr_threshold_db,
        })
        
        # Run benchmark
        benchmark = AccuracyBenchmark(benchmark_config)
        benchmark.engine_config = engine_config  # Set engine config
        result = benchmark.run()
        
        # Log metrics
        pass_rate = result.statistics.get('pass_rate', 0)
        mlflow.log_metrics({
            "accuracy.pass_rate": pass_rate,
            "accuracy.mean_snr_db": result.statistics.get('mean_snr_db', 0),
            "accuracy.mean_error": result.statistics.get('mean_error', 0),
            "accuracy.max_error": result.statistics.get('max_error', 0),
        })
        
        # Save results to CSV (for downstream analysis)
        output_dir = Path(cfg.paths.data)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save test results
        if hasattr(benchmark, 'test_results'):
            results_data = []
            for test_result in benchmark.test_results:
                results_data.append({
                    'signal_type': test_result['signal'].get('type', 'unknown'),
                    'passed': test_result['passed'],
                    'mean_error': test_result['comparison'].get('mean_error', 0),
                    'snr_db': test_result['comparison'].get('snr_db', 0),
                    'engine_nfft': engine_config.nfft,
                    'engine_batch': engine_config.batch,
                })
            
            df = pd.DataFrame(results_data)
            output_path = output_dir / f"accuracy_details_{engine_config.nfft}_{engine_config.batch}.csv"
            df.to_csv(output_path, index=False)
            mlflow.log_artifact(str(output_path))
        
        # Save summary
        summary = {
            'engine_nfft': engine_config.nfft,
            'engine_batch': engine_config.batch,
            'pass_rate': pass_rate,
            'mean_snr_db': result.statistics.get('mean_snr_db', 0),
            'mean_error': result.statistics.get('mean_error', 0),
        }
        
        summary_df = pd.DataFrame([summary])
        summary_path = output_dir / f"accuracy_summary_{engine_config.nfft}_{engine_config.batch}.csv"
        summary_df.to_csv(summary_path, index=False)
        mlflow.log_artifact(str(summary_path))
        
    # Return error rate for minimization
    return 1.0 - pass_rate


if __name__ == "__main__":
    run_accuracy_benchmark()