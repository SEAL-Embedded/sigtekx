/**
 * @file benchmark_engine.cpp
 * @brief Standalone C++ benchmark executable for development-time validation.
 *
 * This executable is designed for C++ kernel development and iteration BEFORE
 * Python integration. For production profiling, use `iprof` with Python
 * benchmarks for end-to-end workflow validation.
 *
 * Usage:
 *   benchmark_engine.exe [--quick|--profile|--full]
 *
 * Modes:
 *   --quick    : 20 iterations, ~10 seconds (default)
 *   --profile  : 100 iterations, ~30 seconds (nsys/ncu profiling)
 *   --full     : 5000 iterations, ~2 minutes (production equivalent)
 */

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <string>
#include <vector>

#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/core/processing_stage.hpp"
#include "ionosense/core/profiling_macros.hpp"
#include "ionosense/engines/research_engine.hpp"

using namespace ionosense;

// Benchmark configuration
struct BenchmarkConfig {
  std::string mode = "quick";
  int iterations = 20;
  int warmup_iters = 5;
  int nfft = 2048;
  int batch = 4;
  float overlap = 0.625f;
  int sample_rate_hz = 48000;
};

// Results structure
struct BenchmarkResults {
  std::vector<float> latencies_us;
  float mean_latency_us = 0.0f;
  float p50_latency_us = 0.0f;
  float p95_latency_us = 0.0f;
  float p99_latency_us = 0.0f;
  float min_latency_us = 0.0f;
  float max_latency_us = 0.0f;
  float std_latency_us = 0.0f;
  float throughput_gbps = 0.0f;
  size_t frames_processed = 0;
};

// Generate test signal
std::vector<float> generate_test_signal(int nfft, int batch, int seed = 42) {
  IONO_NVTX_RANGE("Generate Test Signal", profiling::colors::CYAN);
  std::vector<float> signal(static_cast<size_t>(nfft) * batch);
  std::mt19937 gen(seed);
  std::normal_distribution<float> dist(0.0f, 1.0f);
  for (auto& s : signal) {
    s = dist(gen);
  }
  return signal;
}

// Parse CLI arguments
BenchmarkConfig parse_args(int argc, char* argv[]) {
  BenchmarkConfig config;

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--quick") {
      config.mode = "quick";
      config.iterations = 20;
    } else if (arg == "--profile") {
      config.mode = "profile";
      config.iterations = 100;
    } else if (arg == "--full") {
      config.mode = "full";
      config.iterations = 5000;
    } else if (arg == "--help" || arg == "-h") {
      std::cout << "Usage: benchmark_engine [--quick|--profile|--full]\n";
      std::cout << "\nModes:\n";
      std::cout << "  --quick    : 20 iterations, ~10 seconds (default)\n";
      std::cout << "  --profile  : 100 iterations, ~30 seconds (for "
                   "nsys/ncu)\n";
      std::cout << "  --full     : 5000 iterations, ~2 minutes (production "
                   "equivalent)\n";
      std::exit(0);
    } else {
      std::cerr << "Unknown argument: " << arg << "\n";
      std::cerr << "Use --help for usage information.\n";
      std::exit(1);
    }
  }

  return config;
}

// Run warmup iterations
void run_warmup(ResearchEngine& engine, const BenchmarkConfig& config) {
  IONO_NVTX_RANGE("Warmup Phase", profiling::colors::LIGHT_GRAY);

  std::vector<float> warmup_input(static_cast<size_t>(config.nfft) *
                                   config.batch);
  std::vector<float> warmup_output(
      static_cast<size_t>(config.nfft / 2 + 1) * config.batch);

  for (int i = 0; i < config.warmup_iters; ++i) {
    const std::string name = "Warmup " + std::to_string(i);
    IONO_NVTX_RANGE(name.c_str(), profiling::colors::LIGHT_GRAY);
    engine.process(warmup_input.data(), warmup_output.data(),
                   warmup_input.size());
  }

  {
    IONO_NVTX_RANGE("Warmup Sync", profiling::colors::YELLOW);
    engine.synchronize();
  }
}

