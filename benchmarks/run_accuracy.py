#!/usr/bin/env python
"""
Single-purpose script to run accuracy benchmarks.

This script is Hydra-aware and logs results to MLflow.
Communication with other scripts happens through artifact files.
"""

import warnings
from pathlib import Path

import hydra
import mlflow
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from sigtekx.benchmarks import AccuracyBenchmark, AccuracyBenchmarkConfig
from sigtekx.config import EngineConfig


@hydra.main(version_base=None, config_path="../experiments/conf", config_name="config")
def run_accuracy_benchmark(cfg: DictConfig) -> float:
    """Run accuracy benchmark with MLflow tracking and save results.

    Returns:
        Error rate (1 - pass_rate) for optimization
    """
    # ===== ROBUSTNESS FIX: Auto-load default benchmark if missing =====
    if 'benchmark' not in cfg:
        warnings.warn("⚠️  Benchmark config not specified. Defaulting to '+benchmark=accuracy'.", stacklevel=2)
        # Get the original config directory to reliably find the default file
        config_dir = f"{hydra.utils.get_original_cwd()}/experiments/conf/benchmark"
        default_benchmark = OmegaConf.load(f"{config_dir}/accuracy.yaml")
        # Temporarily disable struct mode to allow adding benchmark key
        OmegaConf.set_struct(cfg, False)
        cfg.benchmark = default_benchmark
        OmegaConf.set_struct(cfg, True)
    # ===== END ROBUSTNESS FIX =====

    # Convert OmegaConf to Pydantic models for validation
    # Filter out metadata fields that aren't part of EngineConfig
    engine_dict = dict(cfg.engine)
    engine_dict.pop("name", None)  # Remove metadata field

    # Merge engine overrides from benchmark config (if present)
    if 'engine' in cfg.benchmark:
        benchmark_engine_overrides = dict(cfg.benchmark.engine)
        engine_dict.update(benchmark_engine_overrides)

    engine_config = EngineConfig(**engine_dict)
    benchmark_config = AccuracyBenchmarkConfig(**cfg.benchmark, engine_config=engine_config.model_dump())

    # Setup MLflow

    mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)
    mlflow.set_experiment(cfg.mlflow.experiment_name)

    with mlflow.start_run(run_name=f"accuracy_{engine_config.nfft}x{engine_config.channels}"):
        # Log configuration
        mlflow.log_params({
            "engine.nfft": engine_config.nfft,
            "engine.channels": engine_config.channels,
            "benchmark.absolute_tolerance": benchmark_config.absolute_tolerance,
            "benchmark.relative_tolerance": benchmark_config.relative_tolerance,
            "benchmark.snr_threshold_db": benchmark_config.snr_threshold_db,
        })

        # Run benchmark
        benchmark = AccuracyBenchmark(benchmark_config)
        result = benchmark.run()

        # Helper function to extract float from potentially nested dict
        def extract_float(value, default=0.0):
            if isinstance(value, dict):
                return float(value.get('mean', default))
            return float(value) if value is not None else default

        # Log metrics - ensure all values are floats
        mlflow.log_metrics({
            "accuracy.pass_rate": extract_float(result.statistics.get('pass_rate', 0)),
            "accuracy.mean_snr_db": extract_float(result.statistics.get('mean_snr_db', 0)),
            "accuracy.mean_error": extract_float(result.statistics.get('mean_error', 0)),
            "accuracy.max_error": extract_float(result.statistics.get('max_error', 0)),
        })

        # Save results to CSV (for downstream analysis)
        output_dir = Path(cfg.paths.data)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save test results with enhanced diagnostics
        if hasattr(benchmark, 'test_results'):
            results_data = []
            for test_result in benchmark.test_results:
                row = {
                    'signal_type': test_result['signal'].get('type', 'unknown'),
                    'passed': test_result['passed'],
                    'mean_error': test_result['comparison'].get('mean_error', 0),
                    'max_error': test_result['comparison'].get('max_abs_error', 0),
                    'max_rel_error': test_result['comparison'].get('max_rel_error', 0),
                    'snr_db': test_result['comparison'].get('snr_db', 0),
                    'engine_nfft': engine_config.nfft,
                    'engine_channels': engine_config.channels,
                }
                # Add GPU vs Reference stats if available
                if 'gpu_stats' in test_result:
                    row['gpu_mean'] = test_result['gpu_stats']['mean']
                    row['gpu_std'] = test_result['gpu_stats']['std']
                    row['ref_mean'] = test_result['ref_stats']['mean']
                    row['ref_std'] = test_result['ref_stats']['std']
                results_data.append(row)

            df = pd.DataFrame(results_data)
            output_path = output_dir / f"accuracy_details_{engine_config.nfft}_{engine_config.channels}.csv"
            df.to_csv(output_path, index=False)
            mlflow.log_artifact(str(output_path))

        # Calculate derived scientific metrics
        hop_size = int(engine_config.nfft * (1 - engine_config.overlap))
        time_resolution_ms = (engine_config.nfft / engine_config.sample_rate_hz) * 1000
        freq_resolution_hz = engine_config.sample_rate_hz / engine_config.nfft

        # Save enriched summary with scientific metrics
        summary = {
            # Core engine parameters
            'engine_nfft': engine_config.nfft,
            'engine_channels': engine_config.channels,
            'engine_overlap': engine_config.overlap,
            'engine_sample_rate_hz': engine_config.sample_rate_hz,
            'engine_mode': engine_config.mode.value if hasattr(engine_config.mode, 'value') else str(engine_config.mode),

            # Derived parameters
            'hop_size': hop_size,
            'time_resolution_ms': time_resolution_ms,
            'freq_resolution_hz': freq_resolution_hz,

            # Accuracy metrics
            'pass_rate': extract_float(result.statistics.get('pass_rate', 0)),
            'mean_snr_db': extract_float(result.statistics.get('mean_snr_db', 0)),
            'mean_error': extract_float(result.statistics.get('mean_error', 0)),
        }

        summary_df = pd.DataFrame([summary])
        summary_path = output_dir / f"accuracy_summary_{engine_config.nfft}_{engine_config.channels}.csv"
        summary_df.to_csv(summary_path, index=False)
        mlflow.log_artifact(str(summary_path))

    # Return error rate for minimization
    pass_rate_value = extract_float(result.statistics.get('pass_rate', 0))
    return 1.0 - pass_rate_value


if __name__ == "__main__":
    run_accuracy_benchmark()
