# Validate PyTorch Denoiser Integration with Inference Benchmarks (Phase 4 Task 4.5)

## Problem

We need to **demonstrate ML model integration works** and validate the inference time threshold (inline <50µs or snapshot mode >100µs). Without experimental validation, the hybrid compute claim lacks scientific evidence.

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 4 Task 4.5):
- Train simple 1D CNN denoiser on synthetic data
- Insert in pipeline: FFT → Denoiser → Magnitude
- Measure inference time, verify RTF <0.3 maintained
- Success: Inline if <50µs, else snapshot mode works

**Impact:**
- Cannot prove hybrid compute capability (DSP + ML in one pipeline)
- PyTorch integration unvalidated (may have unacceptable overhead)
- Missing demonstration for methods paper (ML use case)

## Current Implementation

**No PyTorch validation experiment exists.** Issue #007 (PyTorch integration) must be completed first.

## Proposed Solution

**Create experiment with trained denoiser model:**

```python
# experiments/pytorch_denoiser.py (NEW FILE)
"""
PyTorch denoiser integration experiment.

Trains simple 1D CNN denoiser, inserts in pipeline, validates:
- Inference time (<50µs for inline, >100µs for snapshot)
- RTF maintained (<0.3)
- Accuracy improvement (SNR increase)
"""

import time
import torch
import torch.nn as nn
import numpy as np
from sigtekx import PipelineBuilder, EngineConfig
from sigtekx.benchmarks.utils import lock_gpu_clocks, unlock_gpu_clocks


class Simple1DDenoiser(nn.Module):
    """
    Simple 1D CNN denoiser for spectral data.

    Architecture: Conv1D → ReLU → Conv1D
    Input: Noisy magnitude spectrum
    Output: Denoised spectrum
    """

    def __init__(self, in_channels=1, hidden_channels=32):
        super().__init__()
        self.conv1 = nn.Conv1d(in_channels, hidden_channels, kernel_size=5, padding=2)
        self.relu = nn.ReLU()
        self.conv2 = nn.Conv1d(hidden_channels, in_channels, kernel_size=5, padding=2)

    def forward(self, x):
        """
        Forward pass.

        Args:
            x: Input tensor (batch, channels, length) or (length,)

        Returns:
            Denoised output (same shape as input)
        """
        # Handle 1D input (add batch and channel dims)
        if x.dim() == 1:
            x = x.unsqueeze(0).unsqueeze(0)  # (length,) → (1, 1, length)
            squeeze_output = True
        else:
            squeeze_output = False

        # Denoise
        out = self.conv1(x)
        out = self.relu(out)
        out = self.conv2(out)

        # Remove batch/channel dims if input was 1D
        if squeeze_output:
            out = out.squeeze(0).squeeze(0)

        return out


def generate_synthetic_data(num_samples=1000, nfft=4096):
    """
    Generate synthetic noisy spectral data.

    Args:
        num_samples: Number of training samples
        nfft: FFT size

    Returns:
        (clean_data, noisy_data) tensors
    """
    # Clean signal: sum of sinusoids
    clean = []
    for _ in range(num_samples):
        signal = np.zeros(nfft)
        for freq in [100, 500, 1200]:
            signal += np.sin(2 * np.pi * freq * np.arange(nfft) / nfft)
        clean.append(np.abs(np.fft.rfft(signal)))

    clean = torch.tensor(np.array(clean), dtype=torch.float32)

    # Add noise
    noise = torch.randn_like(clean) * 0.5
    noisy = clean + noise

    return clean, noisy


def train_denoiser(model, num_epochs=50):
    """
    Train denoiser on synthetic data.

    Args:
        model: Denoiser model
        num_epochs: Training epochs

    Returns:
        Trained model
    """
    print("Generating synthetic training data...")
    clean, noisy = generate_synthetic_data(num_samples=1000)

    # Move to GPU
    model = model.cuda()
    clean = clean.cuda()
    noisy = noisy.cuda()

    # Training setup
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.MSELoss()

    print(f"Training denoiser ({num_epochs} epochs)...")
    for epoch in range(num_epochs):
        optimizer.zero_grad()

        # Add channel dimension
        noisy_input = noisy.unsqueeze(1)  # (batch, 1, length)

        # Forward pass
        output = model(noisy_input)

        # Compute loss
        loss = criterion(output.squeeze(1), clean)

        # Backward pass
        loss.backward()
        optimizer.step()

        if (epoch + 1) % 10 == 0:
            print(f"  Epoch {epoch+1}/{num_epochs}, Loss: {loss.item():.6f}")

    print("Training complete")
    return model


def benchmark_inference_time(model, nfft=4096, iterations=1000):
    """
    Benchmark model inference time.

    Args:
        model: Trained denoiser
        nfft: Input size
        iterations: Number of iterations

    Returns:
        Mean inference time (µs)
    """
    model.eval()

    # Dummy input
    input_data = torch.randn(nfft // 2 + 1, device='cuda')

    # Warmup
    with torch.no_grad():
        for _ in range(100):
            _ = model(input_data)

    torch.cuda.synchronize()

    # Benchmark
    start = time.perf_counter()

    with torch.no_grad():
        for _ in range(iterations):
            _ = model(input_data)

    torch.cuda.synchronize()
    end = time.perf_counter()

    mean_time_us = (end - start) / iterations * 1e6

    return mean_time_us


def test_pipeline_with_denoiser(model):
    """
    Test pipeline with denoiser stage.

    Args:
        model: Trained denoiser

    Returns:
        Mean RTF
    """
    pipeline = (PipelineBuilder()
        .add_window('hann')
        .add_fft()
        .add_torch_model(model, adaptive=True)
        .add_magnitude()
        .build())

    config = EngineConfig(nfft=4096, channels=1, overlap=0.75, mode='streaming')
    engine = Engine(config)

    # Run for 5 seconds
    hop_size = int(4096 * (1 - 0.75))
    sample_rate = 32000
    frame_period_s = hop_size / sample_rate

    rtf_samples = []
    start_time = time.time()

    while time.time() - start_time < 5.0:
        frame_start = time.perf_counter()
        _ = engine.process_frame()
        frame_end = time.perf_counter()

        rtf = (frame_end - frame_start) / frame_period_s
        rtf_samples.append(rtf)

    return np.mean(rtf_samples)


def main():
    """Run PyTorch denoiser validation."""
    print("=" * 80)
    print("PyTorch Denoiser Integration Validation")
    print("=" * 80)
    print()

    # Lock GPU clocks
    print("Locking GPU clocks...")
    lock_gpu_clocks()

    try:
        # Train denoiser
        model = Simple1DDenoiser(in_channels=1, hidden_channels=32)
        model = train_denoiser(model, num_epochs=50)

        # Convert to TorchScript (faster inference)
        print("\nConverting to TorchScript...")
        model = torch.jit.script(model)
        model.eval()

        # Benchmark inference time
        print("\nBenchmarking inference time...")
        inference_time_us = benchmark_inference_time(model, nfft=4096, iterations=1000)
        print(f"Mean inference time: {inference_time_us:.2f} µs")

        # Determine mode
        if inference_time_us < 50.0:
            mode = "inline"
            print("✓ Inference <50µs → INLINE mode (data plane)")
        elif inference_time_us < 100.0:
            mode = "medium"
            print("⚠ Inference 50-100µs → MEDIUM (marginal)")
        else:
            mode = "snapshot"
            print("✓ Inference >100µs → SNAPSHOT mode (control plane)")

        # Test pipeline with denoiser
        print(f"\nTesting pipeline with denoiser ({mode} mode)...")
        rtf = test_pipeline_with_denoiser(model)
        print(f"Mean RTF: {rtf:.4f}")

        print()
        print("=" * 80)
        print("Results:")
        print("-" * 80)
        print(f"Inference time:  {inference_time_us:.2f} µs")
        print(f"Mode selected:   {mode}")
        print(f"Pipeline RTF:    {rtf:.4f}")
        print("-" * 80)

        # Verdict
        if rtf < 0.3:
            print("✓ SUCCESS: RTF <0.3 maintained with PyTorch model")
        elif rtf < 0.4:
            print("⚠ ACCEPTABLE: RTF <0.4 (close to target)")
        else:
            print("✗ FAILURE: RTF >0.4 (model too slow)")

    finally:
        print("\nUnlocking GPU clocks...")
        unlock_gpu_clocks()


if __name__ == "__main__":
    main()
```

