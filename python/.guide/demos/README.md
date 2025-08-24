# 🎯 CUDA FFT Engine - Python Demo Suite

This folder contains beginner-friendly demonstrations of the CUDA FFT Engine capabilities. Each demo is self-contained and progressively introduces more advanced concepts.

## 📚 Demo Overview

| Demo | Difficulty | What You'll Learn | Cool Factor |
|------|------------|-------------------|-------------|
| **01_hello_fft** | ⭐ Beginner | Basic GPU usage, CPU vs GPU comparison | See 100x speedup! |
| **02_live_spectrum** | ⭐⭐ Easy | Real-time processing, animations | Live music visualization |
| **03_performance_scaling** | ⭐⭐ Easy | Batch size optimization, benchmarking | Interactive performance graphs |
| **04_batch_file_processing** | ⭐⭐⭐ Intermediate | Parallel file processing, pandas integration | Process 500 files in seconds |
| **05_music_visualizer** | ⭐⭐⭐ Intermediate | Advanced visualization, multi-stream | Professional music visualizer |

## 🚀 Running the Demos

### Prerequisites
```powershell
# Build the engine first (if not already done)
./cli.ps1 setup
./cli.ps1 build
```

### Run Individual Demos
```powershell
# From the project root directory
cd python/examples

# Run any demo
python demo_01_hello_fft.py
python demo_02_live_spectrum.py
python demo_03_performance_scaling.py
python demo_04_batch_file_processing.py
python demo_05_music_visualizer.py
```

## 📖 Demo Descriptions

### Demo 01: Hello FFT 👋
**Your first GPU acceleration!**
- Compare GPU vs CPU processing speed
- Process 32 signals simultaneously
- Visualize frequency spectrum
- Perfect starting point for beginners

**Key Concepts:** Basic engine usage, batch processing, performance comparison

### Demo 02: Live Spectrum Analyzer 🎵
**Real-time audio visualization**
- Animated spectrum display
- Waterfall spectrogram
- Peak frequency tracking
- Smooth 30+ FPS updates

**Key Concepts:** Real-time processing, streaming data, matplotlib animations

### Demo 03: Performance Scaling Explorer 📊
**Interactive performance analysis**
- Test different batch sizes (1-512)
- Compare with/without CUDA Graphs
- Generate performance charts
- Find optimal configurations

**Key Concepts:** Performance tuning, CUDA Graphs impact, throughput vs latency

### Demo 04: Batch File Processing 📂
**Process hundreds of files efficiently**
- Simulate 500 audio files
- Extract spectral features
- Compare GPU batch vs CPU sequential
- Export results to pandas/CSV

**Key Concepts:** Batch processing, feature extraction, pandas integration

### Demo 05: Music Visualizer 🎨
**Professional music visualization**
- Frequency band separation (bass, mids, treble)
- Radial visualizer with color mapping
- Beat detection and response
- Multiple visualization modes

**Key Concepts:** Advanced visualization, multi-channel processing, real-time effects

## 💡 Learning Path

1. **Start with Demo 01** - Understand the basics
2. **Try Demo 02** - See real-time capabilities
3. **Explore Demo 03** - Learn about performance
4. **Scale up with Demo 04** - Apply to real workflows
5. **Have fun with Demo 05** - Create beautiful visualizations

## 🔧 Customization Ideas

Each demo includes comments suggesting modifications:

- **Demo 01:** Try different FFT sizes (512, 1024, 2048, 4096, 8192)
- **Demo 02:** Adjust animation speed, add more visualization modes
- **Demo 03:** Test extreme batch sizes, measure memory usage
- **Demo 04:** Process real audio files, add more features
- **Demo 05:** Create your own visualization patterns, add color themes

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ImportError: cuda_lib` | Run `./cli.ps1 build` from project root |
| Low FPS in visualizations | Reduce batch size or animation interval |
| Out of memory | Lower batch_size parameter |
| Plots not showing | Check matplotlib backend: `plt.show()` |

## 📈 Expected Performance

On a modern GPU (RTX 3070 or better):
- **Demo 01:** 50-200x CPU speedup
- **Demo 02:** 60+ FPS visualization
- **Demo 03:** 500,000+ FFTs/second peak throughput
- **Demo 04:** 1000+ files/second processing
- **Demo 05:** Smooth 30 FPS with complex visualizations

## 🎓 Next Steps

After running these demos:
1. Modify them for your specific use cases
2. Combine techniques from different demos
3. Integrate the engine into your research workflows
4. Check the benchmarking scripts for advanced usage
5. Profile your code with `./cli.ps1 profile nsys your_script`

---

*Have fun exploring GPU acceleration! 🚀*
