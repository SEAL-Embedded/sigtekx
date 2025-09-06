"""
Custom exception hierarchy for ionosense-hpc.

Enhanced with research-specific exceptions for benchmarking,
experiments, and reproducibility following RSE/RE standards.
"""

from typing import Any


class IonosenseError(Exception):
    """Base exception for all ionosense-hpc errors."""

    def __init__(self, message: str, hint: str | None = None, **kwargs):
        super().__init__(message)
        self.hint = hint
        self.context = kwargs

    def __str__(self) -> str:
        msg = super().__str__()
        if self.hint:
            msg += f"\nHint: {self.hint}"
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            msg += f"\nContext: {context_str}"
        return msg


# ============================================================================
# Configuration and Validation Errors
# ============================================================================

class ConfigError(IonosenseError):
    """Configuration validation or compatibility error."""

    def __init__(self, message: str, field: str | None = None, value: Any = None):
        hint = None
        if field:
            hint = f"Check the '{field}' field"
            if value is not None:
                hint += f" (current value: {value})"
        super().__init__(message, hint, field=field, value=value)
        self.field = field
        self.value = value


class ValidationError(IonosenseError):
    """Input data validation error."""

    def __init__(self, message: str, expected: str | None = None, got: str | None = None):
        hint = None
        if expected and got:
            hint = f"Expected {expected}, got {got}"
        super().__init__(message, hint, expected=expected, got=got)
        self.expected = expected
        self.got = got


# ============================================================================
# Hardware and Runtime Errors
# ============================================================================

class DeviceNotFoundError(IonosenseError):
    """No CUDA-capable devices found."""

    def __init__(self, message: str = "No CUDA-capable devices found"):
        hint = "Ensure NVIDIA drivers are installed and a GPU is present"
        super().__init__(message, hint)


class DllLoadError(IonosenseError):
    """Failed to load required DLL/shared library."""

    def __init__(self, dll_name: str, original_error: Exception | None = None):
        message = f"Failed to load {dll_name}"
        if original_error:
            message += f": {original_error}"
        hint = "Check that CUDA toolkit is installed and on PATH"
        super().__init__(message, hint, dll_name=dll_name, original_error=original_error)
        self.dll_name = dll_name
        self.original_error = original_error


class EngineStateError(IonosenseError):
    """Engine is in an invalid state for the requested operation."""

    def __init__(self, message: str, current_state: str | None = None):
        hint = None
        if current_state == "uninitialized":
            hint = "Call initialize() or use the Processor context manager"
        elif current_state == "processing":
            hint = "Wait for current operation to complete"
        super().__init__(message, hint, current_state=current_state)
        self.current_state = current_state


class EngineRuntimeError(IonosenseError):
    """Runtime error during engine processing."""

    def __init__(self, message: str, cuda_error: str | None = None):
        hint = None
        if cuda_error:
            if "out of memory" in cuda_error.lower():
                hint = "Reduce batch size or nfft, or use a GPU with more memory"
            elif "invalid configuration" in cuda_error.lower():
                hint = "Check that nfft is a power of 2 and batch > 0"
        super().__init__(message, hint, cuda_error=cuda_error)
        self.cuda_error = cuda_error


# ============================================================================
# Research and Benchmarking Errors (NEW)
# ============================================================================

class BenchmarkError(IonosenseError):
    """Base class for benchmark-related errors."""

    def __init__(self, message: str, benchmark_name: str | None = None, **kwargs):
        super().__init__(message, benchmark_name=benchmark_name, **kwargs)
        self.benchmark_name = benchmark_name


class BenchmarkTimeoutError(BenchmarkError):
    """Benchmark iteration exceeded timeout."""

    def __init__(self, benchmark_name: str, iteration: int, timeout_s: float):
        message = f"Benchmark '{benchmark_name}' iteration {iteration} exceeded {timeout_s}s timeout"
        hint = "Consider increasing timeout or optimizing the benchmark"
        super().__init__(message, benchmark_name, iteration=iteration, timeout_s=timeout_s, hint=hint)


class BenchmarkValidationError(BenchmarkError):
    """Benchmark results failed validation."""

    def __init__(self, benchmark_name: str, reason: str, metrics: dict[str, Any] | None = None):
        message = f"Benchmark '{benchmark_name}' failed validation: {reason}"
        hint = "Check benchmark configuration and system performance"
        super().__init__(message, benchmark_name, reason=reason, metrics=metrics, hint=hint)
        self.reason = reason
        self.metrics = metrics


class ExperimentError(IonosenseError):
    """Base class for experiment-related errors."""

    def __init__(self, message: str, experiment_id: str | None = None, **kwargs):
        super().__init__(message, experiment_id=experiment_id, **kwargs)
        self.experiment_id = experiment_id