## Additional Technical Insights

- **TorchScript**: Converting to `torch.jit.script` reduces inference time by 2-5× (eliminates Python overhead)

- **Model Size**: Small model (1D CNN, 32 hidden channels) targets <50µs. Larger models use snapshot mode.

- **SNR Improvement**: Compare SNR before/after denoiser (should increase by 3+ dB)

## Implementation Tasks

- [ ] Create `experiments/pytorch_denoiser.py`
- [ ] Implement `Simple1DDenoiser` model (1D CNN)
- [ ] Implement `generate_synthetic_data()` (clean + noisy spectral data)
- [ ] Implement `train_denoiser()` (Adam optimizer, MSE loss)
- [ ] Implement `benchmark_inference_time()` (1000 iterations)
- [ ] Implement `test_pipeline_with_denoiser()` (RTF measurement)
- [ ] Add TorchScript conversion (`torch.jit.script`)
- [ ] Add mode selection logic (<50µs inline, >100µs snapshot)
- [ ] Run experiment: `python experiments/pytorch_denoiser.py`
- [ ] Verify: RTF <0.3 maintained
- [ ] Compute SNR improvement (compare with/without denoiser)
- [ ] Update documentation: `docs/experiments/pytorch-integration.md`
- [ ] Commit: `feat(experiments): add PyTorch denoiser validation`

