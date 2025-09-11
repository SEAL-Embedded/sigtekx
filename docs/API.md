# API Reference

Complete API reference for the ionosense-hpc Python package, with CLI integration examples.

## Getting Started

Before using the Python API, ensure your environment is properly set up using the CLI:

**Linux/WSL2:**
```bash
./scripts/cli.sh setup          # Setup environment
./scripts/cli.sh build          # Build C++ extensions
./scripts/cli.sh test           # Verify installation
```

**Windows:**
```powershell
.\scripts\open_dev_pwsh.ps1     # Start development shell
iono setup                      # Setup environment  
ib                             # Build C++ extensions
it                             # Verify installation
```

## Core Module

### Processor

High-level interface for signal processing with automatic resource management.

```python
class Processor(config: EngineConfig | str | None = None, auto_init: bool = True)
```

**Parameters:**
- `config`: Engine configuration object, preset name ('realtime', 'throughput', 'validation'), or None
- `auto_init`: If True, automatically initialize on creation

**Methods:**

#### `initialize(config: EngineConfig | None = None) -> None`
Initialize the processor with configuration.

#### `process(input_data: np.ndarray | list, return_complex: bool = False) -> np.ndarray`
Process a single frame of input data.

**Parameters:**
- `input_data`: Input signal data (1D array of size nfft * batch)
- `return_complex`: If True, return complex FFT output (not yet implemented)

**Returns:**
- 2D array of magnitude spectra [batch, bins]

#### `process_stream(data_generator, max_frames: int | None = None) -> list[np.ndarray]`
Process a stream of data from a generator.

#### `benchmark(n_iterations: int = 100, input_data: np.ndarray | None = None) -> dict`
Run performance benchmark.

#### `reset() -> None`
Reset the processor, freeing GPU resources.

#### `get_stats() -> dict`
Get performance statistics.

**Properties:**
- `is_initialized`: Whether processor is initialized
- `config`: Current configuration
- `history`: Processing history

**Example:**
```python
from ionosense_hpc import Processor, Presets

# Using context manager (recommended)
with Processor(Presets.realtime()) as proc:
    output = proc.process(input_data)
    
# Manual initialization
proc = Processor(auto_init=False)
proc.initialize(Presets.throughput())
output = proc.process(input_data)
proc.reset()
```

**CLI Integration:**
```bash
# Verify processor functionality via CLI
./scripts/cli.sh validate       # Linux/WSL2
ival                           # Windows (dev shell)

# Performance benchmarking
./scripts/cli.sh bench latency  # Linux/WSL2
ibench latency                 # Windows (dev shell)
```

### Engine

Mid-level wrapper providing validation and buffer management.

```python
class Engine(config: EngineConfig | None = None)
```

**Methods:**

#### `initialize(config: EngineConfig) -> None`
Initialize the engine with configuration.

#### `process(input_data: np.ndarray, output: np.ndarray | None = None) -> np.ndarray`
Process input data with validation.

#### `process_frames(input_data: np.ndarray, hop_size: int | None = None) -> np.ndarray`
Process multiple overlapping frames.

**Returns:**
- 3D array [frames, batch, bins]

#### `synchronize() -> None`
Synchronize all CUDA streams.

### RawEngine

Low-level wrapper around C++ implementation.

```python
class RawEngine()
```

**Class Methods:**

#### `get_available_devices() -> list[str]`
Get list of available CUDA devices.

#### `select_best_device() -> int`
Select the best available CUDA device.

**CLI Integration:**
```bash
# Check available devices
./scripts/cli.sh info devices   # Linux/WSL2
iono info devices              # Windows (dev shell)
```

## Configuration Module

### EngineConfig

Pydantic model for engine configuration with validation.

```python
@dataclass
class EngineConfig:
    nfft: int = 1024              # FFT size (power of 2)
    batch: int = 2                # Number of parallel channels
    overlap: float = 0.5          # Frame overlap [0, 1)
    sample_rate_hz: int = 48000   # Sample rate
    stream_count: int = 3         # CUDA streams
    pinned_buffer_count: int = 2  # Pinned memory buffers
    warmup_iters: int = 1         # Warmup iterations
    timeout_ms: int = 1000        # Operation timeout
    use_cuda_graphs: bool = False # CUDA graphs (future)
    enable_profiling: bool = False # Enable profiling
```

