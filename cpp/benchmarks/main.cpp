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
#include "../benchmarks/core/config.hpp"
#include "../benchmarks/formatters/formatters.hpp"
#include "../benchmarks/core/persistence.hpp"
#include "../benchmarks/core/results.hpp"
#include "../benchmarks/runners/all_runners.hpp"
#include "../benchmarks/core/cli_parser.hpp"
#include "../benchmarks/utils/reference_compute.hpp"
#include "../benchmarks/utils/signal_generator.hpp"

// Executor and core functionality
#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/core/processing_stage.hpp"
#include "ionosense/profiling/nvtx.hpp"
#include "ionosense/executors/batch_executor.hpp"
#include "ionosense/executors/streaming_executor.hpp"

using namespace ionosense;
using namespace ionosense::benchmark;

// ============================================================================
// Helper Functions
// ============================================================================

static RuntimeInfo get_cuda_runtime_info() {
  RuntimeInfo info;

  cudaDeviceProp prop;
  cudaGetDeviceProperties(&prop, 0);
  info.device_name = prop.name;

  int runtime_version = 0;
  cudaRuntimeGetVersion(&runtime_version);
  info.cuda_runtime_version = runtime_version;

  int driver_version = 0;
  cudaDriverGetVersion(&driver_version);
  info.cuda_driver_version = driver_version;

  char version_str[64];
  snprintf(version_str, sizeof(version_str), "%d.%d",
           runtime_version / 1000, (runtime_version % 100) / 10);
  info.cuda_version = version_str;

  return info;
}

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
      if (config.iono_variant == IonoVariant::IONO) {
        std::cout << " (iono)";
      } else if (config.iono_variant == IonoVariant::IONOX) {
        std::cout << " (ionox)";
      }
      std::cout << " | Mode: " << mode_to_string(config.run_mode) << "\n";
      std::cout << "NFFT: " << config.nfft << " | Batch: " << config.batch
                << " | Overlap: " << config.overlap << "\n\n";
    }

    // Initialize executor (BatchExecutor for now)
    BatchExecutor executor;
    ExecutorConfig executor_config;
    executor_config.nfft = config.nfft;
    executor_config.batch = config.batch;
    executor_config.overlap = config.overlap;
    executor_config.sample_rate_hz = config.sample_rate_hz;
    executor_config.stream_count = config.stream_count;
    executor_config.pinned_buffer_count = config.pinned_buffer_count;
    executor_config.warmup_iters = 0;  // Manual warmup
    executor_config.mode = ExecutorConfig::ExecutionMode::BATCH;
    executor_config.device_id = -1;  // Auto-select

    {
      IONO_NVTX_RANGE("Executor Initialization", profiling::colors::DARK_GRAY);
      auto stages = StageFactory::create_default_pipeline();
      executor.initialize(executor_config, std::move(stages));
    }

    RuntimeInfo runtime_info = get_cuda_runtime_info();

    // Warmup
    if (!config.quiet && config.warmup_iterations > 0) {
      std::cout << "Warmup (" << config.warmup_iterations << " iterations)...\n";
    }
    if (config.warmup_iterations > 0) {
      run_warmup(executor, config);
    }

    // Run benchmark based on preset
    if (!config.quiet) {
      std::cout << "Running benchmark...\n";
    }

    switch (config.preset) {
      case BenchmarkPreset::LATENCY:
      case BenchmarkPreset::DEV: {
        auto results = run_latency_benchmark(executor, config);
        print_latency_results(config, results, runtime_info);

        // Save baseline if requested
        if (config.save_baseline) {
          save_latency_baseline(config, results);
          if (!config.quiet) {
            std::cout << "Baseline saved to: " << get_baseline_path(config) << "\n";
          }
        }
        break;
      }

      case BenchmarkPreset::THROUGHPUT: {
        auto results = run_throughput_benchmark(executor, config);
        print_throughput_results(config, results, runtime_info);

        // Save baseline if requested
        if (config.save_baseline) {
          save_throughput_baseline(config, results);
          if (!config.quiet) {
            std::cout << "Baseline saved to: " << get_baseline_path(config) << "\n";
          }
        }
        break;
      }

      case BenchmarkPreset::REALTIME: {
        auto results = run_realtime_benchmark(executor, config);
        print_realtime_results(config, results, runtime_info);

        // Save baseline if requested
        if (config.save_baseline) {
          save_realtime_baseline(config, results);
          if (!config.quiet) {
            std::cout << "Baseline saved to: " << get_baseline_path(config) << "\n";
          }
        }
        break;
      }

      case BenchmarkPreset::ACCURACY: {
        auto results = run_accuracy_benchmark(executor, config);
        print_accuracy_results(config, results, runtime_info);

        // Save baseline if requested
        if (config.save_baseline) {
          save_accuracy_baseline(config, results);
          if (!config.quiet) {
            std::cout << "Baseline saved to: " << get_baseline_path(config) << "\n";
          }
        }
        break;
      }
    }

    // Cleanup
    {
      IONO_NVTX_RANGE("Cleanup", profiling::colors::RED);
      executor.reset();
    }

    return 0;

  } catch (const std::exception& e) {
    std::cerr << "Error: " << e.what() << "\n";
    return 1;
  }
}
