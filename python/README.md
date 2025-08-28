# Ionosense-HPC Python API

Python interface for high-performance dual-channel FFT processing on CUDA.

## Installation

### From Source

```bash
# Ensure C++ module is built first
cd ionosense-hpc-lib
./scripts/cli.sh build

# Install Python package in development mode
cd python
pip install -e .
```

### From Wheel (Future)

```bash
pip install ionosense-hpc-0.0.1-cp311-linux_x86_64.whl
```

## Core API

### Basic Processing

```python
from ionosense_hpc import FFTProcessor

# Initialize processor
processor = FFTProcessor(
    fft_size=4096,    # FFT length (power of 2)
    batch_size=32,    # Number of FFTs per batch (must be even)
    use_graphs=True   # Enable CUDA Graphs optimization
)

# Process data
import numpy as np
ch1 = np.random.randn(4096).astype(np.float32)
ch2 = np.random.randn(4096).astype(np.float32)

magnitude = processor.process(ch1, ch2)
# Returns: (batch_size, n_bins) array
```

### Advanced Usage - Direct Engine Control

```python
from ionosense_hpc.core.engine import RtFftEngine
import numpy as np

# Create engine with specific configuration
engine = RtFftEngine(nfft=4096, batch=32, use_graphs=True, verbose=False)
engine.prepare_for_execution()

# Direct buffer manipulation (zero-copy)
stream_idx = 0
input_buffer = engine.pinned_input(stream_idx)  # Returns numpy view
output_buffer = engine.pinned_output(stream_idx)

# Fill input
input_buffer[:] = np.random.randn(*input_buffer.shape).astype(np.float32)

# Execute asynchronously
engine.execute_async(stream_idx)
engine.sync_stream(stream_idx)

# Results are now in output_buffer
magnitude_spectrum = output_buffer.copy()
```

### Window Functions

```python
from ionosense_hpc import FFTProcessor
import numpy as np

processor = FFTProcessor(fft_size=4096)

# Set custom window
hann_window = np.hanning(4096).astype(np.float32)
processor.engine.set_window(hann_window)
```

### Streaming Processing

```python
from ionosense_hpc import FFTProcessor
import numpy as np

processor = FFTProcessor(fft_size=4096, batch_size=32)

def data_generator(sample_rate=100_000, chunk_size=4096):
    """Simulate streaming data."""
    t = 0
    while True:
        chunk = np.arange(chunk_size) / sample_rate + t
        ch1 = np.sin(2 * np.pi * 1000 * chunk)
        ch2 = np.sin(2 * np.pi * 2000 * chunk)
        yield ch1.astype(np.float32), ch2.astype(np.float32)
        t += chunk_size / sample_rate

# Process stream
stream = data_generator()
for i, (ch1, ch2) in enumerate(stream):
    if i >= 10:  # Process 10 chunks
        break
    result = processor.process(ch1, ch2)
    print(f"Chunk {i}: peak bin = {np.argmax(result[0])}")
```

## Performance Utilities

### Profiling Support

```python
from ionosense_hpc.core.profiling import nvtx_range, timer

with nvtx_range("processing_loop"):  # Visible in Nsight Systems
    with timer("FFT Processing") as t:
        result = processor.process(ch1, ch2)
    print(f"Processing took {t['time_ms']:.3f} ms")
```

### Metrics Collection

```python
from ionosense_hpc.core.metrics import PerformanceMetrics

metrics = PerformanceMetrics()

# Collect latencies
for _ in range(100):
    start = time.perf_counter()
    result = processor.process(ch1, ch2)
    metrics.add_latency((time.perf_counter() - start) * 1000)

# Get statistics
stats = metrics.get_latency_stats()
print(f"Mean: {stats.mean:.3f} ms")
print(f"P99: {stats.p99:.3f} ms")
```

## Signal Generation

```python
from ionosense_hpc.io.signals import generate_test_signal

# Generate dual-channel test signals
signals = generate_test_signal(
    sample_rate=100_000,
    duration=1.0,
    frequencies=[7000, 1000],  # Hz for ch1, ch2
    noise_level=0.01
)

ch1_data = signals['ch1']
ch2_data = signals['ch2']
```

## Configuration

```python
from ionosense_hpc.core.config import ProcessingConfig

config = ProcessingConfig(
    fft_size=8192,
    batch_size=64,  # Auto-selected if None
    window='hann',
    output_type='magnitude',  # Future: 'phase', 'complex'
    use_graphs=True
)

processor = FFTProcessor(**config.__dict__)
```

## Error Handling

```python
try:
    processor = FFTProcessor(fft_size=4096, batch_size=3)  # Odd batch size
except ValueError as e:
    print(f"Configuration error: {e}")

try:
    processor.process(np.ones(2048), np.ones(2048))  # Wrong size
except ValueError as e:
    print(f"Input error: {e}")
```

## Thread Safety

The FFT engine uses separate CUDA streams internally but is **not** thread-safe for concurrent Python access. For multi-threaded processing:

```python
import threading
from threading import Lock

processor = FFTProcessor(fft_size=4096)
processor_lock = Lock()

def worker(data_chunk):
    with processor_lock:
        return processor.process(data_chunk['ch1'], data_chunk['ch2'])
```

## Numerical Validation

```python
from ionosense_hpc.analysis.validators import validate_against_numpy

# Compare against NumPy
processor = FFTProcessor(fft_size=1024)
test_signal = np.random.randn(1024).astype(np.float32)

gpu_result = processor.process(test_signal, test_signal)[0]
cpu_result = np.abs(np.fft.rfft(test_signal * np.hanning(1024)))

rms_error = np.sqrt(np.mean((gpu_result - cpu_result)**2))
print(f"RMS Error: {rms_error:.2e}")  # Should be <1e-5
```

## Troubleshooting

### Import Errors

```python
# Check if module is built
import sys
sys.path.append('path/to/ionosense-hpc-lib/python')
import ionosense_hpc
```

### CUDA Errors

```python
# Verify CUDA is available
import subprocess
result = subprocess.run(['nvidia-smi'], capture_output=True)
if result.returncode != 0:
    print("CUDA not available")
```

### Memory Issues

```python
# Monitor GPU memory
processor = FFTProcessor(fft_size=16384, batch_size=1024)
# If OOM, reduce batch_size
```

## API Reference

See [API Documentation](../docs/API.md) for complete reference.