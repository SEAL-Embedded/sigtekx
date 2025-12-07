# tests/test_exceptions.py

from sigtekx.exceptions import (
    AnalysisError,
    BenchmarkError,
    BenchmarkTimeoutError,
    BenchmarkValidationError,
    ConfigError,
    DataIntegrityError,
    DependencyError,
    DeviceNotFoundError,
    DllLoadError,
    EngineRuntimeError,
    EngineStateError,
    EnvironmentMismatchError,
    ExperimentError,
    InsufficientDataError,
    ReportGenerationError,
    ReproducibilityError,
    ResourceExhaustedError,
    SigTekXError,
    ValidationError,
    WorkflowError,
)


def test_sigtekx_error_str():
    """Test the base __str__ method for SigTekXError."""
    # Without hint
    err = SigTekXError("A base error occurred.")
    assert str(err) == "A base error occurred."

    # With hint
    err_with_hint = SigTekXError("A base error occurred.", hint="Check this.")
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
    assert "Reduce channels or nfft" in str(err_mem)

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


def test_documented_attributes_phase1():
    """Test that Phase 1 exceptions have all documented attributes.

    Verifies SigTekXError and BenchmarkError have the attributes
    documented in their NumPy-style docstrings.
    """
    # SigTekXError
    err_base = SigTekXError("test message", hint="test hint", extra="value")
    assert hasattr(err_base, "hint"), "SigTekXError missing 'hint' attribute"
    assert hasattr(err_base, "context"), "SigTekXError missing 'context' attribute"
    assert err_base.hint == "test hint"
    assert err_base.context == {"extra": "value"}

    # BenchmarkError
    err_bench = BenchmarkError("bench failed", benchmark_name="latency_test")
    assert hasattr(err_bench, "benchmark_name"), "BenchmarkError missing 'benchmark_name' attribute"
    assert hasattr(err_bench, "hint"), "BenchmarkError missing inherited 'hint' attribute"
    assert hasattr(err_bench, "context"), "BenchmarkError missing inherited 'context' attribute"
    assert err_bench.benchmark_name == "latency_test"


def test_documented_attributes_phase2():
    """Test that Phase 2 (Tier 2) exceptions have all documented attributes.

    Verifies the 10 simple exceptions have attributes documented in their docstrings.
    """
    # DeviceNotFoundError
    err_device = DeviceNotFoundError()
    assert hasattr(err_device, "hint")
    assert hasattr(err_device, "context")

    # ValidationError
    err_val = ValidationError("test", expected="int", got="str")
    assert hasattr(err_val, "expected")
    assert hasattr(err_val, "got")
    assert hasattr(err_val, "hint")
    assert err_val.expected == "int"
    assert err_val.got == "str"

    # DllLoadError
    err_dll = DllLoadError("test.dll", original_error=RuntimeError("test"))
    assert hasattr(err_dll, "dll_name")
    assert hasattr(err_dll, "original_error")
    assert hasattr(err_dll, "hint")
    assert err_dll.dll_name == "test.dll"

    # EngineStateError
    err_state = EngineStateError("test", current_state="uninitialized")
    assert hasattr(err_state, "current_state")
    assert hasattr(err_state, "hint")
    assert err_state.current_state == "uninitialized"

    # EngineRuntimeError
    err_runtime = EngineRuntimeError("test", cuda_error="out of memory")
    assert hasattr(err_runtime, "cuda_error")
    assert hasattr(err_runtime, "hint")
    assert err_runtime.cuda_error == "out of memory"

    # ConfigError
    err_config = ConfigError("test", field="nfft", value=1000)
    assert hasattr(err_config, "field")
    assert hasattr(err_config, "value")
    assert hasattr(err_config, "hint")
    assert err_config.field == "nfft"
    assert err_config.value == 1000

    # BenchmarkTimeoutError
    err_timeout = BenchmarkTimeoutError("bench", 5, 10.0)
    assert hasattr(err_timeout, "benchmark_name")
    assert hasattr(err_timeout, "hint")
    assert hasattr(err_timeout, "context")

    # ExperimentError
    err_exp = ExperimentError("test", experiment_id="exp123")
    assert hasattr(err_exp, "experiment_id")
    assert hasattr(err_exp, "hint")
    assert hasattr(err_exp, "context")
    assert err_exp.experiment_id == "exp123"

    # AnalysisError
    err_analysis = AnalysisError("test", analysis_type="latency")
    assert hasattr(err_analysis, "analysis_type")
    assert hasattr(err_analysis, "hint")
    assert hasattr(err_analysis, "context")
    assert err_analysis.analysis_type == "latency"

    # WorkflowError
    err_workflow = WorkflowError("test", workflow_stage="data_collection")
    assert hasattr(err_workflow, "workflow_stage")
    assert hasattr(err_workflow, "hint")
    assert hasattr(err_workflow, "context")
    assert err_workflow.workflow_stage == "data_collection"


