/**
 * @file benchmark_engine.cpp
 * @brief Standalone C++ benchmark executable with preset system.
 *
 * This executable provides comprehensive benchmarking capabilities for C++
 * kernel development and iteration BEFORE Python integration. Supports multiple
 * benchmark presets matching Python configurations.
 *
 * Usage:
 *   benchmark_engine.exe [--preset <name>] [--ionosphere] [options...]
 *
 * Presets:
 *   dev (default) : Quick validation (20 iter, ~10s)
 *   latency       : Latency measurement (5000 iter, ~2min)
 *   throughput    : Throughput measurement (10s duration)
 *   realtime      : Real-time streaming (10s duration)
 *   accuracy      : Accuracy validation (10 iter, 8 signals)
 *
 * Run Modes:
 *   --quick   : Fast validation (reduced iterations/duration)
 *   --profile : Profile-ready (moderate iterations/duration)
 *   --full    : Production equivalent (full iterations/duration, default)
 *
 * Modifiers:
 *   --ionosphere : Apply ionosphere-specific parameters to preset
 *
 * For production profiling, use `iprof` with Python benchmarks for end-to-end
 * workflow validation.
 */

#include <iostream>

#include <cuda_runtime.h>

// Benchmark infrastructure
#include "benchmark_config.hpp"
#include "benchmark_formatters.hpp"
#include "benchmark_results.hpp"
#include "benchmark_runners.hpp"
#include "cli_parser.hpp"
#include "reference_compute.hpp"
#include "signal_generator.hpp"

// Engine and core functionality
#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/core/processing_stage.hpp"
#include "ionosense/core/profiling_macros.hpp"
#include "ionosense/engines/research_engine.hpp"

using namespace ionosense;
using namespace ionosense::benchmark;

// ============================================================================
// Main
// ============================================================================

int main(int argc, char* argv[]) {
  try {
    IONO_NVTX_RANGE("Main", profiling::colors::NVIDIA_BLUE);

    // Check CUDA availability
    int device_count = 0;
    cudaError_t err = cudaGetDeviceCount(&device_count);
    if (err != cudaSuccess || device_count == 0) {
      std::cerr << "Error: No CUDA devices available.\n";
      return 1;
    }

    // Parse arguments
    BenchmarkConfig config = parse_args(argc, argv);

    if (!config.quiet) {
      std::cout << "Ionosense HPC - C++ Benchmark\n";
      std::cout << "Preset: " << preset_to_string(config.preset);
      if (config.ionosphere_variant) {
        std::cout << " (ionosphere)";
      }
      std::cout << " | Mode: " << mode_to_string(config.run_mode) << "\n";
      std::cout << "NFFT: " << config.nfft << " | Batch: " << config.batch
                << " | Overlap: " << config.overlap << "\n\n";
    }

    // Initialize engine
    ResearchEngine engine;
    EngineConfig engine_config;
    engine_config.nfft = config.nfft;
    engine_config.batch = config.batch;
    engine_config.overlap = config.overlap;
    engine_config.sample_rate_hz = config.sample_rate_hz;
    engine_config.stream_count = config.stream_count;
    engine_config.pinned_buffer_count = config.pinned_buffer_count;
    engine_config.warmup_iters = 0;  // Manual warmup
    engine_config.enable_profiling = true;

    {
      IONO_NVTX_RANGE("Engine Initialization", profiling::colors::DARK_GRAY);
      engine.initialize(engine_config);
    }

    RuntimeInfo runtime_info = engine.get_runtime_info();

    // Warmup
    if (!config.quiet && config.warmup_iterations > 0) {
      std::cout << "Warmup (" << config.warmup_iterations << " iterations)...\n";
    }
    if (config.warmup_iterations > 0) {
      run_warmup(engine, config);
    }

    // Run benchmark based on preset
    if (!config.quiet) {
      std::cout << "Running benchmark...\n";
    }

    switch (config.preset) {
      case BenchmarkPreset::LATENCY:
      case BenchmarkPreset::DEV: {
        auto results = run_latency_benchmark(engine, config);
        print_latency_results(config, results, runtime_info);
        break;
      }

      case BenchmarkPreset::THROUGHPUT: {
        auto results = run_throughput_benchmark(engine, config);
        print_throughput_results(config, results, runtime_info);
        break;
      }

      case BenchmarkPreset::REALTIME: {
        auto results = run_realtime_benchmark(engine, config);
        print_realtime_results(config, results, runtime_info);
        break;
      }

      case BenchmarkPreset::ACCURACY: {
        auto results = run_accuracy_benchmark(engine, config);
        print_accuracy_results(config, results, runtime_info);
        break;
      }
    }

    // Cleanup
    {
      IONO_NVTX_RANGE("Cleanup", profiling::colors::RED);
      engine.reset();
    }

    return 0;

  } catch (const std::exception& e) {
    std::cerr << "Error: " << e.what() << "\n";
    return 1;
  }
}
