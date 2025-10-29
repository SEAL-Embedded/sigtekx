"""
Configuration Validation Module
===============================

Validates experiment configurations for safety, compatibility, and performance.
Prevents parameter conflicts and provides helpful error messages.
"""

from pathlib import Path
from typing import Any

import yaml


class ConfigValidationError(ValueError):
    """Raised when configuration validation fails."""
    pass


class ConfigValidator:
    """Validates experiment configurations and parameters."""

    def __init__(self):
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def validate_experiment_config(self, config_path: str) -> tuple[bool, list[str], list[str]]:
        """
        Validate a complete experiment configuration.

        Returns:
            (is_valid, warnings, errors)
        """
        self.warnings.clear()
        self.errors.clear()

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
        except Exception as e:
            self.errors.append(f"Cannot load config file: {e}")
            return False, self.warnings, self.errors

        # Validate different sections
        self._validate_engine_params(config.get('engine', {}))
        self._validate_experiment_params(config.get('experiment', {}))
        self._validate_hydra_params(config.get('hydra', {}))
        self._validate_resource_requirements(config)

        return len(self.errors) == 0, self.warnings, self.errors

    def validate_engine_params(self, nfft: int, batch: int, overlap: float,
                             sample_rate_hz: int = 48000) -> tuple[bool, list[str], list[str]]:
        """
        Validate engine parameters for compatibility and performance.

        Returns:
            (is_valid, warnings, errors)
        """
        self.warnings.clear()
        self.errors.clear()

        # Basic range validation
        if nfft < 128 or nfft > 65536:
            self.errors.append(f"NFFT {nfft} outside valid range [128, 65536]")

        if batch < 1 or batch > 256:
            self.errors.append(f"Batch size {batch} outside valid range [1, 256]")

        if overlap < 0.0 or overlap >= 1.0:
            self.errors.append(f"Overlap {overlap} outside valid range [0.0, 1.0)")

        # Check if NFFT is power of 2 (required for FFT efficiency)
        if nfft & (nfft - 1) != 0:
            self.errors.append(f"NFFT {nfft} is not a power of 2 (required for FFT efficiency)")

        # Memory estimation and warnings
        estimated_memory_mb = self._estimate_memory_usage(nfft, batch)
        if estimated_memory_mb > 8000:  # 8GB
            self.errors.append(f"Estimated memory usage {estimated_memory_mb:.0f}MB exceeds 8GB limit")
        elif estimated_memory_mb > 4000:  # 4GB
            self.warnings.append(f"High memory usage estimated: {estimated_memory_mb:.0f}MB")

        # Performance warnings
        if nfft > 16384:
            self.warnings.append(f"Large NFFT {nfft} may impact real-time performance")

        if batch > 64:
            self.warnings.append(f"Large batch size {batch} may increase latency")

        if overlap > 0.9:
            self.warnings.append(f"Very high overlap {overlap} increases computational load")

        # Compatibility checks
        if nfft >= 8192 and batch >= 32:
            self.warnings.append("Large NFFT + large batch may exceed GPU memory")

        # Real-time feasibility
        samples_per_frame = int(nfft * (1.0 - overlap))
        frame_duration_ms = (samples_per_frame / sample_rate_hz) * 1000
        if frame_duration_ms < 1.0:
            self.warnings.append(f"Very short frame duration {frame_duration_ms:.1f}ms may be challenging for real-time")

        return len(self.errors) == 0, self.warnings, self.errors

    def _validate_engine_params(self, engine_config: dict[str, Any]):
        """Validate engine parameters from config dict."""
        if not engine_config:
            return

        nfft = engine_config.get('nfft', 2048)
        batch = engine_config.get('batch', 8)
        overlap = engine_config.get('overlap', 0.5)
        sample_rate = engine_config.get('sample_rate_hz', 48000)

        is_valid, warnings, errors = self.validate_engine_params(nfft, batch, overlap, sample_rate)
        self.warnings.extend(warnings)
        self.errors.extend(errors)

    def _validate_experiment_params(self, experiment_config: dict[str, Any]):
        """Validate experiment-specific parameters."""
        if not experiment_config:
            self.errors.append("Missing experiment configuration")
            return

        if 'name' not in experiment_config:
            self.errors.append("Experiment must have a name")

        if 'description' not in experiment_config:
            self.warnings.append("Experiment missing description")

    def _validate_hydra_params(self, hydra_config: dict[str, Any]):
        """Validate Hydra multirun parameters."""
        if not hydra_config:
            return

        sweeper = hydra_config.get('sweeper', {})
        params = sweeper.get('params', {})

        if hydra_config.get('mode') == 'MULTIRUN' and not params:
            self.warnings.append("MULTIRUN mode specified but no sweep parameters defined")

        # Check for parameter explosion
        total_combinations = 1
        for _param_name, param_values in params.items():
            if isinstance(param_values, str):
                values = param_values.split(',')
                total_combinations *= len(values)

        if total_combinations > 100:
            self.warnings.append(f"Large parameter sweep: {total_combinations} combinations")
        elif total_combinations > 500:
            self.errors.append(f"Excessive parameter sweep: {total_combinations} combinations (>500)")

    def _validate_resource_requirements(self, config: dict[str, Any]):
        """Validate resource requirements and compatibility."""
        # Check if ionosphere-specific configs have realistic parameters
        experiment = config.get('experiment', {})
        if 'ionosphere' in experiment.get('name', ''):
            engine = config.get('engine', {})
            nfft = engine.get('nfft', 2048)

            if nfft < 1024:
                self.warnings.append("NFFT < 1024 may have insufficient frequency resolution for ionosphere analysis")

    def _estimate_memory_usage(self, nfft: int, batch: int) -> float:
        """Estimate GPU memory usage in MB."""
        # Rough estimation based on typical FFT memory requirements
        # Complex data (8 bytes per sample) + intermediate buffers
        samples_per_batch = nfft * batch
        input_buffer_mb = (samples_per_batch * 8) / (1024 * 1024)  # Complex float32
        fft_workspace_mb = input_buffer_mb * 2  # FFT workspace
        output_buffer_mb = input_buffer_mb  # Output buffer
        overhead_mb = 100  # CUDA overhead

        total_mb = input_buffer_mb + fft_workspace_mb + output_buffer_mb + overhead_mb
        return total_mb


