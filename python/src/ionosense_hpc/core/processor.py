"""High-level context manager for the signal processing engine with NVTX.

This module provides the `Processor`, a user-friendly interface to the CUDA
FFT engine with NVTX instrumentation for key operations. It uses a context
manager for automatic resource management and offers presets for common use
cases like real-time and batch processing.
"""

from typing import Any, cast

import numpy as np

from ionosense_hpc.config import EngineConfig, Presets
from ionosense_hpc.core.engine import Engine
from ionosense_hpc.exceptions import EngineStateError
from ionosense_hpc.utils.device import device_info, monitor_device
from ionosense_hpc.utils.logging import logger
from ionosense_hpc.utils.profiling import (
    ProfileColor,
    ProfilingDomain,
    compute_range,
    nvtx_decorate,
    setup_range,
    teardown_range,
)


class Processor:
    """High-level, context-aware interface for CUDA FFT processing.

    This class simplifies interaction with the engine by managing GPU resources
    automatically via Python's `with` statement. It is the recommended entry
    point for most applications.

    The class is NOT thread-safe; each thread should use its own instance.

    Attributes:
        _config: The current engine configuration.
        _engine: The underlying mid-level Engine instance.
        _is_initialized: A flag indicating if GPU resources are allocated.
        _processing_history: A list of performance metrics from each `process` call.
    """

    def __init__(
        self,
        config: EngineConfig | str | None = None,
        auto_init: bool = True
    ):
        """Initializes the processor.

        Args:
            config: An `EngineConfig` object, a preset name as a string
                (e.g., 'realtime'), or None to use the default 'realtime' preset.
            auto_init: If True and a config is provided, `initialize()` is
                called automatically.

        Raises:
            ValueError: If the provided preset name is not recognized.
        """
        if config is None:
            config = Presets.realtime()
        elif isinstance(config, str):
            presets_map = {
                'realtime': Presets.realtime,
                'throughput': Presets.throughput,
                'validation': Presets.validation,
                'profiling': Presets.profiling
            }
            if config.lower() in presets_map:
                config = presets_map[config.lower()]()
            else:
                raise ValueError(f"Unknown preset: {config}")

        self._config: EngineConfig | None = config
        self._engine: Engine = Engine()
        self._is_initialized = False
        self._context_active = False
        self._processing_history: list[dict[str, Any]] = []

        if auto_init and config is not None:
            self.initialize()

    @nvtx_decorate(
        message="Processor.initialize",
        color=ProfileColor.DARK_GRAY,
        domain=ProfilingDomain.CORE,
    )
    def initialize(self, config: EngineConfig | None = None) -> None:
        """Allocates GPU resources and prepares the engine for processing.

        This method must be called before any processing if `auto_init` was
        False or if the processor was instantiated without a configuration.

        Args:
            config: If provided, this configuration will replace the existing one.

        Raises:
            ValueError: If no configuration is available.
            EngineRuntimeError: If GPU initialization fails.
        """
        with setup_range("Processor.initialize"):
            if config is not None:
                self._config = config

            if self._config is None:
                raise ValueError("No configuration provided")

            info = device_info()
            logger.info(f"Initializing on device: {info['name']}")
            logger.info(
                f"  Memory: {info['memory_free_mb']}/{info['memory_total_mb']} MB free"
            )

            self._engine.initialize(self._config)
            self._is_initialized = True
            logger.info("Processor initialized successfully")

    @nvtx_decorate(
        message="Processor.process",
        color=ProfileColor.PURPLE,
        domain=ProfilingDomain.CORE,
        include_args=False,
    )
    def process(
        self,
        input_data: np.ndarray | list,
        return_complex: bool = False
    ) -> np.ndarray:
        """Processes a single frame of input data.

        Args:
            input_data: The input signal data, typically a 1D NumPy array.
            return_complex: If True, returns complex FFT output. (Not implemented)

        Returns:
            A NumPy array containing the magnitude spectrum.

        Raises:
            EngineStateError: If the processor is not initialized.
            NotImplementedError: If `return_complex` is True.
        """
        if not self._is_initialized:
            raise EngineStateError("Processor not initialized", "Call initialize() or use as context manager")

        if return_complex:
            raise NotImplementedError("Complex output not yet supported")

        output = self._engine.process(input_data)
        stats = self._engine.get_stats()

        self._processing_history.append({
            'frame': len(self._processing_history),
            'latency_us': stats.get('latency_us', 0),
            'shape': output.shape
        })

        return cast(np.ndarray, output)

    @nvtx_decorate(
        message="Processor.process_stream",
        color=ProfileColor.NVIDIA_BLUE,
        domain=ProfilingDomain.CORE,
    )
    def process_stream(
        self,
        data_generator,
        max_frames: int | None = None
    ) -> list[np.ndarray]:
        """Processes a stream of data from a generator.

        Args:
            data_generator: An iterator or generator yielding data frames.
            max_frames: The maximum number of frames to process. If None, processes
                until the generator is exhausted.

        Returns:
            A list of NumPy arrays, each containing the magnitude spectrum
            for a processed frame.
        """
        if not self._is_initialized:
            raise EngineStateError("Processor not initialized")

        outputs = []
        frame_count = 0

        for frame_data in data_generator:
            if max_frames and frame_count >= max_frames:
                break

            with compute_range(f"StreamFrame_{frame_count}"):
                output = self.process(frame_data)
            outputs.append(output)
            frame_count += 1

        logger.info(f"Processed {frame_count} frames from stream")
        return outputs

    @nvtx_decorate(
        message="Processor.benchmark",
        color=ProfileColor.NVIDIA_BLUE,
        domain=ProfilingDomain.CORE,
    )
    def benchmark(
        self,
        n_iterations: int = 100,
        input_data: np.ndarray | None = None
    ) -> dict[str, Any]:
        """Runs a performance benchmark and returns statistical results.

        Args:
            n_iterations: The number of processing iterations to run.
            input_data: Optional test data. If None, zero-filled data matching
                the configuration is used.

        Returns:
            A dictionary containing performance statistics (mean, std, p99 latency, etc.).
        """
        if not self._is_initialized:
            raise EngineStateError("Processor not initialized")

        if input_data is None:
            assert self._config is not None
            input_data = np.zeros(self._config.nfft * self._config.batch, dtype=np.float32)

        latencies_list: list[float] = []
        logger.info(f"Running benchmark with {n_iterations} iterations...")

        for i in range(n_iterations):
            with compute_range(f"BenchmarkIteration_{i}"):
                self.process(input_data)
                stats = self._engine.get_stats()
                latencies_list.append(stats['latency_us'])

        latencies = np.array(latencies_list)
        results = {
            'n_iterations': n_iterations,
            'mean_latency_us': float(np.mean(latencies)),
            'p50_latency_us': float(np.percentile(latencies, 50)),
            'std_latency_us': float(np.std(latencies)),
            'min_latency_us': float(np.min(latencies)),
            'max_latency_us': float(np.max(latencies)),
            'p95_latency_us': float(np.percentile(latencies, 95)),
            'p99_latency_us': float(np.percentile(latencies, 99))
        }

        logger.info(f"Benchmark complete: mean={results['mean_latency_us']:.1f} μs, "
                   f"p99={results['p99_latency_us']:.1f} μs")
        return results

    @nvtx_decorate(
        message="Processor.reset",
        color=ProfileColor.RED,
        domain=ProfilingDomain.CORE,
    )
    def reset(self) -> None:
        """Resets the engine, freeing all GPU resources."""
        with teardown_range("Processor.reset"):
            self._engine.reset()
            self._is_initialized = False
            self._processing_history.clear()
            logger.info("Processor reset")

    def get_stats(self) -> dict[str, Any]:
        """Gets current performance statistics from the engine and processor.

        Returns:
            A dictionary of performance metrics.
        """
        stats = self._engine.get_stats() if self._is_initialized else {}
        stats['total_processed'] = len(self._processing_history)

        if self._processing_history:
            recent = self._processing_history[-10:]
            recent_latencies = [h['latency_us'] for h in recent]
            stats['recent_avg_latency_us'] = np.mean(recent_latencies)

        return stats

    def print_status(self) -> None:
        """Prints a human-readable status report to the console."""
        print("Processor Status:")
        print(f"  Initialized: {self._is_initialized}")

        if self._is_initialized:
            print(f"  Configuration: {self._config}")
            stats = self.get_stats()
            print(f"  Frames Processed: {stats.get('total_processed', 0)}")
            if 'recent_avg_latency_us' in stats:
                print(f"  Recent Latency: {stats['recent_avg_latency_us']:.1f} μs")
            print("\n" + monitor_device())

    @property
    def is_initialized(self) -> bool:
        """Returns True if the processor is initialized."""
        return self._is_initialized

    @property
    def config(self) -> EngineConfig | None:
        """Returns the current processor configuration."""
        return self._config

    @property
    def history(self) -> list[dict[str, Any]]:
        """Returns a copy of the processing history."""
        return self._processing_history.copy()

    def __enter__(self):
        """Enters the context manager, initializing if necessary."""
        if not self._is_initialized:
            self.initialize()
        self._context_active = True
        logger.debug("Processor context entered")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exits the context manager, ensuring GPU synchronization."""
        self._context_active = False
        if exc_type is not None:
            logger.error(f"Exception in processor context: {exc_type.__name__}: {exc_val}")

        try:
            self._engine.synchronize()
            logger.debug("Processor synchronized on context exit")
        except Exception as e:
            logger.warning(f"Failed to synchronize on exit: {e}")

        return False

    def __repr__(self) -> str:
        """Returns a string representation of the processor."""
        state = "initialized" if self._is_initialized else "uninitialized"
        return f"<Processor state={state} config={self._config}>"
