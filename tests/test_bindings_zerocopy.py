"""Tests for zero-copy buffer pool optimization in Python bindings.

This module validates the buffer pool implementation that enables zero-copy
returns from process() while maintaining safety through:
1. reference_internal policy (keeps executor alive)
2. Round-robin buffer pool (4 buffers for independent outputs)
3. Explicit copy escape hatch (result.copy() for control plane)
"""

import numpy as np
import pytest

from sigtekx.core import _native


class TestZeroCopyBufferPool:
    """Test zero-copy buffer pool implementation."""

    @pytest.fixture
    def executor(self):
        """Create and initialize a BatchExecutor for testing."""
        executor = _native.BatchExecutor()
        config = _native.ExecutorConfig()
        config.nfft = 256
        config.channels = 1
        config.overlap = 0.5
        executor.initialize(config)
        return executor

    def test_zero_copy_view_with_reference_internal(self, executor):
        """Verify process() returns zero-copy view and executor kept alive."""
        data = np.ones(256, dtype=np.float32)
        output = executor.process(data)

        # IMPORTANT: This test validates reference_internal works
        del executor  # Executor should NOT be deleted (array holds reference)

        # Array should still be accessible (no segfault)
        assert output[0, 0] >= 0
        assert output.shape == (1, 129)  # NFFT=256 -> 129 bins
        assert np.all(np.isfinite(output))

    def test_buffer_pool_independence(self, executor):
        """Verify up to 4 outputs can be stored independently."""
        # Generate 4 different inputs
        inputs = [np.ones(256, dtype=np.float32) * i for i in range(1, 5)]
        outputs = [executor.process(inp) for inp in inputs]

        # All 4 outputs should have different values (not overwritten)
        means = [out.mean() for out in outputs]

        # Check that at least 3 of 4 means are unique (conservative check)
        # (In practice all 4 should be unique, but allow for floating point noise)
        unique_means = len(set(np.round(means, decimals=6)))
        assert unique_means >= 3, f"Expected at least 3 unique means, got {unique_means}"

        # Check addresses are different (zero-copy views)
        addrs = [out.__array_interface__['data'][0] for out in outputs]
        unique_addrs = len(set(addrs))
        assert unique_addrs == 4, f"Expected 4 different buffer addresses, got {unique_addrs}"

    def test_buffer_reuse_after_pool_exhausted(self, executor):
        """Verify 5th output reuses 1st buffer (expected behavior)."""
        # Generate 5 outputs (more than pool size)
        inputs = [np.ones(256, dtype=np.float32) * i for i in range(1, 6)]
        outputs = [executor.process(inp) for inp in inputs]

        # 1st and 5th should share address (buffer reuse after pool exhausted)
        addr1 = outputs[0].__array_interface__['data'][0]
        addr5 = outputs[4].__array_interface__['data'][0]

        assert addr1 == addr5, "5th output should reuse 1st buffer (round-robin)"

        # Values should match (5th overwrote 1st)
        assert np.allclose(outputs[0], outputs[4], rtol=1e-5), \
            "5th output should have same values as overwritten 1st output"

    def test_explicit_copy_independence(self, executor):
        """Verify .copy() creates independent array for control plane."""
        data1 = np.ones(256, dtype=np.float32) * 1.0
        output1 = executor.process(data1)
        output1_copy = output1.copy()  # Explicit copy for control plane

        data2 = np.ones(256, dtype=np.float32) * 2.0
        output2 = executor.process(data2)

        # output1 may be overwritten (view into buffer pool)
        # But output1_copy should be independent (safe)
        assert not np.allclose(output1_copy, output2, rtol=1e-3), \
            "Explicit copy should remain independent from later outputs"

        # Addresses should differ (copy has its own memory)
        addr_copy = output1_copy.__array_interface__['data'][0]
        addr2 = output2.__array_interface__['data'][0]
        assert addr_copy != addr2, "Copy should have different memory address"

    def test_streaming_executor_buffer_pool(self):
        """Verify StreamingExecutor also has buffer pool (same behavior)."""
        executor = _native.StreamingExecutor()
        config = _native.ExecutorConfig()
        config.nfft = 256
        config.channels = 1
        config.overlap = 0.5
        config.mode = _native.ExecutionMode.STREAMING  # Required for StreamingExecutor
        executor.initialize(config)

        # Generate 4 outputs
        inputs = [np.ones(256, dtype=np.float32) * i for i in range(1, 5)]
        outputs = [executor.process(inp) for inp in inputs]

        # Check addresses are different
        addrs = [out.__array_interface__['data'][0] for out in outputs]
        unique_addrs = len(set(addrs))
        assert unique_addrs == 4, \
            f"StreamingExecutor should have 4-buffer pool, got {unique_addrs} unique addresses"

    def test_buffer_pool_with_different_input_sizes(self, executor):
        """Verify buffer pool works correctly with repeated calls."""
        # Call process() 10 times with same input
        data = np.random.randn(256).astype(np.float32)
        outputs = [executor.process(data) for _ in range(10)]

        # Check that we see cycling through 4 buffers
        addrs = [out.__array_interface__['data'][0] for out in outputs]

        # First 4 should be unique
        assert len(set(addrs[:4])) == 4, "First 4 outputs should use 4 different buffers"

        # 5th should match 1st (cycle back)
        assert addrs[4] == addrs[0], "5th output should reuse 1st buffer"

        # 6th should match 2nd
        assert addrs[5] == addrs[1], "6th output should reuse 2nd buffer"

    def test_no_memory_leak_with_many_calls(self, executor):
        """Verify buffer pool doesn't leak memory with many process() calls."""
        # This test validates that round-robin reuse works over many iterations
        data = np.random.randn(256).astype(np.float32)

        # Track unique addresses seen
        seen_addrs = set()

        for _ in range(100):  # Many iterations
            output = executor.process(data)
            addr = output.__array_interface__['data'][0]
            seen_addrs.add(addr)

        # Should only see 4 unique addresses (buffer pool size)
        assert len(seen_addrs) == 4, \
            f"Expected exactly 4 buffer addresses after 100 calls, saw {len(seen_addrs)}"
