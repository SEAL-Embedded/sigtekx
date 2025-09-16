# Numerical Accuracy Debugging Plan for Ionosense-HPC

## Executive Summary
The accuracy benchmark shows a 33% pass rate (1/3 tests passing), indicating systematic numerical discrepancies between the GPU implementation and scipy reference. This plan provides a structured approach to identify and resolve these issues.

## Most Likely Root Causes (Prioritized)

### 1. **Window Function Mismatch** (HIGHEST PROBABILITY)
- **Issue**: Hann window implementation differs between GPU and scipy
- **Evidence**: Edge values should be near zero but may have different normalization
- **Key Detail**: scipy uses `sym=False` for periodic signals, GPU may use symmetric

### 2. **FFT Scaling/Normalization Discrepancy**
- **Issue**: cuFFT and scipy.fft have different default normalizations
- **Evidence**: Magnitude differences by constant factors
- **Key Detail**: cuFFT doesn't normalize by default, scipy may apply 1/N

### 3. **Complex-to-Magnitude Conversion**
- **Issue**: Incorrect magnitude calculation from complex FFT output
- **Evidence**: Non-linear errors in magnitude spectrum
- **Key Detail**: GPU uses `sqrt(real² + imag²)`, ensure no precision loss

### 4. **Data Layout/Stride Issues**
- **Issue**: Misaligned data between stages
- **Evidence**: Completely wrong frequency content
- **Key Detail**: R2C FFT output is N/2+1 complex values, not N

### 5. **Float32 vs Float64 Precision**
- **Issue**: Reference uses float64, GPU uses float32
- **Evidence**: Small systematic errors accumulating
- **Key Detail**: Can cause ~1e-6 relative errors

## Critical Files to Debug

### C++ Implementation Files
```
cpp/src/ops_fft.cu                  # CUDA kernels - window, magnitude
cpp/src/processing_stage.cpp        # Stage implementations
cpp/src/research_engine.cpp         # Pipeline orchestration
cpp/include/ionosense/cuda_wrappers.hpp  # cuFFT plan configuration
```

### Python Validation Files
```
python/src/ionosense_hpc/benchmarks/accuracy.py  # Main accuracy benchmark
python/src/ionosense_hpc/utils/signals.py        # Gold standard signal generation
python/src/ionosense_hpc/testing/validators.py   # Validation helpers
python/src/ionosense_hpc/core/engine.py         # Python-C++ interface
```

## VSCode Debug Configuration

Add to `.vscode/launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Debug Accuracy Benchmark",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/python/src/ionosense_hpc/benchmarks/accuracy.py",
            "args": ["--tolerance", "1e-5", "--output", "debug_results.json"],
            "console": "integratedTerminal",
            "env": {
                "PYTHONPATH": "${workspaceFolder}/python/src",
                "IONO_LOG_LEVEL": "DEBUG",
                "CUDA_LAUNCH_BLOCKING": "1",  // Synchronous CUDA for better debugging
                "CUDA_VISIBLE_DEVICES": "0"
            },
            "justMyCode": false,
            "cwd": "${workspaceFolder}"
        },
        {
            "name": "Debug C++ Tests",
            "type": "cppdbg",
            "request": "launch",
            "program": "${workspaceFolder}/build/Debug/test_processing_stage",
            "args": ["--gtest_filter=*Window*"],
            "stopAtEntry": false,
            "cwd": "${workspaceFolder}",
            "environment": [
                {"name": "CUDA_LAUNCH_BLOCKING", "value": "1"}
            ],
            "externalConsole": false,
            "MIMode": "gdb",
            "setupCommands": [
                {
                    "description": "Enable pretty-printing for gdb",
                    "text": "-enable-pretty-printing",
                    "ignoreFailures": true
                }
            ],
            "preLaunchTask": "build-debug",
            "miDebuggerPath": "/usr/bin/gdb",
            "linux": {
                "MIMode": "gdb"
            },
            "windows": {
                "program": "${workspaceFolder}/build/Debug/test_processing_stage.exe",
                "miDebuggerPath": "C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/Common7/IDE/CommonExtensions/Microsoft/MIEngine/gdb.exe"
            }
        }
    ]
}
```

## Data Flow Through Pipeline (Key Insights)

### 1. **Input Stage**
- Python generates test signal (float32, shape: [batch*nfft])
- Data copied to pinned host memory
- H2D transfer to device buffer

### 2. **Window Stage** (ops_fft.cu)
```cuda
// Key: Window is pre-uploaded to GPU
apply_window_kernel<<<blocks, threads>>>(input, output, d_window, nfft, batch, stride);
// Each sample multiplied by window coefficient
output[idx] = input[idx] * window[sample_idx];
```