def validate_config_file(config_path: str) -> bool:
    """
    Validate a configuration file and print results.

    Returns:
        True if valid, False if errors found
    """
    validator = ConfigValidator()
    is_valid, warnings, errors = validator.validate_experiment_config(config_path)

    if warnings:
        print("WARNING: Configuration warnings:")
        for warning in warnings:
            print(f"   * {warning}")
        print()

    if errors:
        print("ERROR: Configuration errors:")
        for error in errors:
            print(f"   * {error}")
        print()
        return False

    if not warnings and not errors:
        print("OK: Configuration is valid")

    return True


def validate_engine_parameters(nfft: int, batch: int, overlap: float) -> bool:
    """
    Validate engine parameters and print results.

    Returns:
        True if valid, False if errors found
    """
    validator = ConfigValidator()
    is_valid, warnings, errors = validator.validate_engine_params(nfft, batch, overlap)

    if warnings:
        print("WARNING: Parameter warnings:")
        for warning in warnings:
            print(f"   * {warning}")

    if errors:
        print("ERROR: Parameter errors:")
        for error in errors:
            print(f"   * {error}")
        return False

    return True


if __name__ == '__main__':
    import sys

    if len(sys.argv) != 2:
        print("Usage: python validation.py <config_file.yaml>")
        sys.exit(1)

    config_file = sys.argv[1]
    if not Path(config_file).exists():
        print(f"❌ Config file not found: {config_file}")
        sys.exit(1)

    is_valid = validate_config_file(config_file)
    sys.exit(0 if is_valid else 1)
