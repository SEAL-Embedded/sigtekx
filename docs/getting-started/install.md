# Installation Guide

Detailed installation instructions for ionosense-hpc on various platforms using the integrated CLI platform.

## Table of Contents

- [Requirements](#requirements)
- [Quick Install](#quick-install)
- [Platform-Specific Instructions](#platform-specific-instructions)
  - [Linux](#linux)
  - [Windows](#windows)
  - [WSL2](#wsl2-windows-subsystem-for-linux)
- [Using the CLI Platform](#using-the-cli-platform)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

## Requirements

### Hardware Requirements

- **GPU**: NVIDIA GPU with compute capability 6.0 or higher
  - Minimum: GTX 1060, RTX 2060, or equivalent
  - Recommended: RTX 3070 or better for optimal performance
- **Memory**: 16 GB RAM minimum, 32 GB recommended
- **Storage**: 20 GB free disk space

### Software Requirements

| Component | Linux | Windows | WSL2 |
|-----------|-------|---------|------|
| OS | Ubuntu 22.04/24.04 LTS | Windows 11 | Ubuntu 24.04 LTS |
| CUDA Driver | ≥525 | ≥525 | Host driver |
| Build Tools | GCC 11+ | VS Build Tools 2022 | GCC 11+ |
| Python | 3.11 | 3.11 | 3.11 |
| CMake | ≥3.26 | ≥3.26 | ≥3.26 |

## Quick Install

### Clone Repository

```bash
git clone https://github.com/SEAL-Embedded/ionosense-hpc-lib.git
cd ionosense-hpc-lib
```

### Linux/WSL2

```bash
# One-command setup (creates environment, installs dependencies, builds)
./scripts/cli.sh setup

# Build the project
./scripts/cli.sh build

# Verify installation
./scripts/cli.sh test
```

### Windows

```powershell
# Start enhanced development shell (includes MSVC setup)
.\scripts\init_pwsh.ps1

# One-command setup using alias
iono setup

# Build the project
ib               # Short for 'iono build'

# Verify installation  
it               # Short for 'iono test'
```

## Platform-Specific Instructions

### Linux

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

# Install CUDA Toolkit
sudo apt install -y cuda-toolkit-13-0

# Add CUDA to PATH (add to ~/.bashrc for persistence)
echo 'export PATH=/usr/local/cuda-13.0/bin${PATH:+:${PATH}}' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-13.0/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}' >> ~/.bashrc
source ~/.bashrc

# Verify installation
nvcc --version
nvidia-smi
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

#### 4. Install Mamba (Recommended)

```bash
# Install mamba in base environment for faster dependency resolution
conda install mamba -n base -c conda-forge

# Verify installation
mamba --version
```

#### 5. Setup with CLI

```bash
# Clone repository
git clone https://github.com/SEAL-Embedded/ionosense-hpc-lib.git
cd ionosense-hpc-lib

# Use CLI for complete setup
./scripts/cli.sh setup    # Creates conda env, installs dependencies
./scripts/cli.sh build    # Builds C++ extensions
./scripts/cli.sh test     # Verifies installation
```

### Windows

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

#### 3. PowerShell 7

Install PowerShell 7 using Windows Package Manager (winget):

```powershell
# Install PowerShell 7 (run in Windows PowerShell or Command Prompt)
winget install --id Microsoft.Powershell --source winget

# Verify installation
pwsh --version
```

After installation, **close and reopen PowerShell**. For the remaining steps, use PowerShell 7 (pwsh) instead of Windows PowerShell.

To launch PowerShell 7:
- Search for "PowerShell 7" or "pwsh" in the Start menu, or
- Run `pwsh` from any terminal

#### 4. Miniconda Installation

Install Miniconda using PowerShell 7:

```powershell
# Download Miniconda installer
Invoke-WebRequest -Uri "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe" -OutFile "$env:TEMP\Miniconda3-installer.exe"

# Install silently with specific options
Start-Process -FilePath "$env:TEMP\Miniconda3-installer.exe" -ArgumentList @(
    "/InstallationType=JustMe",
    "/AddToPath=0",
    "/RegisterPython=0", 
    "/ClearPackageCache=1",
    "/S",
    "/D=$env:USERPROFILE\miniconda3"
) -Wait

# Clean up installer
Remove-Item "$env:TEMP\Miniconda3-installer.exe"

# Initialize conda for PowerShell (call directly from install location)
& "$env:USERPROFILE\miniconda3\Scripts\conda.exe" init powershell
```

**Important**: Close and reopen PowerShell 7 for the conda initialization to take effect.

#### 5. Install Mamba

```powershell
# Install mamba for faster environment solving
conda install mamba -n base -c conda-forge

# (Optional) Configure global channel settings
# Note: The environment.yml already specifies channels, but this sets
# global defaults for manual conda/mamba commands outside the environment
conda config --set channel_priority strict
conda config --add channels conda-forge
conda config --add channels nvidia
```

#### 6. Setup with Enhanced Development Shell

**Important**: Before running setup, ensure you're in the ionosense-hpc environment or run setup from the enhanced development shell.

```powershell
# Clone repository
git clone https://github.com/SEAL-Embedded/ionosense-hpc-lib.git
cd ionosense-hpc-lib

# Option 1: Start enhanced development shell first (recommended)
.\scripts\init_pwsh.ps1 -Interactive

# Then run setup (will create environment if needed)
iono setup

# Option 2: Direct setup (for automation/CI)
# The CLI will use conda run to ensure correct environment
.\scripts\cli.ps1 setup

# Build and test
ib               # Builds C++ extensions (iono build)
it               # Verifies installation (iono test)

# Check environment
iono doctor      # Comprehensive environment verification
```

#### 7. OpenCppCoverage (Code Coverage Tool)

Install OpenCppCoverage for C++ code coverage analysis:

```powershell
# Install using winget (recommended)
winget install --id OpenCppCoverage.OpenCppCoverage --source winget

# Alternative: Install using Chocolatey
# First install Chocolatey if needed:
# winget install --id Chocolatey.Chocolatey --source winget
# Then install OpenCppCoverage:
# choco install opencppcoverage -y

# Verify installation
OpenCppCoverage --version
```

**Note**: You may need to restart PowerShell 7 or add OpenCppCoverage to your PATH manually if the command is not recognized immediately.

#### 8. Create Development Shell Shortcut (Optional)

For convenience, create a desktop shortcut that launches PowerShell 7 with the development environment pre-configured:

```powershell
# Run from repo root
.\scripts\create-dev-shortcut.ps1
```

This creates a shortcut on your desktop that you can double-click to launch directly into your configured development environment!

### WSL2 (Windows Subsystem for Linux)

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

Follow the [Linux Setup](#linux) steps for Miniconda, Mamba, and CLI usage.

## Using the CLI Platform

### Linux/WSL2 CLI

The `cli.sh` script provides comprehensive project management:

```bash
# Environment commands
./scripts/cli.sh setup      # One-time environment setup
./scripts/cli.sh doctor     # Verify all dependencies
./scripts/cli.sh info       # Show system information

# Build commands
./scripts/cli.sh build      # Build project (release)
./scripts/cli.sh rebuild    # Clean rebuild
./scripts/cli.sh clean      # Clean artifacts

# Testing and validation
./scripts/cli.sh test       # Run all tests
./scripts/cli.sh test py    # Python tests only
./scripts/cli.sh test cpp   # C++ tests only

# Code quality
./scripts/cli.sh format     # Format C++ code
./scripts/cli.sh lint       # Lint all code
./scripts/cli.sh check      # Run all checks
```

### Windows Development Shell

The enhanced development shell (`init_pwsh.ps1`) provides:

- **Automatic MSVC Configuration**: Sets up 64-bit Visual Studio tools
- **Conda Environment**: Activates ionosense-hpc environment
- **Convenient Aliases**: Short commands for all operations
- **Tab Completion**: Smart completion for all commands

```powershell
# Start development shell
.\scripts\init_pwsh.ps1

# Available aliases:
iono <command>      # Main CLI alias
ib                  # Build (iono build)
ir                  # Rebuild (iono rebuild)
it                  # Test all (iono test)
itp                 # Test Python (iono test py)
itc                 # Test C++ (iono test cpp)
ifmt                # Format code (iono format)
ilint               # Lint code (iono lint)
ibench              # Benchmark suite
iprof               # Profile code
ival                # Validate installation
imon                # Monitor GPU
iinfo               # System info
iclean              # Clean artifacts
```

### Advanced CLI Features

```bash
# Benchmarking workflows
./scripts/cli.sh bench suite              # Complete benchmark suite
./scripts/cli.sh profile nsys latency     # Profile with Nsight Systems
./scripts/cli.sh sweep experiment.yaml    # Parameter sweep experiments

# Research workflows  
./scripts/cli.sh report results/          # Generate research reports
./scripts/cli.sh validate                 # Numerical validation
./scripts/cli.sh monitor                  # Real-time GPU monitoring
```

## Verification

### 1. Environment Check

```bash
# Linux/WSL2
./scripts/cli.sh doctor

# Windows (in dev shell)
iono doctor
```

Expected output should show all components as "OK" with minimal warnings.

### 2. Run Tests

```bash
# Linux/WSL2
./scripts/cli.sh test

# Windows (in dev shell)  
it                 # or 'iono test'
```

Expected: All C++ and Python tests passing.

### 3. Quick Performance Check

```bash
# Linux/WSL2
./scripts/cli.sh bench latency

# Windows (in dev shell)
ibench latency     # or 'iono bench latency'
```

### 4. Python Import Test

```python
# Quick validation
python -c "import ionosense_hpc; print('✓ Import successful')"

# Interactive test
```python
>>> from ionosense_hpc import Engine, Presets, generate_test_signal
>>> engine = Engine(Presets.throughput())
>>> signals = generate_test_signal(sample_rate=100_000, duration=0.1)
>>> frame = signals['ch1'][: engine.config.nfft * engine.config.batch]
>>> output = engine.process(frame)
>>> print(f"Output shape: {output.shape}")
>>> engine.close()
```

### Common Issues

#### 1. CUDA Not Found

**Error**: `CUDA runtime library not found`

**Solution**:
```bash
# Linux
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# Windows: Add CUDA\v13.0\bin to system PATH
```

#### 2. CLI Script Permissions (Linux)

**Error**: `Permission denied`

**Solution**:
```bash
chmod +x scripts/cli.sh
```

#### 3. Windows Development Shell Issues

**Error**: MSVC tools not found

**Solution**:
```powershell
# Ensure you're using the development shell
.\scripts\init_pwsh.ps1

# Verify 64-bit PowerShell
[System.Environment]::Is64BitProcess  # Must return True
```

#### 4. Import Error After Build

**Error**: `ImportError: cannot import name '_engine'`

**Solution**:
```bash
# Linux/WSL2
./scripts/cli.sh rebuild

# Windows (in dev shell)
ir                 # or 'iono rebuild'
```

#### 5. Conda Environment Issues

**Error**: Environment activation fails

**Solution**:
```bash
# Linux/WSL2
./scripts/cli.sh clean -All
./scripts/cli.sh setup

# Windows (in dev shell)
iono clean -All
iono setup
```

### Debug Mode

Enable verbose logging:
```bash
# Linux/WSL2
export IONO_LOG_LEVEL=DEBUG
./scripts/cli.sh 