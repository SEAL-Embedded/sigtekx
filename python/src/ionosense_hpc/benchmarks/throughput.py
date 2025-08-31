"""
ionosense_hpc.benchmarks.throughput
-----------------------------------
Benchmark for measuring the maximum sustainable throughput of the engine.

This test focuses on how many FFTs can be processed per second when the
pipeline is kept fully saturated with work, leveraging asynchronous execution
and multiple CUDA streams.
"""
from __future__ import annotations

import time
import numpy as np

from .base import BenchmarkBase
from ..core.pipelines import Pipeline, PipelineBuilder
from ..core.config import FFTConfig
from ..utils.console import safe_print

class ThroughputBenchmark(BenchmarkBase):
    """
    Measures maximum sustainable FFTs/second using an asynchronous pipeline.
    """

    def run_single(self, fft_size: int, batch_size: int) -> dict:
        """
        Runs a throughput test for a single configuration.

        Args:
            fft_size: The FFT length to test.
            batch_size: The number of simultaneous signals to test.

        Returns:
            A dictionary containing throughput metrics.
        """
        if self.config.verbose:
            safe_print(f"  Measuring throughput: FFT Size={fft_size}, Batch Size={batch_size}")

        # 1. Build a pipeline configured for maximum throughput
        fft_config = FFTConfig(nfft=fft_size, batch_size=batch_size)
        builder = PipelineBuilder()
        builder.with_fft(fft_config.nfft, fft_config.batch_size)
        builder.with_streams(self.config.num_streams)
        builder.with_graphs(self.config.use_graphs)
        pipeline = builder.build()
        pipeline.prepare()

        # 2. Prepare dummy data for all streams to keep the GPU busy
        for i in range(self.config.num_streams):
            input_buffer = pipeline.get_input_buffer(i)
            input_buffer[:] = np.random.randn(*input_buffer.shape).astype(np.float32)

        # 3. Warmup phase
        for i in range(self.config.warmup_iterations):
            pipeline.execute(stream_idx=i % self.config.num_streams)
        pipeline.sync_all()

        # 4. Measurement loop
        start_time = time.perf_counter()
        for i in range(self.config.num_iterations):
            # This is a fire-and-forget loop, relying on the C++ engine's
            # internal stream synchronization to manage the pipeline.
            pipeline.execute(stream_idx=i % self.config.num_streams)

        # 5. Final synchronization to ensure all work is complete
        pipeline.sync_all()
        end_time = time.perf_counter()

        # 6. Calculate and return metrics
        elapsed_seconds = end_time - start_time
        total_ffts = self.config.num_iterations * batch_size
        ffts_per_second = total_ffts / elapsed_seconds if elapsed_seconds > 0 else 0
        gbytes_per_second = (total_ffts * fft_size * 4 * 2) / elapsed_seconds / 1e9 # Input+Output

        return {
            "total_ffts": total_ffts,
            "elapsed_seconds": elapsed_seconds,
            "ffts_per_second": ffts_per_second,
            "gbytes_per_second": gbytes_per_second,
        }
