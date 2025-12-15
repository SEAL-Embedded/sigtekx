# Integrate PyTorch Models as Pipeline Stages with Adaptive Routing (Phase 2 Task 2.3)

## Problem

There is **no ML model integration** in SigTekX pipelines. Scientists cannot inject PyTorch models for hybrid compute (DSP + ML in one pipeline). This limits the innovation scope: "Custom stages" currently means CUDA kernels only, not trained models.

**Roadmap Context** (`docs/development/methods-paper-roadmap.md` Phase 2 Task 2.3):
- Hybrid compute: PyTorch models in pipeline (GPU inference without Python bottleneck)
- Adaptive routing: Fast models (<50µs) run inline, slow models (>100µs) offload to control plane
- Use case: Denoiser models, anomaly detectors, classification in real-time
- Critical for methods paper: demonstrate ML integration with real-time guarantees

**Impact:**
- Cannot demonstrate ML + DSP hybrid pipelines
- Limited to traditional signal processing (no learned features)
- Competitive gap vs frameworks with ML integration (TensorRT-based)
- Missing key use case for ionosphere research (learned anomaly detection)

## Current Implementation

**No PyTorch integration exists.** User would need to:
1. Process with SigTekX pipeline
2. Copy output to CPU
3. Run PyTorch model separately (blocking)
4. Copy result back

This breaks real-time guarantees (Python GIL, CPU↔GPU transfers).

## Proposed Solution

**Create `TorchStage` wrapper with adaptive routing:**

```python
# src/sigtekx/stages/pytorch.py (NEW FILE)
"""PyTorch model integration for hybrid DSP+ML pipelines."""

from typing import Optional
import torch
import torch.nn as nn

class TorchStage:
    """
    Wrapper for PyTorch models in SigTekX pipelines.

    Supports two modes:
    - Inline: Model inference <50µs, runs in data plane
    - Snapshot: Model inference >100µs, offloaded to control plane

    Example:
        >>> class Denoiser(nn.Module):
        >>>     def forward(self, x):
        >>>         return torch.relu(x - 0.1)  # Threshold denoiser
        >>>
        >>> model = Denoiser().cuda().eval()
        >>> pipeline = (PipelineBuilder()
        >>>     .add_fft()
        >>>     .add_torch_model(model, adaptive=True)
        >>>     .add_magnitude()
        >>>     .build())
    """

    def __init__(self,
                 model: nn.Module,
                 adaptive: bool = True,
                 inline_threshold_us: float = 50.0):
        """
        Initialize PyTorch stage.

        Args:
            model: PyTorch model (must be on GPU, in eval mode)
            adaptive: Enable adaptive routing (auto-detect inline vs snapshot)
            inline_threshold_us: Max inference time for inline mode (µs)
        """
        if not isinstance(model, nn.Module):
            raise TypeError(f"Expected torch.nn.Module, got {type(model)}")

        if not next(model.parameters()).is_cuda:
            raise ValueError("Model must be on CUDA device (.cuda())")

        # Convert to TorchScript for faster inference
        self.model = torch.jit.script(model)
        self.model.eval()

        self.adaptive = adaptive
        self.inline_threshold_us = inline_threshold_us
        self.mode = None  # Set during benchmark

        # Benchmark inference time
        if adaptive:
            self._benchmark_inference_time()

    def _benchmark_inference_time(self):
        """Benchmark model inference to determine inline vs snapshot mode."""
        # Create dummy input (assume 1D signal)
        dummy_input = torch.randn(4096, device='cuda')

        # Warmup
        for _ in range(10):
            _ = self.model(dummy_input)

        # Measure
        torch.cuda.synchronize()
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)

        start.record()
        for _ in range(100):
            _ = self.model(dummy_input)
        end.record()
        torch.cuda.synchronize()

        avg_time_us = start.elapsed_time(end) * 1000 / 100  # ms → µs

        # Determine mode
        if avg_time_us < self.inline_threshold_us:
            self.mode = 'inline'
        else:
            self.mode = 'snapshot'

        print(f"TorchStage: {avg_time_us:.1f}µs inference → {self.mode} mode")

    def process(self, input_tensor: torch.Tensor) -> torch.Tensor:
        """
        Process input through PyTorch model.

        Args:
            input_tensor: CUDA tensor from previous stage

        Returns:
            Output tensor (same device)
        """
        with torch.no_grad():
            return self.model(input_tensor)

    def __repr__(self) -> str:
        return f"TorchStage(mode={self.mode}, threshold={self.inline_threshold_us}µs)"
```

