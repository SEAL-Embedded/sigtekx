"""Mid-level engine wrapper with validation, buffer management, and NVTX profiling."""

from typing import Any

import numpy as np

from ionosense_hpc.config import EngineConfig, validate_batch_size, validate_input_array
from ionosense_hpc.core.raw_engine import RawEngine
from ionosense_hpc.exceptions import EngineStateError, ValidationError
from ionosense_hpc.utils.logging import log_config, log_performance, logger
from ionosense_hpc.utils.profiling import (
    ProfileColor,
    ProfilingDomain,
    compute_range,
    nvtx_decorate,
    nvtx_range,
    setup_range,
    sync_range,
    teardown_range,
    transfer_range,
    warmup_range,
)


class Engine:
    """Mid-level wrapper providing validation and buffer management.

    This class adds input validation, automatic buffer sizing, and
    performance tracking on top of the raw C++ engine. It handles
    the details of preparing data for the GPU while exposing a
    clean interface.
    """

    def __init__(self, config: EngineConfig | None = None):
        """Initialize the engine.

        Args:
            config: Engine configuration (can be set later)
        """
        self._raw_engine = RawEngine()
        self._config: EngineConfig | None = None
        self._input_buffer: np.ndarray | None = None
        self._output_buffer: np.ndarray | None = None
        self._frame_count = 0
        self._total_latency_us = 0.0
        self._is_warming_up = False

        if config is not None:
            self.initialize(config)

    @nvtx_decorate(
        message="Engine.initialize",
        color=ProfileColor.DARK_GRAY,
        domain=ProfilingDomain.CORE,
    )
    def initialize(self, config: EngineConfig) -> None:
        """Initialize the engine with configuration.

        Args:
            config: Validated engine configuration

        Raises:
            EngineRuntimeError: If initialization fails
        """
        with setup_range("Engine.initialize"):
            # Store config
            self._config = config

            # Pre-allocate buffers
            input_size = config.nfft * config.batch
            output_size = config.num_output_bins * config.batch

            with nvtx_range("AllocateBuffers", color=ProfileColor.DARK_GRAY):
                self._input_buffer = np.zeros(input_size, dtype=np.float32)
                self._output_buffer = np.zeros(output_size, dtype=np.float32)

            # Initialize raw engine
            with nvtx_range("InitializeRawEngine", color=ProfileColor.DARK_GRAY):
                config_dict = config.model_dump()
                self._raw_engine.initialize(config_dict)

            # Reset statistics
            self._frame_count = 0
            self._total_latency_us = 0.0

            # Log configuration
            log_config(config)
            logger.info(
                f"Engine initialized with preset buffers: input={input_size}, output={output_size}"
            )

            # Run warmup if configured
            if config.warmup_iters > 0:
                self._run_warmup(config.warmup_iters)

    @nvtx_decorate(
        message="Engine.process",
        color=ProfileColor.PURPLE,
        domain=ProfilingDomain.CORE,
    )
    def process(
        self,
        input_data: np.ndarray | list,
        output: np.ndarray | None = None
    ) -> np.ndarray:
        """Process a batch of input data.

        Args:
            input_data: Input samples as array or list
            output: Optional pre-allocated output buffer

        Returns:
            2D array of magnitude spectra [batch, bins]

        Raises:
            EngineStateError: If not initialized
            ValidationError: If input is invalid
        """
        if not self.is_initialized:
            raise EngineStateError("Engine not initialized")

        with nvtx_range("ValidateInput", color=ProfileColor.YELLOW):
            # Convert and validate input
            if not isinstance(input_data, np.ndarray):
                input_data = np.asarray(input_data, dtype=np.float32)

            input_data = validate_input_array(
                input_data,
                expected_dtype=np.dtype(np.float32),
                name="input_data",
            )

        # Validate size
        assert self._config is not None
        validate_batch_size(input_data, self._config)

        # Copy to internal buffer if needed
        with transfer_range("CopyInput", direction="H2D"):
            assert self._input_buffer is not None
            if input_data.shape != self._input_buffer.shape:
                input_data = input_data.flatten()
            np.copyto(self._input_buffer, input_data)

        # Process through raw engine
        with compute_range("RawProcess"):
            result = self._raw_engine.process(self._input_buffer)

        # Update statistics
        if not self._is_warming_up:
            stats = self._raw_engine.get_stats()
            self._frame_count += 1
            self._total_latency_us += stats['latency_us']

        # Copy to output if provided
        if output is not None:
            expected_shape = (self._config.batch, self._config.num_output_bins)
            if output.shape != expected_shape:
                raise ValidationError(
                    "Output buffer shape mismatch",
                    expected=str(expected_shape),
                    got=str(output.shape),
                )
            with transfer_range("CopyOutput", direction="D2H"):
                np.copyto(output, result)
            return output

        return result

    @nvtx_decorate(
        message="Engine.process_frames",
        color=ProfileColor.NVIDIA_BLUE,
        domain=ProfilingDomain.CORE,
    )
    def process_frames(
        self,
        input_data: np.ndarray,
        hop_size: int | None = None
    ) -> np.ndarray:
        """Process multiple overlapping frames.

        Args:
            input_data: Long input signal
            hop_size: Samples between frames (None for config default)

        Returns:
            3D array of spectra [frames, batch, bins]
        """
        if not self.is_initialized:
            raise EngineStateError("Engine not initialized")

        if hop_size is None:
            assert self._config is not None
            hop_size = self._config.hop_size

        with nvtx_range("ValidateFramedInput", color=ProfileColor.YELLOW):
            # Validate input
            input_data = validate_input_array(
                input_data,
                expected_dtype=np.dtype(np.float32),
                name="input_data",
            )

        # Calculate number of frames
        assert self._config is not None
        frame_size = self._config.nfft * self._config.batch
        if len(input_data) < frame_size:
            raise ValidationError(
                "Input too short for even one frame",
                expected=f">= {frame_size} samples",
                got=f"{len(input_data)} samples"
            )

        n_frames = (len(input_data) - frame_size) // (hop_size * self._config.batch) + 1

        # Process frames
        output_shape = (n_frames, self._config.batch, self._config.num_output_bins)
        output = np.zeros(output_shape, dtype=np.float32)

        with compute_range(f"ProcessFrames_{n_frames}"):
            for i in range(n_frames):
                with nvtx_range(f"Frame_{i}", color=ProfileColor.PURPLE, payload=i):
                    start_idx = i * hop_size * self._config.batch
                    end_idx = start_idx + frame_size
                    frame_data = input_data[start_idx:end_idx]
                    output[i] = self.process(frame_data)

        return output

    @nvtx_decorate(
        message="Engine.reset",
        color=ProfileColor.RED,
        domain=ProfilingDomain.CORE,
    )
    def reset(self) -> None:
        """Reset the engine to uninitialized state."""
        with teardown_range("Engine.reset"):
            self._raw_engine.reset()
            self._config = None
            self._input_buffer = None
            self._output_buffer = None
            self._frame_count = 0
            self._total_latency_us = 0.0
            logger.info("Engine reset")

    @nvtx_decorate(
        message="Engine.synchronize",
        color=ProfileColor.YELLOW,
        domain=ProfilingDomain.CORE,
    )
    def synchronize(self) -> None:
        """Synchronize all CUDA streams."""
        with sync_range("Engine.synchronize"):
            self._raw_engine.synchronize()

    def get_stats(self) -> dict[str, Any]:
        """Get accumulated performance statistics.

        Returns:
            Dictionary with performance metrics
        """
        stats = self._raw_engine.get_stats()

        # Add averaged metrics
        if self._frame_count > 0:
            stats['avg_latency_us'] = self._total_latency_us / self._frame_count
            stats['total_frames'] = self._frame_count

        return stats

    def log_performance(self) -> None:
        """Log current performance statistics."""
        stats = self.get_stats()
        log_performance(stats)

    @property
    def is_initialized(self) -> bool:
        """Check if engine is initialized."""
        return self._raw_engine.is_initialized

    @property
    def config(self) -> EngineConfig | None:
        """Get current configuration."""
        return self._config

    @property
    def device_info(self) -> dict[str, Any]:
        """Get information about the current CUDA device."""
        return self._raw_engine.get_runtime_info()

    def _run_warmup(self, iterations: int) -> None:
        """Run warmup iterations to stabilize GPU clocks.

        Args:
            iterations: Number of warmup iterations
        """
        logger.info(f"Running {iterations} warmup iterations...")
        self._is_warming_up = True

        # Create dummy data
        assert self._config is not None
        dummy_input = np.zeros(
            self._config.nfft * self._config.batch,
            dtype=np.float32
        )

        with warmup_range("EngineWarmup"):
            for i in range(iterations):
                with nvtx_range(
                    f"WarmupIteration_{i}", color=ProfileColor.LIGHT_GRAY, payload=i
                ):
                    self.process(dummy_input)

        self._is_warming_up = False
        self._frame_count = 0
        self._total_latency_us = 0.0

        # Get warmup stats
        stats = self._raw_engine.get_stats()
        logger.info(f"Warmup complete. Final latency: {stats['latency_us']:.1f} μs")

    def __repr__(self) -> str:
        if self.is_initialized:
            return f"<Engine initialized config={self._config}>"
        return "<Engine uninitialized>"

    def __del__(self):
        """Ensure cleanup on deletion."""
        try:
            if hasattr(self, '_raw_engine') and self.is_initialized:
                self.reset()
        except Exception:
            pass