**Computed Properties:**
- `hop_size`: Samples between frames
- `num_output_bins`: FFT output bins (nfft/2 + 1)
- `frame_duration_ms`: Frame duration in milliseconds
- `hop_duration_ms`: Hop duration in milliseconds
- `effective_fps`: Effective frames per second
- `memory_estimate_mb`: Estimated GPU memory usage

### Presets

Pre-configured settings for common use cases.

```python
class Presets:
    @staticmethod
    def realtime() -> EngineConfig       # Low-latency processing
    
    @staticmethod
    def throughput() -> EngineConfig     # High-throughput batch
    
    @staticmethod
    def validation() -> EngineConfig     # Testing and validation
    
    @staticmethod
    def profiling() -> EngineConfig      # Performance profiling
    
    @staticmethod
    def custom(**kwargs) -> EngineConfig # Custom configuration
```

**CLI Integration:**
```bash
# View available presets
./scripts/cli.sh info presets   # Linux/WSL2
iono info presets              # Windows (dev shell)
```

## Benchmarking Module

The benchmarking module integrates seamlessly with the CLI platform for comprehensive performance evaluation.

### BaseBenchmark

Abstract base class for all benchmarks.

```python
class BaseBenchmark(config: BenchmarkConfig | dict | None = None)
```

**Abstract Methods (must implement):**
- `setup()`: Initialize resources
- `execute_iteration()`: Run single iteration
- `teardown()`: Clean up resources

**Methods:**
- `run() -> BenchmarkResult`: Execute benchmark
- `validate_environment() -> tuple[bool, list[str]]`: Validate environment

**CLI Integration:**
```bash
# Run individual benchmarks
./scripts/cli.sh bench latency        # Linux/WSL2
ibench latency                       # Windows (dev shell)

# Custom benchmarks can be added and run via CLI
./scripts/cli.sh bench custom_benchmark
```

### BenchmarkConfig

Configuration for benchmark execution.

```python
@dataclass
class BenchmarkConfig:
    name: str                        # Benchmark name
    iterations: int = 1000           # Number of iterations
    warmup_iterations: int = 0       # Warmup iterations
    timeout_seconds: float = 300.0   # Timeout per iteration
    confidence_level: float = 0.95   # Confidence level
    outlier_threshold: float = 3.0   # Z-score threshold
    min_samples: int = 30            # Min samples for statistics
    engine_config: dict = {}         # Engine configuration
    seed: int = 42                   # Random seed
    deterministic: bool = True       # Deterministic mode
    save_raw_data: bool = True       # Save measurements
    output_format: str = "json"      # Output format
    verbose: bool = True             # Verbose output
```

### BenchmarkResult

Result container for benchmarks.

```python
@dataclass
class BenchmarkResult:
    name: str                    # Benchmark name
    config: dict                 # Configuration used
    context: BenchmarkContext    # Environment context
    measurements: np.ndarray     # Raw measurements
    statistics: dict = {}        # Computed statistics
    metadata: dict = {}          # Additional metadata
    passed: bool = True          # Pass/fail status
    errors: list = []           # Error messages
```

### BenchmarkSuite

Orchestrates multiple benchmarks.

```python
class BenchmarkSuite(config: SuiteConfig | dict | str | None = None)
```

**Methods:**
- `run() -> dict`: Execute all benchmarks
- `analyze_results(result: BenchmarkResult) -> dict`: Analyze results

**CLI Integration:**
```bash
# Run complete benchmark suite
./scripts/cli.sh bench suite          # Linux/WSL2
ibench suite                         # Windows (dev shell)

# Run suite with custom configuration
./scripts/cli.sh bench suite --config research.yaml
ibench suite --config research.yaml
```

### ParameterSweep

Manages parameter sweep experiments.

```python
class ParameterSweep(config: ExperimentConfig | dict | str)
```

**Methods:**
- `generate_parameter_grid() -> Generator[dict]`: Generate parameter combinations
- `run() -> list[ExperimentRun]`: Execute sweep
- `run_single(parameters: dict, run_id: str) -> ExperimentRun`: Run single configuration