### 3. **FFT Stage** (cuFFT)
According to [NVIDIA cuFFT documentation](https://docs.nvidia.com/cuda/cufft/index.html#function-cufftexecr2c):
- **R2C Transform**: Real input of size N → Complex output of size N/2+1
- **No automatic normalization**: Output is scaled by N compared to mathematical DFT
- **Layout**: Packed complex format (float2)
- **Batch processing**: Multiple transforms in single call

```cpp
// From processing_stage.cpp
plan_.create_plan_many(
    1,                    // rank (1D)
    n,                    // dimensions [nfft]
    nullptr,              // inembed
    1,                    // istride
    config.nfft,          // idist (distance between batches)
    nullptr,              // onembed
    1,                    // ostride  
    config.nfft/2 + 1,    // odist (R2C output distance)
    CUFFT_R2C,           // type
    config.batch,         // number of transforms
    stream
);
```

### 4. **Magnitude Stage** (ops_fft.cu)
```cuda
// magnitude_kernel computes sqrt(real² + imag²) * scale
output[idx] = sqrtf(complex.x * complex.x + complex.y * complex.y) * scale;
// Scale factor depends on StageConfig::ScalePolicy
```

### 5. **Reference Implementation** (accuracy.py)
```python
# scipy reference path
window = scipy.signal.windows.hann(nfft, sym=False)
data_windowed = data * window
fft_result = scipy.fft.rfft(data_windowed, axis=1)
magnitude = np.abs(fft_result) / nfft  # Normalized by N
```

## Debugging Steps (Sequential)

### Step 1: Verify Window Function
```python
# In accuracy.py, add window comparison
def _test_window_consistency(self):
    # Generate GPU window (extract from pipeline)
    gpu_window = self._get_gpu_window()  # Need to implement
    
    # Generate scipy reference
    scipy_window = scipy.signal.windows.hann(self.engine_config.nfft, sym=False)
    
    # Compare
    np.testing.assert_allclose(gpu_window, scipy_window, rtol=1e-6)
```

### Step 2: Check FFT Normalization
```python
# Test with DC signal (all ones)
test_signal = np.ones(nfft, dtype=np.float32)
# Expected: DC bin = sum(window) without normalization
# With 1/N normalization: DC bin = sum(window)/N
```

### Step 3: Validate Complex-to-Magnitude
```cpp
// In test_processing_stage.cpp, add direct magnitude test
TEST_F(ProcessingStageTest, MagnitudeStageKnownInput) {
    // Test with (3,4) → magnitude should be 5
    // Test with (1,0) → magnitude should be 1
    // Verify scaling policy application
}
```

### Step 4: Compare Precision
```python
# Force scipy to use float32
def _compute_reference_fft(self, data):
    if not self.config.use_double_precision_reference:
        data = data.astype(np.float32)
        # All operations in float32
```

## Test Signal Priority (Use scipy generators)

From `ionosense_hpc/utils/signals.py` (GOLD STANDARD):
1. **DC Signal**: `np.ones()` - Tests normalization
2. **Single Sine**: `make_sine()` - Tests frequency accuracy
3. **Impulse**: `signal[0] = 1.0` - Tests all frequencies equally
4. **Nyquist**: `np.cos(np.pi * np.arange(nfft))` - Tests edge cases

**DO NOT USE** `ionosense_hpc/utils/benchmark_utils.py` generators for truth.

## Key cuFFT Details

From [NVIDIA cuFFT Guide](https://docs.nvidia.com/cuda/cufft/index.html):

1. **Transform Scaling**:
   - Forward FFT: No scaling (output scaled by N)
   - Inverse FFT: No scaling (output scaled by N)
   - User must apply 1/N for normalized DFT

2. **R2C Output Format**:
   - Input: N real values
   - Output: N/2+1 complex values
   - DC component (index 0): Always real
   - Nyquist (index N/2 if N even): Always real

3. **Memory Layout**:
   - Complex values stored as `cufftComplex` (equivalent to float2)
   - Interleaved format: `[real0, imag0, real1, imag1, ...]`

## Validation Criteria Adjustment

```python
# In accuracy.py, consider adjusting tolerances
self.config.relative_tolerance = 1e-4  # Relaxed for float32
self.config.absolute_tolerance = 1e-5
self.config.snr_threshold_db = 50.0    # Account for float32 noise floor
```

## Expected Resolution

After following this plan:
1. **Window mismatch**: Ensure `sym=False` matches between implementations
2. **Scaling**: Apply consistent 1/N normalization
3. **Precision**: Use float32 throughout or account for precision differences
4. **Pass rate**: Should achieve >95% with proper tolerances

## Quick Validation Script

```python
# quick_validate.py
import numpy as np
from scipy import signal
from ionosense_hpc import Engine
from ionosense_hpc.config import Presets

config = Presets.validation()
engine = Engine(config)


# Test DC signal
test = np.ones(config.nfft * config.batch, dtype=np.float32)
gpu_out = engine.process(test)

# Reference
window = signal.windows.hann(config.nfft, sym=False)
ref_windowed = test.reshape(config.batch, config.nfft) * window
ref_fft = np.fft.rfft(ref_windowed, axis=1)
ref_mag = np.abs(ref_fft) / config.nfft

print(f"GPU DC: {gpu_out[0,0]:.6f}")
print(f"Ref DC: {ref_mag[0,0]:.6f}")
print(f"Error: {abs(gpu_out[0,0] - ref_mag[0,0]):.2e}")
```

## Documentation References

- [cuFFT User Guide](https://docs.nvidia.com/cuda/cufft/index.html)
- [cuFFT API Reference](https://docs.nvidia.com/cuda/cufft/index.html#cufft-api-reference)
- [SciPy FFT Documentation](https://docs.scipy.org/doc/scipy/reference/fft.html)
- [SciPy Window Functions](https://docs.scipy.org/doc/scipy/reference/signal.windows.html)
- [NumPy FFT Normalization](https://numpy.org/doc/stable/reference/routines.fft.html#normalization)