// Run benchmark and collect statistics
BenchmarkResults run_benchmark(ResearchEngine& engine,
                                const BenchmarkConfig& config) {
  BenchmarkResults results;

  const size_t input_size = static_cast<size_t>(config.nfft) * config.batch;
  const size_t output_size =
      static_cast<size_t>(config.nfft / 2 + 1) * config.batch;

  std::vector<float> input = generate_test_signal(config.nfft, config.batch);
  std::vector<float> output(output_size);

  results.latencies_us.reserve(config.iterations);

  {
    IONO_NVTX_RANGE("Benchmark Loop", profiling::colors::NVIDIA_BLUE);

    for (int i = 0; i < config.iterations; ++i) {
      const std::string iter_name =
          "Iteration " + std::to_string(i + 1) + "/" +
          std::to_string(config.iterations);
      IONO_NVTX_RANGE(iter_name.c_str(), profiling::colors::NVIDIA_BLUE);

      auto t0 = std::chrono::high_resolution_clock::now();
      engine.process(input.data(), output.data(), input_size);
      auto t1 = std::chrono::high_resolution_clock::now();

      float latency_us =
          std::chrono::duration<float, std::micro>(t1 - t0).count();
      results.latencies_us.push_back(latency_us);
    }
  }

  // Synchronize before computing stats
  {
    IONO_NVTX_RANGE("Final Sync", profiling::colors::YELLOW);
    engine.synchronize();
  }

  // Compute statistics
  {
    IONO_NVTX_RANGE("Compute Statistics", profiling::colors::CYAN);

    std::vector<float> sorted_latencies = results.latencies_us;
    std::sort(sorted_latencies.begin(), sorted_latencies.end());

    results.mean_latency_us =
        std::accumulate(sorted_latencies.begin(), sorted_latencies.end(),
                        0.0f) /
        static_cast<float>(sorted_latencies.size());

    results.p50_latency_us =
        sorted_latencies[sorted_latencies.size() / 2];
    results.p95_latency_us =
        sorted_latencies[sorted_latencies.size() * 95 / 100];
    results.p99_latency_us =
        sorted_latencies[sorted_latencies.size() * 99 / 100];
    results.min_latency_us = sorted_latencies.front();
    results.max_latency_us = sorted_latencies.back();

    // Standard deviation
    float variance = 0.0f;
    for (float lat : sorted_latencies) {
      float diff = lat - results.mean_latency_us;
      variance += diff * diff;
    }
    results.std_latency_us =
        std::sqrt(variance / static_cast<float>(sorted_latencies.size()));

    // Get throughput from engine stats
    auto stats = engine.get_stats();
    results.throughput_gbps = stats.throughput_gbps;
    results.frames_processed = stats.frames_processed;
  }

  return results;
}

// Print results
void print_results(const BenchmarkConfig& config,
                   const BenchmarkResults& results,
                   const RuntimeInfo& runtime_info) {
  std::cout << "\n";
  std::cout << "========================================\n";
  std::cout << "  Benchmark Results (" << config.mode << " mode)\n";
  std::cout << "========================================\n\n";

  // Configuration
  std::cout << "Configuration:\n";
  std::cout << "  NFFT        : " << config.nfft << "\n";
  std::cout << "  Batch       : " << config.batch << "\n";
  std::cout << "  Overlap     : " << config.overlap << "\n";
  std::cout << "  Sample Rate : " << config.sample_rate_hz << " Hz\n";
  std::cout << "  Iterations  : " << config.iterations << "\n";
  std::cout << "  Warmup      : " << config.warmup_iters << "\n\n";

  // Runtime info
  std::cout << "Runtime Info:\n";
  std::cout << "  Device      : " << runtime_info.device_name << "\n";
  std::cout << "  CUDA        : " << runtime_info.cuda_version << "\n";
  std::cout << "  Compute Cap : " << runtime_info.device_compute_capability_major
            << "." << runtime_info.device_compute_capability_minor << "\n\n";

  // Results
  std::cout << std::fixed << std::setprecision(2);
  std::cout << "Latency (µs):\n";
  std::cout << "  Mean        : " << results.mean_latency_us << "\n";
  std::cout << "  P50         : " << results.p50_latency_us << "\n";
  std::cout << "  P95         : " << results.p95_latency_us << "\n";
  std::cout << "  P99         : " << results.p99_latency_us << "\n";
  std::cout << "  Min         : " << results.min_latency_us << "\n";
  std::cout << "  Max         : " << results.max_latency_us << "\n";
  std::cout << "  Std Dev     : " << results.std_latency_us << "\n\n";

  std::cout << "Throughput:\n";
  std::cout << "  GB/s        : " << results.throughput_gbps << "\n";
  std::cout << "  Frames      : " << results.frames_processed << "\n\n";

  // CSV output for scripting
  std::cout << "CSV Output (for automation):\n";
  std::cout << "mode,nfft,batch,iterations,mean_us,p50_us,p95_us,p99_us,min_"
               "us,max_us,std_us,throughput_gbps\n";
  std::cout << config.mode << "," << config.nfft << "," << config.batch << ","
            << config.iterations << "," << results.mean_latency_us << ","
            << results.p50_latency_us << "," << results.p95_latency_us << ","
            << results.p99_latency_us << "," << results.min_latency_us << ","
            << results.max_latency_us << "," << results.std_latency_us << ","
            << results.throughput_gbps << "\n";

  std::cout << "\n========================================\n\n";
}

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

    std::cout << "Ionosense HPC - C++ Benchmark\n";
    std::cout << "Mode: " << config.mode << " (" << config.iterations
              << " iterations)\n\n";

    // Initialize engine
    ResearchEngine engine;
    EngineConfig engine_config;
    engine_config.nfft = config.nfft;
    engine_config.batch = config.batch;
    engine_config.overlap = config.overlap;
    engine_config.sample_rate_hz = config.sample_rate_hz;
    engine_config.stream_count = 3;
    engine_config.pinned_buffer_count = 2;
    engine_config.warmup_iters = 0;  // Manual warmup
    engine_config.enable_profiling = true;

    {
      IONO_NVTX_RANGE("Engine Initialization", profiling::colors::DARK_GRAY);
      engine.initialize(engine_config);
    }

    // Get runtime info
    RuntimeInfo runtime_info = engine.get_runtime_info();

    // Warmup
    std::cout << "Running warmup (" << config.warmup_iters
              << " iterations)...\n";
    run_warmup(engine, config);

    // Benchmark
    std::cout << "Running benchmark (" << config.iterations
              << " iterations)...\n";
    BenchmarkResults results = run_benchmark(engine, config);

    // Print results
    print_results(config, results, runtime_info);

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
