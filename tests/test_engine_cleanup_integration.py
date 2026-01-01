"""Integration tests for Engine cleanup with real GPU.

These tests require actual GPU hardware and validate memory leak detection
and cleanup behavior under realistic conditions.
"""

import os

import pytest

from sigtekx import Engine, EngineConfig
from sigtekx.utils.device import get_gpu_memory_snapshot

# -----------------------------------------------------------------------------
# GPU Integration Tests
# -----------------------------------------------------------------------------

@pytest.mark.gpu
class TestRealGPUCleanup:
    """Tests that require actual GPU hardware."""

    def test_repeated_create_close_no_leak(self):
        """Test that creating and closing 10 engines doesn't leak memory."""
        # Force enable memory tracking
        original_env = os.environ.get('SIGX_TRACK_CLEANUP_MEMORY')

        try:
            os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = '1'

            # Get baseline memory
            baseline = get_gpu_memory_snapshot(0)

            # Create and close engines 10 times
            for i in range(10):
                config = EngineConfig(
                    nfft=1024,
                    channels=2,
                    overlap=0.5,
                    sample_rate_hz=48000,
                    warmup_iters=0,
                    enable_profiling=False
                )
                engine = Engine(config=config)
                engine.close()

            # Check final memory
            final = get_gpu_memory_snapshot(0)
            leak = final['used_mb'] - baseline['used_mb']

            # Allow 20 MB tolerance for GPU memory variance
            assert leak < 20, f"Memory leak detected: {leak} MB"

        finally:
            if original_env is None:
                os.environ.pop('SIGX_TRACK_CLEANUP_MEMORY', None)
            else:
                os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = original_env

    def test_context_manager_cleanup_releases_memory(self):
        """Test that context manager properly releases GPU memory."""
        # Force enable memory tracking
        original_env = os.environ.get('SIGX_TRACK_CLEANUP_MEMORY')

        try:
            os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = '1'

            # Get baseline memory
            baseline = get_gpu_memory_snapshot(0)

            # Use context manager
            config = EngineConfig(
                nfft=4096,
                channels=4,
                overlap=0.75,
                sample_rate_hz=48000,
                warmup_iters=0,
                enable_profiling=False
            )

            with Engine(config=config) as engine:
                pass  # Engine allocates GPU memory

            # Check memory after context exit
            final = get_gpu_memory_snapshot(0)
            leak = final['used_mb'] - baseline['used_mb']

            # Allow 20 MB tolerance
            assert leak < 20, f"Memory leak detected: {leak} MB"

        finally:
            if original_env is None:
                os.environ.pop('SIGX_TRACK_CLEANUP_MEMORY', None)
            else:
                os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = original_env

    @pytest.mark.slow
    def test_long_duration_no_leak(self):
        """Test that 100 iterations don't accumulate memory leaks.

        This is a stress test for the methods paper requirements
        (long-duration stability validation).
        """
        # Force enable memory tracking
        original_env = os.environ.get('SIGX_TRACK_CLEANUP_MEMORY')

        try:
            os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = '1'

            # Get baseline memory
            baseline = get_gpu_memory_snapshot(0)
            print(f"\nBaseline GPU memory: {baseline['used_mb']} MB")

            config = EngineConfig(
                nfft=2048,
                channels=2,
                overlap=0.625,
                sample_rate_hz=48000,
                warmup_iters=0,
                enable_profiling=False
            )

            # Run 100 iterations
            for i in range(100):
                engine = Engine(config=config)
                engine.close()

                # Check memory every 20 iterations
                if (i + 1) % 20 == 0:
                    current = get_gpu_memory_snapshot(0)
                    leak = current['used_mb'] - baseline['used_mb']
                    print(f"Iteration {i + 1}: GPU memory = {current['used_mb']} MB (delta = {leak:+d} MB)")

                    # Fail early if leak exceeds threshold
                    assert leak < 50, f"Memory leak detected at iteration {i + 1}: {leak} MB"

            # Final check
            final = get_gpu_memory_snapshot(0)
            leak = final['used_mb'] - baseline['used_mb']
            print(f"Final GPU memory: {final['used_mb']} MB (total leak = {leak:+d} MB)")

            # Final tolerance: 30 MB for 100 iterations
            assert leak < 30, f"Memory leak detected after 100 iterations: {leak} MB"

        finally:
            if original_env is None:
                os.environ.pop('SIGX_TRACK_CLEANUP_MEMORY', None)
            else:
                os.environ['SIGX_TRACK_CLEANUP_MEMORY'] = original_env


# -----------------------------------------------------------------------------
# Profiler Compatibility Tests
# -----------------------------------------------------------------------------

@pytest.mark.gpu
class TestProfilerCompatibility:
    """Tests for profiler-aware logging behavior."""

    def test_cleanup_under_profiler_minimal_logging(self, monkeypatch, caplog):
        """Test that cleanup logging is minimal when running under profiler."""
        # Mock profiler environment
        monkeypatch.setenv('NSYS_PROFILING_SESSION_ID', 'test_session')

        config = EngineConfig(
            nfft=512,
            channels=1,
            overlap=0.0,
            sample_rate_hz=8000,
            warmup_iters=0,
            enable_profiling=False
        )

        with caplog.at_level("DEBUG"):
            engine = Engine(config=config)
            engine.close()

        # Under profiler, should have minimal debug logging
        # (verbose logging should be disabled)
        debug_messages = [record for record in caplog.records if record.levelname == "DEBUG"]

        # Should have no verbose cleanup debug messages
        cleanup_debug_msgs = [msg for msg in debug_messages if "cleanup step" in msg.message.lower()]
        assert len(cleanup_debug_msgs) == 0, "Verbose logging should be disabled under profiler"