**CLI Integration:**
```bash
# Run parameter sweeps
./scripts/cli.sh sweep experiment.yaml     # Linux/WSL2
iono sweep experiment.yaml                # Windows (dev shell)

# Parallel sweeps
./scripts/cli.sh sweep experiment.yaml --parallel --workers 4
iono sweep experiment.yaml --parallel --workers 4
```

## Utility Functions

### Signal Generation

```python
def make_sine(
    frequency: float,
    duration: float,
    sample_rate: int = 48000,
    amplitude: float = 1.0,
    phase: float = 0.0,
    dtype: np.dtype = np.float32
) -> np.ndarray
```

Generate sine wave signal.

```python
def make_chirp(
    f_start: float,
    f_end: float,
    duration: float,
    sample_rate: int = 48000,
    method: str = "linear",
    amplitude: float = 1.0,
    dtype: np.dtype = np.float32
) -> np.ndarray
```

Generate frequency sweep signal.

```python
def make_noise(
    duration: float,
    sample_rate: int = 48000,
    noise_type: str = "white",  # "white", "pink", "brown"
    amplitude: float = 1.0,
    seed: int | None = None,
    dtype: np.dtype = np.float32
) -> np.ndarray
```

Generate noise signal.

```python
def make_multitone(
    frequencies: list[float],
    duration: float,
    sample_rate: int = 48000,
    amplitudes: list[float] | None = None,
    phases: list[float] | None = None,
    dtype: np.dtype = np.float32
) -> np.ndarray
```

Generate multi-tone signal.

```python
def make_test_batch(
    nfft: int,
    batch: int,
    signal_type: str = "sine",
    sample_rate: int = 48000,
    seed: int | None = None,
    **kwargs
) -> np.ndarray
```

Generate batch of test signals.

### Device Management

```python
def gpu_count() -> int
```
Get number of available CUDA devices.

```python
def current_device() -> int
```
Get current CUDA device ID.

```python
def device_info(device_id: int | None = None) -> dict
```
Get detailed device information.

```python
def get_memory_usage() -> tuple[int, int]
```
Get GPU memory usage (used_mb, total_mb).

```python
def monitor_device(device_id: int | None = None) -> str
```
Get formatted device status string.

**CLI Integration:**
```bash
# Monitor GPU in real-time
./scripts/cli.sh monitor         # Linux/WSL2
imon                           # Windows (dev shell)

# Get device information
./scripts/cli.sh info devices   # Linux/WSL2  
iono info devices              # Windows (dev shell)
```

### Profiling

```python
@contextmanager
def nvtx_range(
    name: str,
    color: str | ProfileColor = ProfileColor.NVIDIA_BLUE,
    domain: str | ProfilingDomain = ProfilingDomain.CORE,
    category: str | ProfileCategory | None = None,
    payload: Any | None = None
)
```
Create NVTX range for profiling.

```python
def nvtx_decorate(
    message: str | None = None,
    color: str | ProfileColor = ProfileColor.NVIDIA_BLUE,
    domain: str | ProfilingDomain = ProfilingDomain.CORE,
    category: str | ProfileCategory | None = None,
    include_args: bool = False
) -> Callable
```
Decorator for automatic NVTX profiling.

**CLI Integration:**
```bash
# Profile with Nsight Systems
./scripts/cli.sh profile nsys benchmark    # Linux/WSL2
iprof nsys benchmark                      # Windows (dev shell)

# Profile with Nsight Compute
./scripts/cli.sh profile ncu benchmark     # Linux/WSL2
iprof ncu benchmark                       # Windows (dev shell)
```

### Statistics

```python
def calculate_statistics(
    data: np.ndarray,
    config: BenchmarkConfig | None = None
) -> dict[str, Any]
```
Calculate comprehensive statistics with outlier detection.

**Returns dictionary with:**
- Basic: n, mean, std, min, max, median
- Percentiles: p1, p5, p25, p50, p75, p90, p95, p99
- Confidence intervals: ci_lower, ci_upper, ci_margin
- Derived: cv (coefficient of variation), iqr, range

## Exceptions

### Exception Hierarchy

