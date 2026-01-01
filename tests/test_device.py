"""Tests for device utility functions and NVML context manager."""

import pytest

from sigtekx.utils.device import (
    check_cuda_available,
    device_info,
    get_compute_capability,
    get_memory_usage,
    gpu_count,
    monitor_device,
    nvml_context,
)


class TestNVMLContextManager:
    """Test suite for NVML context manager."""

    def test_nvml_context_basic(self):
        """Test NVML context manager normal operation."""
        # Should complete without error (whether NVML available or not)
        with nvml_context():
            pass
        # NVML should be properly shutdown after context exit

    def test_nvml_context_with_exception(self):
        """Test context manager handles exceptions properly."""
        # Context manager should still cleanup even when exception occurs
        with pytest.raises(RuntimeError):
            with nvml_context():
                raise RuntimeError("Test exception")
        # NVML should still be properly shutdown

    def test_nvml_context_multiple_sequential(self):
        """Test multiple sequential context manager uses."""
        # Should work correctly with repeated use
        for _ in range(5):
            with nvml_context():
                pass


class TestGPUCount:
    """Test suite for gpu_count() function."""

    def test_gpu_count_returns_int(self):
        """Test gpu_count returns an integer."""
        count = gpu_count()
        assert isinstance(count, int)
        assert count >= 0

    def test_gpu_count_consistent(self):
        """Test gpu_count returns consistent results."""
        count1 = gpu_count()
        count2 = gpu_count()
        assert count1 == count2

    def test_gpu_count_multiple_calls(self):
        """Test gpu_count handles multiple sequential calls."""
        # Should work efficiently without resource leaks
        for _ in range(10):
            count = gpu_count()
            assert isinstance(count, int)


class TestDeviceInfo:
    """Test suite for device_info() function."""

    def test_device_info_returns_dict(self):
        """Test device_info returns a dictionary."""
        if gpu_count() == 0:
            pytest.skip("No CUDA devices available")

        info = device_info(0)
        assert isinstance(info, dict)

    def test_device_info_has_required_fields(self):
        """Test device_info returns all required fields."""
        if gpu_count() == 0:
            pytest.skip("No CUDA devices available")

        info = device_info(0)
        required_fields = [
            'id', 'name', 'memory_total_mb', 'memory_free_mb',
            'compute_capability', 'temperature_c', 'power_w',
            'utilization_gpu', 'utilization_memory'
        ]
        for field in required_fields:
            assert field in info

    def test_device_info_name_not_unknown(self):
        """Test device_info populates device name."""
        if gpu_count() == 0:
            pytest.skip("No CUDA devices available")

        info = device_info(0)
        # Should populate name from either NVML or C++ backend
        assert info['name'] != 'Unknown'

    def test_device_info_no_threading_timeout(self):
        """Test device_info completes quickly without threading overhead."""
        if gpu_count() == 0:
            pytest.skip("No CUDA devices available")

        import time
        start = time.time()
        info = device_info(0)
        elapsed = time.time() - start

        # Should complete in < 1 second (no 5s timeout)
        assert elapsed < 1.0
        assert info['name'] != 'Unknown'

    def test_device_info_multiple_sequential_calls(self):
        """Test device_info handles multiple sequential calls efficiently."""
        if gpu_count() == 0:
            pytest.skip("No CUDA devices available")

        # Test that multiple calls work without resource leaks
        for _ in range(10):
            info = device_info(0)
            assert info['name'] != 'Unknown'

    def test_device_info_compute_capability(self):
        """Test device_info returns valid compute capability."""
        if gpu_count() == 0:
            pytest.skip("No CUDA devices available")

        info = device_info(0)
        cc = info['compute_capability']
        assert isinstance(cc, tuple)
        assert len(cc) == 2
        # Modern GPUs have CC >= 3.0
        assert cc[0] >= 3

    def test_device_info_includes_cuda_version(self):
        """Test device_info returns CUDA version."""
        if gpu_count() == 0:
            pytest.skip("No CUDA devices available")

        info = device_info(0)
        assert 'cuda_version' in info

        # CUDA version should be populated if NVML available
        # Format should be like "12.0" or "11.8"
        if info['cuda_version'] != 'Unknown':
            assert '.' in info['cuda_version']
            # Should be parseable as version
            parts = info['cuda_version'].split('.')
            assert len(parts) == 2
            assert int(parts[0]) >= 10  # CUDA 10.0+

    def test_device_info_invalid_device_raises(self):
        """Test device_info raises error for invalid device ID."""
        count = gpu_count()
        if count == 0:
            pytest.skip("No CUDA devices available")

        from sigtekx.exceptions import DeviceNotFoundError

        # Should raise for device ID >= count
        with pytest.raises(DeviceNotFoundError):
            device_info(count + 10)

        # Should raise for negative device ID
        with pytest.raises(DeviceNotFoundError):
            device_info(-1)


