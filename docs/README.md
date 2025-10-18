# Ionosense HPC - Documentation

Comprehensive documentation for the ionosense-hpc CUDA-accelerated FFT processing library.

---

## 📚 Quick Navigation

### Getting Started
- [Installation Guide](getting-started/install.md) - Environment setup for Windows and Linux
- [Workflow Guide](getting-started/workflow-guide.md) - Development workflow and CLI usage

### User Guides
- [API Reference](guides/api-reference.md) - Complete Python API documentation
- [Benchmarking Guide](guides/benchmarking.md) - Performance testing and profiling
- [Development Guide](guides/development.md) - Contributing and development workflow
- [Contributing Guidelines](guides/contributing.md) - How to create issues and pull requests

### Architecture & Design
- [Architecture Overview](architecture/overview.md) - System design and components
- [Project Structure](architecture/project-structure.md) - Codebase organization
- [Python Package Structure](architecture/python-package-structure.md) - Python package reading order
- **[Thread Safety](architecture/thread-safety.md)** - Multi-threading guide and thread safety guarantees
- [Architecture Diagrams](architecture/diagrams/) - Visual system documentation

### Performance & Optimization
- **[Stability Improvements](performance/stability-improvements.md)** - ⭐ Executive summary of CV reduction journey
- [GPU Clock Locking](performance/gpu-clock-locking.md) - Benchmark stability guide (CV: 40% → 18.72%)
- [Benchmark Timing Strategies](performance/benchmark-timing-strategies.md) - Technical deep-dive into timing optimization

### Technical Notes
- [IEEE754 Compliance](technical-notes/ieee754-compliance.md) - Floating-point accuracy validation
- [Buffer Synchronization Fix](technical-notes/buffer-synchronization-fix.md) - Multi-buffer pipeline synchronization
- [Thread Safety Audit v0.9.3](technical-notes/thread-safety-audit-v0.9.3.md) - Comprehensive thread safety analysis

---

## 🚀 Recommended Reading Order

### For New Users
1. [Installation Guide](getting-started/install.md)
2. [API Reference](guides/api-reference.md)
3. [Benchmarking Guide](guides/benchmarking.md)

### For Contributors
1. [Development Guide](guides/development.md)
2. [Architecture Overview](architecture/overview.md)
3. [Thread Safety](architecture/thread-safety.md)
4. [Contributing Guidelines](guides/contributing.md)

### For Performance Optimization
1. **[Stability Improvements](performance/stability-improvements.md)** - Start here!
2. [GPU Clock Locking](performance/gpu-clock-locking.md)
3. [Benchmark Timing Strategies](performance/benchmark-timing-strategies.md)

### For Researchers
1. [Benchmarking Guide](guides/benchmarking.md)
2. [Stability Improvements](performance/stability-improvements.md)
3. [Architecture Diagrams](architecture/diagrams/)

---

## 📖 Documentation Categories

### Getting Started
Everything needed to install and start using the library.

**Key Topics**:
- Environment setup (Conda, CUDA, dependencies)
- Quick start examples
- Development workflow
- CLI usage

**Files**: `getting-started/`

---

### User Guides
Comprehensive guides for using the library effectively.

**Key Topics**:
- Python API reference
- Benchmarking and profiling
- Development practices
- Contributing guidelines

**Files**: `guides/`

---

### Architecture & Design
System design, structure, and visual documentation.

**Key Topics**:
- High-level architecture
- Component interactions
- Codebase organization
- **Thread safety and multi-threading**
- Visual diagrams

**Files**: `architecture/`

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
- ⭐ [stability-improvements.md](performance/stability-improvements.md) - Executive summary of 4-phase optimization
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

## 🎯 Quick Links

### Common Tasks

**Run a Benchmark**:
```powershell
# Quick test
ionoc bench

# Production latency benchmark with clock locking
ionoc bench --preset latency --full --ionosphere --lock-clocks
```

**Profile Performance**:
```powershell
# Nsight Systems profiling
iprof nsys latency --stats

# Nsight Compute kernel analysis
iprof ncu latency --set roofline
```

**Save Baseline**:
```powershell
ionoc bench --preset latency --full --lock-clocks --save-baseline
```

**View Documentation**:
- Start with: [Stability Improvements](performance/stability-improvements.md)
- For setup: [Installation Guide](getting-started/install.md)
- For API: [API Reference](guides/api-reference.md)

---

## 📊 Key Achievements

### Benchmark Stability
**Final CV: 18.72%** (down from 40% - 53% improvement)

| Phase | Implementation | Result |
|-------|----------------|--------|
| Phase 1 | Blocking sync | ✅ 26% better |
| Phase 2 | Hybrid timing | ✅ 33% better |
| Phase 3 | Warmup + outliers | ✅ 31% better |
| Phase 4 | GPU clock locking | ✅ 24% better |

**Total**: 40% CV → **18.72%** = Production-ready! 🎉

See [Stability Improvements](performance/stability-improvements.md) for full story.

---

## 🔍 Search & Navigation Tips

**By Topic**:
- **Installation** → `getting-started/install.md`
- **API Usage** → `guides/api-reference.md`
- **Benchmarking** → `guides/benchmarking.md` or `performance/`
- **Performance** → `performance/stability-improvements.md` (start here!)
- **Thread Safety** → `architecture/thread-safety.md`
- **Architecture** → `architecture/overview.md`
- **Contributing** → `guides/contributing.md`

**By File Type**:
- **Guides**: `guides/`
- **Technical Details**: `technical-notes/`
- **Performance**: `performance/`
- **Diagrams**: `architecture/diagrams/`

**By Audience**:
- **Users**: Start in `getting-started/`
- **Contributors**: Read `guides/development.md`
- **Researchers**: Check `performance/` folder
- **Architects**: See `architecture/`

---

## 📝 Documentation Maintenance

**Last Updated**: 2025-10-17

**Recent Changes**:
- ✅ Added comprehensive thread safety documentation (v0.9.3)
- ✅ Added thread safety audit report with Google terminology
- ✅ Reorganized into category-based structure
- ✅ Added stability-improvements.md executive summary
- ✅ Updated gpu-clock-locking.md with validated results (CV=18.72%)
- ✅ Documented realtime timing instability (accepted)
- ✅ Renamed files to lowercase-with-hyphens for consistency

**Contributing to Docs**:
See [Contributing Guidelines](guides/contributing.md) for documentation standards and workflow.

---

## External Resources

- [CUDA Programming Guide](https://docs.nvidia.com/cuda/cuda-c-programming-guide/)
- [NVIDIA Nsight Systems](https://developer.nvidia.com/nsight-systems)
- [NVIDIA System Management Interface](https://developer.nvidia.com/nvidia-system-management-interface)
- [IEEE 754 Floating-Point Standard](https://ieeexplore.ieee.org/document/8766229)

---

**Need Help?**
- Check the [Installation Guide](getting-started/install.md) first
- Read the [API Reference](guides/api-reference.md) for usage examples
- See [Contributing Guidelines](guides/contributing.md) for issue reporting
