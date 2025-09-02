# python/tests/test_exceptions.py

from ionosense_hpc.exceptions import (
    ConfigError,
    DeviceNotFoundError,
    DllLoadError,
    EngineRuntimeError,
    EngineStateError,
    IonosenseError,
    ValidationError,
)


def test_ionosense_error_str():
    """Test the base __str__ method for IonosenseError."""
    # Without hint
    err = IonosenseError("A base error occurred.")
    assert str(err) == "A base error occurred."

    # With hint
    err_with_hint = IonosenseError("A base error occurred.", hint="Check this.")
    assert str(err_with_hint) == "A base error occurred.\nHint: Check this."

def test_config_error():
    """Test the ConfigError exception."""
    # With field and value
    err = ConfigError("Invalid setting", field="nfft", value=1000)
    assert err.field == "nfft"
    assert err.value == 1000
    assert "Check the 'nfft' field (current value: 1000)" in str(err)

    # With field only
    err_field = ConfigError("Missing setting", field="window")
    assert "Check the 'window' field" in str(err_field)

def test_device_not_found_error():
    """Test the DeviceNotFoundError exception."""
    err = DeviceNotFoundError()
    assert "No CUDA-capable devices found" in str(err)
    assert "Ensure NVIDIA drivers are installed" in str(err)

def test_dll_load_error():
    """Test the DllLoadError exception."""
    # Without original error
    err = DllLoadError("cudart64_110.dll")
    assert "Failed to load cudart64_110.dll" in str(err)
    assert "Check that CUDA toolkit is installed" in str(err)

    # With original error
    original = RuntimeError("File not found")
    err_orig = DllLoadError("cufft64_110.dll", original_error=original)
    assert f": {original}" in str(err_orig)

def test_engine_state_error():
    """Test the EngineStateError exception."""
    # Uninitialized state
    err_uninit = EngineStateError("Not ready", current_state="uninitialized")
    assert "Call initialize()" in str(err_uninit)

    # Processing state
    err_proc = EngineStateError("Busy", current_state="processing")
    assert "Wait for current operation to complete" in str(err_proc)

    # Other state (no specific hint)
    err_other = EngineStateError("Some state", current_state="idle")
    assert "Hint:" not in str(err_other)

def test_engine_runtime_error():
    """Test the EngineRuntimeError exception."""
    # Out of memory error
    err_mem = EngineRuntimeError("CUDA Error", cuda_error="out of memory")
    assert "Reduce batch size or nfft" in str(err_mem)

    # Invalid configuration error
    err_config = EngineRuntimeError("CUDA Error", cuda_error="invalid configuration")
    assert "Check that nfft is a power of 2" in str(err_config)

    # Other CUDA error (no specific hint)
    err_other = EngineRuntimeError("CUDA Error", cuda_error="unspecified launch failure")
    assert "Hint:" not in str(err_other)

def test_validation_error():
    """Test the ValidationError exception."""
    # With expected and got
    err = ValidationError("Bad input shape", expected="(1024,)", got="(512,)")
    assert "Expected (1024,), got (512,)" in str(err)

    # Without expected/got (no hint)
    err_plain = ValidationError("Bad input value")
    assert "Hint:" not in str(err_plain)
