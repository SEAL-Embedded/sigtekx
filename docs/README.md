# SigTekX - Documentation

Comprehensive documentation for the sigtekx CUDA-accelerated FFT processing library.

---

## Quick Navigation

### Getting Started
- [Installation Guide](getting-started/install.md) - Environment setup for Windows and Linux
- [Workflow Guide](getting-started/workflow-guide.md) - Development workflow and CLI usage

### Reference
- [API Reference](reference/api-reference.md) - Complete Python API documentation
- [Configuration Guide](reference/configuration.md) - EngineConfig and StageConfig reference
- [Benchmarking Guide](benchmarking/) - Performance testing and profiling

### Architecture & Design
- [Architecture Overview](architecture/overview.md) - System design and components
- **[Executor Architecture](architecture/executors.md)** - BatchExecutor vs StreamingExecutor deep dive
- [Project Structure](architecture/project-structure.md) - Codebase organization
- [Python Package Structure](architecture/python-package-structure.md) - Python package reading order
- **[Thread Safety](architecture/thread-safety.md)** - Multi-threading guide and thread safety guarantees
- [Architecture Diagrams](diagrams/) - Visual system documentation

### Performance & Optimization
- **[Stability Improvements](performance/stability-improvements.md)** - Executive summary of CV reduction journey
- [GPU Clock Locking](performance/gpu-clock-locking.md) - Benchmark stability guide (CV: 40% → 18.72%)
- [Benchmark Timing Strategies](performance/benchmark-timing-strategies.md) - Technical deep-dive into timing optimization

### Technical Notes
- [IEEE754 Compliance](technical-notes/ieee754-compliance.md) - Floating-point accuracy validation
- [Buffer Synchronization Fix](technical-notes/buffer-synchronization-fix.md) - Multi-buffer pipeline synchronization
- [Thread Safety Audit v0.9.3](technical-notes/thread-safety-audit-v0.9.3.md) - Comprehensive thread safety analysis
- [Spectrogram Pipeline Guide](technical-notes/spectrogram-pipeline-guide.md) - STFT pipeline walkthrough

---

## Recommended Reading Order

### For Users / Researchers
1. [Installation](getting-started/install.md)
2. [Workflow Guide](getting-started/workflow-guide.md)
3. [API Reference](reference/api-reference.md)
4. [Benchmarking](benchmarking/)

### For Technical Recruiters / Hiring Managers
1. [Architecture Overview](architecture/overview.md)
2. [Project Structure](architecture/project-structure.md)
3. [Executor Architecture](architecture/executors.md)
4. [Ring Buffer Optimization](performance/ring-buffer-optimization-results.md)

### For JOSS Reviewers / Academic Evaluators
1. [Architecture Overview](architecture/overview.md)
2. [Executor Architecture](architecture/executors.md)
3. [IEEE754 Compliance](technical-notes/ieee754-compliance.md)
4. [Experiment Guide](benchmarking/experiment-guide.md)
5. [Stability Improvements](performance/stability-improvements.md)

### For Contributors
See [CONTRIBUTING.md](../CONTRIBUTING.md) at repo root.

---

## Documentation Categories

### Getting Started
Everything needed to install and start using the library.

**Key Topics**:
- Environment setup (Conda, CUDA, dependencies)
- Quick start examples
- Development workflow
- CLI usage

**Files**: `getting-started/`

---

### Reference
Comprehensive guides for using the library effectively.

**Key Topics**:
- Python API reference
- Benchmarking and profiling
- Configuration reference

**Files**: `reference/`

---

### Architecture & Design
System design, structure, and visual documentation.

**Key Topics**:
- High-level architecture
- **Executor deep dive** (BatchExecutor vs StreamingExecutor)
- Component interactions
- Codebase organization
- **Thread safety and multi-threading**
- Visual diagrams

**Files**: `architecture/`

---

### Benchmarking & Experiments
Comprehensive experiment taxonomy and benchmarking methodology.

**Key Topics**:
- **Experiment design** (26 experiments, zero redundancy)
- Experiment selection guide (quick vs deep, mode separation)
- Sample rate strategies (100kHz vs 48kHz)
- Ionosphere research experiments
- Baseline performance experiments

**Files**: `benchmarking/`

