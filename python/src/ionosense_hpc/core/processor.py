"""High-level context manager for the signal processing engine."""

from typing import Any

import numpy as np

from ionosense_hpc.config import EngineConfig, Presets
from ionosense_hpc.core.engine import Engine
from ionosense_hpc.exceptions import EngineStateError
from ionosense_hpc.utils.device import device_info, monitor_device
from ionosense_hpc.utils.logging import logger


class Processor:
    """High-level interface with context manager support.

    This class provides the most Pythonic interface to the engine,
    with automatic resource management, presets, and convenience methods.
    It's designed to be used as a context manager for proper cleanup.

    Examples:
        >>> from ionosense_hpc import Processor, Presets
        >>> with Processor(Presets.realtime()) as proc:
        ...     output = proc.process(input_data)
    """

    def __init__(
        self,
        config: EngineConfig | str | None = None,
        auto_init: bool = True
    ):
        """Initialize the processor.

        Args:
            config: Configuration object, preset name, or None for default
            auto_init: Whether to initialize immediately
        """
        # Handle config input
        if config is None:
            config = Presets.realtime()
        elif isinstance(config, str):
            # Try to get preset by name
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

        self._config = config
        self._engine = Engine()
        self._is_initialized = False
        self._context_active = False
        self._processing_history = []

        if auto_init and config is not None:
            self.initialize()

    def initialize(self, config: EngineConfig | None = None) -> None:
        """Initialize the processor and engine.

        Args:
            config: Optional new configuration
        """
        if config is not None:
            self._config = config

        if self._config is None:
            raise ValueError("No configuration provided")

        # Log device info
        info = device_info()
        logger.info(f"Initializing on device: {info['name']}")
        logger.info(f"  Memory: {info['memory_free_mb']}/{info['memory_total_mb']} MB free")
        logger.info(f"  Compute Capability: {info['compute_capability']}")

        # Initialize engine
        self._engine.initialize(self._config)
        self._is_initialized = True

        logger.info("Processor initialized successfully")

    def process(
        self,
        input_data: np.ndarray | list,
        return_complex: bool = False
    ) -> np.ndarray:
        """Process input data through the FFT pipeline.

        Args:
            input_data: Input signal data
            return_complex: If True, return complex spectrum (future feature)

        Returns:
            Magnitude spectrum [batch, bins]

        Raises:
            EngineStateError: If not initialized
        """
        if not self._is_initialized:
            raise EngineStateError(
                "Processor not initialized",
                "Use as context manager or call initialize()"
            )

        if return_complex:
            raise NotImplementedError("Complex output not yet supported")

        # Process through engine
        output = self._engine.process(input_data)

        # Track in history
        stats = self._engine.get_stats()
        self._processing_history.append({
            'frame': len(self._processing_history),
            'latency_us': stats.get('latency_us', 0),
            'shape': output.shape
        })

        return output

    def process_stream(
        self,
        data_generator,
        max_frames: int | None = None
    ) -> list[np.ndarray]:
        """Process a stream of data frames.

        Args:
            data_generator: Iterator yielding input frames
            max_frames: Maximum frames to process

        Returns:
            List of output spectra
        """
        if not self._is_initialized:
            raise EngineStateError("Processor not initialized")

        outputs = []
        frame_count = 0

        for frame_data in data_generator:
            if max_frames and frame_count >= max_frames:
                break

            output = self.process(frame_data)
            outputs.append(output)
            frame_count += 1

        logger.info(f"Processed {frame_count} frames from stream")
        return outputs

    def benchmark(
        self,
        n_iterations: int = 100,
        input_data: np.ndarray | None = None
    ) -> dict[str, Any]:
        """Run a quick benchmark.

        Args:
            n_iterations: Number of iterations
            input_data: Optional test data (None for zeros)

        Returns:
            Benchmark results dictionary
        """
        if not self._is_initialized:
            raise EngineStateError("Processor not initialized")

        # Prepare test data
        if input_data is None:
            input_data = np.zeros(
                self._config.nfft * self._config.batch,
                dtype=np.float32
            )

        # Run benchmark
        latencies = []
        logger.info(f"Running benchmark with {n_iterations} iterations...")

        for _ in range(n_iterations):
            self.process(input_data)
            stats = self._engine.get_stats()
            latencies.append(stats['latency_us'])

        # Calculate statistics
        latencies = np.array(latencies)
        results = {
            'n_iterations': n_iterations,
            'mean_latency_us': float(np.mean(latencies)),
            'std_latency_us': float(np.std(latencies)),
            'min_latency_us': float(np.min(latencies)),
            'max_latency_us': float(np.max(latencies)),
            'p50_latency_us': float(np.percentile(latencies, 50)),
            'p95_latency_us': float(np.percentile(latencies, 95)),
            'p99_latency_us': float(np.percentile(latencies, 99))
        }

        logger.info(f"Benchmark complete: mean={results['mean_latency_us']:.1f} μs, "
                   f"p99={results['p99_latency_us']:.1f} μs")

        return results

    def reset(self) -> None:
        """Reset the processor and engine."""
        self._engine.reset()
        self._is_initialized = False
        self._processing_history.clear()
        logger.info("Processor reset")

    def get_stats(self) -> dict[str, Any]:
        """Get current statistics.

        Returns:
            Combined statistics dictionary
        """
        stats = self._engine.get_stats() if self._is_initialized else {}

        # Add processor-level stats
        stats['total_processed'] = len(self._processing_history)

        if self._processing_history:
            recent = self._processing_history[-10:]  # Last 10 frames
            recent_latencies = [h['latency_us'] for h in recent]
            stats['recent_avg_latency_us'] = np.mean(recent_latencies)

        return stats

    def print_status(self) -> None:
        """Print current processor status."""
        print("Processor Status:")
        print(f"  Initialized: {self._is_initialized}")

        if self._is_initialized:
            print(f"  Configuration: {self._config}")
            stats = self.get_stats()
            print(f"  Frames Processed: {stats.get('total_processed', 0)}")
            if 'recent_avg_latency_us' in stats:
                print(f"  Recent Latency: {stats['recent_avg_latency_us']:.1f} μs")

            # Device status
            print("\n" + monitor_device())

    @property
    def is_initialized(self) -> bool:
        """Check if processor is initialized."""
        return self._is_initialized

    @property
    def config(self) -> EngineConfig | None:
        """Get current configuration."""
        return self._config

    @property
    def history(self) -> list[dict[str, Any]]:
        """Get processing history."""
        return self._processing_history.copy()

    def __enter__(self):
        """Enter context manager."""
        if not self._is_initialized:
            self.initialize()
        self._context_active = True
        logger.debug("Processor context entered")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager with cleanup."""
        self._context_active = False

        # Log any exception
        if exc_type is not None:
            logger.error(f"Exception in processor context: {exc_type.__name__}: {exc_val}")

        # Always cleanup
        try:
            self._engine.synchronize()
            logger.debug("Processor synchronized on context exit")
        except Exception as e:
            logger.warning(f"Failed to synchronize on exit: {e}")

        # Don't suppress exceptions
        return False

    def __repr__(self) -> str:
        state = "initialized" if self._is_initialized else "uninitialized"
        return f"<Processor state={state} config={self._config}>"
