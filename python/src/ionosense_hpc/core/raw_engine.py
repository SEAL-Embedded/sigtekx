"""Low-level wrapper for the C++ _engine extension module."""

import warnings
from typing import Any

import numpy as np

from ionosense_hpc.exceptions import DllLoadError, EngineRuntimeError, EngineStateError


def import_engine():
    """Import the native extension with proper error handling.

    Returns:
        The loaded _engine module

    Raises:
        DllLoadError: If the extension cannot be loaded
    """
    try:
        # This assumes DLL bootstrap has already happened in __init__.py
        from . import _engine  # type: ignore[attr-defined]
        return _engine
    except ImportError as e:
        # Check for common error patterns
        error_str = str(e)
        if "DLL load failed" in error_str or "cannot open shared object" in error_str:
            raise DllLoadError("_engine", e) from e
        elif "No module named" in error_str:
            raise DllLoadError(
                "_engine",
                RuntimeError("Extension module not found. Run build first: ./scripts/cli.sh build")
            ) from e
        else:
            raise


class RawEngine:
    """Thin wrapper around the C++ ResearchEngine.

    This class provides minimal Python-level processing, mostly translating
    exceptions and checking module availability. For most use cases, use
    the higher-level Engine or Processor classes instead.
    """

    def __init__(self):
        """Initialize the raw engine wrapper."""
        self._engine_module = import_engine()
        self._engine = self._engine_module.ResearchEngine()
        self._initialized = False
        self._config = None

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the engine with a configuration dictionary.

        Args:
            config: Configuration parameters as a dict

        Raises:
            EngineRuntimeError: If initialization fails
        """
        try:
            # Create C++ config object
            cpp_config = self._engine_module.EngineConfig()
            for key, value in config.items():
                if hasattr(cpp_config, key):
                    setattr(cpp_config, key, value)

            self._engine.initialize(cpp_config)
            self._config = config
            self._initialized = True
        except RuntimeError as e:
            raise EngineRuntimeError(f"Failed to initialize engine: {e}", str(e)) from e

    def process(self, input_data: np.ndarray) -> np.ndarray:
        """Process a batch of input data.

        Args:
            input_data: 1D array of float32 samples

        Returns:
            2D array of magnitude spectra [batch, bins]

        Raises:
            EngineStateError: If engine is not initialized
            EngineRuntimeError: If processing fails
        """
        if not self._initialized:
            raise EngineStateError("Engine not initialized", "uninitialized")

        try:
            # Ensure float32 and contiguous
            if input_data.dtype != np.float32:
                input_data = input_data.astype(np.float32)
            if not input_data.flags['C_CONTIGUOUS']:
                input_data = np.ascontiguousarray(input_data)

            return self._engine.process(input_data)  # type: ignore[no-any-return]
        except RuntimeError as e:
            error_str = str(e)
            if "size mismatch" in error_str.lower():
                raise EngineRuntimeError(
                    f"Input size error: {e}",
                    "Check that input size matches nfft * batch"
                ) from e
            else:
                raise EngineRuntimeError(f"Processing failed: {e}", error_str) from e

    def reset(self) -> None:
        """Reset the engine to uninitialized state."""
        try:
            self._engine.reset()
            self._initialized = False
            self._config = None
        except RuntimeError as e:
            warnings.warn(f"Reset warning: {e}", stacklevel=2)

    def synchronize(self) -> None:
        """Synchronize all CUDA streams."""
        if not self._initialized:
            return
        try:
            self._engine.synchronize()
        except RuntimeError as e:
            raise EngineRuntimeError(f"Synchronization failed: {e}") from e

    def get_stats(self) -> dict[str, Any]:
        """Get processing statistics.

        Returns:
            Dictionary with latency_us, throughput_gbps, frames_processed
        """
        if not self._initialized:
            return {
                'latency_us': 0.0,
                'throughput_gbps': 0.0,
                'frames_processed': 0
            }

        stats = self._engine.get_stats()
        return {
            'latency_us': stats.latency_us,
            'throughput_gbps': stats.throughput_gbps,
            'frames_processed': stats.frames_processed
        }

    def get_runtime_info(self) -> dict[str, Any]:
        """Get CUDA runtime information.

        Returns:
            Dictionary with device and CUDA version info
        """
        info = self._engine.get_runtime_info()
        return {
            'device_name': info.device_name,
            'cuda_version': info.cuda_version,
            'device_memory_mb': getattr(info, 'device_memory_total_mb', 0),
            'device_memory_free_mb': getattr(info, 'device_memory_free_mb', 0)
        }

    @property
    def is_initialized(self) -> bool:
        """Check if engine is initialized."""
        return self._initialized and self._engine.is_initialized

    @property
    def config(self) -> dict[str, Any] | None:
        """Get current configuration."""
        return self._config.copy() if self._config else None

    @classmethod
    def get_available_devices(cls) -> list:
        """Get list of available CUDA devices.

        Returns:
            List of device description strings
        """
        try:
            engine_module = import_engine()
            return engine_module.get_available_devices()  # type: ignore[no-any-return]
        except Exception as e:
            warnings.warn(f"Failed to query devices: {e}", stacklevel=2)
            return []

    @classmethod
    def select_best_device(cls) -> int:
        """Select the best available CUDA device.

        Returns:
            Device ID of the best device
        """
        try:
            engine_module = import_engine()
            return int(engine_module.select_best_device())  # type: ignore[no-any-return]
        except Exception:
            return 0  # Default to device 0

    def __repr__(self) -> str:
        state = "initialized" if self._initialized else "uninitialized"
        return f"<RawEngine state={state}>"

    def __del__(self):
        """Ensure cleanup on deletion."""
        try:
            if hasattr(self, '_engine') and self._initialized:
                self.reset()
        except Exception:
            pass  # Suppress errors during cleanup
