# tests/test_exceptions.py

from ionosense_hpc.exceptions import (
    AnalysisError,
    BenchmarkError,
    BenchmarkTimeoutError,
    ConfigError,
    DeviceNotFoundError,
    DllLoadError,
    EngineRuntimeError,
    EngineStateError,
    ExperimentError,
    IonosenseError,
    ValidationError,
    WorkflowError,
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

    Verifies IonosenseError and BenchmarkError have the attributes
    documented in their NumPy-style docstrings.
    """
    # IonosenseError
    err_base = IonosenseError("test message", hint="test hint", extra="value")
    assert hasattr(err_base, "hint"), "IonosenseError missing 'hint' attribute"
    assert hasattr(err_base, "context"), "IonosenseError missing 'context' attribute"
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

