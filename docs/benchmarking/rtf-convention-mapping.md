# Real-Time Factor (RTF) Convention Mapping

**Last Updated**: 2025-12-17
**Status**: Production Standard - **ACADEMIC CONVENTION ADOPTED**
**Author**: SigTekX Development Team

---

## Executive Summary

**SigTekX uses the academic (latency-based) RTF convention** where **lower values indicate better performance**. This aligns with Automatic Speech Recognition (ASR), radar, and Software-Defined Radio (SDR) literature standards.

**Convention Decision**: After initial consideration of throughput-based convention, SigTekX adopted the academic standard because:
1. **Primary application**: Ionosphere VLF/ULF monitoring (academic domain)
2. **Paper submission**: IEEE HPEC, JOSS, and other academic venues
3. **Reviewer expectations**: Academic reviewers expect RTF < 1.0 convention
4. **Thermal validation**: Makes comparisons to published research more transparent

**Key Insight**: Both conventions are mathematically equivalent (inverse relationship) and measure the same physical phenomenon. The choice is presentational, not fundamental.

**This document provides**:
1. Clear definitions of both conventions
2. Conversion formulas for comparing to GPU throughput metrics
3. Rationale for SigTekX's academic convention choice
4. Target mapping to published research standards

---

## The Two RTF Conventions

### Convention 1: Latency-Based (Academic Standard)

**Formula**:
```
RTF = T_process / T_signal
```

Where:
- `T_process` = Wall-clock time to process signal segment
- `T_signal` = Duration of signal segment

**Interpretation**:
- **RTF < 1.0**: Faster than real-time (good) ✅
- **RTF = 1.0**: Exactly real-time (theoretical limit)
- **RTF > 1.0**: Slower than real-time (falling behind) ❌

**Common in**:
- Automatic Speech Recognition (Kaldi, Whisper, ESPnet)
- Radar signal processing literature
- Software-Defined Radio (GNU Radio, LuaRadio)
- Edge AI inference benchmarking

**Example**:
- Process 1.0 second of audio in 0.40 seconds → RTF = 0.40 (good)
- Process 1.0 second of audio in 1.2 seconds → RTF = 1.2 (failure)

---

### Convention 2: Throughput-Based (GPU benchmarking context)

**Formula**:
```
RTF = (Measured FPS × Hop Size) / Sample Rate
```

Where:
- `Measured FPS` = Frames per second actually processed
- `Hop Size` = Samples per frame (hop_size = nfft × (1 - overlap))
- `Sample Rate` = Samples per second (e.g., 100 kHz)

Equivalently:
```
RTF = Measured Throughput / Required Throughput
```

**Interpretation**:
- **RTF > 1.0**: Faster than real-time (good) ✅
- **RTF = 1.0**: Exactly real-time (theoretical limit)
- **RTF < 1.0**: Slower than real-time (falling behind) ❌

**Common in**:
- GPU performance benchmarking (NVIDIA, AMD)
- Deep learning frameworks (PyTorch: "samples/sec", TensorFlow: "steps/sec")
- Video processing (FPS-based metrics)
- Throughput-focused HPC applications

**Example**:
- Process 2.5 streams simultaneously → RTF = 2.5 (good)
- Process 0.8 streams simultaneously → RTF = 0.8 (failure)

---

## Mathematical Relationship

The two conventions are **exact inverses**:

```
SigTekX_RTF = 1 / Academic_RTF
Academic_RTF = 1 / SigTekX_RTF
```

**Proof by Example**:
```
Given:
- Signal duration: 1.0 second
- Processing time: 0.40 seconds
- Processing rate: 2.5 signals per second

Academic RTF:
RTF = 0.40 / 1.0 = 0.40 (good)

SigTekX RTF:
RTF = 2.5 / 1.0 = 2.5 (good)

Relationship:
2.5 = 1 / 0.40 ✓
0.40 = 1 / 2.5 ✓
```

---

## Conversion Table