# ============================================================================
# Error Code Tests (Phase 2)
# ============================================================================

def test_error_codes_present():
    """Test that all exceptions have error_code class attribute."""
    exceptions = [
        SigTekXError,
        ConfigError,
        ValidationError,
        DeviceNotFoundError,
        DllLoadError,
        EngineStateError,
        EngineRuntimeError,
        BenchmarkError,
        BenchmarkTimeoutError,
        BenchmarkValidationError,
        ExperimentError,
        ReproducibilityError,
        EnvironmentMismatchError,
        DataIntegrityError,
        AnalysisError,
        InsufficientDataError,
        ReportGenerationError,
        WorkflowError,
        DependencyError,
        ResourceExhaustedError,
    ]

    for exc_class in exceptions:
        assert hasattr(exc_class, 'error_code'), f"{exc_class.__name__} missing 'error_code' attribute"
        assert exc_class.error_code.startswith('E'), f"{exc_class.__name__}.error_code should start with 'E'"


def test_error_codes_unique():
    """Test that all error codes are unique."""
    exceptions = [
        SigTekXError,
        ConfigError,
        ValidationError,
        DeviceNotFoundError,
        DllLoadError,
        EngineStateError,
        EngineRuntimeError,
        BenchmarkError,
        BenchmarkTimeoutError,
        BenchmarkValidationError,
        ExperimentError,
        ReproducibilityError,
        EnvironmentMismatchError,
        DataIntegrityError,
        AnalysisError,
        InsufficientDataError,
        ReportGenerationError,
        WorkflowError,
        DependencyError,
        ResourceExhaustedError,
    ]

    codes = [exc.error_code for exc in exceptions]
    assert len(codes) == len(set(codes)), f"Duplicate error codes found: {codes}"


def test_error_code_in_repr():
    """Test that error code appears in repr()."""
    err = ConfigError("Invalid nfft", field="nfft")
    repr_str = repr(err)
    assert "E1010" in repr_str, f"Error code E1010 not found in repr: {repr_str}"
    assert "ConfigError" in repr_str, f"Class name not found in repr: {repr_str}"


def test_error_code_not_in_str():
    """Test backward compat - error code NOT in str()."""
    err = ConfigError("Invalid nfft", field="nfft")
    str_repr = str(err)
    assert "E1010" not in str_repr, f"Error code E1010 should not be in str(): {str_repr}"
    assert "Invalid nfft" in str_repr, f"Message not found in str(): {str_repr}"


def test_backward_compatibility():
    """Test that existing exception catching works."""
    import pytest

    # Test exception catching
    with pytest.raises(ConfigError):
        raise ConfigError("test")

    # Test instance attributes
    err = ConfigError("test", field="nfft", value=1000)
    assert err.field == "nfft"
    assert err.value == 1000

    # Test error code access
    assert err.error_code == "E1010"
    assert ConfigError.error_code == "E1010"


def test_error_code_in_logging():
    """Test that error codes appear in logged exceptions."""
    import logging
    from io import StringIO

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.ERROR)
    logger = logging.getLogger('test_error_codes')
    logger.setLevel(logging.ERROR)
    logger.addHandler(handler)

    try:
        raise ConfigError("Invalid config", field="nfft")
    except ConfigError as e:
        logger.error(f"Error: {repr(e)}")

    log_output = log_stream.getvalue()
    assert "E1010" in log_output, f"Error code E1010 not found in log output: {log_output}"

    # Cleanup
    logger.removeHandler(handler)

