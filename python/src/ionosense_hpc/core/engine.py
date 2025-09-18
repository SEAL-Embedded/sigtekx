"""Unified CUDA FFT Signal Processing Engine.

A single, obvious API for high-performance signal processing that follows
Research Software Engineering (RSE) and Reproducible Engineering (RE) standards.

Design Philosophy:
    - Make simple things simple, complex things possible
    - Explicit is better than implicit
    - Boring method names are better than clever ones
    - One way to do things
    - Fail fast and loud

This module provides the Engine class, which directly wraps the C++ ResearchEngine
with minimal overhead while providing a Pythonic, NumPy-compatible interface.
"""

from __future__ import annotations

import contextlib
import warnings
from typing import TYPE_CHECKING, Any, Literal, cast, overload

import numpy as np
from numpy.typing import ArrayLike, NDArray

from ionosense_hpc.config import (
    EngineConfig,
    Presets,
    validate_batch_size,
    validate_config_device_compatibility,
    validate_input_array,
)
from ionosense_hpc.exceptions import (
    DeviceNotFoundError,
    DllLoadError,
    EngineRuntimeError,
    EngineStateError,
    ValidationError,
)

if TYPE_CHECKING:
    from typing import TypeAlias

    FloatArray: TypeAlias = NDArray[np.float32]
    ComplexArray: TypeAlias = NDArray[np.complex64]
else:
    FloatArray = NDArray[np.float32]
    ComplexArray = NDArray[np.complex64]


# Constants
_DEFAULT_PRESET = "realtime"
_SUPPORTED_DTYPES = (np.float32,)  # Extensible for future types


def _import_cpp_engine() -> Any:
    """Import the C++ extension with proper error handling.

    Returns:
        The loaded _engine module

    Raises:
        DllLoadError: If the extension cannot be loaded
    """
    try:
        from . import _engine  # type: ignore[attr-defined]
        return _engine
    except ImportError as e:
        error_str = str(e)
        if "DLL load failed" in error_str or "cannot open shared object" in error_str:
            raise DllLoadError("_engine", e) from e
        elif "No module named" in error_str:
            raise DllLoadError(
                "_engine",
                RuntimeError("Extension not found. Build with: ./scripts/cli.sh build")
            ) from e
        raise


