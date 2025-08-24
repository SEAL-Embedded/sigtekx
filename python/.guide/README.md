# 🚀 CUDA FFT Engine - Python Research Guide

## 📋 Table of Contents
- [Overview](#overview)
- [Project Structure](#project-structure)
- [Why GPU Acceleration?](#why-gpu-acceleration)
- [Understanding the Engine](#understanding-the-engine)
- [Thinking in Parallel: Core Concepts](#thinking-in-parallel-core-concepts)
- [Quick Start](#quick-start)
- [Core API Reference](#core-api-reference)
- [Benchmark Scripts](#benchmark-scripts)
- [Integration Examples](#integration-examples)
- [Performance Tips](#performance-tips)
- [Troubleshooting](#troubleshooting)

---

## Overview

This CUDA FFT Engine is a high-performance signal processing tool that accelerates Fast Fourier Transform (FFT) operations by **100-1000x** compared to CPU processing. Built for real-time signal analysis, it's perfect for processing large datasets with pandas, creating visualizations, and feeding ML models.

### 🎯 Key Features
- **Massive Parallelization**: Process thousands of FFTs simultaneously.
- **Triple-Stream Pipeline**: Overlapping operations for continuous throughput.
- **CUDA Graphs**: Ultra-low latency with pre-captured execution patterns.
- **Python-First Design**: Simple NumPy-like interface with zero-copy memory access.

---

## Project Structure

```
cuda/
│
├── cli.ps1                 # 🎮 Master CLI tool (run everything from here!)
├── requirements.txt        # 📦 Python dependencies
├── CMakeLists.txt          # 🔧 Build configuration
│
├── src/                    # C++/CUDA source code
│   ├── fft/
│   │   ├── cuda_fft.cu   # Core CUDA FFT implementation
│   │   └── cuda_fft.h    # Engine class definition
│   └── bindings/
│       └── bindings.cpp  # Python bindings (pybind11)
│
├── tests/                  # C++ unit tests (GoogleTest)
│   ├── test_fft.cpp      # Validates engine correctness
│   └── CMakeLists.txt    # Test configuration
│
├── python/
│   ├── benchmarks/       # 📊 Performance benchmarking scripts
│   └── examples/         # 💡 Integration examples
│
├── build/                  # 🏗️ (Generated) Compiled module & artifacts
│
└── .venv/                  # 🐍 (Generated) Python virtual environment
```

---

## Why GPU Acceleration?

### The CPU vs GPU Difference (Pizza Delivery Analogy 🍕)

**CPU (1 Fast Delivery Driver)**
- One very skilled driver with a sports car.
- Can deliver pizzas very quickly, but only one at a time.
- Great for complex routes with special instructions.

**GPU (1000 Scooter Drivers)**
- An army of scooter drivers working in parallel.
- Each driver is slower, but all deliver simultaneously.
- Perfect when you have 1000 identical deliveries.

---

## Understanding the Engine

### 🔄 The Triple-Stream Pipeline

Our engine uses 3 concurrent "assembly lines" that overlap different stages of processing:

```
Stream 0: [Copy to GPU] → [Process] → [Copy Back] → ...
Stream 1:              ↘  [Copy to GPU] → [Process] → [Copy Back] → ...
Stream 2:                             ↘  [Copy to GPU] → [Process] → [Copy Back] → ...

Time →    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

While Stream 0 is copying results back, Stream 1 is processing, and Stream 2 is uploading new data. This creates a continuous flow with no idle time.

### 🎯 CUDA Graphs: The Secret Sauce

Instead of telling the GPU what to do step-by-step (slow), we record the entire workflow once and replay it (fast):

```python
# First time: Records all operations
engine.prepare_for_execution()  # "Learn the recipe"

# Every time after: Instant replay
engine.execute_async(0)  # "Make it again!" - 10x faster
```

---

## Thinking in Parallel: Core Concepts

To use the engine effectively, it helps to understand two key concepts that make it so fast.

### 🧠 The Asynchronous Mindset

In normal Python, code runs sequentially. With the GPU, you want to think **asynchronously**.
- **`execute_async()` is Non-Blocking**: When you call this function, you are giving the GPU a work order. The function returns control to your Python script *immediately*, without waiting for the GPU to finish. This allows your CPU to continue working on other things (like preparing the next batch of data) while the GPU works in parallel.
- **`sync_stream()` is the Checkpoint**: You only call this function when you absolutely need the results from a specific task. It's the point where your Python script will pause and wait for the GPU to report that it's done.

Adopting this "fire-and-forget" mindset is crucial for keeping both the CPU and GPU busy and achieving maximum performance.

### 🚀 Why Pinned Memory Matters

You'll notice the API uses `pinned_input()` and `pinned_output()` instead of taking a normal NumPy array as an argument. This is a critical optimization.
- **Normal Memory (Pageable)**: Standard NumPy arrays live in "pageable" memory. For the GPU to access it, the CUDA driver must first copy the data into a special "pinned" buffer before transferring it to the GPU. This is an expensive, hidden copy operation.
- **Pinned Memory**: The engine pre-allocates these special pinned buffers for you. This memory has a fixed physical address, allowing the GPU to read from and write to it directly using DMA (Direct Memory Access) without the extra driver-side copy. This is what enables true "zero-copy" access and is essential for the high-speed, overlapping pipeline to work.

By writing your data directly into `engine.pinned_input(i)`, you are using the GPU's express lane for data transfers.

---

## Quick Start

### 🛠️ Setting Up a 64-bit Development Terminal

For C++ and CUDA development on Windows, it's **crucial** to use a terminal that has been properly configured with the 64-bit Visual Studio environment. This ensures that compilers (`cl.exe`) and other build tools are found correctly.

#### Recommended Method: Create a Permanent PowerShell Shortcut
This method creates a dedicated, reusable shortcut that launches a correctly configured 64-bit PowerShell environment with a single click.

1.  **Find and Copy the Original Shortcut**
    - Click the **Start Menu** and type `Developer PowerShell`.
    - Right-click on **Developer PowerShell for VS 2022**.
    - Select **More > Open file location**.
    - In the File Explorer window that opens, copy and paste the shortcut to create a duplicate. Rename the copy to something memorable, like `CUDA PowerShell (x64)`.

2.  **Modify the Shortcut Target**
    - Right-click your new shortcut and select **Properties**.
    - In the **Target** field, replace the entire existing text with the following:
      ```
      C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -noe -c "&{Import-Module 'YOUR_VS_INSTALL_PATH\Common7\Tools\Microsoft.VisualStudio.DevShell.dll'; Enter-VsDevShell -VsInstallPath 'YOUR_VS_INSTALL_PATH' -Arch amd64}"
      ```
    > **Important**: Replace both instances of `YOUR_VS_INSTALL_PATH` with the actual path to your Visual Studio installation. The default is typically `"C:\Program Files\Microsoft Visual Studio\2022\Community"`.

3.  **Verify and Use**
    - Launch your new shortcut and confirm it's running in 64-bit mode by running `[System.Environment]::Is64BitProcess`. It **must** return `True`. You can now move this shortcut to your desktop or taskbar for convenient access.

### ⚙️ The CLI Tool & Installation

Once your terminal is set up, you can use the project's CLI tool.

> **⚠️ Important:** Before running any commands, open `cli.ps1` and verify the paths at the top (`$Config`) point to your local installations of Nsight Compute, Nsight Systems, and the CUDA Toolkit.

#### Installation Steps

1.  **First-time Setup** (do this once in your configured terminal)
    ```powershell
    # Complete environment setup
    ./cli.ps1 setup    # Creates venv, installs requirements.txt
    ./cli.ps1 build    # Compiles the CUDA FFT module
    ```

2.  **Verify Installation**
    ```powershell
    # The build command automatically verifies the module.
    # You should see: "✓ Module imported successfully! Version: 1.x.x"
    ```

### CLI Command Reference

| Command | Description | Example |
|---|---|---|
| `clean` | Remove all build artifacts and venv | `./cli.ps1 clean` |
| `setup` | Create Python venv & install deps | `./cli.ps1 setup` |
| `build [config]`| Build C++ module (release/debug) | `./cli.ps1 build release` |
| `rebuild [config]`| Clean + Setup + Build | `./cli.ps1 rebuild` |
| `test [config]` | Run C++ unit tests | `./cli.ps1 test` |
| `bench <name> [args]` | Run a benchmark script | `./cli.ps1 bench fft_raw -b 32` |
| `profile <tool> <name> [args]`| Profile with Nsight | `./cli.ps1 profile nsys fft_raw -b 32` |

### Basic Usage

```python
from cuda_lib import CudaFftEngine
import numpy as np

# Create engine: 4096-point FFT, batch of 32
engine = CudaFftEngine(nfft=4096, batch=32, use_graphs=True)

# Prepare for high-speed execution
engine.prepare_for_execution()

# Generate test signals (32 signals × 4096 samples)
signals = np.random.randn(32 * 4096).astype(np.float32)

# Process on GPU
stream_idx = 0
engine.pinned_input(stream_idx)[:] = signals
engine.execute_async(stream_idx)
engine.sync_stream(stream_idx)

# Get magnitude results (32 FFTs × 2049 frequency bins)
magnitudes = engine.pinned_output(stream_idx)
```

---

## Core API Reference

### CudaFftEngine Class

```python
engine = CudaFftEngine(nfft, batch, use_graphs=True, verbose=True)
```

| Parameter | Type | Description | Example |
|---|---|---|---|
| `nfft` | int | FFT size (must be power of 2) | 4096 |
| `batch` | int | Number of FFTs per execution | 32 |
| `use_graphs`| bool | Enable CUDA Graphs optimization | True |
| `verbose` | bool | Print debug information | False |

### Key Methods

#### 🚀 `prepare_for_execution()`
Warms up the GPU and captures the execution graph. Call once before your main loop.

```python
engine.prepare_for_execution()
```

#### ⚡ `execute_async(stream_idx)`
Launches FFT processing on the specified stream (0, 1, or 2).

```python
for i in range(100):
    stream_idx = i % 3
    engine.execute_async(stream_idx)
```

#### 🛑 `sync_stream(stream_idx)`
Waits for a stream to finish. Always sync before reading output!

```python
engine.sync_stream(0)
results = engine.pinned_output(0)
```

#### 📥 `pinned_input(stream_idx)`
Returns a NumPy array view of the input buffer. Zero-copy access!

```python
# Direct write to GPU-accessible memory
engine.pinned_input(0)[:] = my_signal_data
```

#### 📤 `pinned_output(stream_idx)`
Returns a NumPy array view of the output magnitudes.

```python
magnitudes = engine.pinned_output(0)
# Shape: (batch_size * (nfft//2 + 1),)
```

#### 🪟 `set_window(window_array)`
Applies a window function (Hanning, Hamming, etc.) to all FFTs.

```python
window = np.hanning(4096).astype(np.float32)
engine.set_window(window)
```

### Properties

| Property | Returns | Description |
|---|---|---|
| `engine.fft_size` | int | FFT length (nfft) |
| `engine.batch_size` | int | Number of FFTs per batch |
| `engine.num_streams`| int | Number of concurrent streams (always 3) |

---

## Benchmark Scripts

The repository includes several benchmark scripts. Run them using the CLI tool:

### 🏃 `fft_raw` - Raw Throughput
Measures maximum FFTs/second without timing constraints.

```powershell
./cli.ps1 bench fft_raw --nfft 4096 --batch-size 64 --duration 10
```

### ⏱️ `fft_realtime` - Real-time Latency
Simulates real-time streaming with deadline constraints.

```powershell
./cli.ps1 bench fft_realtime --nfft 4096 --sr 100000 --overlap 0.5
```

### 📊 `fft_batch_scaling` - Batch Size Analysis
Tests how performance scales with batch size to find the optimal configuration.

```powershell
./cli.ps1 bench fft_batch_scaling --min-batch 2 --max-batch 256 -o results.csv
```

### 🎯 `fft_graphs_comp` - CUDA Graphs Impact
Compares performance with and without CUDA Graphs to quantify the benefit.

```powershell
./cli.ps1 bench fft_graphs_comp --nfft 4096 --batch 32
```

### ✅ `verify_accuracy` - Numerical Validation
Confirms GPU results match a NumPy reference implementation to ensure correctness.

```powershell
./cli.ps1 bench verify_accuracy --nfft 4096 --batch-size 32
```

### 🔬 Profiling with NVIDIA Tools

Profile any benchmark to understand GPU behavior:

```powershell
# Profile with Nsight Systems (timeline view)
./cli.ps1 profile nsys fft_raw -b 128

# Profile with Nsight Compute (kernel analysis)
./cli.ps1 profile ncu fft_graphs_comp -b 64
```

---

## Integration Examples

### 📈 Simple Real-time Spectrogram (Matplotlib)

This example provides a tangible starting point for visualization. It shows how to use the engine to generate spectral data and plot it in a simple, continuously updating spectrogram.

```python
import numpy as np
import matplotlib.pyplot as plt
from cuda_lib import CudaFftEngine
import time

# --- Configuration ---
NFFT = 2048
BATCH_SIZE = 8
SAMPLE_RATE = 48000
SPECTROGRAM_HISTORY = 100 # How many FFT frames to show

# --- Setup ---
engine = CudaFftEngine(nfft=NFFT, batch=BATCH_SIZE, use_graphs=True, verbose=False)
engine.prepare_for_execution()

# Prepare the plot
plt.style.use('dark_background')
fig, ax = plt.subplots(figsize=(10, 6))
spectrogram_data = np.zeros((SPECTROGRAM_HISTORY, NFFT // 2 + 1))

im = ax.imshow(spectrogram_data, aspect='auto', cmap='viridis',
               extent=[0, SAMPLE_RATE / 2, 0, SPECTROGRAM_HISTORY])
ax.set_xlabel("Frequency (Hz)")
ax.set_ylabel("Time (Frames)")
ax.set_title("Real-time Spectrogram")
plt.colorbar(im, label="Magnitude")

# --- Main Loop ---
stream_idx = 0
try:
    while True:
        engine.sync_stream(stream_idx)
        
        # Generate synthetic data for the example
        t = np.arange(NFFT * BATCH_SIZE) / SAMPLE_RATE
        noise = np.random.randn(NFFT * BATCH_SIZE).astype(np.float32) * 0.1
        sine_wave = np.sin(2 * np.pi * 5000 * t).astype(np.float32)
        input_data = noise + sine_wave

        engine.pinned_input(stream_idx)[:] = input_data
        engine.execute_async(stream_idx)

        # Retrieve results from the previous iteration to keep the pipeline full
        prev_stream_idx = (stream_idx - 1 + engine.num_streams) % engine.num_streams
        magnitudes = engine.pinned_output(prev_stream_idx).reshape(BATCH_SIZE, -1)
        
        # Update spectrogram data buffer
        spectrogram_data = np.roll(spectrogram_data, -BATCH_SIZE, axis=0)
        spectrogram_data[-BATCH_SIZE:] = magnitudes

        # Update plot
        im.set_data(spectrogram_data)
        im.set_clim(vmin=0, vmax=np.max(spectrogram_data))
        fig.canvas.draw()
        fig.canvas.flush_events()
        
        stream_idx = (stream_idx + 1) % engine.num_streams
        
        plt.pause(0.001)

except KeyboardInterrupt:
    print("Stopping visualization.")
finally:
    engine.synchronize_all_streams()
    plt.close()
```

---

## Performance Tips

### ⚡ Best Practices

#### 1. Use the Canonical Processing Loop
This is the **safest and most efficient** pattern for continuous processing. It ensures you never overwrite a buffer the GPU is still using and maximizes parallelism.

```python
# The Canonical Processing Loop
stream_idx = 0
for i in range(num_iterations):
    # 1. Wait for the CURRENT stream's previous work to finish.
    engine.sync_stream(stream_idx)

    # 2. Prepare and copy the next batch of data.
    new_data = get_next_data_chunk()
    engine.pinned_input(stream_idx)[:] = new_data

    # 3. Asynchronously launch the GPU processing.
    engine.execute_async(stream_idx)

    # 4. Rotate to the next stream for the next iteration.
    stream_idx = (stream_idx + 1) % engine.num_streams

# Sync all streams at the end to ensure all work is complete.
engine.synchronize_all_streams()
```

#### 2. Always use CUDA Graphs for Production
```python
engine = CudaFftEngine(nfft, batch, use_graphs=True)  # 30-50% faster
```

#### 3. Rotate Through All 3 Streams
```python
for i in range(1000):
    stream_idx = i % 3  # Don't just use stream 0!
    engine.execute_async(stream_idx)
```

#### 4. Pre-allocate and Reuse Buffers
```python
# Good: Write directly to pinned memory
engine.pinned_input(0)[:] = data

# Bad: Create new arrays each time, which causes hidden allocation overhead
engine.pinned_input(0)[:] = np.array(data) 
```

---

## Troubleshooting

### Common Issues and Solutions

| Problem | Solution |
|---|---|
| `ImportError: cuda_lib` | Run `./cli.ps1 build` to compile the C++ module. |
| `PowerShell script cannot be loaded` | In PowerShell, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| `Virtual environment not found` | Run `./cli.ps1 setup` first. |
| `Ninja not found` | Install with `pip install ninja` or `choco install ninja`. |
| `CUDA Error: out of memory` | Reduce batch size or close other GPU applications. |
| `FFT size must be power of 2` | Use sizes like 256, 512, 1024, 4096, etc. |

### 🔍 Debugging Checklist

1.  **Verify CUDA Toolkit and Driver**
    Run these commands in your terminal. They should execute without errors.
    ```bash
    nvcc --version
    nvidia-smi
    ```

2.  **Verify the Engine Can Initialize**
    This Python snippet is the best way to confirm the library was built correctly and can communicate with the GPU.
    ```python
    from cuda_lib import CudaFftEngine
    
    try:
        test_engine = CudaFftEngine(nfft=1024, batch=1, verbose=True)
        print("\n✅ CUDA engine initialized successfully!")
    except Exception as e:
        print(f"\n❌ Failed to initialize CUDA engine: {e}")
    ```

3.  **Verify Numerical Accuracy**
    Once the engine initializes, run the accuracy benchmark.
    ```powershell
    ./cli.ps1 bench verify_accuracy --nfft 4096 --batch-size 32
    ```

---

## 📚 Additional Resources

- **CUDA Programming Guide**: [NVIDIA Docs](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)
- **cuFFT Library**: [cuFFT Documentation](https://docs.nvidia.com/cuda/cufft/)
- **CUDA Graphs**: [Graph Optimization Guide](https://developer.nvidia.com/blog/cuda-graphs/)
- **Nsight Systems**: [Profiling Tutorial](https://docs.nvidia.com/nsight-systems/)

---

*Built with ❤️ for high-performance signal processing*
