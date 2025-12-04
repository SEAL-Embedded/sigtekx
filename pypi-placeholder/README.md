# SigTekX

**Package name reservation - Full release coming soon**

## About

**SigTekX** (Signal + Tekton "builder" + X "acceleration") is a high-performance GPU-accelerated signal processing library for building real-time FFT analysis pipelines.

This placeholder reserves the `sigtekx` package name on PyPI. The library is currently in development (v0.9.4) and will be published under this name in an upcoming release.

## Current Status

The library is in **active development** (Beta) with a working implementation featuring:

- **Sub-200μs latency** CUDA FFT engine
- **Python API** with C++ backend via pybind11
- **Multi-stream async execution** for throughput optimization
- **Research infrastructure** (Hydra, MLflow, DVC, Snakemake)
- **Professional benchmarking** suite with statistical analysis
- **NVTX profiling** support for NVIDIA tools

## Coming Soon

The rebranded `sigtekx` package will include:

- Complete CUDA-accelerated FFT processing engine
- Type-safe Python API with Pydantic configuration
- Batch and streaming execution modes
- Comprehensive benchmark and profiling tools
- Pre-configured presets for common use cases
- Full documentation and examples

## Repository

Development is happening at: https://github.com/SEAL-Embedded/ionosense-hpc-lib

**Note**: Repository will be renamed to `sigtekx` upon package release.

## Requirements (Future Release)

- Python 3.11+
- NVIDIA GPU with CUDA compute capability 6.0+ (Pascal or newer)
- CUDA Toolkit 13.0+
- Windows 11 or Linux

## Contact

**Author**: Kevin Rahsaz
**Email**: rahsaz.kevin@gmail.com

## License

MIT License
