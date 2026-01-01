"""Unified CUDA FFT Signal Processing Engine.

Single, cohesive API for high-performance signal processing following best practices:
- Simple over easy (PyTorch philosophy)
- Explicit configuration (scikit-learn pattern)
- One obvious way to do things (Python zen)
- Sensible defaults with full customization

The Engine class is the single entry point for all processing modes:
- Preset-based: Engine(preset='iono')
- Config-based: Engine(config=my_config)
- Pipeline-based: Engine(pipeline=my_pipeline)
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import numpy as np
from numpy.typing import ArrayLike, NDArray

from sigtekx.config import (
    EngineConfig,
    ExecutionMode,
    OutputMode,
    ScalePolicy,
    WindowNorm,
    WindowSymmetry,
    WindowType,
    validate_config_device_compatibility,
    validate_input_array,
    validate_input_size,
)
from sigtekx.exceptions import (
    DeviceNotFoundError,
    DllLoadError,
    EngineRuntimeError,
    EngineStateError,
    ValidationError,
)

if TYPE_CHECKING:
    from sigtekx.core.builder import Pipeline

# Type aliases
FloatArray = NDArray[np.float32]


def _import_cpp_engine() -> Any:
    """Import the C++ extension with proper error handling.

    Returns:
        The loaded _native module

    Raises:
        DllLoadError: If the extension cannot be loaded
    """
    try:
        from . import _native  # type: ignore[attr-defined]
        return _native
    except ImportError as e:
        error_str = str(e)
        if "DLL load failed" in error_str or "cannot open shared object" in error_str:
            raise DllLoadError("_native", e) from e
        elif "No module named" in error_str:
            raise DllLoadError(
                "_native",
                RuntimeError("Extension not found. Build with: ./scripts/cli.ps1 build")
            ) from e
        raise


class Engine:
    """Unified CUDA FFT signal processing engine.

    Single entry point supporting three initialization patterns:
    1. Preset-based (simple): Engine(preset='iono')
    2. Config-based (flexible): Engine(config=custom_config)
    3. Pipeline-based (advanced): Engine(pipeline=custom_pipeline)

    The engine automatically selects the appropriate executor (Batch or Streaming)
    based on the execution mode.

    Examples:
        # Preset-based (90% of use cases)
        >>> engine = Engine(preset='iono')
        >>> engine = Engine(preset='iono', mode='streaming')

        # Config-based (custom requirements)
        >>> config = EngineConfig(nfft=4096, channels=8, overlap=0.75)
        >>> engine = Engine(config=config)

        # Pipeline-based (full control)
        >>> from sigtekx import PipelineBuilder
        >>> pipeline = (PipelineBuilder()
        ...     .add_window('blackman')
        ...     .add_fft('1/N')
        ...     .add_magnitude()
        ...     .configure(nfft=4096, channels=8)
        ...     .build())
        >>> engine = Engine(pipeline=pipeline)

        # Quick parameter overrides
        >>> engine = Engine(preset='iono', nfft=8192, overlap=0.875)

        # Context manager (recommended)
        >>> with Engine(preset='iono') as engine:
        ...     output = engine.process(signal_data)

    Attributes:
        config: Read-only engine configuration
        is_initialized: Whether GPU resources are allocated
        stats: Performance statistics dictionary
        device_info: CUDA device information dictionary
    """

    def __init__(
        self,
        preset: str | None = None,
        config: EngineConfig | None = None,
        pipeline: Pipeline | None = None,
        builder: Callable[[Any], Any] | None = None,
        mode: str | ExecutionMode | None = None,
        **overrides: Any
    ) -> None:
        """Initialize the engine.

        Args:
            preset: Preset name ('default', 'iono', 'ionox')
            config: Custom EngineConfig object
            pipeline: Pre-built Pipeline from PipelineBuilder
            builder: Builder function for custom pipeline (advanced)
            mode: Execution mode override ('batch', 'streaming')
            **overrides: Quick parameter overrides (nfft, channels, overlap, etc.)

        Raises:
            ValueError: If configuration is invalid
            ConfigError: If parameters are incompatible
            DeviceNotFoundError: If no CUDA devices available
            DllLoadError: If C++ extension cannot be loaded

        Examples:
            >>> engine = Engine()  # Uses 'default' preset
            >>> engine = Engine(preset='iono')
            >>> engine = Engine(preset='iono', mode='streaming')
            >>> engine = Engine(config=my_config)
            >>> engine = Engine(pipeline=my_pipeline)
            >>> engine = Engine(preset='iono', nfft=8192, overlap=0.9)
        """
        # Import C++ module
        self._cpp_module = _import_cpp_engine()

        # Resolve configuration (priority: pipeline > config > preset > default)
        self._config = self._resolve_config(preset, config, pipeline, builder)

        # Apply mode override
        if mode is not None:
            self._apply_mode(mode)

        # Apply parameter overrides
        if overrides:
            for key, value in overrides.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)
                else:
                    raise ValueError(f"Unknown parameter: {key}")

        # Validate final configuration
        self._config.model_validate(self._config)

        # Store pipeline if provided
        self._pipeline = pipeline
        self._expected_samples = self._config.nfft * self._config.channels

        # Initialize state
        self._cpp_engine: Any = None
        self._initialized = False
        self._closed = False
        self._in_context = False

        # Statistics tracking
        self._total_frames = 0
        self._total_latency_us = 0.0

        # Validate device and initialize
        self._validate_device_requirements()
        self._initialize()

    def _resolve_config(
        self,
        preset: str | None,
        config: EngineConfig | None,
        pipeline: Pipeline | None,
        builder: Callable[[Any], Any] | None
    ) -> EngineConfig:
        """Resolve configuration from various input sources.

        Priority: pipeline > builder > config > preset > default
        """
        if pipeline is not None:
            return pipeline.config

        if builder is not None:
            from sigtekx.core.builder import PipelineBuilder
            b = PipelineBuilder()
            builder(b)
            self._pipeline = b.build()
            return self._pipeline.config

        if config is not None:
            return config.model_copy(deep=True)

        # Use preset (default to 'default')
        preset_name = preset or 'default'
        return EngineConfig.from_preset(preset_name)

    def _apply_mode(self, mode: str | ExecutionMode) -> None:
        """Apply execution mode overrides to configuration."""
        if isinstance(mode, str):
            mode = ExecutionMode(mode)

        # Import here to avoid circular dependency
        from sigtekx.config.schemas import _apply_mode_overrides
        self._config = _apply_mode_overrides(self._config, mode)

    def _validate_device_requirements(self) -> None:
        """Validate CUDA device availability and compatibility."""
        try:
            from sigtekx.utils.device import device_info
        except Exception as exc:
            raise DeviceNotFoundError(
                "Unable to import CUDA device utilities"
            ) from exc

        try:
            info = device_info()
        except DeviceNotFoundError:
            raise
        except Exception as exc:
            raise DeviceNotFoundError(
                "Unable to query CUDA device information"
            ) from exc

        total_mb = int(info.get("memory_total_mb", 0) or 0)
        compute_capability = info.get("compute_capability", (0, 0))

        if not isinstance(compute_capability, tuple) or len(compute_capability) != 2:
            raise DeviceNotFoundError("Invalid CUDA compute capability")

        major, minor = compute_capability
        if total_mb <= 0:
            raise DeviceNotFoundError("CUDA device reports zero memory")

        validate_config_device_compatibility(
            self._config,
            total_mb,
            (int(major), int(minor)),
        )

    def _initialize(self) -> None:
        """Initialize GPU resources and C++ executor."""
        if self._initialized:
            return

        if self._closed:
            raise EngineStateError(
                "Cannot initialize closed engine",
                current_state="closed"
            )

        try:
            # Create appropriate executor based on execution mode
            if self._config.mode == ExecutionMode.BATCH:
                self._cpp_engine = self._cpp_module.BatchExecutor()
            elif self._config.mode == ExecutionMode.STREAMING:
                self._cpp_engine = self._cpp_module.StreamingExecutor()
            else:
                raise ValueError(f"Unknown execution mode: {self._config.mode}")

            # Convert Python config to C++ ExecutorConfig
            cpp_config = self._cpp_module.ExecutorConfig()

            # Map Python config to C++ config
            # Copy all fields that exist in C++ ExecutorConfig (extends EngineConfig)
            cpp_fields = {
                'nfft', 'channels', 'overlap', 'sample_rate_hz',
                'stream_count', 'pinned_buffer_count', 'warmup_iters',
                'device_id'
            }

            for key in cpp_fields:
                if hasattr(self._config, key):
                    value = getattr(self._config, key)
                    setattr(cpp_config, key, value)

            # Map enum fields (convert Python enum to C++ enum objects)
            # WindowType: RECTANGULAR, HANN, BLACKMAN
            if hasattr(self._config, 'window'):
                window_map = {
                    WindowType.RECTANGULAR: self._cpp_module.WindowType.RECTANGULAR,
                    WindowType.HANN: self._cpp_module.WindowType.HANN,
                    WindowType.BLACKMAN: self._cpp_module.WindowType.BLACKMAN,
                }
                cpp_config.window_type = window_map.get(self._config.window, self._cpp_module.WindowType.HANN)

            # WindowSymmetry: PERIODIC, SYMMETRIC
            if hasattr(self._config, 'window_symmetry'):
                symmetry_map = {
                    WindowSymmetry.PERIODIC: self._cpp_module.WindowSymmetry.PERIODIC,
                    WindowSymmetry.SYMMETRIC: self._cpp_module.WindowSymmetry.SYMMETRIC,
                }
                cpp_config.window_symmetry = symmetry_map.get(self._config.window_symmetry, self._cpp_module.WindowSymmetry.PERIODIC)

            # WindowNorm: UNITY, SQRT
            if hasattr(self._config, 'window_norm'):
                norm_map = {
                    WindowNorm.UNITY: self._cpp_module.WindowNorm.UNITY,
                    WindowNorm.SQRT: self._cpp_module.WindowNorm.SQRT,
                }
                cpp_config.window_norm = norm_map.get(self._config.window_norm, self._cpp_module.WindowNorm.UNITY)

            # ScalePolicy: NONE, ONE_OVER_N, ONE_OVER_SQRT_N
            if hasattr(self._config, 'scale'):
                scale_map = {
                    ScalePolicy.NONE: self._cpp_module.ScalePolicy.NONE,
                    ScalePolicy.ONE_OVER_N: self._cpp_module.ScalePolicy.ONE_OVER_N,
                    ScalePolicy.ONE_OVER_SQRT_N: self._cpp_module.ScalePolicy.ONE_OVER_SQRT_N,
                }
                cpp_config.scale_policy = scale_map.get(self._config.scale, self._cpp_module.ScalePolicy.ONE_OVER_N)

            # OutputMode: MAGNITUDE, COMPLEX (Python) -> COMPLEX_PASSTHROUGH (C++)
            if hasattr(self._config, 'output'):
                output_map = {
                    OutputMode.MAGNITUDE: self._cpp_module.OutputMode.MAGNITUDE,
                    OutputMode.COMPLEX: self._cpp_module.OutputMode.COMPLEX_PASSTHROUGH,
                }
                cpp_config.output_mode = output_map.get(self._config.output, self._cpp_module.OutputMode.MAGNITUDE)

            # ExecutionMode: BATCH, STREAMING
            if hasattr(self._config, 'mode'):
                mode_map = {
                    ExecutionMode.BATCH: self._cpp_module.ExecutionMode.BATCH,
                    ExecutionMode.STREAMING: self._cpp_module.ExecutionMode.STREAMING,
                }
                cpp_config.mode = mode_map.get(self._config.mode, self._cpp_module.ExecutionMode.BATCH)

            # Initialize C++ executor
            self._cpp_engine.initialize(cpp_config)
            self._initialized = True

        except RuntimeError as e:
            error_msg = str(e)
            if "No CUDA-capable devices" in error_msg:
                raise DeviceNotFoundError() from e
            raise EngineRuntimeError(f"Initialization failed: {e}") from e

    def process(self, data: ArrayLike) -> FloatArray:
        """Process input data through the signal processing pipeline.

        Args:
            data: Input signal data (array-like, shape: nfft * channels)

        Returns:
            Magnitude spectrum array (shape: channels × num_output_bins)

        Raises:
            EngineStateError: If engine is closed or not initialized
            ValidationError: If input is invalid
            EngineRuntimeError: If processing fails

        Examples:
            >>> engine = Engine(preset='iono')
            >>> signal = np.random.randn(32768).astype(np.float32)  # 4096 × 8
            >>> spectrum = engine.process(signal)
            >>> spectrum.shape
            (8, 2049)  # channels × (nfft//2 + 1)
        """
        if self._closed:
            raise EngineStateError(
                "Cannot process with closed engine",
                current_state="closed"
            )

        if not self._initialized:
            raise EngineStateError(
                "Engine not initialized",
                current_state="created"
            )

        # Convert to numpy array
        raw_array = np.asarray(data)

        if np.iscomplexobj(raw_array):
            raise ValidationError(
                "Complex input not supported",
                expected="float32",
                got=str(raw_array.dtype)
            )

        # Ensure float32
        input_array = raw_array.astype(np.float32, copy=False)

        # Validate and prepare input
        input_array = self._prepare_input(input_array)

        try:
            # Process through native executor
            output = self._cpp_engine.process(input_array)

            # Update statistics
            if self._config.enable_profiling:
                stats = self._cpp_engine.get_stats()
                self._total_frames += 1
                self._total_latency_us += stats.latency_us

            return cast(FloatArray, output)

        except RuntimeError as e:
            error_str = str(e)
            if "size mismatch" in error_str.lower():
                raise ValidationError(
                    "Input size mismatch",
                    expected=f"{self._expected_samples} samples",
                    got=f"{input_array.size} samples"
                ) from e
            raise EngineRuntimeError(f"Processing failed: {e}") from e

    def _prepare_input(self, data: NDArray[Any]) -> FloatArray:
        """Validate and prepare input array for processing."""
        from sigtekx.config.schemas import ValidationMode

        # Fast path: disabled validation (C++ still validates)
        if self._config.validation_mode == ValidationMode.DISABLED:
            # Minimal conversion only
            if not isinstance(data, np.ndarray):
                data = np.asarray(data, dtype=np.float32)
            elif data.dtype != np.float32:
                data = data.astype(np.float32, copy=False)
            return cast(FloatArray, data)

        # Basic validation: type/shape/contiguity only (skip NaN check)
        skip_nan = self._config.validation_mode == ValidationMode.BASIC

        # Validate using utility function
        validated = validate_input_array(
            data,
            expected_dtype=np.dtype(np.float32),
            name="input",
            skip_nan_check=skip_nan,
        )

        # Ensure 1D
        if validated.ndim != 1:
            raise ValidationError(
                "Input must be 1D",
                expected=f"({self._expected_samples},)",
                got=str(validated.shape)
            )

        # Validate input size
        validate_input_size(validated, self._config)

        return cast(FloatArray, validated)

    def reset(self) -> None:
        """Reset engine to initial state.

        Deallocates GPU resources and resets statistics while keeping configuration.
        The engine will re-initialize on the next process() call.

        Examples:
            >>> engine.reset()
        """
        if self._closed:
            raise EngineStateError(
                "Cannot reset closed engine",
                current_state="closed"
            )

        if self._cpp_engine is not None:
            try:
                self._cpp_engine.reset()
            except RuntimeError as e:
                warnings.warn(f"Reset warning: {e}", stacklevel=2)

        self._initialized = False
        self._total_frames = 0
        self._total_latency_us = 0.0

        # Re-initialize
        self._initialize()

    def _should_track_cleanup_memory(self) -> bool:
        """Determine if GPU memory tracking should be enabled during cleanup.

        Controlled by SIGX_TRACK_CLEANUP_MEMORY environment variable.
        Defaults to True in debug builds (__debug__==True), False in release.

        Returns:
            bool: True if memory tracking should be enabled
        """
        import os
        env_val = os.environ.get('SIGX_TRACK_CLEANUP_MEMORY', '').strip().lower()

        if env_val in {'1', 'true', 'yes', 'on'}:
            return True
        elif env_val in {'0', 'false', 'no', 'off'}:
            return False
        else:
            # Default: enabled in debug builds, disabled in release
            return __debug__

    def close(self) -> None:
        """Close engine and release all resources.

        Performs comprehensive cleanup with optional GPU memory leak detection.

        Build Mode Behavior:
            Debug builds: Verbose logging, raises EngineCleanupError on serious errors
            Release builds: Minimal logging, logs but doesn't raise

        Raises:
            EngineCleanupError: In debug builds only, on serious errors (GPU memory
                leaks, unknown C++ errors)

        Examples:
            >>> engine.close()
        """
        # Step 0: Early return if already closed (idempotent)
        if self._closed:
            return

        # Step 1: Determine logging verbosity and memory tracking
        from sigtekx.utils.logging import _is_running_under_profiler, logger

        verbose = __debug__ and not _is_running_under_profiler()
        track_memory = self._should_track_cleanup_memory()

        if verbose:
            logger.debug("Engine cleanup started (device_id=%s)",
                         self._config.device_id if hasattr(self._config, 'device_id') else 0)

        # Step 2: GPU memory snapshot (before cleanup)
        memory_before = None
        device_id = self._config.device_id if hasattr(self._config, 'device_id') else 0

        if track_memory:
            try:
                from sigtekx.utils.device import get_gpu_memory_snapshot
                memory_before = get_gpu_memory_snapshot(device_id)
                if verbose:
                    logger.debug("GPU memory before cleanup: used=%d MB",
                               memory_before['used_mb'])
            except Exception as e:
                logger.debug("Failed to capture memory snapshot (before): %s", e)
                memory_before = None

        # Step 3: Cleanup operations with error classification
        cleanup_errors = []

        if self._cpp_engine is not None:
            # Step 3a: Synchronize pending operations
            if verbose:
                logger.debug("Cleanup step: synchronize pending operations")

            try:
                self._cpp_engine.synchronize()
            except RuntimeError as e:
                error_str = str(e).lower()

                if "cuda" in error_str and ("device" in error_str or "context" in error_str):
                    logger.info("CUDA device error during synchronize (expected): %s", e)
                else:
                    logger.warning("Synchronization failed during cleanup: %s", e)
                    cleanup_errors.append(('synchronize', e))
            except Exception as e:
                logger.warning("Unexpected error during synchronize: %s", e)
                cleanup_errors.append(('synchronize', e))

            # Step 3b: Reset C++ engine
            if verbose:
                logger.debug("Cleanup step: reset C++ engine")

            try:
                self._cpp_engine.reset()
            except RuntimeError as e:
                error_str = str(e).lower()

                if "cuda" in error_str and ("device" in error_str or "context" in error_str):
                    logger.info("CUDA device error during reset (expected): %s", e)
                elif "memory" in error_str or "allocation" in error_str:
                    logger.error("Memory error during reset: %s", e)
                    cleanup_errors.append(('reset_memory', e))
                else:
                    logger.warning("C++ reset failed: %s", e)
                    cleanup_errors.append(('reset', e))
            except Exception as e:
                logger.error("Unexpected C++ error during reset: %s", e)
                cleanup_errors.append(('reset_unknown', e))

        # Step 4: Clear Python state
        if verbose:
            logger.debug("Cleanup step: clear Python state")

        self._cpp_engine = None
        self._initialized = False

        # Step 5: GPU memory validation (after cleanup)
        memory_leaked_mb = 0

        if track_memory and memory_before is not None:
            if verbose:
                logger.debug("Cleanup step: validate GPU memory released")

            try:
                from sigtekx.utils.device import get_gpu_memory_snapshot
                memory_after = get_gpu_memory_snapshot(device_id)

                memory_leaked_mb = memory_after['used_mb'] - memory_before['used_mb']

                if verbose:
                    logger.debug("GPU memory after cleanup: used=%d MB (delta=%+d MB)",
                               memory_after['used_mb'], memory_leaked_mb)

                # 10 MB threshold for reporting
                LEAK_THRESHOLD_MB = 10

                if memory_leaked_mb > LEAK_THRESHOLD_MB:
                    logger.error("Potential GPU memory leak detected: %d MB not released",
                               memory_leaked_mb)
                    cleanup_errors.append((
                        'memory_leak',
                        RuntimeError(f"GPU memory increased by {memory_leaked_mb} MB during cleanup")
                    ))
                elif memory_leaked_mb > 0:
                    logger.debug("Minor GPU memory delta: %d MB (within normal variance)",
                               memory_leaked_mb)
            except Exception as e:
                logger.debug("Failed to validate memory release: %s", e)

        # Step 6: Mark as closed
        self._closed = True

        if verbose:
            logger.debug("Engine cleanup completed (errors=%d)", len(cleanup_errors))

        # Step 7: Report accumulated errors
        if cleanup_errors:
            error_messages = []
            serious_errors = []

            for step, error in cleanup_errors:
                error_messages.append(f"{step}: {error}")

                # Serious errors: memory leaks, unknown errors
                if step in ('reset_memory', 'reset_unknown', 'memory_leak'):
                    serious_errors.append((step, error))

            # Raise in debug builds only
            should_raise = __debug__ and len(serious_errors) > 0

            if should_raise:
                from sigtekx.exceptions import EngineCleanupError

                primary_step, primary_error = serious_errors[0]
                raise EngineCleanupError(
                    f"Engine cleanup failed at step '{primary_step}' (with {len(cleanup_errors)} total errors)",
                    cleanup_step=primary_step,
                    gpu_memory_leaked_mb=memory_leaked_mb if memory_leaked_mb > 0 else None,
                    original_error=primary_error,
                    all_errors=error_messages,
                    gpu_memory_before=memory_before,
                    device_id=device_id
                )
            else:
                logger.error("Engine cleanup completed with %d errors (not raising in release build)",
                            len(cleanup_errors))
                for msg in error_messages:
                    logger.error("  - %s", msg)

    def synchronize(self) -> None:
        """Synchronize all GPU operations.

        Blocks until all pending operations complete.
        """
        if not self._initialized or self._cpp_engine is None:
            return
        try:
            self._cpp_engine.synchronize()
        except RuntimeError as exc:
            raise EngineRuntimeError(f"Synchronization failed: {exc}") from exc

    # -------------------------------------------------------------------------
    # Properties (Read-only interface)
    # -------------------------------------------------------------------------

    @property
    def config(self) -> EngineConfig:
        """Get engine configuration (read-only)."""
        return self._config

    @property
    def is_initialized(self) -> bool:
        """Check if engine is initialized with GPU resources."""
        return self._initialized and not self._closed

    @property
    def stats(self) -> dict[str, Any]:
        """Get performance statistics.

        Returns:
            Dictionary with:
                - latency_us: Last frame latency
                - throughput_gbps: Memory throughput
                - frames_processed: Total frames
                - avg_latency_us: Average latency (if profiling enabled)
        """
        if not self._initialized or self._cpp_engine is None:
            return {
                "latency_us": 0.0,
                "throughput_gbps": 0.0,
                "frames_processed": 0,
            }

        stats = self._cpp_engine.get_stats()
        result = {
            "latency_us": float(stats.latency_us),
            "throughput_gbps": float(stats.throughput_gbps),
            "frames_processed": int(stats.frames_processed),
        }

        if self._config.enable_profiling and self._total_frames > 0:
            result["avg_latency_us"] = self._total_latency_us / self._total_frames
            result["total_frames"] = self._total_frames

        return result

    @property
    def device_info(self) -> dict[str, Any]:
        """Get CUDA device information.

        Returns device information using a three-tier fallback strategy:
        1. Native RuntimeInfo (fast, minimal dependencies)
        2. NVML device query (comprehensive, optional dependency)
        3. Error state with diagnostic message

        Returns:
            Dictionary with device information. If all queries fail,
            returns partial info with 'error' field explaining the failure.

        Example:
            >>> engine = Engine(preset='default')
            >>> info = engine.device_info
            >>> print(info['device_name'])
            'NVIDIA GeForce RTX 3090'
            >>> print(info['cuda_version'])
            '12.3'
        """
        # Import here to avoid circular dependencies (matches existing pattern)
        from sigtekx.utils.logging import _is_running_under_profiler, logger

        # Case 1: Uninitialized engine
        if not self._initialized or self._cpp_engine is None:
            return {
                "device_name": "Not initialized",
                "cuda_version": "Unknown",
                "device_memory_mb": 0,
                "device_memory_free_mb": 0,
            }

        # Case 2: Try RuntimeInfo (primary source - fast and accurate)
        try:
            from sigtekx.core import _native
            runtime_info = _native.get_runtime_info(0)  # Query device 0

            # Success - return RuntimeInfo as primary source
            result = {
                "device_name": str(runtime_info.device_name),
                "cuda_version": str(runtime_info.cuda_version),
                "device_memory_mb": 0,  # RuntimeInfo doesn't have memory info
                "device_memory_free_mb": 0,
            }

            # Try to augment with NVML memory info (best-effort, no error if fails)
            try:
                from sigtekx.utils.device import device_info as get_device_info
                nvml_info = get_device_info()
                result["device_memory_mb"] = int(nvml_info.get("memory_total_mb", 0))
                result["device_memory_free_mb"] = int(nvml_info.get("memory_free_mb", 0))
            except Exception:
                pass  # Ignore NVML errors when augmenting RuntimeInfo

            return result

        except Exception as e:
            # RuntimeInfo failed - log at DEBUG (expected in some environments)
            logger.debug(
                "RuntimeInfo query failed (falling back to NVML): %s", e
            )

        # Case 3: Fall back to NVML (secondary source)
        try:
            from sigtekx.utils.device import device_info as get_device_info
            info = get_device_info()
            return {
                "device_name": str(info.get("name", "Unknown")),
                "cuda_version": str(info.get("cuda_version", "Unknown")),
                "device_memory_mb": int(info.get("memory_total_mb", 0)),
                "device_memory_free_mb": int(info.get("memory_free_mb", 0)),
            }

        except ImportError as e:
            # NVML not available
            if not _is_running_under_profiler():
                logger.warning(
                    "Device info unavailable: RuntimeInfo and NVML both failed (%s)", e
                )
            return {
                "device_name": "Unknown",
                "cuda_version": "Unknown",
                "device_memory_mb": 0,
                "device_memory_free_mb": 0,
                "error": "Device utilities not available"
            }

        except RuntimeError as e:
            # CUDA/NVML runtime error
            if not _is_running_under_profiler():
                logger.warning(
                    "Unable to query device info: %s", e
                )
            return {
                "device_name": "Unknown",
                "cuda_version": "Unknown",
                "device_memory_mb": 0,
                "device_memory_free_mb": 0,
                "error": f"Device query failed: {e}"
            }

        except Exception as e:
            # Unexpected error
            logger.debug(
                "Unexpected error querying device info: %s: %s",
                type(e).__name__, e
            )
            return {
                "device_name": "Unknown",
                "cuda_version": "Unknown",
                "device_memory_mb": 0,
                "device_memory_free_mb": 0,
                "error": f"Device info unavailable: {type(e).__name__}"
            }

    # -------------------------------------------------------------------------
    # Context Manager Protocol
    # -------------------------------------------------------------------------

    def __enter__(self) -> Engine:
        """Enter context manager."""
        if self._closed:
            raise EngineStateError("Cannot enter context with closed engine")
        self._in_context = True
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager and ensure cleanup."""
        self._in_context = False

        # Synchronize pending operations
        if self._initialized and self._cpp_engine is not None:
            try:
                self._cpp_engine.synchronize()
            except Exception as e:
                from sigtekx.utils.logging import logger
                logger.warning("Synchronization failed during context exit: %s", e)

        # Log user exception if present
        if exc_type is not None:
            from sigtekx.utils.logging import logger
            logger.warning("Engine context exited due to exception: %s", exc_val)

        # Close engine (may raise EngineCleanupError in debug builds)
        self.close()

        # Return None to propagate user exceptions
        return None

    # -------------------------------------------------------------------------
    # Class Methods
    # -------------------------------------------------------------------------

    @classmethod
    def get_available_devices(cls) -> list[str]:
        """Get list of available CUDA devices."""
        try:
            cpp_module = _import_cpp_engine()
            return list(cpp_module.get_available_devices())
        except Exception as e:
            warnings.warn(f"Failed to query devices: {e}", stacklevel=2)
            return []

    @classmethod
    def select_best_device(cls) -> int:
        """Select the best available CUDA device."""
        try:
            cpp_module = _import_cpp_engine()
            return int(cpp_module.select_best_device())
        except Exception:
            return 0

    # -------------------------------------------------------------------------
    # String Representation
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        """Get string representation for debugging."""
        state = "closed" if self._closed else ("initialized" if self._initialized else "created")
        return f"<Engine state={state} config={self._config}>"

    def __del__(self) -> None:
        """Ensure cleanup on deletion.

        Note: GPU memory tracking is disabled in __del__ to avoid NVML/CUDA
        issues during interpreter shutdown.
        """
        if not self._closed and self._initialized:
            warnings.warn(
                "Engine not properly closed. Use context manager or call close()",
                ResourceWarning,
                stacklevel=2
            )

            # Temporarily disable memory tracking for this cleanup
            try:
                import os
                original_env = os.environ.get('SIGX_TRACK_CLEANUP_MEMORY')
                os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = '0'

                try:
                    self.close()
                finally:
                    if original_env is None:
                        os.environ.pop('SIGX_TRACK_CLEANUP_MEMORY', None)
                    else:
                        os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = original_env
            except Exception:
                # Finalizers must not raise
                pass