## Edge Cases to Handle

- **Model Too Slow**: Inference >100µs
  - Mitigation: Use snapshot mode (control plane offload)

- **TorchScript Conversion Failure**: Some models don't support JIT
  - Mitigation: Fall back to eager mode, accept slower inference

- **GPU Memory Exhaustion**: Model too large
  - Mitigation: Document model size limits, use smaller architecture

## Testing Strategy

```bash
# Run experiment
python experiments/pytorch_denoiser.py

# Expected output:
# Generating synthetic training data...
# Training denoiser (50 epochs)...
#   Epoch 10/50, Loss: 0.085423
#   Epoch 50/50, Loss: 0.012345
# Converting to TorchScript...
# Benchmarking inference time...
# Mean inference time: 38.45 µs
# ✓ Inference <50µs → INLINE mode (data plane)
#
# Testing pipeline with denoiser (inline mode)...
# Mean RTF: 0.28
#
# Results:
# Inference time:  38.45 µs
# Mode selected:   inline
# Pipeline RTF:    0.28
# ✓ SUCCESS: RTF <0.3 maintained with PyTorch model
```

## Acceptance Criteria

- [ ] `Simple1DDenoiser` model implemented
- [ ] Training on synthetic data works
- [ ] TorchScript conversion works
- [ ] Inference time measured (<50µs or >100µs)
- [ ] Adaptive mode selection works (inline vs snapshot)
- [ ] Pipeline RTF <0.3 maintained
- [ ] SNR improvement measured (≥3dB)
- [ ] Documentation includes results
- [ ] All tests pass

## Benefits

- **Hybrid Compute Validated**: DSP + ML in real-time pipeline proven
- **Adaptive Routing Demonstrated**: Fast models inline, slow models snapshot
- **Methods Paper Ready**: PyTorch integration use case
- **User Confidence**: ML researchers understand integration capabilities

---

**Labels:** `task`, `team-4-research`, `python`, `research`

**Estimated Effort:** 6-8 hours (model training, inference benchmarking)

**Priority:** Medium (Demonstrates ML integration, not critical for v1.0)

**Roadmap Phase:** Phase 4 (v1.0)

**Dependencies:** Issue #007 (PyTorch integration)

**Blocks:** None (validation task)