class TestGetMemoryUsage:
    """Test suite for get_memory_usage() function."""

    def test_get_memory_usage_returns_tuple(self):
        """Test get_memory_usage returns a tuple."""
        if gpu_count() == 0:
            pytest.skip("No CUDA devices available")

        used, total = get_memory_usage()
        assert isinstance(used, int)
        assert isinstance(total, int)
        assert used >= 0
        assert total > 0
        assert used <= total


class TestCheckCUDAAvailable:
    """Test suite for check_cuda_available() function."""

    def test_check_cuda_available_returns_bool(self):
        """Test check_cuda_available returns a boolean."""
        result = check_cuda_available()
        assert isinstance(result, bool)

    def test_check_cuda_available_consistent_with_gpu_count(self):
        """Test check_cuda_available is consistent with gpu_count."""
        has_cuda = check_cuda_available()
        count = gpu_count()

        if has_cuda:
            assert count > 0
        else:
            assert count == 0


class TestGetComputeCapability:
    """Test suite for get_compute_capability() function."""

    def test_get_compute_capability_returns_tuple(self):
        """Test get_compute_capability returns a tuple."""
        if gpu_count() == 0:
            pytest.skip("No CUDA devices available")

        major, minor = get_compute_capability(0)
        assert isinstance(major, int)
        assert isinstance(minor, int)
        assert major >= 3  # Modern GPUs


class TestMonitorDevice:
    """Test suite for monitor_device() function."""

    def test_monitor_device_returns_string(self):
        """Test monitor_device returns a formatted string."""
        if gpu_count() == 0:
            pytest.skip("No CUDA devices available")

        status = monitor_device(0)
        assert isinstance(status, str)
        assert len(status) > 0

    def test_monitor_device_contains_key_info(self):
        """Test monitor_device output contains key device information."""
        if gpu_count() == 0:
            pytest.skip("No CUDA devices available")

        status = monitor_device(0)
        # Should contain device name and basic info
        assert 'Device' in status
        assert 'Memory' in status
        assert 'Compute Capability' in status


class TestResourceManagement:
    """Test suite for NVML resource management and cleanup."""

    def test_no_resource_leaks_repeated_calls(self):
        """Test that repeated calls don't leak resources."""
        if gpu_count() == 0:
            pytest.skip("No CUDA devices available")

        # Make many calls - should not hang or leak resources
        for i in range(100):
            count = gpu_count()
            assert count >= 0

            if i % 10 == 0:
                info = device_info(0)
                assert info['name'] != 'Unknown'

    def test_context_manager_exception_safety(self):
        """Test context manager cleanup works even with exceptions."""
        # This should work multiple times without resource leaks
        for _ in range(10):
            try:
                with nvml_context():
                    if gpu_count() > 0:
                        # Force an error by using invalid device
                        from sigtekx.exceptions import DeviceNotFoundError
                        with pytest.raises(DeviceNotFoundError):
                            device_info(999)
            except Exception:
                pass

        # Should still work after exceptions
        if gpu_count() > 0:
            info = device_info(0)
            assert info['name'] != 'Unknown'