```python
IonosenseError                    # Base exception
├── ConfigError                   # Configuration errors
├── ValidationError               # Input validation errors
├── DeviceNotFoundError          # No CUDA devices
├── DllLoadError                 # Failed to load library
├── EngineStateError             # Invalid engine state
├── EngineRuntimeError           # Runtime processing error
├── BenchmarkError               # Benchmark base error
│   ├── BenchmarkTimeoutError    # Iteration timeout
│   └── BenchmarkValidationError # Results validation failed
├── ExperimentError              # Experiment base error
│   └── ParameterSweepError      # Parameter sweep error
├── ReproducibilityError         # Reproducibility issues
├── DataIntegrityError           # Data corruption
├── AnalysisError                # Analysis errors
├── ReportGenerationError        # Report generation failed
└── WorkflowError                # Workflow execution error
```

### Common Exception Patterns

```python
from ionosense_hpc.exceptions import *

# Configuration validation
try:
    config = EngineConfig(nfft=1000)  # Not power of 2
except ConfigError as e:
    print(f"Config error: {e}")
    print(f"Hint: {e.hint}")

# Engine state management
try:
    engine.process(data)
except EngineStateError as e:
    if e.current_state == "uninitialized":
        engine.initialize()

# Resource errors
try:
    processor = Processor(config)
except DeviceNotFoundError:
    print("No GPU available, using CPU fallback")
    
# Benchmark validation
try:
    result = benchmark.run()
    if not result.passed:
        raise BenchmarkValidationError(
            benchmark_name=result.name,
            reason="Accuracy below threshold",
            metrics=result.statistics
        )
except BenchmarkValidationError as e:
    print(f"Benchmark failed: {e.reason}")
    print(f"Metrics: {e.metrics}")
```

**CLI Integration:**
```bash
# Diagnose errors with CLI
./scripts/cli.sh doctor           # Environment diagnosis
./scripts/cli.sh validate         # Numerical validation
./scripts/cli.sh test             # Comprehensive testing

# Windows (dev shell)
iono doctor                       # Environment diagnosis
ival                             # Numerical validation (iono validate)
it                               # Comprehensive testing (iono test)
```

## Testing Utilities

### Validators

```python
from ionosense_hpc.testing.validators import *

# Numerical comparison
assert_allclose(actual, expected, rtol=1e-5, atol=1e-8)

# Spectral analysis
assert_spectral_peak(spectrum, expected_freq, sample_rate, nfft, tolerance_hz=10)

# Energy conservation
assert_parseval(time_signal, freq_spectrum, tolerance=1e-12)

# Signal quality
snr = assert_snr(signal, noise, min_snr_db=60)

# FFT properties
is_valid = validate_fft_symmetry(complex_spectrum)

# Harmonic distortion
thd = calculate_thd(spectrum, fundamental_idx, num_harmonics=5)

# Stability
is_stable = check_numerical_stability(outputs, max_variance=1e-12)
```

### Test Fixtures

```python
import pytest
from ionosense_hpc.testing.fixtures import *

def test_processor(test_processor):
    """test_processor fixture provides initialized Processor."""
    assert test_processor.is_initialized

def test_with_config(validation_config):
    """validation_config provides small test configuration."""
    assert validation_config.nfft == 256

def test_signals(test_sine_data, test_batch_data):
    """Signal generation fixtures."""
    assert test_sine_data.dtype == np.float32
```

**CLI Integration:**
```bash
# Run tests with fixtures
./scripts/cli.sh test py          # Linux/WSL2
itp                              # Windows (dev shell)

# Run with coverage to see fixture usage
./scripts/cli.sh test --coverage  # Linux/WSL2
iono test --coverage             # Windows (dev shell)
```

## Type Hints

The package uses comprehensive type hints for better IDE support:

```python
from typing import Any, Callable, Generator
import numpy as np
from numpy.typing import NDArray

# Type aliases used in the package
ArrayLike = np.ndarray | list | tuple
ConfigLike = EngineConfig | dict | str | None
PathLike = str | Path

# Example function signatures
def process(
    data: ArrayLike,
    config: ConfigLike = None,
    validate: bool = True
) -> NDArray[np.float32]: ...

def benchmark(
    iterations: int,
    callback: Callable[[int], None] | None = None
) -> dict[str, Any]: ...
```