```python
# src/sigtekx/core/builder.py (ENHANCED)
from sigtekx.stages.pytorch import TorchStage

class PipelineBuilder:
    # ... existing methods ...

    def add_torch_model(self,
                        model: nn.Module,
                        adaptive: bool = True,
                        inline_threshold_us: float = 50.0) -> Self:
        """
        Add PyTorch model as pipeline stage.

        Args:
            model: PyTorch model (must be .cuda() and .eval())
            adaptive: Auto-detect inline vs snapshot mode
            inline_threshold_us: Max inference time for inline (default: 50µs)

        Returns:
            Self for method chaining

        Example:
            >>> model = MyDenoiser().cuda().eval()
            >>> pipeline = (PipelineBuilder()
            >>>     .add_fft()
            >>>     .add_torch_model(model)
            >>>     .add_magnitude()
            >>>     .build())
        """
        torch_stage = TorchStage(model, adaptive, inline_threshold_us)

        self._stages.append({
            'type': 'torch',
            'stage': torch_stage
        })

        return self
```

## Additional Technical Insights

- **TorchScript Compilation**: Using `torch.jit.script()` eliminates Python overhead (2-5× speedup vs eager mode). Critical for <50µs target.

- **GPU Memory Sharing**: PyTorch tensor shares GPU memory with CUDA arrays (no copy needed). Pass pointer directly from C++ via pybind11.