class ParameterSweepError(ExperimentError):
    """Error during parameter sweep execution."""

    def __init__(self, message: str, parameter: str | None = None, value: Any = None, **kwargs):
        hint = None
        if parameter:
            hint = f"Check parameter '{parameter}'"
            if value is not None:
                hint += f" with value {value}"
        super().__init__(message, parameter=parameter, value=value, hint=hint, **kwargs)
        self.parameter = parameter
        self.value = value


class ReproducibilityError(IonosenseError):
    """Error related to research reproducibility."""

    def __init__(self, message: str, missing_info: list[str] | None = None, **kwargs):
        hint = None
        if missing_info:
            hint = f"Missing reproducibility information: {', '.join(missing_info)}"
        super().__init__(message, hint=hint, missing_info=missing_info, **kwargs)
        self.missing_info = missing_info


class EnvironmentMismatchError(ReproducibilityError):
    """Environment doesn't match expected configuration for reproduction."""

    def __init__(self, expected: dict[str, Any], actual: dict[str, Any]):
        differences = []
        for key in expected:
            if key in actual and expected[key] != actual[key]:
                differences.append(f"{key}: expected={expected[key]}, actual={actual[key]}")

        message = "Environment mismatch detected"
        if differences:
            message += f": {'; '.join(differences[:3])}"  # Show first 3 differences
            if len(differences) > 3:
                message += f" (and {len(differences)-3} more)"

        super().__init__(message, expected=expected, actual=actual, differences=differences)
        self.expected = expected
        self.actual = actual
        self.differences = differences


class DataIntegrityError(IonosenseError):
    """Data corruption or integrity check failure."""

    def __init__(self, message: str, expected_hash: str | None = None, actual_hash: str | None = None):
        hint = "Data may be corrupted or modified"
        if expected_hash and actual_hash:
            hint += f" (hash mismatch: expected {expected_hash[:8]}..., got {actual_hash[:8]}...)"
        super().__init__(message, hint=hint, expected_hash=expected_hash, actual_hash=actual_hash)
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash


# ============================================================================
# Analysis and Reporting Errors
# ============================================================================

class AnalysisError(IonosenseError):
    """Error during result analysis."""

    def __init__(self, message: str, analysis_type: str | None = None, **kwargs):
        super().__init__(message, analysis_type=analysis_type, **kwargs)
        self.analysis_type = analysis_type


class ReportGenerationError(IonosenseError):
    """Error generating benchmark report."""

    def __init__(self, message: str, report_format: str | None = None, **kwargs):
        hint = None
        if report_format == "pdf":
            hint = "Ensure matplotlib and required fonts are installed"
        elif report_format == "html":
            hint = "Check that all template files are available"
        super().__init__(message, hint=hint, report_format=report_format, **kwargs)
        self.report_format = report_format


class InsufficientDataError(AnalysisError):
    """Not enough data for statistical analysis."""

    def __init__(self, required: int, actual: int, analysis_type: str | None = None):
        message = f"Insufficient data: need {required} samples, got {actual}"
        hint = "Increase number of iterations or check data collection"
        super().__init__(message, analysis_type=analysis_type, required=required, actual=actual, hint=hint)
        self.required = required
        self.actual = actual


# ============================================================================
# Workflow and Orchestration Errors
# ============================================================================

class WorkflowError(IonosenseError):
    """Error in research workflow execution."""

    def __init__(self, message: str, workflow_stage: str | None = None, **kwargs):
        super().__init__(message, workflow_stage=workflow_stage, **kwargs)
        self.workflow_stage = workflow_stage


class DependencyError(WorkflowError):
    """Required dependency not met."""

    def __init__(self, message: str, missing_dependencies: list[str] | None = None):
        hint = None
        if missing_dependencies:
            hint = f"Install missing dependencies: {', '.join(missing_dependencies)}"
        super().__init__(message, missing_dependencies=missing_dependencies, hint=hint)
        self.missing_dependencies = missing_dependencies


class ResourceExhaustedError(IonosenseError):
    """System resource exhausted (memory, disk, etc.)."""

    def __init__(self, resource_type: str, required: Any = None, available: Any = None):
        message = f"{resource_type} exhausted"
        if required and available:
            message += f": required {required}, available {available}"

        hint = None
        if resource_type.lower() == "gpu memory":
            hint = "Reduce batch size or nfft"
        elif resource_type.lower() == "disk space":
            hint = "Clean up old results or increase storage"

        super().__init__(message, hint=hint, resource_type=resource_type,
                        required=required, available=available)
        self.resource_type = resource_type
        self.required = required
        self.available = available
