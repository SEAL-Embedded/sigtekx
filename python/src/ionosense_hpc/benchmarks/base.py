"""
ionosense_hpc.benchmarks.base
-----------------------------
Defines the foundational classes and data structures for the entire
benchmarking framework. Establishes a consistent and extensible pattern
for creating new performance tests.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..utils.device import get_device_info, get_cuda_version

class BenchmarkMode(Enum):
    """Enumeration of available benchmark execution modes."""
    ACCURACY = "accuracy"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    SWEEP = "sweep"

@dataclass
class BenchmarkConfig:
    """
    A structured, validated configuration for a benchmark run.

    This dataclass ensures that all benchmarks are run with a consistent
    set of parameters, promoting reproducibility (RE).
    """
    mode: BenchmarkMode
    fft_sizes: List[int] = field(default_factory=lambda: [4096])
    batch_sizes: List[int] = field(default_factory=lambda: [2])
    num_iterations: int = 1000
    warmup_iterations: int = 100
    use_graphs: bool = True
    num_streams: int = 3
    output_dir: Path = Path("research/results/benchmarks")
    save_results: bool = True
    verbose: bool = True

@dataclass
class BenchmarkResult:
    """
    A structured container for storing the outcome of a benchmark run.
    Ensures that results are self-documenting and easily archivable.
    """
    config: BenchmarkConfig
    timestamp: datetime
    device_info: Dict[str, Any]
    metrics: Dict[str, Any]
    raw_data: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def save(self) -> Path:
        """Saves the benchmark result to a versioned JSON file."""
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        ts_str = self.timestamp.strftime("%Y%m%d_%H%M%S")
        filename = f"{self.config.mode.value}_{ts_str}.json"
        filepath = self.config.output_dir / filename

        # Prepare data for JSON serialization
        data_to_save = {
            "config": self.config.__dict__,
            "timestamp": self.timestamp.isoformat(),
            "device_info": self.device_info,
            "metrics": self.metrics,
            "metadata": self.metadata,
        }
        # Convert non-serializable types
        data_to_save['config']['mode'] = self.config.mode.value
        data_to_save['config']['output_dir'] = str(self.config.output_dir)
        if self.raw_data is not None:
            data_to_save['raw_data'] = self.raw_data.tolist()

        with open(filepath, 'w') as f:
            json.dump(data_to_save, f, indent=2)

        return filepath

class BenchmarkBase:
    """
    Abstract base class for all benchmark implementations.
    This ensures all benchmarks follow the same setup -> run -> teardown
    workflow, a key principle of good RSE design.
    """
    def __init__(self, config: BenchmarkConfig):
        self.config = config

    def setup(self) -> None:
        """Code to run before any benchmark iterations."""
        if self.config.verbose:
            print(f"Setting up {self.config.mode.value} benchmark...")

    def teardown(self) -> None:
        """Code to run after all benchmark iterations."""
        if self.config.verbose:
            print(f"Tearing down {self.config.mode.value} benchmark...")

    def run_single(self, fft_size: int, batch_size: int) -> Dict[str, Any]:
        """
        Execute the core logic for a single configuration point.
        Must be implemented by all subclasses.
        """
        raise NotImplementedError("Subclasses must implement the run_single method.")

    def run(self) -> BenchmarkResult:
        """
        Orchestrates the entire benchmark run: setup, loop over configs, teardown.
        """
        self.setup()
        try:
            device_info = get_device_info(0).__dict__
            all_metrics = {}

            for fft_size in self.config.fft_sizes:
                for batch_size in self.config.batch_sizes:
                    key = f"fft{fft_size}_batch{batch_size}"
                    all_metrics[key] = self.run_single(fft_size, batch_size)

            result = BenchmarkResult(
                config=self.config,
                timestamp=datetime.now(),
                device_info=device_info,
                metrics=all_metrics,
                metadata={
                    "cuda_version": ".".join(map(str, get_cuda_version()))
                }
            )

            if self.config.save_results:
                filepath = result.save()
                if self.config.verbose:
                    print(f"Results saved to: {filepath}")

            return result
        finally:
            self.teardown()