**Highlights**:
- [experiment-guide.md](benchmarking/experiment-guide.md) - Complete experiment taxonomy and selection guide
- [warmup-methodology.md](benchmarking/warmup-methodology.md) - Warmup iteration methodology
- [rtf-convention-mapping.md](benchmarking/rtf-convention-mapping.md) - Real-Time Factor conventions
- [thermal-degradation-protocol.md](benchmarking/thermal-degradation-protocol.md) - GPU thermal testing

---

### Performance & Optimization
Detailed performance analysis and optimization strategies.

**Key Topics**:
- **Benchmark stability** (CV reduction from 40% → 18.72%)
- GPU clock locking for reproducible results
- Timing strategies (GPU events vs CPU timing)
- Warmup iterations and outlier filtering

**Files**: `performance/`

**Highlights**:
- [stability-improvements.md](performance/stability-improvements.md) - Executive summary of 4-phase optimization
- [gpu-clock-locking.md](performance/gpu-clock-locking.md) - Production-ready guide with validated results
- [benchmark-timing-strategies.md](performance/benchmark-timing-strategies.md) - Technical deep-dive

---

### Technical Notes
Detailed technical documentation on specific features and fixes.

**Key Topics**:
- IEEE754 compliance validation
- Buffer synchronization patterns
- **Thread safety audit and analysis**
- Architecture decisions
- Implementation details

**Files**: `technical-notes/`

---

## Quick Links

### Common Tasks

**Run a Benchmark**:
```powershell
# Quick test
sigxc bench

# Production latency benchmark with clock locking
sigxc bench --preset latency --full --ionosphere --lock-clocks
```

**Profile Performance**:
```powershell
# Nsight Systems profiling
sxp nsys latency --stats

# Nsight Compute kernel analysis
sxp ncu latency --set roofline
```

**Save Baseline**:
```powershell
sigxc bench --preset latency --full --lock-clocks --save-dataset
```

**View Documentation**:
- Start with: [Stability Improvements](performance/stability-improvements.md)
- For setup: [Installation Guide](getting-started/install.md)
- For API: [API Reference](reference/api-reference.md)

---

## Key Achievements

### Benchmark Stability
**Final CV: 18.72%** (down from 40% - 53% improvement)

| Phase | Implementation | Result |
|-------|----------------|--------|
| Phase 1 | Blocking sync | 26% better |
| Phase 2 | Hybrid timing | 33% better |
| Phase 3 | Warmup + outliers | 31% better |
| Phase 4 | GPU clock locking | 24% better |

**Total**: 40% CV → **18.72%** = Production-ready!

See [Stability Improvements](performance/stability-improvements.md) for full story.

---

## Search & Navigation Tips

**By Topic**:
- **Installation** → `getting-started/install.md`
- **API Usage** → `reference/api-reference.md`
- **Experiments** → `benchmarking/experiment-guide.md` (26 experiments explained!)
- **Benchmarking** → `benchmarking/` or `performance/`
- **Performance** → `performance/stability-improvements.md` (start here!)
- **Executors** → `architecture/executors.md` (BatchExecutor vs StreamingExecutor)
- **Thread Safety** → `architecture/thread-safety.md`
- **Architecture** → `architecture/overview.md`
- **Contributing** → `../CONTRIBUTING.md`

**By File Type**:
- **Reference**: `reference/`
- **Technical Details**: `technical-notes/`
- **Performance**: `performance/`
- **Diagrams**: `diagrams/`

**By Audience**:
- **Users**: Start in `getting-started/`
- **Contributors**: See `../CONTRIBUTING.md`
- **Researchers**: Check `performance/` folder
- **Architects**: See `architecture/`

---

## External Resources

- [CUDA Programming Guide](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)
- [NVIDIA Nsight Systems](https://developer.nvidia.com/nsight-systems)
- [NVIDIA System Management Interface](https://developer.nvidia.com/nvidia-system-management-interface)
- [IEEE 754 Floating-Point Standard](https://ieeexplore.ieee.org/document/8766229)

---

**Need Help?**
- Check the [Installation Guide](getting-started/install.md) first
- Read the [API Reference](reference/api-reference.md) for usage examples
- See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines and issue reporting