- **Adaptive Routing**:
  - Inline mode (<50µs): Model runs in data plane, maintains real-time
  - Snapshot mode (>100µs): Copy to snapshot buffer, run in control plane (Issue #009)
  - Threshold configurable per use case

- **Inference Benchmarking**: Auto-measures inference time on init (100 iterations). User can override with `adaptive=False`.

- **Model Export**: For production, export TorchScript to file, load from disk (faster startup).

- **Batch Processing**: If model expects batches, accumulate N frames before inference. Trade latency for throughput.

## Implementation Tasks

- [ ] Create `src/sigtekx/stages/pytorch.py`
- [ ] Implement `TorchStage` class with `__init__()`, `process()`, `_benchmark_inference_time()`
- [ ] Add validation: model is `nn.Module`, on CUDA, in eval mode
- [ ] Implement TorchScript conversion: `torch.jit.script(model)`
- [ ] Implement adaptive routing: benchmark → set mode (inline/snapshot)
- [ ] Add `__repr__()` for debugging
- [ ] Open `src/sigtekx/core/builder.py`
- [ ] Add `add_torch_model()` method to `PipelineBuilder`
- [ ] Import `TorchStage`, `torch.nn` at top
- [ ] Update `pyproject.toml`: add `torch>=2.0` to dependencies
- [ ] Create integration test: `tests/test_pytorch_stage.py`
  - Test: Simple threshold denoiser (inline mode)
  - Test: Complex CNN model (snapshot mode)
  - Test: Model not on CUDA raises ValueError
  - Test: Adaptive routing selects correct mode
- [ ] Create example: `examples/pytorch_denoiser.py`
  - Train simple 1D CNN on synthetic data
  - Insert in pipeline, measure RTF
- [ ] Update documentation: `docs/api/pytorch-integration.md`
- [ ] Build: `./scripts/cli.ps1 build`
- [ ] Test: `./scripts/cli.ps1 test python`
- [ ] Commit: `feat(python): add PyTorch model integration with adaptive routing`

## Edge Cases to Handle

- **Model Not on CUDA**: Raises ValueError with clear message
  - Mitigation: Check `next(model.parameters()).is_cuda` in `__init__()`

- **Model Not in Eval Mode**: Warning (inference may use dropout/batchnorm incorrectly)
  - Mitigation: Call `model.eval()` automatically, log warning if not already in eval

- **TorchScript Compilation Failure**: Some models don't support JIT
  - Mitigation: Catch exception, fall back to eager mode with performance warning

- **Inference Time Varies**: Warm-up vs steady-state, different input sizes
  - Mitigation: Benchmark with representative input size, warmup iterations

- **GPU Memory Exhaustion**: Large models may OOM
  - Mitigation: User responsibility to ensure model fits; provide clear OOM error

## Testing Strategy

**Integration Test (Python):**

```python
# tests/test_pytorch_stage.py
import torch
import torch.nn as nn
from sigtekx import PipelineBuilder

class ThresholdDenoiser(nn.Module):
    """Simple denoiser: ReLU(x - threshold)"""
    def __init__(self, threshold=0.1):
        super().__init__()
        self.threshold = threshold

    def forward(self, x):
        return torch.relu(x - self.threshold)

def test_torch_stage_inline():
    """Test PyTorch stage in inline mode."""
    model = ThresholdDenoiser().cuda().eval()

    pipeline = (PipelineBuilder()
        .add_fft()
        .add_torch_model(model, adaptive=True)
        .add_magnitude()
        .build())

    # Process test signal
    signal = torch.randn(4096, device='cuda')
    result = pipeline.process(signal)

    # Verify model executed (output affected by threshold)
    assert result.shape == (2049,)  # RFFT output

def test_torch_stage_model_not_cuda():
    """Test error for CPU model."""
    model = ThresholdDenoiser()  # Not .cuda()

    with pytest.raises(ValueError, match="must be on CUDA"):
        TorchStage(model)

def test_adaptive_routing():
    """Test adaptive mode selection."""
    fast_model = ThresholdDenoiser().cuda().eval()  # <50µs
    torch_stage = TorchStage(fast_model, adaptive=True)

    assert torch_stage.mode == 'inline'  # Should select inline
```

**Performance Validation:**

```bash
# After Issue #016 (PyTorch validation experiment)
python experiments/pytorch_denoiser.py
# Expected: RTF <0.3 maintained with inline model
```

## Acceptance Criteria

- [ ] `TorchStage` class implemented
- [ ] TorchScript compilation works (`torch.jit.script`)
- [ ] Adaptive routing benchmarks and selects mode
- [ ] `PipelineBuilder.add_torch_model()` method works
- [ ] Integration test passes: threshold denoiser
- [ ] Error handling: model not on CUDA raises ValueError
- [ ] Adaptive routing test: fast model → inline, slow model → snapshot
- [ ] Documentation includes user example
- [ ] Works with PyTorch >= 2.0
- [ ] All Python tests pass

## Benefits

- **Hybrid Compute**: DSP + ML in single real-time pipeline
- **Adaptive Performance**: Fast models inline, slow models async (maintains RTF <0.3)
- **Scientific Productivity**: Insert trained models without C++ rewrite
- **Use Case Enabled**: Learned anomaly detection for ionosphere research
- **Methods Paper Ready**: Demonstrates ML integration innovation
- **Competitive Feature**: Matches TensorRT-based frameworks (but Python-native)

---

**Labels:** `feature`, `team-3-python`, `team-4-research`, `python`, `architecture`

**Estimated Effort:** 6-8 hours (PyTorch/CUDA interop, adaptive routing, testing)

**Priority:** High (Hybrid Compute - Phase 2 Task 2.3)

**Roadmap Phase:** Phase 2 (v0.9.7)

**Dependencies:** Issue #005 (CustomStage foundation)

**Blocks:** Issue #016 (PyTorch validation experiment)