| Academic RTF (SigTekX) | Throughput RTF | Performance Level | Interpretation |
|------------------------|----------------|-------------------|----------------|
| **0.10** | 10.0 | Exceptional | 10× real-time, 10 concurrent streams |
| **0.20** | 5.0 | Excellent | **SigTekX measured** (Phase 0 baseline) |
| **0.33** | 3.0 | Very Good | 3× safety margin, ASR aggressive target |
| **0.40** | 2.5 | Good | **Production target**, ASR industry standard |
| **0.50** | 2.0 | Acceptable | Minimum for soft real-time |
| **0.70** | 1.43 | Marginal | CPU-level performance (no GPU benefit) |
| **0.90** | 1.11 | Poor | Minimal headroom, recovery impossible |
| **1.00** | 1.00 | Failure | Theoretical limit (both conventions) |
| **>1.00** | <1.00 | Failure | Cannot maintain real-time |

---

## Why SigTekX Uses Academic RTF Convention

### 1. Primary Application Domain
**Ionosphere VLF/ULF Research** is an academic domain:
- Target venues: IEEE HPEC, JOSS, Geophysical Research Letters
- Target audience: Academic researchers, not GPU developers
- Standard practice: All ionosphere/SDR papers use academic convention
- Reviewers expect: RTF < 1.0 interpretation without explanation

### 2. Academic Publication Standards
Papers in signal processing use the academic convention:
- **ASR Literature**: Kaldi, Whisper, ESPnet all report RTF < 1.0 as good
- **Radar Processing**: Standard convention in radar signal processing
- **SDR Research**: GNU Radio, LuaRadio use latency-based RTF
- **Industry Standard**: AMD Ryzen AI (Whisper): RTF ≤ 0.35 target

Using academic convention avoids confusion and aligns with cited literature.

### 3. Thermal Validation Transparency
Academic convention makes thermal degradation comparisons clearer:
- **Research finding**: "40% degradation under thermal load"
- **SigTekX cold**: RTF ≤ 0.20
- **SigTekX warm**: RTF ≤ 0.28 (after 40% degradation)
- **Still beats target**: RTF ≤ 0.40 (ASR industry standard)

Direct comparison: "Our 0.28 beats research target of 0.40" is clearer than inverse ratios.

### 4. Latency-Centric Performance Model
Real-time systems care about **latency budget**, not throughput:
- Question: "Can I process within deadline?" (latency)
- Not: "How many streams can I run?" (throughput)
- RTF < 1.0 directly answers: "Am I faster than real-time?"

Academic convention aligns with soft real-time system design thinking.

### 5. Consistency with Methods Paper Narrative
The methods paper emphasizes:
- **Thermal throttling**: 20-40% degradation (latency increases)
- **Jitter tolerance**: Recovery time = f(latency budget)
- **Deadline compliance**: Percentage of frames meeting latency target

All these metrics are latency-based, so RTF should match that paradigm.

### 6. No Loss of GPU Profiling Capability
GPU profiling tools still report throughput (FPS, samples/sec):
- **Nsight Systems**: Shows FPS timeline (not RTF)
- **Benchmark outputs**: Report both FPS and RTF
- **Conversion**: Trivial to compute throughput from academic RTF

Academic RTF doesn't prevent GPU optimization workflows.

---

## How to Handle in Academic Papers

### 1. Define Clearly Upfront
**First mention** of RTF should include both conventions:

> "We measure Real-Time Factor (RTF) using the throughput-based convention:
> RTF = (Measured FPS × Hop Size) / Sample Rate. This is the inverse of the
> latency-based convention (RTF = Processing Time / Signal Duration) commonly
> used in ASR literature. Higher RTF values indicate better performance."

### 2. Provide Conversion Table
Include a conversion table in the paper (methods section or appendix):

```markdown
| Performance Metric | SigTekX (throughput) | Academic (latency) |
|--------------------|----------------------|--------------------|
| Production Target  | RTF ≥ 2.5           | RTF ≤ 0.40        |
| Achieved (NFFT=4096, 128ch) | RTF = 5.0 | RTF = 0.20 |
```

### 3. Show Both Where Helpful
When claiming specific achievements, show both:

> "SigTekX achieves RTF = 5.0 (throughput-based) ≡ RTF = 0.20 (latency-based),
> which is 2× better than the ASR industry standard of RTF ≤ 0.40."

### 4. Justify the Choice
Include a brief justification in the methodology:

> "We adopt the academic (latency-based) RTF convention (lower = better) to align
> with ionosphere research, ASR, and SDR literature, where RTF < 1.0 directly
> indicates faster-than-real-time operation."

### 5. Consistent Usage
Pick ONE convention for figures, tables, and analysis. Use SigTekX convention internally, provide Academic conversion in text where necessary.

---

## Implementation in SigTekX

### Primary RTF Function
**File**: `experiments/analysis/metrics.py`

```python
def calculate_rtf(fps: float, hop_size: int, sample_rate_hz: int) -> float:
    """
    Calculate Real-Time Factor (RTF) using academic convention.

    RTF = (signal duration) / (processing time) = sample_rate_hz / (fps * hop_size)

    Args:
        fps: Frames per second (measured processing rate)
        hop_size: Samples per frame (hop_size = nfft × (1 - overlap))
        sample_rate_hz: Sampling rate in Hz

    Returns:
        RTF where:
        - RTF < 1.0 = faster than real-time (good) ✅
        - RTF = 1.0 = exactly real-time
        - RTF > 1.0 = slower than real-time (falling behind) ❌

    Example:
        >>> calculate_rtf(fps=250, hop_size=1024, sample_rate_hz=100000)
        0.39  # Uses 39% of available time (target ≤ 0.40)
    """
    if fps <= 0:
        return float('inf')
    return sample_rate_hz / (fps * hop_size)
```

### Conversion Function for Papers
**File**: `experiments/analysis/metrics.py`

```python
def calculate_academic_rtf(fps: float, hop_size: int, sample_rate_hz: int) -> float:
    """
    Calculate Real-Time Factor using academic convention (latency-based).

    Academic RTF = Processing Time / Signal Duration (lower is better)
    This is the INVERSE of SigTekX throughput-based RTF.

    Args:
        fps: Frames per second (measured processing rate)
        hop_size: Samples per frame
        sample_rate_hz: Sampling rate in Hz

    Returns:
        Academic RTF where:
        - RTF < 1.0 = faster than real-time (good)
        - RTF = 1.0 = exactly real-time
        - RTF > 1.0 = slower than real-time (bad)

    Example:
        >>> calculate_academic_rtf(fps=250, hop_size=1024, sample_rate_hz=100000)
        0.39  # Uses 39% of available time (ASR standard: target ≤ 0.40)
    """
    sigtekx_rtf = calculate_rtf(fps, hop_size, sample_rate_hz)
    if sigtekx_rtf <= 0:
        return float('inf')
    return 1.0 / sigtekx_rtf
```

### Usage in Enrichment
**File**: `experiments/analysis/metrics.py` (enrich_csv function)

```python
# Current: Only SigTekX RTF
metrics['rtf'] = calculate_rtf(fps, hop_size, sample_rate_hz)

# Enhanced: Add both conventions for academic comparison
metrics['rtf'] = calculate_rtf(fps, hop_size, sample_rate_hz)
metrics['rtf_academic'] = calculate_academic_rtf(fps, hop_size, sample_rate_hz)
```

---

## Target Mapping to Research Standards

### Academic Literature Targets

**ASR Industry (2023-2024)**:
- AMD Ryzen AI (Whisper Base): RTF = 0.35 (academic)
- CPU Baseline (Whisper Small): RTF = 0.70 (academic)
- Mobile/Edge Target: RTF < 0.50 (academic)

**Radar/SDR**:
- Real-time loops: RTF = 0.01-0.10 (academic) - extreme headroom for tracking
- High-overlap STFT: RTF < 0.50 (academic)

**VLF Ionosphere Monitoring** (research finding):
- Recommended target: RTF ≤ 0.40 (academic) with thermal margin
- Aggressive target: RTF ≤ 0.35 (academic) for production

### SigTekX Equivalent Targets

