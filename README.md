# Ionosense-HPC-Lib

High-performance CUDA FFT engine for dual-channel ULF/VLF antenna signal processing with Python bindings.

## Features

- **Real-time Processing**: <200 μs latency per dual-channel FFT pair
- **CUDA Optimization**: Multi-stream concurrency with CUDA Graphs support
- **Research-Grade**: IEEE 754 float32 accuracy, validated against FFTW/MKL
- **Python Integration**: Zero-copy NumPy interface via pybind11
- **Cross-Platform**: Linux-first development, Windows deployment support

## Quick Start

### Prerequisites

- CUDA Toolkit ≥12.0
- CMake ≥3.26
- Python 3.11
- Conda/Mamba

### Installation

```bash
# Clone repository
git clone https://github.com/SEAL-Embedded/ionosense-hpc-lib.git
cd ionosense-hpc-lib

# Setup environment (Linux)
./scripts/cli.sh setup
conda activate ionosense-hpc

# Build
./scripts/cli.sh build

# Run tests
./scripts/cli.sh test
```

For Windows, use `.\scripts\cli.ps1` with the same commands.

### Basic Usage

```python
from ionosense_hpc import FFTProcessor, generate_test_signal

# Initialize processor
processor = FFTProcessor(fft_size=4096, batch_size=2)

# Generate test signals
signals = generate_test_signal(sample_rate=100_000, duration=1.0)

# Process
magnitude = processor.process(signals['ch1'][:4096], signals['ch2'][:4096])
```

## Architecture

```
┌─────────────────┐
│   Python API    │  Research interface
├─────────────────┤
│  Pybind11 Layer │  Zero-copy bindings
├─────────────────┤
│   C++ Engine    │  Stream orchestration
├─────────────────┤
│  CUDA Kernels   │  FFT, windowing, magnitude
└─────────────────┘
```

## Performance

Benchmarked on RTX 3090 Ti:

| Metric | Value | Target |
|--------|-------|--------|
| Latency (per dual FFT) | 110 μs | <200 μs |
| Throughput | >1M FFTs/s | - |
| Numerical Error (RMS) | <1e-5 | IEEE 754 |

## Documentation

- [Python API Guide](python/README.md) - Detailed usage and examples
- [Development Guide](docs/DEVELOPMENT.md) - Architecture and contributing
- [Benchmark Guide](docs/BENCHMARKS.md) - Performance testing methodology

## Citation

If you use this software in your research, please cite:

```bibtex
@software{ionosense-hpc-2025,
  title = {Ionosense-HPC: GPU-Accelerated FFT Processing for ULF/VLF Antennas},
  author = {Rahsaz, Kevin and {SEAL Lab}},
  year = {2025},
  institution = {University of Washington},
  url = {https://github.com/SEAL-Embedded/ionosense-hpc-lib}
}
```