**CLI Integration:**
```bash
# Type checking via CLI
./scripts/cli.sh typecheck        # Linux/WSL2
iono typecheck                   # Windows (dev shell)

# Include tests in type checking
./scripts/cli.sh typecheck --include-tests
iono typecheck --include-tests
```

## Environment Variables

Control package behavior via environment variables:

```bash
# Logging level
export IONO_LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR

# CUDA settings
export CUDA_VISIBLE_DEVICES=0  # Select GPU
export CUDA_LAUNCH_BLOCKING=1  # Synchronous execution (debugging)

# Profiling
export NVTX_ENABLE=1  # Enable NVTX markers

# Paths
export IONOSENSE_DATA_DIR=/path/to/data
export IONOSENSE_CACHE_DIR=/path/to/cache
```

**CLI Integration:**
```bash
# Set debug logging and run
export IONO_LOG_LEVEL=DEBUG      # Linux/WSL2
./scripts/cli.sh test

# Windows (dev shell)
$env:IONO_LOG_LEVEL="DEBUG"
it
```

## Thread Safety

- **Processor**: NOT thread-safe, use one instance per thread
- **Engine**: NOT thread-safe
- **RawEngine**: NOT thread-safe
- **Configuration objects**: Immutable after creation, safe to share
- **Benchmark classes**: NOT thread-safe, create new instances

For multi-threaded usage:

```python
import threading
from ionosense_hpc import Processor, Presets

def worker(thread_id):
    # Each thread gets its own processor
    proc = Processor(Presets.realtime())
    # ... do work ...
    proc.reset()

threads = []
for i in range(4):
    t = threading.Thread(target=worker, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()
```

## CLI Development Integration

### API Development Workflow

When developing with the API, use the CLI for environment management and validation:

**Linux/WSL2:**
```bash
# Setup development environment
./scripts/cli.sh setup

# During development
./scripts/cli.sh build          # Rebuild C++ extensions
./scripts/cli.sh test py        # Test Python changes
./scripts/cli.sh validate       # Validate numerical correctness

# Performance testing
./scripts/cli.sh bench latency  # Quick performance check
./scripts/cli.sh profile nsys custom_code  # Profile new code
```

**Windows (Development Shell):**
```powershell
# Start enhanced development shell
.\scripts\open_dev_pwsh.ps1

# Setup development environment
iono setup

# During development
ib                             # Rebuild C++ extensions (iono build)
itp                            # Test Python changes (iono test py)
ival                           # Validate numerical correctness

# Performance testing
ibench latency                 # Quick performance check
iprof nsys custom_code         # Profile new code
```

### API Documentation Generation

The CLI can help verify API examples work correctly:

```bash
# Test all examples in documentation
./scripts/cli.sh test --pattern "test_examples"  # Linux/WSL2
iono test --pattern "test_examples"              # Windows (dev shell)

# Validate API examples
./scripts/cli.sh validate                        # Linux/WSL2
ival                                            # Windows (dev shell)
```

### Debugging API Issues

```bash
# Comprehensive environment check
./scripts/cli.sh doctor --verbose               # Linux/WSL2
iono doctor --verbose                          # Windows (dev shell)

# Check GPU status
./scripts/cli.sh info devices                  # Linux/WSL2
iono info devices                              # Windows (dev shell)

# Monitor GPU during API usage
./scripts/cli.sh monitor                       # Linux/WSL2
imon                                          # Windows (dev shell)
```

### Performance Validation

```bash
# Quick performance validation
./scripts/cli.sh bench latency                 # Linux/WSL2
ibench latency                                # Windows (dev shell)

# Comprehensive benchmarking
./scripts/cli.sh bench suite                   # Linux/WSL2
ibench suite                                  # Windows (dev shell)

# Custom performance tests
./scripts/cli.sh profile nsys my_benchmark     # Linux/WSL2
iprof nsys my_benchmark                       # Windows (dev shell)
```

This API reference provides comprehensive coverage of all ionosense-hpc functionality with integrated CLI workflows for development, testing, and validation. The CLI platform ensures consistent environment management and reproducible results across all API usage scenarios.