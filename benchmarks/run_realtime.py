#!/usr/bin/env python
"""
Single-purpose script to run real-time benchmarks.

This script is Hydra-aware and logs results to MLflow.
It integrates with the modern artifacts layout (artifacts/experiments + artifacts/data).
"""

import warnings
from pathlib import Path

import hydra
import mlflow
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from ionosense_hpc.benchmarks import RealtimeBenchmark, RealtimeBenchmarkConfig
from ionosense_hpc.config import EngineConfig


@hydra.main(version_base=None, config_path="../experiments/conf", config_name="config")
def run_realtime_benchmark(cfg: DictConfig) -> float:
    """Run real-time benchmark with MLflow tracking and save results.

    Returns:
        Error surrogate (1 - compliance) for Hydra optimization
    """
    # ===== ROBUSTNESS FIX: Auto-load default benchmark if missing =====
    if 'benchmark' not in cfg:
        warnings.warn("⚠️  Benchmark config not specified. Defaulting to '+benchmark=realtime'.", stacklevel=2)
        # Get the original config directory to reliably find the default file
        config_dir = f"{hydra.utils.get_original_cwd()}/experiments/conf/benchmark"
        default_benchmark = OmegaConf.load(f"{config_dir}/realtime.yaml")
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
    benchmark_config = RealtimeBenchmarkConfig(**cfg.benchmark, engine_config=engine_config.model_dump())

    # Setup MLflow
    mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)
    mlflow.set_experiment(cfg.mlflow.experiment_name)

    run_name = f"realtime_{engine_config.nfft}x{engine_config.channels}"
    with mlflow.start_run(run_name=run_name):
        # Log configuration parameters
        mlflow.log_params({
            "engine.nfft": engine_config.nfft,
            "engine.channels": engine_config.channels,
            "engine.overlap": engine_config.overlap,
            "benchmark.stream_duration_s": benchmark_config.stream_duration_s,
            "benchmark.frame_deadline_ms": benchmark_config.frame_deadline_ms,
            "benchmark.strict_timing": benchmark_config.strict_timing,
            "benchmark.measure_jitter": benchmark_config.measure_jitter,
            "benchmark.buffer_ahead_frames": benchmark_config.buffer_ahead_frames,
            "benchmark.simulate_io_delay": benchmark_config.simulate_io_delay,
        })

        # Run benchmark
        benchmark = RealtimeBenchmark(benchmark_config)
        result = benchmark.run()

        stats = result.statistics if isinstance(result.statistics, dict) else {}
        # Extract scalar metrics from potentially nested statistics dictionaries
        def extract_float(value, default=0.0) -> float:
            if isinstance(value, dict):
                for key in ("mean", "median", "value"):
                    if key in value and value[key] is not None:
                        try:
                            return float(value[key])
                        except (TypeError, ValueError):
                            continue
                for candidate in value.values():
                    if candidate is None:
                        continue
                    try:
                        return float(candidate)
                    except (TypeError, ValueError):
                        continue
                return float(default)
            try:
                return float(value)
            except (TypeError, ValueError):
                return float(default)

        compliance = extract_float(stats.get("deadline_compliance_rate"), 0.0)
        mlflow.log_metrics({
            "realtime.compliance_rate": compliance,
            "realtime.mean_latency_ms": extract_float(stats.get("mean_latency_ms"), 0.0),
            "realtime.p99_latency_ms": extract_float(stats.get("p99_latency_ms"), 0.0),
            "realtime.mean_jitter_ms": extract_float(stats.get("mean_jitter_ms"), 0.0),
            "realtime.frames_processed": extract_float(stats.get("frames_processed"), 0.0),
            "realtime.deadline_misses": extract_float(stats.get("deadline_misses"), 0.0),
            "realtime.frames_dropped": extract_float(stats.get("frames_dropped"), 0.0),
        })

        # Persist summary to artifacts/data
        output_dir = Path(cfg.paths.data)
        output_dir.mkdir(parents=True, exist_ok=True)

        summary = {
            "engine_nfft": engine_config.nfft,
            "engine_channels": engine_config.channels,
            "stream_duration_s": benchmark_config.stream_duration_s,
            "deadline_compliance_rate": compliance,
            "mean_latency_ms": extract_float(stats.get("mean_latency_ms"), 0.0),
            "p99_latency_ms": extract_float(stats.get("p99_latency_ms"), 0.0),
            "mean_jitter_ms": extract_float(stats.get("mean_jitter_ms"), 0.0),
            "frames_processed": extract_float(stats.get("frames_processed"), 0.0),
            "deadline_misses": extract_float(stats.get("deadline_misses"), 0.0),
            "frames_dropped": extract_float(stats.get("frames_dropped"), 0.0),
        }

        summary_df = pd.DataFrame([summary])
        summary_path = output_dir / f"realtime_summary_{engine_config.nfft}_{engine_config.channels}.csv"
        summary_df.to_csv(summary_path, index=False)
        mlflow.log_artifact(str(summary_path))

    # Hydra minimises objective: return miss rate surrogate
    return 1.0 - compliance


if __name__ == "__main__":
    run_realtime_benchmark()