class Engine:
    """Unified CUDA FFT signal processing engine.

    A high-performance signal processing engine that manages GPU resources,
    performs FFT operations, and provides both simple and advanced interfaces
    for research workflows.

    The engine follows an explicit lifecycle model:
        Created -> Initialized -> Closed

    Basic Usage:
        >>> engine = Engine("realtime")
        >>> output = engine.process(input_data)
        >>> engine.close()

    Context Manager (Recommended):
        >>> with Engine("realtime") as engine:
        ...     output = engine.process(input_data)

    Advanced Research Usage:
        >>> engine = Engine(
        ...     config=custom_config,
        ...     validate_inputs=False,  # Skip validation for speed
        ...     profile_mode=True,      # Enable profiling
        ...     cuda_graphs=True        # Use CUDA graphs (future)
        ... )

    Attributes:
        config: Read-only engine configuration
        is_initialized: Whether GPU resources are allocated
        stats: Performance statistics
        device_info: CUDA device information

    Note:
        This class is NOT thread-safe. Each thread should use its own instance.
    """

    def __init__(
        self,
        config: EngineConfig | str | None = None,
        *,
        # Advanced options for research workflows
        validate_inputs: bool = True,
        profile_mode: bool = False,
        cuda_graphs: bool = False,
        stream_count: int | None = None,
        deterministic: bool = False,
        debug_mode: bool = False,
    ) -> None:
        """Initialize the engine.

        Args:
            config: Engine configuration - can be:
                - EngineConfig object for full control
                - String preset name ("realtime", "throughput", "validation", "profiling")
                - None to use default "realtime" preset
            validate_inputs: Whether to validate input arrays (disable for max speed)
            profile_mode: Enable internal profiling and detailed metrics
            cuda_graphs: Use CUDA graphs for reduced launch overhead (future feature)
            stream_count: Override number of CUDA streams (None uses config default)
            deterministic: Enable deterministic algorithms for reproducibility
            debug_mode: Enable debug checks and verbose logging

        Raises:
            ValueError: If preset name is invalid
            ConfigError: If configuration is invalid
            DeviceNotFoundError: If no CUDA devices are available
            DllLoadError: If C++ extension cannot be loaded
        """
        # Import C++ module
        self._cpp_module = _import_cpp_engine()

        # Process configuration
        self._config = self._process_config(config)

        # Apply advanced options
        if stream_count is not None:
            self._config.stream_count = stream_count
        if profile_mode:
            self._config.enable_profiling = True
        if cuda_graphs:
            self._config.use_cuda_graphs = True
        self._expected_samples = self._config.nfft * self._config.batch

        # Store settings
        self._validate_inputs = validate_inputs
        self._deterministic = deterministic
        self._debug_mode = debug_mode

        # Initialize state
        self._cpp_engine: Any = None
        self._initialized = False
        self._closed = False
        self._in_context = False

        # Statistics tracking
        self._total_frames = 0
        self._total_latency_us = 0.0

        # Best-effort device validation before allocation
        self._validate_device_requirements()
        # Auto-initialize (lazy init removed for explicitness)
        self._initialize()

    def _process_config(self, config: EngineConfig | str | None) -> EngineConfig:
        """Process and validate configuration input.

        Args:
            config: Configuration input

        Returns:
            Validated EngineConfig object

        Raises:
            ValueError: If preset name is invalid
        """
        if config is None:
            return Presets.realtime()

        if isinstance(config, str):
            preset_map = {
                "realtime": Presets.realtime,
                "throughput": Presets.throughput,
                "validation": Presets.validation,
                "profiling": Presets.profiling,
            }
            preset_name = config.lower()
            if preset_name not in preset_map:
                raise ValueError(
                    f"Unknown preset '{config}'. "
                    f"Available: {', '.join(preset_map.keys())}"
                )
            return preset_map[preset_name]()

        if not isinstance(config, EngineConfig):
            raise TypeError(
                f"config must be EngineConfig, str, or None, got {type(config).__name__}"
            )

        return cast(EngineConfig, config.model_copy(deep=True))

    def _validate_device_requirements(self) -> None:
        try:
            from ionosense_hpc.utils.device import device_info
        except Exception:
            return

        info = device_info()
        total_mb = int(info.get("memory_total_mb", 0) or 0)
        compute_capability = info.get("compute_capability", (0, 0))
        if not isinstance(compute_capability, tuple) or len(compute_capability) != 2:
            compute_capability = (0, 0)

        if total_mb <= 0 and compute_capability == (0, 0):
            return

        major, minor = compute_capability
        validate_config_device_compatibility(
            self._config,
            total_mb,
            (int(major), int(minor)),
        )

    def _initialize(self) -> None:
        """Initialize GPU resources and C++ engine.

        Raises:
            EngineRuntimeError: If initialization fails
            DeviceNotFoundError: If no CUDA devices available
        """
        if self._initialized:
            return

        if self._closed:
            raise EngineStateError(
                "Cannot initialize closed engine",
                current_state="closed"
            )

        self._validate_device_requirements()
        try:
            # Create C++ engine
            self._cpp_engine = self._cpp_module.ResearchEngine()

            # Convert config to C++ format
            cpp_config = self._cpp_module.EngineConfig()
            for key, value in self._config.model_dump().items():
                if hasattr(cpp_config, key):
                    setattr(cpp_config, key, value)

            # Initialize C++ engine
            self._cpp_engine.initialize(cpp_config)
            self._initialized = True

            # Log if debug mode
            if self._debug_mode:
                info = self.device_info
                print(f"[DEBUG] Engine initialized on {info['device_name']}")
                print(f"[DEBUG] Memory: {info['device_memory_free_mb']}/{info['device_memory_mb']} MB free")

        except RuntimeError as e:
            error_msg = str(e)
            if "No CUDA-capable devices" in error_msg:
                raise DeviceNotFoundError() from e
            raise EngineRuntimeError(f"Initialization failed: {e}") from e

    def process(self, data: ArrayLike) -> FloatArray:
        """Process input data through the FFT pipeline.

        This is the primary method for signal processing. It accepts array-like
        input, processes it through the GPU pipeline (windowing -> FFT -> magnitude),
        and returns the magnitude spectrum.

        Args:
            data: Input signal data. Can be:
                - NumPy array (preferred)
                - Python list
                - Any array-like object
                Shape should be (nfft * batch,) for batched processing

        Returns:
            2D array of magnitude spectra with shape (batch, num_output_bins)
            where num_output_bins = nfft // 2 + 1

        Raises:
            EngineStateError: If engine is closed
            ValidationError: If input validation fails (when enabled)
            EngineRuntimeError: If processing fails

        Example:
            >>> engine = Engine("realtime")
            >>> signal = np.random.randn(2048).astype(np.float32)  # 1024 * 2 batch
            >>> spectrum = engine.process(signal)  # Returns (2, 513) array
        """
        if self._closed:
            raise EngineStateError("Cannot process with closed engine", current_state="closed")

        if not self._initialized:
            raise EngineStateError(
                "Engine not initialized",
                current_state="created"
            )

        raw_array = np.asarray(data)
        if np.iscomplexobj(raw_array):
            raise ValidationError(
                "Unsupported data type",
                expected="float32 or convertible",
                got=str(raw_array.dtype)
            )

        input_array = raw_array.astype(np.float32, copy=False)

        if self._validate_inputs:
            input_array = self._validate_input(input_array)
        else:
            if input_array.ndim != 1:
                input_array = np.reshape(input_array, -1)
            if not input_array.flags["C_CONTIGUOUS"]:
                input_array = np.ascontiguousarray(input_array)
        input_array = cast(FloatArray, input_array)
        try:
            output = self._cpp_engine.process(input_array)

            if self._config.enable_profiling:
                stats = self._cpp_engine.get_stats()
                self._total_frames += 1
                self._total_latency_us += stats.latency_us

            return cast(FloatArray, output)

        except RuntimeError as e:
            error_str = str(e)
            if "size mismatch" in error_str.lower():
                if self._validate_inputs:
                    raise ValidationError(
                        "Input size mismatch",
                        expected=f"{self._expected_samples} samples",
                        got=f"{input_array.size} samples"
                    ) from e
                raise
            raise EngineRuntimeError(f"Processing failed: {e}") from e

    def _validate_input(self, data: NDArray[Any]) -> FloatArray:
        """Validate and prepare input data."""
        validated = validate_input_array(
            data,
            expected_dtype=np.dtype(np.float32),
            name="input",
        )

        if validated.ndim != 1:
            raise ValidationError(
                "Input shape mismatch",
                expected=f"({self._expected_samples},)",
                got=str(validated.shape)
            )

        validate_batch_size(validated, self._config)

        if self._debug_mode and np.issubdtype(validated.dtype, np.floating):
            finite_mask = np.isfinite(validated)
            if not bool(finite_mask.all()):
                n_nan = int(np.isnan(validated).sum())
                n_inf = int(np.isinf(validated).sum())
                print(f"[DEBUG] Input contains {n_nan} NaN and {n_inf} Inf values")

        return cast(FloatArray, validated)

    def reset(self) -> None:
        """Reset the engine to initial state.

        This deallocates GPU resources and resets statistics, but keeps
        the configuration. The engine will auto-initialize on next process().

        Note:
            This is primarily useful for benchmarking or recovering from errors.
            For normal usage, use close() instead.
        """
        if self._closed:
            raise EngineStateError("Cannot reset closed engine", current_state="closed")

        if self._cpp_engine is not None:
            try:
                self._cpp_engine.reset()
            except RuntimeError as e:
                warnings.warn(f"Reset warning: {e}", stacklevel=2)

        self._initialized = False
        self._total_frames = 0
        self._total_latency_us = 0.0

        # Re-initialize immediately to maintain invariant
        self._initialize()

    def close(self) -> None:
        """Close the engine and release all resources.

        After calling close(), the engine cannot be used again.
        This is automatically called when using the context manager.

        Note:
            It's safe to call close() multiple times.
        """
        if self._closed:
            return

        if self._cpp_engine is not None:
            with contextlib.suppress(Exception):
                self._cpp_engine.reset()

        self._cpp_engine = None
        self._initialized = False
        self._closed = True

    def synchronize(self) -> None:
        """Synchronize GPU operations for the engine."""
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
        """Get the engine configuration (read-only)."""
        return self._config

    @property
    def is_initialized(self) -> bool:
        """Check if engine is initialized with GPU resources."""
        return self._initialized and not self._closed

    @property
    def stats(self) -> dict[str, Any]:
        """Get performance statistics.

        Returns:
            Dictionary containing:
                - latency_us: Last frame latency in microseconds
                - throughput_gbps: Achieved memory throughput
                - frames_processed: Total frames since initialization
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

        # Add computed statistics if profiling
        if self._config.enable_profiling and self._total_frames > 0:
            result["avg_latency_us"] = self._total_latency_us / self._total_frames
            result["total_frames"] = self._total_frames

        return result

    @property
    def device_info(self) -> dict[str, Any]:
        """Get CUDA device information.

        Returns:
            Dictionary containing device name, memory, CUDA version, etc.
        """
        if not self._initialized or self._cpp_engine is None:
            return {
                "device_name": "Not initialized",
                "cuda_version": "Unknown",
                "device_memory_mb": 0,
                "device_memory_free_mb": 0,
            }

        info = self._cpp_engine.get_runtime_info()
        return {
            "device_name": str(info.device_name),
            "cuda_version": str(info.cuda_version),
            "device_memory_mb": int(getattr(info, "device_memory_total_mb", 0)),
            "device_memory_free_mb": int(getattr(info, "device_memory_free_mb", 0)),
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

        # Synchronize on exit
        if self._initialized and self._cpp_engine is not None:
            with contextlib.suppress(Exception):
                self._cpp_engine.synchronize()

        if exc_type is not None:
            warnings.warn(
                "Engine closed due to exception in context.",
                ResourceWarning,
                stacklevel=2
            )

        self.close()
    # -------------------------------------------------------------------------
    # Advanced Research Interface
    # -------------------------------------------------------------------------

    def get_cuda_stream(self, index: int = 0) -> int:
        """Get raw CUDA stream handle for interoperability.

        Args:
            index: Stream index (0 to stream_count - 1)

        Returns:
            CUDA stream handle as integer

        Raises:
            IndexError: If stream index is out of range
            EngineStateError: If engine not initialized

        Warning:
            This is for advanced users only. Improper use can cause crashes.
        """
        if not self._initialized:
            raise EngineStateError("Engine not initialized")

        if index < 0 or index >= self._config.stream_count:
            raise IndexError(f"Stream index {index} out of range [0, {self._config.stream_count})")

        warnings.warn(
            "Using raw CUDA stream handle. This is for advanced interop only.",
            stacklevel=2
        )

        # This would need C++ support to expose stream handles
        raise NotImplementedError("Stream handle access will be added in v2.0")

    def get_device_ptr(self) -> int:
        """Get raw device memory pointer for interoperability.

        Returns:
            Device memory address as integer

        Warning:
            This is for advanced users only. Improper use can cause crashes.
        """
        if not self._initialized:
            raise EngineStateError("Engine not initialized")

        warnings.warn(
            "Using raw device pointer. This is for advanced interop only.",
            stacklevel=2
        )

        # This would need C++ support to expose device pointers
        raise NotImplementedError("Device pointer access will be added in v2.0")

    @property
    def detailed_metrics(self) -> dict[str, Any]:
        """Get detailed performance metrics for research.

        Returns:
            Dictionary with kernel timings, memory throughput, etc.

        Note:
            Only available when profile_mode=True
        """
        if not self._config.enable_profiling:
            return {"error": "Enable profile_mode for detailed metrics"}

        base_stats = self.stats

        # Add derived metrics
        if base_stats["frames_processed"] > 0:
            base_stats["avg_throughput_gbps"] = base_stats.get("throughput_gbps", 0.0)

            # Compute theoretical limits
            bytes_per_frame = (
                self._config.nfft * self._config.batch * 4 +  # Input
                self._config.num_output_bins * self._config.batch * 4  # Output
            )
            base_stats["bytes_per_frame"] = bytes_per_frame

            if "avg_latency_us" in base_stats and base_stats["avg_latency_us"] > 0:
                base_stats["achieved_bandwidth_gbps"] = (
                    bytes_per_frame / base_stats["avg_latency_us"] / 1000
                )

        return base_stats

    def enable_experimental_feature(self, feature: str) -> None:
        """Enable experimental features for research.

        Args:
            feature: Feature name to enable

        Raises:
            ValueError: If feature is unknown

        Available features:
            - "unsafe_mode": Disable all validation
            - "cuda_graphs": Use CUDA graphs (when implemented)
            - "multi_stream": Use multiple streams for single call
        """
        if feature == "unsafe_mode":
            self._validate_inputs = False
            warnings.warn("Unsafe mode enabled - no input validation", stacklevel=2)
        elif feature == "cuda_graphs":
            if not self._config.use_cuda_graphs:
                warnings.warn("CUDA graphs not yet implemented", stacklevel=2)
            self._config.use_cuda_graphs = True
        elif feature == "multi_stream":
            warnings.warn("Multi-stream processing not yet implemented", stacklevel=2)
        else:
            raise ValueError(f"Unknown experimental feature: {feature}")

    # -------------------------------------------------------------------------
    # Class Methods
    # -------------------------------------------------------------------------

    @classmethod
    def get_available_devices(cls) -> list[str]:
        """Get list of available CUDA devices.

        Returns:
            List of device description strings
        """
        try:
            cpp_module = _import_cpp_engine()
            return list(cpp_module.get_available_devices())
        except Exception as e:
            warnings.warn(f"Failed to query devices: {e}", stacklevel=2)
            return []

    @classmethod
    def select_best_device(cls) -> int:
        """Select the best available CUDA device.

        Returns:
            Device ID of the selected device
        """
        try:
            cpp_module = _import_cpp_engine()
            return int(cpp_module.select_best_device())
        except Exception:
            return 0

    # -------------------------------------------------------------------------
    # Debugging Support
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        """Get string representation for debugging."""
        state = "closed" if self._closed else ("initialized" if self._initialized else "created")
        return f"<Engine state={state} config={self._config}>"

    def __del__(self) -> None:
        """Ensure cleanup on deletion."""
        if not self._closed and self._initialized:
            warnings.warn(
                "Engine not properly closed. Use 'with Engine() as e:' or call engine.close()",
                ResourceWarning,
                stacklevel=2
            )
            with contextlib.suppress(Exception):
                self.close()


# -----------------------------------------------------------------------------
# Convenience Functions
# -----------------------------------------------------------------------------

@overload
def process_signal(
    data: ArrayLike,
    config: Literal["realtime", "throughput", "validation", "profiling"] = "realtime"
) -> FloatArray: ...

@overload
def process_signal(
    data: ArrayLike,
    config: EngineConfig
) -> FloatArray: ...

def process_signal(
    data: ArrayLike,
    config: EngineConfig | str = "realtime"
) -> FloatArray:
    """One-shot signal processing without explicit engine management.

    Convenience function for simple use cases where you just want to
    process data without managing an engine instance.

    Args:
        data: Input signal data
        config: Configuration (preset name or EngineConfig object)

    Returns:
        Magnitude spectrum array

    Example:
        >>> spectrum = process_signal(signal_data, "realtime")
    """
    with Engine(config) as engine:
        return engine.process(data)


def benchmark_latency(
    config: EngineConfig | str = "realtime",
    iterations: int = 100,
    data_size: int | None = None
) -> dict[str, float]:
    """Benchmark processing latency.

    Args:
        config: Engine configuration
        iterations: Number of iterations to run
        data_size: Input data size (None uses config default)

    Returns:
        Dictionary with latency statistics (mean, min, max, p99, etc.)
    """
    engine = Engine(config, profile_mode=True)

    # Prepare test data
    if data_size is None:
        data_size = engine.config.nfft * engine.config.batch
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
