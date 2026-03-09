#!/usr/bin/env python
"""
Single-purpose script to run throughput benchmarks.

This script is Hydra-aware and logs results to MLflow.
Communication with other scripts happens through artifact files.
"""

import sys
import warnings
from pathlib import Path

import hydra
import mlflow
import pandas as pd
from omegaconf import DictConfig, OmegaConf

from sigtekx.benchmarks import ThroughputBenchmark, ThroughputBenchmarkConfig
from sigtekx.benchmarks.mlflow_utils import log_benchmark_errors, setup_mlflow
from sigtekx.config import EngineConfig

# Add experiments directory to path for metrics import
sys.path.insert(0, str(Path(__file__).parent.parent / "experiments"))
from analysis.metrics import calculate_rtf


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
    setup_mlflow(cfg)

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

        # Log error metrics to MLflow (using shared utility)
        log_benchmark_errors(result, Path(cfg.paths.data), result.config)

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

        # Calculate derived scientific metrics
        hop_size = int(engine_config.nfft * (1 - engine_config.overlap))
        time_resolution_ms = (engine_config.nfft / engine_config.sample_rate_hz) * 1000
        freq_resolution_hz = engine_config.sample_rate_hz / engine_config.nfft

        # Real-Time Factor (RTF): Academic convention (lower is better)
        # RTF = sample_rate_hz / (fps * hop_size)
        # RTF < 1.0 means faster than real-time, RTF > 1.0 means falling behind
        rtf = calculate_rtf(fps, hop_size, engine_config.sample_rate_hz)

        # Extract experiment metadata from cfg (with fallbacks)
        experiment_group = cfg.get('experiment', {}).get('experiment_group', 'unknown')
        sample_rate_category = cfg.get('experiment', {}).get('sample_rate_category', f"{engine_config.sample_rate_hz/1000:.0f}kHz")

        # Save enriched summary with scientific metrics
        summary = {
            # Experiment metadata (for dashboard filtering)
            'experiment_group': experiment_group,
            'sample_rate_category': sample_rate_category,

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

            # Performance metrics
            'frames_per_second': fps,
            'gb_per_second': result.statistics.get('gb_per_second', {}).get('mean', 0),
            'gpu_utilization': result.statistics.get('gpu_utilization_mean', 0),

            # Scientific metrics for ionosphere research
            'rtf': rtf,  # Real-Time Factor - critical for real-time processing capability
        }

        summary_df = pd.DataFrame([summary])

        # === CSV WRITE: UNIQUE FILENAME PATTERN ===
        # Each configuration writes to unique CSV to prevent race conditions during
        # parallel multirun sweeps. Filename encodes full config:
        #   Format: throughput_summary_{nfft}_{channels}_{overlap}_{mode}.csv
        #   Example: throughput_summary_4096_2_0p7500_streaming.csv
        #
        # Why this works:
        #   - Different configs → different files → zero collision risk
        #   - Same config re-run → atomic overwrite (desired behavior)
        #   - Analysis scripts auto-merge via glob pattern (*_summary_*.csv)
        #
        # Verified safe by: tests/test_csv_multirun_safety.py
        # Design rationale: docs/benchmarking/csv-file-organization.md
        exec_mode = engine_config.mode.value if hasattr(engine_config.mode, 'value') else str(engine_config.mode)
        overlap_str = f"{engine_config.overlap:.4f}".replace('.', 'p')  # 0.75 -> 0p7500
        summary_path = output_dir / f"throughput_summary_{engine_config.nfft}_{engine_config.channels}_{overlap_str}_{exec_mode}.csv"
        summary_df.to_csv(summary_path, index=False)
        mlflow.log_artifact(str(summary_path))

    # Return negative FPS for minimization (Hydra sweeper minimizes by default)
    return -fps


if __name__ == "__main__":
    run_throughput_benchmark()