# -----------------------------------------------------------------------------
# Convenience Functions
# -----------------------------------------------------------------------------

def process_signal(
    data: ArrayLike,
    preset: str = 'default',
    **kwargs: Any
) -> FloatArray:
    """One-shot signal processing without engine management.

    Convenience function for simple cases.

    Args:
        data: Input signal data
        preset: Preset name ('default', 'iono', 'ionox')
        **kwargs: Additional configuration overrides

    Returns:
        Magnitude spectrum array

    Examples:
        >>> spectrum = process_signal(signal, preset='iono')
        >>> spectrum = process_signal(signal, preset='iono', nfft=8192)
    """
    with Engine(preset=preset, **kwargs) as engine:
        return engine.process(data)


def benchmark_latency(
    preset: str = 'default',
    iterations: int = 100,
    **kwargs: Any
) -> dict[str, float]:
    """Benchmark processing latency.

    Args:
        preset: Preset name
        iterations: Number of iterations
        **kwargs: Configuration overrides

    Returns:
        Dictionary with latency statistics

    Examples:
        >>> stats = benchmark_latency(preset='iono', iterations=1000)
        >>> print(f"Mean: {stats['mean']:.2f} µs")
    """
    engine = Engine(preset=preset, **kwargs)

    # Prepare test data
    data_size = engine.config.nfft * engine.config.channels
    test_data = np.random.randn(data_size).astype(np.float32)

    # Warmup
    for _ in range(10):
        engine.process(test_data)

    # Benchmark
    latencies = []
    for _ in range(iterations):
        engine.process(test_data)
        stats = engine.stats
        latencies.append(stats["latency_us"])

    engine.close()

    # Compute statistics
    latencies_array = np.array(latencies)
    return {
        "mean": float(np.mean(latencies_array)),
        "std": float(np.std(latencies_array)),
        "min": float(np.min(latencies_array)),
        "max": float(np.max(latencies_array)),
        "p50": float(np.percentile(latencies_array, 50)),
        "p95": float(np.percentile(latencies_array, 95)),
        "p99": float(np.percentile(latencies_array, 99)),
    }
