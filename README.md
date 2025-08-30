# Ionosense HPC Library

**High-performance CUDA FFT engine for dual-channel ULF/VLF antenna signal processing**

[![CUDA](https://img.shields.io/badge/CUDA-13.0+-green.svg)](https://developer.nvidia.com/cuda-toolkit)
[![CMake](https://img.shields.io/badge/CMake-3.26+-blue.svg)](https://cmake.org)
[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

Professional-grade, research-oriented HPC library optimized for real-time signal processing of dual-channel ULF/VLF antenna data. Designed for 24/7 continuous operation with sub-200μs latency per dual FFT pair, targeting both academic research and field deployment.

### Key Features

- **Real-time Performance**: <200μs latency per dual-channel FFT pair (targeting <100μs)
- **CUDA Optimization**: Multi-stream concurrency with CUDA Graphs support
- **Research-Grade Accuracy**: IEEE 754 float32 compliance, validated against FFTW/MKL (not yet)
- **Cross-Platform**: Linux-first development (native + WSL2), Windows deployment support
- **Python Integration**: Zero-copy NumPy interface via pybind11
- **Production Ready**: Designed for 24/7 continuous field operation

## Table of Contents

- [System Requirements](#system-requirements)
- [Platform Setup](#platform-setup)
  - [Linux Setup (Ubuntu 24.04 LTS)](#linux-setup-ubuntu-2404-lts)
  - [Windows Setup (Native)](#windows-setup-native)
  - [WSL2 Setup (Windows Subsystem for Linux)](#wsl2-setup-windows-subsystem-for-linux)
- [Environment Installation](#environment-installation)
- [Building the Project](#building-the-project)
- [Verification](#verification)
- [Development Workflow](#development-workflow)
- [Performance Benchmarks](#performance-benchmarks)
- [Troubleshooting](#troubleshooting)

## System Requirements

### Hardware Requirements

- **GPU**: NVIDIA GPU's listed below (easy to add more)
  - Development: RTX 3090 Ti (CC 8.6)
  - Deployment: RTX 4000 Ada (CC 8.9)
- **RAM**: 16GB minimum, 32GB recommended
- **Storage**: 20GB free space for build artifacts and datasets

### Software Prerequisites

| Component | Linux | Windows | WSL2 |
|-----------|-------|---------|------|
| OS | Ubuntu 22.04/24.04 LTS | Windows 11 | Ubuntu 24.04 LTS |
| CUDA Driver | ≥525 | ≥525 | Host driver |
| Build Tools | GCC 11+ | VS Build Tools 2022 | GCC 11+ |
| Python | 3.11 | 3.11 | 3.11 |
| CMake | ≥3.26 | ≥3.26 | ≥3.26 |

## Platform Setup

### Linux Setup (Ubuntu 24.04 LTS)

#### 1. System Updates & Essential Tools

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install essential build tools
sudo apt install -y \
    build-essential \
    gcc-11 g++-11 \
    git curl wget \
    ca-certificates \
    gnupg lsb-release

# Set GCC 11 as default
sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-11 100
sudo update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-11 100
```

#### 2. NVIDIA CUDA Toolkit

```bash
# Add NVIDIA package repositories
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update

# Install CUDA Toolkit (without driver if using WSL2)
sudo apt install -y cuda-toolkit-13-0

# Add CUDA to PATH (add to ~/.bashrc for persistence)
echo 'export PATH=/usr/local/cuda-13.0/bin${PATH:+:${PATH}}' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}' >> ~/.bashrc
source ~/.bashrc

# Verify installation
nvcc --version
nvidia-smi  # Skip if WSL2
```

#### 3. Miniconda Installation

```bash
# Download Miniconda installer
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

# Install with default settings
bash Miniconda3-latest-Linux-x86_64.sh -b -p $HOME/miniconda3

# Initialize conda for bash
$HOME/miniconda3/bin/conda init bash
source ~/.bashrc

# Configure conda for strict channel priority
conda config --set channel_priority strict
conda config --add channels conda-forge
conda config --add channels nvidia
```

#### 4. Mamba Installation (Recommended)

```bash
# Install mamba in base environment for faster dependency resolution
conda install mamba -n base -c conda-forge

# Verify installation
mamba --version
```

### Windows Setup (Native)

#### 1. Visual Studio Build Tools 2022

Download and install [Visual Studio Build Tools 2022](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022):

1. Run the installer as Administrator
2. Select **"Desktop development with C++"** workload
3. Ensure these components are selected:
   - MSVC v143 - VS 2022 C++ x64/x86 build tools
   - Windows 11 SDK (or Windows 10 SDK)
   - CMake tools for Windows
4. Install and restart if prompted

#### 2. NVIDIA CUDA Toolkit

1. Download [CUDA Toolkit 13.0](https://developer.nvidia.com/cuda-13-0-download-archive) for Windows
2. Run installer with default settings
3. Verify installation:
   ```powershell
   nvcc --version
   nvidia-smi
   ```

#### 3. Miniconda Installation

Download the [Miniconda installer](https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe) and run it directly in PowerShell:

```powershell
# Run installer (PowerShell in the same directory)
.\miniconda.exe
```

Follow the GUI installation steps:

1. **Agree** to the license terms.
2. Select **"Just Me (recommended)"**.
3. Set the destination folder to:
   ```
   C:\Users\<your-username>\miniconda3
   ```
4. Check the following options:
   - **Create shortcuts (supported packages only)**
   - **Clear the package cache upon completion**
5. Click **Install** and finish the setup.

Once complete, restart PowerShell and run:

```powershell
conda init powershell
```

Then close and reopen PowerShell to activate Conda.

#### 4. Mamba Installation

```powershell
# Install mamba for faster environment solving
conda install mamba -n base -c conda-forge
(agree to all)

# Configure channels
mamba config --set channel_priority strict
mamba config --add channels conda-forge
mamba config --add channels nvidia
```

#### 5. Configure 64-bit Development Terminal (Critical)

**⚠️ Important**: You MUST use a properly configured 64-bit terminal for builds to work correctly.

##### Option A: Create Custom PowerShell Shortcut (Recommended)

1. **Create the helper script**:
   Save this as `scripts/start-devshell-x64.ps1` in your project:
   ```powershell
   Import-Module "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\Microsoft.VisualStudio.DevShell.dll"
   Enter-VsDevShell -VsInstallPath "C:\Program Files\Microsoft Visual Studio\2022\Community" -Arch amd64
   ```
   Adjust paths if VS is installed elsewhere (e.g., `Professional` or `Enterprise` edition).

2. **Create a permanent shortcut**:
   - Find "Developer PowerShell for VS 2022" in Start Menu
   - Right-click → More → Open file location
   - Copy the shortcut, rename to "CUDA PowerShell (x64)"
   - Right-click → Properties
   - Replace Target field with:
     ```
     C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -noe -c "& 'C:\path\to\your\project\scripts\start-devshell-x64.ps1'"
     ```
   - Click OK and pin to taskbar

3. **Verify 64-bit mode**:
   ```powershell
   [System.Environment]::Is64BitProcess  # Must return True
   where cl  # Should find cl.exe
   ```

##### Option B: Quick Access Method

1. Open "**x64 Native Tools Command Prompt for VS 2022**" from Start Menu
2. Type `powershell` to switch from cmd to PowerShell
3. Verify with `[System.Environment]::Is64BitProcess` (must be `True`)

**Note**: Regular "Developer PowerShell" may default to 32-bit. Always verify you're in 64-bit mode before building.

### WSL2 Setup (Windows Subsystem for Linux)

#### 1. Install WSL2 with Ubuntu 24.04

```powershell
# Run in Administrator PowerShell
wsl --install -d Ubuntu-24.04

# Set WSL2 as default version
wsl --set-default-version 2

# Verify installation
wsl --list --verbose
```

#### 2. Configure WSL2 for CUDA

Create/edit `%USERPROFILE%\.wslconfig`:

```ini
[wsl2]
memory=16GB
processors=8
localhostForwarding=true
kernelCommandLine=nvidia-drm.modeset=1

[experimental]
autoMemoryReclaim=gradual
sparseVhd=true
```

#### 3. Inside WSL2 Ubuntu

```bash
# Update and upgrade
sudo apt update && sudo apt upgrade -y

# Install CUDA toolkit (WSL2 specific - no driver needed)
wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update
sudo apt install -y cuda-toolkit-13-0

# Verify CUDA access
nvidia-smi  # Should show Windows host GPU
```

Follow the [Linux Setup](#linux-setup-ubuntu-2404-lts) steps 3-4 for Miniconda and Mamba installation.

## Environment Installation

### Clone Repository

```bash
# Linux/WSL2
git clone https://github.com/SEAL-Embedded/ionosense-hpc-lib.git
cd ionosense-hpc-lib

# Windows (PowerShell)
git clone https://github.com/SEAL-Embedded/ionosense-hpc-lib.git
cd ionosense-hpc-lib
```

### Create Conda Environment

#### Linux/WSL2

```bash
# Setup environment using project CLI
./scripts/cli.sh setup

# Activate environment
mamba activate ionosense-hpc

# Verify environment
which python
python --version  # Should show 3.11.x
```

#### Windows

```powershell
# In Developer PowerShell for VS 2022
.\scripts\cli.ps1 setup

# Activate environment
conda activate ionosense-hpc

# Verify environment
where python
python --version  # Should show 3.11.x
```

## Building the Project

### Quick Build

#### Linux/WSL2

```bash
# Ensure environment is activated
mamba activate ionosense-hpc

# Build release version
./scripts/cli.sh build

# Or build specific configuration
./scripts/cli.sh build linux-rel    # Release build (default)
./scripts/cli.sh build linux-debug  # Debug build
```

#### Windows

```powershell
# IMPORTANT: Use your configured 64-bit terminal (see setup section)
# Verify you're in 64-bit mode:
[System.Environment]::Is64BitProcess  # Must return True

# Activate environment
mamba activate ionosense-hpc

# Build release version
.\scripts\cli.ps1 build

# Or build specific configuration
.\scripts\cli.ps1 build windows-rel    # Release build (default)
.\scripts\cli.ps1 build windows-debug  # Debug build
```

### Clean Rebuild

```bash
# Linux/WSL2
./scripts/cli.sh rebuild

# Windows
.\scripts\cli.ps1 rebuild
```

## Verification

### 1. Run Tests

```bash
# Linux/WSL2
./scripts/cli.sh test

# Windows
.\scripts\cli.ps1 test
```

Expected output:
- C++ tests (GoogleTest): All tests passing
- Python tests (pytest): All tests passing
- Import validation: `_engine` module loads successfully

### 2. Run Benchmarks

```bash
# List available benchmarks
./scripts/cli.sh list benchmarks        # Linux/WSL2
.\scripts\cli.ps1 list benchmarks       # Windows

# Run throughput benchmark
./scripts/cli.sh bench raw_throughput -n 4096   # Linux/WSL2
.\scripts\cli.ps1 bench raw_throughput -n 4096  # Windows
```

### 3. Python Import Test

```python
# Quick validation
python -c "from ionosense_hpc import FFTProcessor; print('✓ Import successful')"

# Interactive test
python
>>> from ionosense_hpc import FFTProcessor, generate_test_signal
>>> processor = FFTProcessor(fft_size=4096, batch_size=2)
>>> signals = generate_test_signal(sample_rate=100_000, duration=0.1)
>>> result = processor.process(signals['ch1'][:4096], signals['ch2'][:4096])
>>> print(f"Output shape: {result.shape}")
```

## Development Workflow

### Daily Development Cycle

```bash
# 1. Activate environment
mamba activate ionosense-hpc

# 2. Pull latest changes
git pull origin main

# 3. Rebuild if needed
./scripts/cli.sh rebuild

# 4. Run tests
./scripts/cli.sh test

# 5. Run benchmarks
./scripts/cli.sh bench realtime

# 6. Profile if needed
./scripts/cli.sh profile nsys raw_throughput
```

### Project Structure

```
ionosense-hpc-lib/
├── include/           # C++ headers
├── src/              # CUDA/C++ implementation
├── bindings/         # Python bindings (pybind11)
├── python/           # Python package
│   ├── benchmarks/   # Performance benchmarks
│   ├── src/ionosense_hpc/  # Main package
│   └── tests/        # Python tests
├── tests/            # C++ tests (GoogleTest)
├── scripts/          # CLI utilities
├── docs/             # Documentation
└── build/            # Build artifacts (git-ignored)
```

## Performance Benchmarks

### Target Specifications

| Metric | Target | Current | Hardware |
|--------|--------|---------|----------|
| Latency (dual FFT) | <200 μs | ~110 μs | RTX 3090 Ti |
| Throughput | >1M FFTs/s | 1.2M/s | RTX 3090 Ti |
| Memory Transfer | <40% time | 38% | - |
| Numerical Error | <1e-5 RMS | 8.3e-6 | IEEE 754 |

### Profiling

```bash
# Nsight Systems profiling
./scripts/cli.sh profile nsys realtime

# Nsight Compute profiling
./scripts/cli.sh profile ncu raw_throughput

# View reports in: build/nsight_reports/
```

## Troubleshooting

### Common Issues

#### CUDA Not Found

```bash
# Verify CUDA installation
nvcc --version
echo $CUDA_HOME

# Set CUDA_HOME if missing
export CUDA_HOME=/usr/local/cuda-13.0
```

#### Python Module Import Error

```bash
# Check module location
find . -name "_engine*.so" -o -name "_engine*.pyd"

# Rebuild with verbose output
./scripts/cli.sh rebuild
```

#### Windows VS Build Tools Issues

1. **Ensure you're using a 64-bit terminal**:
   ```powershell
   [System.Environment]::Is64BitProcess  # MUST return True
   ```
2. Verify cl.exe is available: `where cl`
3. Check environment: `$env:VSINSTALLDIR`
4. If using regular PowerShell, run the helper script:
   ```powershell
   & ".\scripts\start-devshell-x64.ps1"
   ```

#### WSL2 GPU Access

```bash
# Check GPU visibility
nvidia-smi

# If not visible, update Windows GPU drivers
# Ensure Windows 11 or Windows 10 21H2+
```

### Debug Build for Troubleshooting

```bash
# Linux/WSL2
./scripts/cli.sh build linux-debug
gdb ./build/linux-debug/test_engine

# Windows
.\scripts\cli.ps1 build windows-debug
```

## Contributing

See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for detailed development guidelines, coding standards, and contribution workflow.

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