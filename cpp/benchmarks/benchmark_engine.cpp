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

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#include "benchmark_config.hpp"
#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/core/processing_stage.hpp"
#include "ionosense/core/profiling_macros.hpp"
#include "ionosense/engines/research_engine.hpp"

#include <cuda_runtime.h>
#include <cufft.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

using namespace ionosense;
using namespace ionosense::benchmark;

// ============================================================================
// Results Structures
// ============================================================================

struct LatencyResults {
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

struct ThroughputResults {
  float frames_per_second = 0.0f;
  float gb_per_second = 0.0f;
  float samples_per_second = 0.0f;
  size_t total_frames = 0;
  float test_duration_s = 0.0f;
};

struct RealtimeResults {
  float compliance_rate = 0.0f;
  float mean_latency_ms = 0.0f;
  float p99_latency_ms = 0.0f;
  float mean_jitter_ms = 0.0f;
  size_t frames_processed = 0;
  size_t deadline_misses = 0;
  size_t frames_dropped = 0;
};

struct AccuracyResults {
  float pass_rate = 0.0f;
  float mean_snr_db = 0.0f;
  float mean_mae = 0.0f;         // Mean Absolute Error
  float mean_rmse = 0.0f;        // Root Mean Square Error
  float max_error = 0.0f;        // Peak Error
  float mean_relative_error = 0.0f;  // Mean relative error
  int tests_passed = 0;
  int tests_total = 0;
};

// ============================================================================
// Test Signal Generation
// ============================================================================

enum class SignalType {
  WHITE_NOISE,
  PURE_SINE,
  MULTI_TONE,
  CHIRP
};

std::vector<float> generate_test_signal(int nfft, int batch, int seed = 42,
                                         SignalType type = SignalType::WHITE_NOISE) {
  IONO_NVTX_RANGE("Generate Test Signal", profiling::colors::CYAN);
  std::vector<float> signal(static_cast<size_t>(nfft) * batch);
  std::mt19937 gen(seed);

  switch (type) {
    case SignalType::WHITE_NOISE: {
      std::normal_distribution<float> dist(0.0f, 1.0f);
      for (auto& s : signal) {
        s = dist(gen);
      }
      break;
    }

    case SignalType::PURE_SINE: {
      // Generate a pure sine wave at a known frequency
      // Frequency bin 10 (arbitrary choice in lower third of spectrum)
      const float freq_bin = 10.0f;
      const float amplitude = 1.0f;
      for (int b = 0; b < batch; ++b) {
        for (int i = 0; i < nfft; ++i) {
          const int idx = b * nfft + i;
          signal[idx] = amplitude * std::sin(2.0f * M_PI * freq_bin * i / nfft);
        }
      }
      break;
    }

    case SignalType::MULTI_TONE: {
      // Generate sum of 3 sine waves at known frequencies
      const std::vector<float> freq_bins = {5.0f, 15.0f, 25.0f};
      const std::vector<float> amplitudes = {0.8f, 0.6f, 0.4f};
      for (int b = 0; b < batch; ++b) {
        for (int i = 0; i < nfft; ++i) {
          const int idx = b * nfft + i;
          signal[idx] = 0.0f;
          for (size_t t = 0; t < freq_bins.size(); ++t) {
            signal[idx] += amplitudes[t] *
                          std::sin(2.0f * M_PI * freq_bins[t] * i / nfft);
          }
        }
      }
      break;
    }

    case SignalType::CHIRP: {
      // Linear frequency sweep
      const float f0 = 5.0f / nfft;   // Start frequency
      const float f1 = 50.0f / nfft;  // End frequency
      const float amplitude = 1.0f;
      for (int b = 0; b < batch; ++b) {
        for (int i = 0; i < nfft; ++i) {
          const int idx = b * nfft + i;
          const float t = static_cast<float>(i) / nfft;
          const float phase = 2.0f * M_PI * (f0 * t + (f1 - f0) * t * t / 2.0f) * nfft;
          signal[idx] = amplitude * std::sin(phase);
        }
      }
      break;
    }
  }

  return signal;
}

// ============================================================================
// Reference FFT (using cuFFT CPU-side for validation)
// ============================================================================

std::vector<float> compute_reference_fft(const std::vector<float>& input,
                                         int nfft, int batch) {
  IONO_NVTX_RANGE("Reference FFT Computation", profiling::colors::PURPLE);

  const size_t num_bins = static_cast<size_t>(nfft / 2 + 1);
  const size_t complex_output_size = num_bins * batch;
  const size_t magnitude_output_size = complex_output_size;

  // Allocate device memory for reference computation
  float* d_input = nullptr;
  cufftComplex* d_complex_output = nullptr;
  float* d_magnitude_output = nullptr;

  cudaMalloc(&d_input, input.size() * sizeof(float));
  cudaMalloc(&d_complex_output, complex_output_size * sizeof(cufftComplex));
  cudaMalloc(&d_magnitude_output, magnitude_output_size * sizeof(float));

  // Copy input to device
  cudaMemcpy(d_input, input.data(), input.size() * sizeof(float),
             cudaMemcpyHostToDevice);

  // Create cuFFT plan for reference
  cufftHandle plan;
  int n[1] = {nfft};
  cufftPlanMany(&plan, 1, n, nullptr, 1, nfft, nullptr, 1, num_bins,
                CUFFT_R2C, batch);

  // Execute FFT
  cufftExecR2C(plan, d_input, d_complex_output);

  // Copy complex result back to host and compute magnitude on CPU
  // (This is reference code, so CPU computation is acceptable for simplicity)
  std::vector<cufftComplex> complex_output(complex_output_size);
  cudaMemcpy(complex_output.data(), d_complex_output,
             complex_output_size * sizeof(cufftComplex),
             cudaMemcpyDeviceToHost);

  // Compute magnitude on host
  std::vector<float> output(magnitude_output_size);
  for (size_t i = 0; i < complex_output_size; ++i) {
    const float real = complex_output[i].x;
    const float imag = complex_output[i].y;
    output[i] = std::hypot(real, imag);
  }

  // Cleanup
  cufftDestroy(plan);
  cudaFree(d_input);
  cudaFree(d_complex_output);

  return output;
}

// ============================================================================
// Error Metrics
// ============================================================================

struct ErrorMetrics {
  float mae = 0.0f;          // Mean Absolute Error
  float rmse = 0.0f;         // Root Mean Square Error
  float peak_error = 0.0f;   // Maximum absolute error
  float snr_db = 0.0f;       // Signal-to-Noise Ratio in dB
  float relative_error = 0.0f;  // Relative error (normalized by reference magnitude)
};

ErrorMetrics compute_error_metrics(const std::vector<float>& output,
                                    const std::vector<float>& reference) {
  ErrorMetrics metrics;

  if (output.size() != reference.size()) {
    return metrics;  // Return zeros if size mismatch
  }

  const size_t n = output.size();
  double sum_abs_error = 0.0;
  double sum_sq_error = 0.0;
  double sum_sq_signal = 0.0;
  float max_error = 0.0f;

  for (size_t i = 0; i < n; ++i) {
    const float error = std::abs(output[i] - reference[i]);
    const float signal = std::abs(reference[i]);

    sum_abs_error += error;
    sum_sq_error += error * error;
    sum_sq_signal += signal * signal;
    max_error = std::max(max_error, error);
  }

  metrics.mae = static_cast<float>(sum_abs_error / n);
  metrics.rmse = std::sqrt(static_cast<float>(sum_sq_error / n));
  metrics.peak_error = max_error;

  // Compute SNR: 10 * log10(signal_power / noise_power)
  const double noise_power = sum_sq_error / n;
  const double signal_power = sum_sq_signal / n;

  if (noise_power > 1e-20) {  // Avoid division by zero
    metrics.snr_db = 10.0f * std::log10(static_cast<float>(signal_power / noise_power));
  } else {
    metrics.snr_db = 200.0f;  // Effectively perfect match
  }

  // Compute relative error
  const double ref_magnitude = std::sqrt(signal_power);
  if (ref_magnitude > 1e-10) {
    metrics.relative_error = static_cast<float>(std::sqrt(sum_sq_error / n) / ref_magnitude);
  }

  return metrics;
}

// ============================================================================
// CLI Argument Parser
// ============================================================================

BenchmarkConfig parse_args(int argc, char* argv[]) {
  // Two-pass approach: first collect preset/mode/ionosphere, then apply overrides

  // Pass 1: Determine preset, mode, and ionosphere flag
  BenchmarkPreset preset = BenchmarkPreset::DEV;
  RunMode mode = RunMode::FULL;
  bool ionosphere = false;
  OutputFormat output_format = OutputFormat::TABLE;
  bool quiet = false;

  // Also collect parameter overrides
  struct Override {
    bool has_nfft = false;
    bool has_batch = false;
    bool has_overlap = false;
    bool has_sample_rate = false;
    bool has_streams = false;
    bool has_iterations = false;
    bool has_duration = false;
    bool has_warmup = false;
    bool has_seed = false;
    int nfft = 0;
    int batch = 0;
    float overlap = 0.0f;
    int sample_rate_hz = 0;
    int stream_count = 0;
    int iterations = 0;
    float duration_seconds = 0.0f;
    int warmup_iterations = 0;
    int random_seed = 0;
  } overrides;

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];