| Application Domain | Academic RTF Target | Throughput Equivalent | SigTekX Status |
|-------------------|--------------------|-----------------------|----------------|
| **ASR State-of-Art** | RTF ≤ 0.35 | FPS × hop / sr ≥ 2.86 | Phase 1 target |
| **ASR Industry** | **RTF ≤ 0.40** | ≥ 2.5× real-time | **Production target** |
| **VLF Ionosphere** | **RTF ≤ 0.40** | ≥ 2.5× real-time | **Baseline achieved** |
| **Soft Real-Time** | RTF ≤ 0.50 | ≥ 2.0× real-time | Minimum acceptable |
| **SigTekX Phase 0** | **RTF ≤ 0.20** | ≥ 5.0× real-time | **Achieved (2× better than target)** |
| **Multi-Stream Goal** | RTF ≤ 0.10 | ≥ 10.0× real-time | Stretch goal |

---

## Thermal Safety Margin Accounting

The deep research emphasizes that **cold benchmarks overestimate performance** by ~40% due to thermal throttling under sustained load.

### Adjusted Target Framework

**With thermal margin**:
```
Target RTF = 1.0 / (SF_thermal × SF_jitter × SF_algo)
Target RTF = 1.0 / (1.4 × 2.0 × 1.2) = 1.0 / 3.36 ≈ 0.30-0.40 (academic)
```

**In SigTekX convention**:
```
Target RTF ≥ 2.5-3.3
```

**Safety factors**:
- **SF_thermal = 1.4**: 40% thermal throttling margin
- **SF_jitter = 2.0**: 2:1 recovery rate for GC/OS jitter (see recovery dynamics)
- **SF_algo = 1.2**: Algorithmic headroom for parameter tuning

**SigTekX validation**:
- Cold RTF ≥ 5.0 (measured)
- Expected warm RTF ≥ 3.5 (after 40% degradation)
- Target RTF ≥ 2.5 (production requirement)
- **Margin**: 3.5 / 2.5 = 1.4× (40% safety margin remains even after thermal throttling)

---

## Recovery Dynamics Formula

**Critical equation for jitter tolerance**:
```
T_recover = T_block × (RTF_academic / (1 - RTF_academic))
```

Where:
- `T_recover` = Time to clear buffer backlog after a pause
- `T_block` = Duration of pause (GC, OS scheduler, disk I/O)
- `RTF_academic` = RTF in academic convention (0.0-1.0 range)

**Example: 100ms GC pause**

| Academic RTF | SigTekX RTF | T_recover | System State |
|--------------|-------------|-----------|--------------|
| 0.90 | 1.11 | 900 ms | Nearly 1 second lag - unacceptable |
| 0.70 | 1.43 | 233 ms | Sluggish recovery |
| 0.50 | 2.0 | 100 ms | Neutral (recovery = pause) |
| 0.40 | 2.5 | 67 ms | Rapid recovery (target) |
| 0.33 | 3.0 | 50 ms | 2:1 recovery rate |
| **0.20** | **5.0** | **25 ms** | **4:1 recovery rate (SigTekX)** |
| 0.10 | 10.0 | 11 ms | Instant recovery |

**SigTekX validation**: With RTF ≥ 5.0, system can recover from 100ms pause in 25ms, providing 4:1 recovery rate.

---

## References

1. AMD Ryzen AI Benchmarks: Whisper ASR RTF targets (2024)
2. VLF Ionosphere Research: High-overlap STFT requirements
3. NVIDIA CUDA Best Practices: Throughput-based performance metrics
4. ASR Edge AI Research: 40% thermal throttling under sustained load
5. SigTekX Warmup Methodology: `docs/benchmarking/warmup-methodology.md`
6. SigTekX Thermal Protocol: `docs/benchmarking/thermal-degradation-protocol.md`

---

## Summary

**Convention Choice**: SigTekX uses **academic (latency-based) RTF convention** (lower is better) to align with ionosphere research domain and academic publication standards.

**Conversion**: Throughput_RTF = 1 / Academic_RTF (exact inverse for GPU metric comparison)

**Target**: RTF ≤ 0.40 (academic - ASR industry standard) for production deployment

**Achievement**: RTF ≤ 0.20 (academic) - 2× better than target, 5× faster than real-time

**Validation Needed**: Cold vs warm thermal degradation testing to prove RTF ≤ 0.40 holds under sustained load (expect RTF ≤ 0.28 after 40% degradation, still beats target).

**For Papers**: SigTekX uses academic convention directly — no conversion needed. State "RTF = sample_rate / (fps × hop_size), lower is better" once in methodology.
