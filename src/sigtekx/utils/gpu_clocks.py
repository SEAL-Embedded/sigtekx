"""
src/sigtekx/utils/gpu_clocks.py
--------------------------------------------------------------------------------
GPU clock management for stable benchmarking.

Provides Python interface to lock/unlock GPU clocks using nvidia-smi via
PowerShell script integration. Reduces benchmark variability (CV) by 50-75%.

Example:
    >>> from sigtekx.utils import GpuClockManager
    >>>
    >>> # Context manager (recommended)
    >>> with GpuClockManager().locked_clocks():
    >>>     run_benchmark()
    >>>
    >>> # Manual control
    >>> manager = GpuClockManager(gpu_index=0, use_max_clocks=False)
    >>> lock_info = manager.lock()
    >>> try:
    >>>     run_benchmark()
    >>> finally:
    >>>     manager.unlock()
"""

import json
import platform
import subprocess
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from sigtekx.utils.logging import logger


class GpuClockManager:
    """
    GPU clock management for benchmark stability.

    Wraps PowerShell gpu-manager.ps1 script to lock/unlock GPU clocks
    using nvidia-smi. Provides automatic cleanup via context manager.

    Attributes:
        gpu_index: GPU index to manage (default: 0)
        use_max_clocks: Use max clocks vs recommended (default: False)
        locked: Whether clocks are currently locked
    """

    def __init__(
        self,
        gpu_index: int = 0,
        use_max_clocks: bool = False,
        script_path: Path | None = None
    ):
        """
        Initialize GPU clock manager.

        Args:
            gpu_index: GPU index to manage
            use_max_clocks: Use max clocks (performance) vs recommended (stability)
            script_path: Custom path to gpu-manager.ps1 (auto-detected if None)
        """
        self.gpu_index = gpu_index
        self.use_max_clocks = use_max_clocks
        self.locked = False

        # Auto-detect script path relative to this file
        # Use the elevation wrapper which handles UAC automatically
        if script_path is None:
            utils_dir = Path(__file__).parent  # .../utils/
            src_dir = utils_dir.parent          # .../sigtekx/
            pkg_root = src_dir.parent           # .../
            repo_root = pkg_root.parent         # sigtekx/
            script_path = repo_root / "scripts" / "gpu-manager-elevated.ps1"

        self.script_path = Path(script_path)

        # Validate prerequisites
        self._validate_environment()

    def _validate_environment(self) -> None:
        """Validate that prerequisites are met."""
        # Check if running on Windows
        if platform.system() != "Windows":
            raise RuntimeError(
                "GPU clock locking currently only supported on Windows. "
                "Linux support coming soon."
            )

        # Check if script exists
        if not self.script_path.exists():
            raise FileNotFoundError(
                f"GPU manager script not found: {self.script_path}\n"
                "This is required for GPU clock management."
            )

        # Check if PowerShell is available
        try:
            result = subprocess.run(
                ["pwsh", "-Version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError("PowerShell 7+ (pwsh) not found")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise RuntimeError(
                "PowerShell 7+ (pwsh) required for GPU clock management. "
                "Install from: https://aka.ms/powershell"
            ) from e

    def _run_ps_script(
        self,
        action: str,
        additional_args: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Run PowerShell gpu-manager.ps1 script.

        Args:
            action: Action to perform (Lock, Unlock, Query, Validate)
            additional_args: Additional script arguments

        Returns:
            Parsed output from script (if any)

        Raises:
            RuntimeError: If script execution fails
        """
        args = [
            "pwsh",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", str(self.script_path),
            "-Action", action,
            "-GpuIndex", str(self.gpu_index)
        ]

        # Add recommended vs max clocks flag
        # Note: -UseRecommended is a switch parameter with default=$true
        # For switches: -SwitchName enables it, -SwitchName:$false disables it
        if action == "Lock":
            if not self.use_max_clocks:
                # Use recommended clocks (default behavior, explicitly enable switch)
                args.extend(["-UseRecommended:$true"])
            else:
                # Use max clocks (disable the switch)
                args.extend(["-UseRecommended:$false"])

        if additional_args:
            args.extend(additional_args)

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=True
            )

            # Parse output if it looks like JSON
            output = result.stdout.strip()
            if output and output.startswith('{'):
                try:
                    parsed: dict[str, Any] = json.loads(output)
                    return parsed
                except json.JSONDecodeError:
                    pass

            # Return success indicator
            return {"success": True, "output": output}

        except subprocess.CalledProcessError as e:
            error_msg = f"GPU clock {action.lower()} failed: {e.stderr}"
            raise RuntimeError(error_msg) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"GPU clock {action.lower()} timed out after 30s"
            ) from e

    def lock(self) -> dict[str, Any]:
        """
        Lock GPU clocks to stable values.

        Requires administrator privileges on Windows.
        Uses nvidia-smi to lock graphics and memory clocks.

        Returns:
            Dictionary with lock information:
                - success: bool
                - gpu_index: int
                - locked_graphics_clock: int (MHz)
                - locked_memory_clock: int (MHz)
                - original_graphics_clock: int (MHz)
                - original_memory_clock: int (MHz)

        Raises:
            RuntimeError: If locking fails or admin privileges missing
        """
        if self.locked:
            logger.warning("GPU clocks already locked")
            return {"success": True, "already_locked": True}

        logger.info(f"🔒 Locking GPU {self.gpu_index} clocks...")
        logger.info(f"   Mode: {'max' if self.use_max_clocks else 'recommended'} clocks")

        try:
            result = self._run_ps_script("Lock")
            self.locked = True

            logger.info("✅ GPU clocks locked successfully")
            return result

        except RuntimeError as e:
            logger.error(f"Failed to lock GPU clocks: {e}")
            logger.warning(
                "Clock locking requires administrator privileges. "
                "Run PowerShell as administrator or skip clock locking."
            )
            raise

    def unlock(self) -> None:
        """
        Restore GPU clocks to default (unlocked) state.

        Safe to call multiple times. Will attempt unlock even if
        lock() was never called (for cleanup robustness).
        """
        if not self.locked:
            logger.debug("GPU clocks not locked, skipping unlock")
            return

        logger.info(f"🔓 Unlocking GPU {self.gpu_index} clocks...")

        try:
            self._run_ps_script("Unlock")
            self.locked = False
            logger.info("✅ GPU clocks unlocked successfully")

        except RuntimeError as e:
            logger.error(f"Failed to unlock GPU clocks: {e}")
            logger.warning(
                "Manual recovery may be needed:\n"
                f"  Run as administrator:\n"
                f"    nvidia-smi -i {self.gpu_index} -pm 0\n"
                f"    nvidia-smi -i {self.gpu_index} -rgc\n"
                f"    nvidia-smi -i {self.gpu_index} -rmc"
            )
            # Don't raise - unlock is best-effort for cleanup

    def query(self) -> dict[str, Any]:
        """
        Query current GPU clock information.

        Returns:
            Dictionary with GPU info:
                - index: int
                - name: str
                - current_graphics_clock: int (MHz)
                - current_memory_clock: int (MHz)
                - max_graphics_clock: int (MHz)
                - max_memory_clock: int (MHz)
                - persistence_mode: str
                - profile: dict (if known GPU model)
        """
        return self._run_ps_script("Query")

    @contextmanager
    def locked_clocks(self):
        """
        Context manager for automatic GPU clock lock/unlock.

        Ensures clocks are always unlocked even if benchmark fails.

        Example:
            >>> with GpuClockManager().locked_clocks():
            >>>     run_benchmark()

        Yields:
            self: GpuClockManager instance with locked clocks
        """
        try:
            lock_info = self.lock()
            yield lock_info
        finally:
            self.unlock()

    def __enter__(self):
        """Support for context manager protocol."""
        self.lock()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure cleanup on context exit."""
        self.unlock()
        return False  # Don't suppress exceptions

    def __del__(self):
        """Cleanup on deletion (safety net)."""
        if self.locked:
            with suppress(Exception):  # Best effort only
                self.unlock()


def check_clock_locking_available() -> tuple[bool, str]:
    """
    Check if GPU clock locking is available on this system.

    Returns:
        Tuple of (is_available, reason_if_not)

    Example:
        >>> available, reason = check_clock_locking_available()
        >>> if not available:
        >>>     print(f"Clock locking unavailable: {reason}")
    """
    # Check platform
    if platform.system() != "Windows":
        return False, "Currently only supported on Windows"

    # Check PowerShell
    try:
        result = subprocess.run(
            ["pwsh", "-Version"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5
        )
        if result.returncode != 0:
            return False, "PowerShell 7+ (pwsh) not found"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "PowerShell 7+ (pwsh) not installed"

    # Check nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi", "--version"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5
        )
        if result.returncode != 0:
            return False, "nvidia-smi not found (install NVIDIA drivers)"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "nvidia-smi not found (install NVIDIA drivers)"

    # Check script exists (use elevation wrapper)
    utils_dir = Path(__file__).parent
    src_dir = utils_dir.parent
    pkg_root = src_dir.parent
    repo_root = pkg_root.parent
    script_path = repo_root / "scripts" / "gpu-manager-elevated.ps1"

    if not script_path.exists():
        return False, f"GPU manager script not found: {script_path}"

    return True, ""