    // Help
    if (arg == "--help" || arg == "-h") {
      std::cout << R"(
Usage: benchmark_engine [--preset <name>] [--ionosphere] [options...]

PRESETS:
  --preset dev          Quick validation (20 iter, ~10s) [default]
  --preset latency      Latency measurement (5000 iter, ~2min)
  --preset throughput   Throughput measurement (10s duration)
  --preset realtime     Real-time streaming (10s duration)
  --preset accuracy     Accuracy validation (10 iter, 8 signals)

RUN MODES:
  --quick               Fast validation (reduced iterations/duration)
  --profile             Profile-ready (moderate iterations/duration)
  --full                Production equivalent (default)

MODIFIERS:
  --ionosphere          Apply ionosphere-specific parameters

ENGINE PARAMETERS:
  --nfft <value>        FFT size (default: preset-dependent)
  --batch <value>       Batch size (default: preset-dependent)
  --overlap <value>     Overlap ratio 0-1 (default: preset-dependent)
  --sample-rate <hz>    Sample rate in Hz (default: 48000)
  --streams <n>         CUDA streams (default: 3)

BENCHMARK PARAMETERS:
  --iterations <n>      Number of iterations (iteration-based benchmarks)
  --duration <seconds>  Test duration in seconds (time-based benchmarks)
  --warmup <n>          Warmup iterations (default: preset-dependent)
  --seed <n>            Random seed (default: 42)

OUTPUT CONTROL:
  --csv                 Output CSV only (no formatting)
  --json                Output JSON format
  --quiet               Minimal output

EXAMPLES:
  # Quick development validation (default)
  benchmark_engine

  # Production latency benchmark
  benchmark_engine --preset latency --full

  # Ionosphere realtime profiling
  benchmark_engine --preset realtime --ionosphere --profile

  # Custom experimentation
  benchmark_engine --preset throughput --nfft 4096 --batch 16 --quick

  # Blank canvas (override everything)
  benchmark_engine --nfft 8192 --batch 32 --overlap 0.875 --iterations 100
)";
      std::exit(0);
    }

    // Preset
    else if (arg == "--preset") {
      if (i + 1 < argc) {
        std::string preset_name = argv[++i];
        preset = string_to_preset(preset_name);
      }
    }

    // Run mode
    else if (arg == "--quick") {
      mode = RunMode::QUICK;
    } else if (arg == "--profile") {
      mode = RunMode::PROFILE;
    } else if (arg == "--full") {
      mode = RunMode::FULL;
    }

    // Ionosphere variant
    else if (arg == "--ionosphere") {
      ionosphere = true;
    }

    // Engine parameters (overrides)
    else if (arg == "--nfft" && i + 1 < argc) {
      overrides.nfft = std::stoi(argv[++i]);
      overrides.has_nfft = true;
    } else if (arg == "--batch" && i + 1 < argc) {
      overrides.batch = std::stoi(argv[++i]);
      overrides.has_batch = true;
    } else if (arg == "--overlap" && i + 1 < argc) {
      overrides.overlap = std::stof(argv[++i]);
      overrides.has_overlap = true;
    } else if (arg == "--sample-rate" && i + 1 < argc) {
      overrides.sample_rate_hz = std::stoi(argv[++i]);
      overrides.has_sample_rate = true;
    } else if (arg == "--streams" && i + 1 < argc) {
      overrides.stream_count = std::stoi(argv[++i]);
      overrides.has_streams = true;
    }

    // Benchmark parameters (overrides)
    else if (arg == "--iterations" && i + 1 < argc) {
      overrides.iterations = std::stoi(argv[++i]);
      overrides.has_iterations = true;
    } else if (arg == "--duration" && i + 1 < argc) {
      overrides.duration_seconds = std::stof(argv[++i]);
      overrides.has_duration = true;
    } else if (arg == "--warmup" && i + 1 < argc) {
      overrides.warmup_iterations = std::stoi(argv[++i]);
      overrides.has_warmup = true;
    } else if (arg == "--seed" && i + 1 < argc) {
      overrides.random_seed = std::stoi(argv[++i]);
      overrides.has_seed = true;
    }

    // Output control
    else if (arg == "--csv") {
      output_format = OutputFormat::CSV;
    } else if (arg == "--json") {
      output_format = OutputFormat::JSON;
    } else if (arg == "--quiet") {
      quiet = true;
    }

    // Unknown argument
    else {
      std::cerr << "Unknown argument: " << arg << "\n";
      std::cerr << "Use --help for usage information.\n";
      std::exit(1);
    }
  }

  // Pass 2: Build config from preset + mode
  BenchmarkConfig config;

  switch (preset) {
    case BenchmarkPreset::DEV:
      config = get_dev_config();
      break;
    case BenchmarkPreset::LATENCY:
      config = get_latency_config(mode);
      break;
    case BenchmarkPreset::THROUGHPUT:
      config = get_throughput_config(mode);
      break;
    case BenchmarkPreset::REALTIME:
      config = get_realtime_config(mode);
      break;
    case BenchmarkPreset::ACCURACY:
      config = get_accuracy_config(mode);
      break;
  }

  // Apply ionosphere variant if requested
  if (ionosphere) {
    config.ionosphere_variant = true;
    apply_ionosphere_variant(config);
  }

  // Apply output settings
  config.output_format = output_format;
  config.quiet = quiet;

  // Apply parameter overrides
  if (overrides.has_nfft) config.nfft = overrides.nfft;
  if (overrides.has_batch) config.batch = overrides.batch;
  if (overrides.has_overlap) config.overlap = overrides.overlap;
  if (overrides.has_sample_rate) config.sample_rate_hz = overrides.sample_rate_hz;
  if (overrides.has_streams) config.stream_count = overrides.stream_count;
  if (overrides.has_iterations) config.iterations = overrides.iterations;
  if (overrides.has_duration) config.duration_seconds = overrides.duration_seconds;
  if (overrides.has_warmup) config.warmup_iterations = overrides.warmup_iterations;
  if (overrides.has_seed) config.random_seed = overrides.random_seed;

  return config;
}

