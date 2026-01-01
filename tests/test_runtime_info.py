"""Tests for RuntimeInfo bindings and module function."""

import pytest

from sigtekx.core import _native


class TestRuntimeInfoStruct:
    """Test RuntimeInfo struct binding."""

    def test_runtime_info_has_all_fields(self):
        """Verify RuntimeInfo has all expected fields."""
        info = _native.get_runtime_info(0)

        # Check all fields exist
        assert hasattr(info, 'device_name')
        assert hasattr(info, 'cuda_version')
        assert hasattr(info, 'cuda_runtime_version')
        assert hasattr(info, 'cuda_driver_version')

    def test_runtime_info_field_types(self):
        """Verify RuntimeInfo field types are correct."""
        info = _native.get_runtime_info(0)

        assert isinstance(info.device_name, str)
        assert isinstance(info.cuda_version, str)
        assert isinstance(info.cuda_runtime_version, int)
        assert isinstance(info.cuda_driver_version, int)

    def test_runtime_info_device_name_not_empty(self):
        """Verify device_name is populated."""
        info = _native.get_runtime_info(0)
        assert len(info.device_name) > 0
        assert info.device_name != "Unknown"

    def test_runtime_info_cuda_version_format(self):
        """Verify cuda_version has expected format."""
        info = _native.get_runtime_info(0)

        # Format should be "X.Y" (e.g., "12.3")
        assert '.' in info.cuda_version
        parts = info.cuda_version.split('.')
        assert len(parts) == 2
        assert int(parts[0]) >= 10  # CUDA 10.0+
        assert int(parts[1]) >= 0

    def test_runtime_info_version_consistency(self):
        """Verify version string matches integer version."""
        info = _native.get_runtime_info(0)

        # Extract major.minor from integer (e.g., 12030 -> "12.3")
        expected_major = info.cuda_runtime_version // 1000
        expected_minor = (info.cuda_runtime_version % 100) // 10
        expected_version = f"{expected_major}.{expected_minor}"

        assert info.cuda_version == expected_version

    def test_runtime_info_repr(self):
        """Verify __repr__ is implemented."""
        info = _native.get_runtime_info(0)
        repr_str = repr(info)

        assert 'RuntimeInfo' in repr_str
        assert info.device_name in repr_str
        assert info.cuda_version in repr_str


class TestGetRuntimeInfoFunction:
    """Test module-level get_runtime_info() function."""

    def test_get_runtime_info_default_device(self):
        """Test get_runtime_info() with default device."""
        info = _native.get_runtime_info()  # Default: device 0
        assert info.device_name != ""

    def test_get_runtime_info_explicit_device_0(self):
        """Test get_runtime_info(0) explicitly."""
        info = _native.get_runtime_info(0)
        assert info.device_name != ""

    def test_get_runtime_info_invalid_device_negative(self):
        """Test get_runtime_info() raises on negative device index."""
        with pytest.raises(RuntimeError, match="Invalid device index"):
            _native.get_runtime_info(-1)

    def test_get_runtime_info_invalid_device_too_large(self):
        """Test get_runtime_info() raises on out-of-bounds device."""
        # Query actual device count first
        devices = _native.get_available_devices()
        invalid_index = len(devices) + 10

        with pytest.raises(RuntimeError, match="Invalid device index"):
            _native.get_runtime_info(invalid_index)

    def test_get_runtime_info_consistent_results(self):
        """Test get_runtime_info() returns consistent results."""
        info1 = _native.get_runtime_info(0)
        info2 = _native.get_runtime_info(0)

        # Same device should return identical info
        assert info1.device_name == info2.device_name
        assert info1.cuda_version == info2.cuda_version
        assert info1.cuda_runtime_version == info2.cuda_runtime_version
        assert info1.cuda_driver_version == info2.cuda_driver_version


class TestRuntimeInfoErrorHandling:
    """Test RuntimeInfo error handling and edge cases."""

    def test_runtime_info_survives_multiple_calls(self):
        """Test that get_runtime_info() can be called multiple times."""
        # Should not leak resources or cause errors
        for _ in range(100):
            info = _native.get_runtime_info(0)
            assert info.device_name != ""

    def test_runtime_info_version_integers_positive(self):
        """Test that version integers are positive and reasonable."""
        info = _native.get_runtime_info(0)

        # CUDA versions should be positive integers
        assert info.cuda_runtime_version > 0
        assert info.cuda_driver_version > 0

        # Should be at least CUDA 10.0 (10000)
        assert info.cuda_runtime_version >= 10000
        assert info.cuda_driver_version >= 10000

        # Should not exceed CUDA 99.9 (99900) - sanity check
        assert info.cuda_runtime_version < 100000
        assert info.cuda_driver_version < 100000