// ============================================================================
// Warmup
// ============================================================================

void run_warmup(ResearchEngine& engine, const BenchmarkConfig& config) {
  IONO_NVTX_RANGE("Warmup Phase", profiling::colors::LIGHT_GRAY);

  std::vector<float> warmup_input(static_cast<size_t>(config.nfft) *
                                   config.batch);
  std::vector<float> warmup_output(
      static_cast<size_t>(config.nfft / 2 + 1) * config.batch);

  for (int i = 0; i < config.warmup_iterations; ++i) {
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

// ============================================================================
// Benchmark Runners
// ============================================================================

LatencyResults run_latency_benchmark(ResearchEngine& engine,
                                       const BenchmarkConfig& config) {
  IONO_NVTX_RANGE("Latency Benchmark", profiling::colors::NVIDIA_BLUE);

  LatencyResults results;

  const size_t input_size = static_cast<size_t>(config.nfft) * config.batch;
  const size_t output_size =
      static_cast<size_t>(config.nfft / 2 + 1) * config.batch;

  std::vector<float> input =
      generate_test_signal(config.nfft, config.batch, config.random_seed);
  std::vector<float> output(output_size);

  results.latencies_us.reserve(config.iterations);

  for (int i = 0; i < config.iterations; ++i) {
    const std::string iter_name = "Iteration " + std::to_string(i + 1) + "/" +
                                  std::to_string(config.iterations);
    IONO_NVTX_RANGE(iter_name.c_str(), profiling::colors::NVIDIA_BLUE);

    auto t0 = std::chrono::high_resolution_clock::now();
    engine.process(input.data(), output.data(), input_size);
    engine.synchronize();  // Ensure GPU work is complete
    auto t1 = std::chrono::high_resolution_clock::now();

    float latency_us =
        std::chrono::duration<float, std::micro>(t1 - t0).count();
    results.latencies_us.push_back(latency_us);
  }

  // Compute statistics
  IONO_NVTX_RANGE("Compute Statistics", profiling::colors::CYAN);

  std::vector<float> sorted_latencies = results.latencies_us;
  std::sort(sorted_latencies.begin(), sorted_latencies.end());

  results.mean_latency_us =
      std::accumulate(sorted_latencies.begin(), sorted_latencies.end(), 0.0f) /
      static_cast<float>(sorted_latencies.size());

  results.p50_latency_us = sorted_latencies[sorted_latencies.size() / 2];
  results.p95_latency_us = sorted_latencies[sorted_latencies.size() * 95 / 100];
  results.p99_latency_us = sorted_latencies[sorted_latencies.size() * 99 / 100];
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

  return results;
}

ThroughputResults run_throughput_benchmark(ResearchEngine& engine,
                                            const BenchmarkConfig& config) {
  IONO_NVTX_RANGE("Throughput Benchmark", profiling::colors::GREEN);

  ThroughputResults results;

  const size_t input_size = static_cast<size_t>(config.nfft) * config.batch;
  const size_t output_size =
      static_cast<size_t>(config.nfft / 2 + 1) * config.batch;

  std::vector<float> input =
      generate_test_signal(config.nfft, config.batch, config.random_seed);
  std::vector<float> output(output_size);

  size_t frame_count = 0;

  auto start = std::chrono::high_resolution_clock::now();
  auto end = start + std::chrono::duration<float>(config.duration_seconds);

  while (std::chrono::high_resolution_clock::now() < end) {
    const std::string iter_name = "Frame " + std::to_string(frame_count + 1);
    IONO_NVTX_RANGE(iter_name.c_str(), profiling::colors::GREEN);

    engine.process(input.data(), output.data(), input_size);
    frame_count++;
  }

  engine.synchronize();
  auto actual_end = std::chrono::high_resolution_clock::now();

  float actual_duration =
      std::chrono::duration<float>(actual_end - start).count();

  results.total_frames = frame_count;
  results.test_duration_s = actual_duration;
  results.frames_per_second =
      static_cast<float>(frame_count) / actual_duration;

  // Calculate data rates
  size_t bytes_per_frame = input_size * sizeof(float) + output_size * sizeof(float);
  float total_gb = (static_cast<float>(bytes_per_frame * frame_count)) / (1024.0f * 1024.0f * 1024.0f);
  results.gb_per_second = total_gb / actual_duration;
  results.samples_per_second = results.frames_per_second * static_cast<float>(input_size);

  return results;
}

RealtimeResults run_realtime_benchmark(ResearchEngine& engine,
                                        const BenchmarkConfig& config) {
  IONO_NVTX_RANGE("Realtime Benchmark", profiling::colors::ORANGE);

  RealtimeResults results;

  // Calculate frame deadline if not specified
  float frame_deadline_ms = config.frame_deadline_ms;
  if (frame_deadline_ms == 0.0f) {
    // Calculate based on hop size
    int hop_size = static_cast<int>(config.nfft * (1.0f - config.overlap));
    frame_deadline_ms =
        (static_cast<float>(hop_size) / static_cast<float>(config.sample_rate_hz)) * 1000.0f;
  }

  const size_t input_size = static_cast<size_t>(config.nfft) * config.batch;
  const size_t output_size =
      static_cast<size_t>(config.nfft / 2 + 1) * config.batch;

  std::vector<float> input =
      generate_test_signal(config.nfft, config.batch, config.random_seed);
  std::vector<float> output(output_size);

  std::vector<float> frame_latencies_ms;
  size_t frame_count = 0;
  size_t deadline_misses = 0;

  auto start = std::chrono::high_resolution_clock::now();
  auto end = start + std::chrono::duration<float>(config.duration_seconds);

  while (std::chrono::high_resolution_clock::now() < end) {
    const std::string iter_name = "Frame " + std::to_string(frame_count + 1);
    IONO_NVTX_RANGE(iter_name.c_str(), profiling::colors::ORANGE);

    auto frame_start = std::chrono::high_resolution_clock::now();
    engine.process(input.data(), output.data(), input_size);
    engine.synchronize();
    auto frame_end = std::chrono::high_resolution_clock::now();

    float frame_latency_ms =
        std::chrono::duration<float, std::milli>(frame_end - frame_start)
            .count();
    frame_latencies_ms.push_back(frame_latency_ms);

    if (config.strict_timing && frame_latency_ms > frame_deadline_ms) {
      deadline_misses++;
    }

    frame_count++;
  }

  // Compute statistics
  results.frames_processed = frame_count;
  results.deadline_misses = deadline_misses;
  results.frames_dropped = 0;  // Not tracking frame drops in this implementation
  results.compliance_rate = 1.0f - (static_cast<float>(deadline_misses) /
                                    static_cast<float>(frame_count));

  if (!frame_latencies_ms.empty()) {
    results.mean_latency_ms =
        std::accumulate(frame_latencies_ms.begin(), frame_latencies_ms.end(),
                        0.0f) /
        static_cast<float>(frame_latencies_ms.size());

    std::vector<float> sorted_latencies = frame_latencies_ms;
    std::sort(sorted_latencies.begin(), sorted_latencies.end());
    results.p99_latency_ms =
        sorted_latencies[sorted_latencies.size() * 99 / 100];

    // Calculate jitter (standard deviation of latencies)
    float variance = 0.0f;
    for (float lat : frame_latencies_ms) {
      float diff = lat - results.mean_latency_ms;
      variance += diff * diff;
    }
    results.mean_jitter_ms =
        std::sqrt(variance / static_cast<float>(frame_latencies_ms.size()));
  }

  return results;
}

AccuracyResults run_accuracy_benchmark(ResearchEngine& engine,
                                        const BenchmarkConfig& config) {
  IONO_NVTX_RANGE("Accuracy Benchmark", profiling::colors::PURPLE);

  AccuracyResults results;

  // For now, run simplified accuracy test
  // In a full implementation, this would test multiple signal types
  const size_t input_size = static_cast<size_t>(config.nfft) * config.batch;
  const size_t output_size =
      static_cast<size_t>(config.nfft / 2 + 1) * config.batch;

  int tests_passed = 0;
  int tests_total = config.num_test_signals * config.iterations;

  std::vector<ErrorMetrics> all_metrics;
  all_metrics.reserve(tests_total);

  // Define signal types to test
  const std::vector<SignalType> signal_types = {
      SignalType::WHITE_NOISE, SignalType::PURE_SINE,
      SignalType::MULTI_TONE, SignalType::CHIRP
  };

  for (int sig = 0; sig < config.num_test_signals; ++sig) {
    for (int iter = 0; iter < config.iterations; ++iter) {
      const SignalType sig_type = signal_types[sig % signal_types.size()];
      const std::string test_name =
          "Signal " + std::to_string(sig + 1) + " Iter " +
          std::to_string(iter + 1);
      IONO_NVTX_RANGE(test_name.c_str(), profiling::colors::PURPLE);

      // Generate test signal with specific type
      std::vector<float> input = generate_test_signal(
          config.nfft, config.batch, config.random_seed + sig * 100 + iter,
          sig_type);
      std::vector<float> output(output_size);

      // Run engine processing
      engine.process(input.data(), output.data(), input_size);
      engine.synchronize();

      // Compute reference FFT output for comparison
      std::vector<float> reference = compute_reference_fft(input, config.nfft, config.batch);

      // Compute error metrics by comparing against reference
      ErrorMetrics metrics = compute_error_metrics(output, reference);

      // Check if test passed (based on tolerance thresholds)
      bool test_passed = true;
      test_passed &= metrics.snr_db >= config.snr_threshold_db;
      test_passed &= metrics.relative_error <= config.relative_tolerance;
      test_passed &= std::isfinite(metrics.mae) && std::isfinite(metrics.rmse);

      if (test_passed) {
        tests_passed++;
      }

      all_metrics.push_back(metrics);
    }
  }

  results.tests_passed = tests_passed;
  results.tests_total = tests_total;
  results.pass_rate =
      static_cast<float>(tests_passed) / static_cast<float>(tests_total);

  // Aggregate metrics across all tests
  if (!all_metrics.empty()) {
    double sum_snr = 0.0, sum_mae = 0.0, sum_rmse = 0.0, sum_rel = 0.0;
    float max_peak = 0.0f;

    for (const auto& m : all_metrics) {
      sum_snr += m.snr_db;
      sum_mae += m.mae;
      sum_rmse += m.rmse;
      sum_rel += m.relative_error;
      max_peak = std::max(max_peak, m.peak_error);
    }

    const size_t n = all_metrics.size();
    results.mean_snr_db = static_cast<float>(sum_snr / n);
    results.mean_mae = static_cast<float>(sum_mae / n);
    results.mean_rmse = static_cast<float>(sum_rmse / n);
    results.mean_relative_error = static_cast<float>(sum_rel / n);
    results.max_error = max_peak;
  }

  return results;
}

// ============================================================================
// Output Formatters
// ============================================================================

void print_latency_results(const BenchmarkConfig& config,
                            const LatencyResults& results,
                            const RuntimeInfo& runtime_info) {
  if (config.output_format == OutputFormat::TABLE && !config.quiet) {
    std::cout << "\n";
    std::cout << "========================================\n";
    std::cout << "  Latency Benchmark Results\n";
    std::cout << "========================================\n\n";

    std::cout << "Configuration:\n";
    std::cout << "  Preset      : " << preset_to_string(config.preset);
    if (config.ionosphere_variant)
      std::cout << " (ionosphere)";
    std::cout << "\n";
    std::cout << "  Run Mode    : " << mode_to_string(config.run_mode) << "\n";
    std::cout << "  NFFT        : " << config.nfft << "\n";
    std::cout << "  Batch       : " << config.batch << "\n";
    std::cout << "  Overlap     : " << config.overlap << "\n";
    std::cout << "  Iterations  : " << config.iterations << "\n\n";

    std::cout << "Runtime:\n";
    std::cout << "  Device      : " << runtime_info.device_name << "\n";
    std::cout << "  CUDA        : " << runtime_info.cuda_version << "\n\n";

    std::cout << std::fixed << std::setprecision(2);
    std::cout << "Latency (µs):\n";
    std::cout << "  Mean        : " << results.mean_latency_us << "\n";
    std::cout << "  P50         : " << results.p50_latency_us << "\n";
    std::cout << "  P95         : " << results.p95_latency_us << "\n";
    std::cout << "  P99         : " << results.p99_latency_us << "\n";
    std::cout << "  Min         : " << results.min_latency_us << "\n";
    std::cout << "  Max         : " << results.max_latency_us << "\n";
    std::cout << "  Std Dev     : " << results.std_latency_us << "\n\n";

    std::cout << "========================================\n\n";
  }

  if (config.output_format == OutputFormat::CSV ||
      (config.output_format == OutputFormat::TABLE && !config.quiet)) {
    if (config.output_format == OutputFormat::TABLE) {
      std::cout << "CSV Output:\n";
    }
    std::cout << "preset,mode,ionosphere,nfft,batch,iterations,mean_us,p50_"
                 "us,p95_us,p99_us,min_us,max_us,std_us\n";
    std::cout << preset_to_string(config.preset) << ","
              << mode_to_string(config.run_mode) << ","
              << (config.ionosphere_variant ? "yes" : "no") << ","
              << config.nfft << "," << config.batch << "," << config.iterations
              << "," << results.mean_latency_us << "," << results.p50_latency_us
              << "," << results.p95_latency_us << "," << results.p99_latency_us
              << "," << results.min_latency_us << "," << results.max_latency_us
              << "," << results.std_latency_us << "\n";
  }
}

void print_throughput_results(const BenchmarkConfig& config,
                               const ThroughputResults& results,
                               const RuntimeInfo& runtime_info) {
  if (config.output_format == OutputFormat::TABLE && !config.quiet) {
    std::cout << "\n";
    std::cout << "========================================\n";
    std::cout << "  Throughput Benchmark Results\n";
    std::cout << "========================================\n\n";

    std::cout << "Configuration:\n";
    std::cout << "  Preset      : " << preset_to_string(config.preset);
    if (config.ionosphere_variant)
      std::cout << " (ionosphere)";
    std::cout << "\n";
    std::cout << "  Run Mode    : " << mode_to_string(config.run_mode) << "\n";
    std::cout << "  NFFT        : " << config.nfft << "\n";
    std::cout << "  Batch       : " << config.batch << "\n";
    std::cout << "  Duration    : " << config.duration_seconds << "s\n\n";

    std::cout << "Runtime:\n";
    std::cout << "  Device      : " << runtime_info.device_name << "\n";
    std::cout << "  CUDA        : " << runtime_info.cuda_version << "\n\n";

    std::cout << std::fixed << std::setprecision(2);
    std::cout << "Throughput:\n";
    std::cout << "  FPS         : " << results.frames_per_second << "\n";
    std::cout << "  GB/s        : " << results.gb_per_second << "\n";
    std::cout << "  Samples/s   : " << results.samples_per_second << "\n";
    std::cout << "  Frames      : " << results.total_frames << "\n\n";

    std::cout << "========================================\n\n";
  }

  if (config.output_format == OutputFormat::CSV ||
      (config.output_format == OutputFormat::TABLE && !config.quiet)) {
    if (config.output_format == OutputFormat::TABLE) {
      std::cout << "CSV Output:\n";
    }
    std::cout << "preset,mode,ionosphere,nfft,batch,duration_s,fps,gb_per_s,"
                 "samples_per_s,total_frames\n";
    std::cout << preset_to_string(config.preset) << ","
              << mode_to_string(config.run_mode) << ","
              << (config.ionosphere_variant ? "yes" : "no") << ","
              << config.nfft << "," << config.batch << ","
              << results.test_duration_s << "," << results.frames_per_second
              << "," << results.gb_per_second << ","
              << results.samples_per_second << "," << results.total_frames
              << "\n";
  }
}

void print_realtime_results(const BenchmarkConfig& config,
                             const RealtimeResults& results,
                             const RuntimeInfo& runtime_info) {
  if (config.output_format == OutputFormat::TABLE && !config.quiet) {
    std::cout << "\n";
    std::cout << "========================================\n";
    std::cout << "  Realtime Benchmark Results\n";
    std::cout << "========================================\n\n";

    std::cout << "Configuration:\n";
    std::cout << "  Preset      : " << preset_to_string(config.preset);
    if (config.ionosphere_variant)
      std::cout << " (ionosphere)";
    std::cout << "\n";
    std::cout << "  Run Mode    : " << mode_to_string(config.run_mode) << "\n";
    std::cout << "  NFFT        : " << config.nfft << "\n";
    std::cout << "  Batch       : " << config.batch << "\n";
    std::cout << "  Duration    : " << config.duration_seconds << "s\n\n";

    std::cout << "Runtime:\n";
    std::cout << "  Device      : " << runtime_info.device_name << "\n";
    std::cout << "  CUDA        : " << runtime_info.cuda_version << "\n\n";

    std::cout << std::fixed << std::setprecision(2);
    std::cout << "Real-time Performance:\n";
    std::cout << "  Compliance  : " << (results.compliance_rate * 100.0f)
              << "%\n";
    std::cout << "  Mean Lat    : " << results.mean_latency_ms << " ms\n";
    std::cout << "  P99 Lat     : " << results.p99_latency_ms << " ms\n";
    std::cout << "  Mean Jitter : " << results.mean_jitter_ms << " ms\n";
    std::cout << "  Frames      : " << results.frames_processed << "\n";
    std::cout << "  Misses      : " << results.deadline_misses << "\n\n";

    std::cout << "========================================\n\n";
  }

  if (config.output_format == OutputFormat::CSV ||
      (config.output_format == OutputFormat::TABLE && !config.quiet)) {
    if (config.output_format == OutputFormat::TABLE) {
      std::cout << "CSV Output:\n";
    }
    std::cout << "preset,mode,ionosphere,nfft,batch,compliance_rate,mean_lat_"
                 "ms,p99_lat_ms,jitter_ms,frames,misses\n";
    std::cout << preset_to_string(config.preset) << ","
              << mode_to_string(config.run_mode) << ","
              << (config.ionosphere_variant ? "yes" : "no") << ","
              << config.nfft << "," << config.batch << ","
              << results.compliance_rate << "," << results.mean_latency_ms
              << "," << results.p99_latency_ms << "," << results.mean_jitter_ms
              << "," << results.frames_processed << ","
              << results.deadline_misses << "\n";
  }
}

void print_accuracy_results(const BenchmarkConfig& config,
                             const AccuracyResults& results,
                             const RuntimeInfo& runtime_info) {
  if (config.output_format == OutputFormat::TABLE && !config.quiet) {
    std::cout << "\n";
    std::cout << "========================================\n";
    std::cout << "  Accuracy Benchmark Results\n";
    std::cout << "========================================\n\n";

    std::cout << "Configuration:\n";
    std::cout << "  Preset      : " << preset_to_string(config.preset);
    if (config.ionosphere_variant)
      std::cout << " (ionosphere)";
    std::cout << "\n";
    std::cout << "  Run Mode    : " << mode_to_string(config.run_mode) << "\n";
    std::cout << "  NFFT        : " << config.nfft << "\n";
    std::cout << "  Signals     : " << config.num_test_signals << "\n";
    std::cout << "  Iterations  : " << config.iterations << "\n\n";

    std::cout << "Runtime:\n";
    std::cout << "  Device      : " << runtime_info.device_name << "\n";
    std::cout << "  CUDA        : " << runtime_info.cuda_version << "\n\n";

    std::cout << std::fixed << std::setprecision(2);
    std::cout << "Accuracy:\n";
    std::cout << "  Pass Rate   : " << (results.pass_rate * 100.0f) << "%\n";
    std::cout << "  Tests Pass  : " << results.tests_passed << "/"
              << results.tests_total << "\n";
    std::cout << "  Mean SNR    : " << results.mean_snr_db << " dB\n";
    std::cout << std::fixed << std::setprecision(6);
    std::cout << "  Mean MAE    : " << results.mean_mae << "\n";
    std::cout << "  Mean RMSE   : " << results.mean_rmse << "\n";
    std::cout << "  Rel Error   : " << results.mean_relative_error << "\n";
    std::cout << std::fixed << std::setprecision(2);
    std::cout << "  Peak Error  : " << results.max_error << "\n\n";

    std::cout << "========================================\n\n";
  }

  if (config.output_format == OutputFormat::CSV ||
      (config.output_format == OutputFormat::TABLE && !config.quiet)) {
    if (config.output_format == OutputFormat::TABLE) {
      std::cout << "CSV Output:\n";
    }
    std::cout << "preset,mode,ionosphere,nfft,signals,pass_rate,tests_passed,"
                 "tests_total,mean_snr_db,mean_mae,mean_rmse,mean_rel_error,peak_error\n";
    std::cout << preset_to_string(config.preset) << ","
              << mode_to_string(config.run_mode) << ","
              << (config.ionosphere_variant ? "yes" : "no") << ","
              << config.nfft << "," << config.num_test_signals << ","
              << results.pass_rate << "," << results.tests_passed << ","
              << results.tests_total << "," << results.mean_snr_db << ","
              << results.mean_mae << "," << results.mean_rmse << ","
              << results.mean_relative_error << "," << results.max_error << "\n";
  }
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
