/**
 * @file cli_parser.hpp
 * @brief Command-line argument parser for benchmark executable.
 *
 * Provides comprehensive CLI parsing with support for presets, run modes,
 * parameter overrides, and output formatting options.
 */

#pragma once

#include <iostream>
#include <string>

#include "../benchmarks/core/config.hpp"

namespace sigtekx {
namespace benchmark {

// ============================================================================
// CLI Argument Parser
// ============================================================================

/**
 * @brief Parse command-line arguments into BenchmarkConfig.
 *
 * Two-pass approach:
 * 1. Parse preset, mode, and ionosphere flag
 * 2. Apply parameter overrides on top of preset defaults
 *
 * @param argc Argument count
 * @param argv Argument values
 * @return BenchmarkConfig with parsed settings
 */
inline BenchmarkConfig parse_args(int argc, char* argv[]) {
  // Two-pass approach: first collect preset/mode/ionosphere, then apply overrides

  // Pass 1: Determine preset, mode, and iono variant
  BenchmarkPreset preset = BenchmarkPreset::DEV;
  RunMode mode = RunMode::FULL;
  IonoVariant iono_variant = IonoVariant::NONE;
  OutputFormat output_format = OutputFormat::TABLE;
  bool quiet = false;
  bool safe_print = false;
  bool save_dataset = false;

  // Also collect parameter overrides
  struct Override {
    bool has_nfft = false;
    bool has_channels = false;
    bool has_overlap = false;
    bool has_sample_rate = false;
    bool has_streams = false;
    bool has_iterations = false;
    bool has_duration = false;
    bool has_warmup = false;
    bool has_seed = false;
    bool has_exec_mode = false;
    int nfft = 0;
    int channels = 0;
    float overlap = 0.0f;
    int sample_rate_hz = 0;
    int stream_count = 0;
    int iterations = 0;
    float duration_seconds = 0.0f;
    int warmup_iterations = 0;
    int random_seed = 0;
    ExecutorConfig::ExecutionMode exec_mode;
  } overrides;

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];

    // Help
    if (arg == "--help" || arg == "-h") {
      std::cout << R"(
Usage: benchmark_engine [--preset <name>] [--iono|--ionox] [options...]

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

IONOSPHERE VARIANTS (mutually exclusive):
  --iono                Standard ionosphere (48kHz, 4096/16384 NFFT, 0.75 overlap)
  --ionox               Extreme ionosphere (48kHz, 8192/32768 NFFT, 0.9/0.9375 overlap)

ENGINE PARAMETERS:
  --nfft <value>        FFT size (default: preset-dependent)
  --channels <value>    Number of signal channels (default: preset-dependent)
  --overlap <value>     Overlap ratio 0-1 (default: preset-dependent)
  --sample-rate <hz>    Sample rate in Hz (default: 48000)
  --streams <n>         CUDA streams (default: 3)
  --exec-mode <mode>    Execution mode: batch or streaming (default: preset-dependent)
                        latency/realtime/accuracy → streaming (low-latency)
                        throughput → batch (high-throughput)

BENCHMARK PARAMETERS:
  --iterations <n>      Number of iterations (iteration-based benchmarks)
  --duration <seconds>  Test duration in seconds (time-based benchmarks)
  --warmup <n>          Warmup iterations (default: preset-dependent)
  --seed <n>            Random seed (default: 42)

OUTPUT CONTROL:
  --csv                 Output CSV only (no formatting)
  --json                Output JSON format
  --quiet               Minimal output
  --safe-print          Use ASCII-only output (for profiling/redirect)

DATASET TRACKING:
  --save-dataset       Save results as dataset for future comparison

EXAMPLES:
  # Quick development validation (default)
  benchmark_engine

  # Production latency benchmark
  benchmark_engine --preset latency --full

  # Standard ionosphere realtime profiling
  benchmark_engine --preset realtime --iono --profile

  # Extreme ionosphere throughput (missile detection)
  benchmark_engine --preset throughput --ionox --full

  # Custom experimentation
  benchmark_engine --preset throughput --nfft 4096 --channels 16 --quick

  # Blank canvas (override everything)
  benchmark_engine --nfft 8192 --channels 32 --overlap 0.875 --iterations 100

IONOSPHERE PARAMETER REFERENCE:
  Preset      | --iono (standard)        | --ionox (extreme)
  ------------|--------------------------|---------------------------
  latency     | 4096 NFFT, 0.75 overlap  | 8192 NFFT, 0.9 overlap
  throughput  | 16384 NFFT, 0.75 overlap | 32768 NFFT, 0.9375 overlap
  realtime    | 4096 NFFT, 0.75 overlap  | 8192 NFFT, 0.9 overlap
  accuracy    | 4096 NFFT, 0.75 overlap  | 8192 NFFT, 0.9 overlap

  Both variants use 48kHz sample rate for ionosphere research.
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

    // Ionosphere variants (mutually exclusive)
    else if (arg == "--iono") {
      iono_variant = IonoVariant::IONO;
    } else if (arg == "--ionox") {
      iono_variant = IonoVariant::IONOX;
    }

    // Engine parameters (overrides)
    else if (arg == "--nfft" && i + 1 < argc) {
      overrides.nfft = std::stoi(argv[++i]);
      overrides.has_nfft = true;
    } else if (arg == "--channels" && i + 1 < argc) {
      overrides.channels = std::stoi(argv[++i]);
      overrides.has_channels = true;
    } else if (arg == "--overlap" && i + 1 < argc) {
      overrides.overlap = std::stof(argv[++i]);
      overrides.has_overlap = true;
    } else if (arg == "--sample-rate" && i + 1 < argc) {
      overrides.sample_rate_hz = std::stoi(argv[++i]);
      overrides.has_sample_rate = true;
    } else if (arg == "--streams" && i + 1 < argc) {
      overrides.stream_count = std::stoi(argv[++i]);
      overrides.has_streams = true;
    } else if (arg == "--exec-mode" && i + 1 < argc) {
      overrides.exec_mode = string_to_exec_mode(argv[++i]);
      overrides.has_exec_mode = true;
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
    } else if (arg == "--safe-print") {
      safe_print = true;
    }

    // Dataset control
    else if (arg == "--save-dataset") {
      save_dataset = true;
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
  config.iono_variant = iono_variant;
  if (iono_variant == IonoVariant::IONO) {
    apply_iono_variant(config);
  } else if (iono_variant == IonoVariant::IONOX) {
    apply_ionox_variant(config);
  }

  // Apply output settings
  config.output_format = output_format;
  config.quiet = quiet;
  config.safe_print = safe_print;

  // Apply dataset settings
  config.save_dataset = save_dataset;

  // Apply parameter overrides
  if (overrides.has_nfft) config.nfft = overrides.nfft;
  if (overrides.has_channels) config.channels = overrides.channels;
  if (overrides.has_overlap) config.overlap = overrides.overlap;
  if (overrides.has_sample_rate) config.sample_rate_hz = overrides.sample_rate_hz;
  if (overrides.has_streams) config.stream_count = overrides.stream_count;
  if (overrides.has_iterations) config.iterations = overrides.iterations;
  if (overrides.has_duration) config.duration_seconds = overrides.duration_seconds;
  if (overrides.has_warmup) config.warmup_iterations = overrides.warmup_iterations;
  if (overrides.has_seed) config.random_seed = overrides.random_seed;
  if (overrides.has_exec_mode) config.exec_mode = overrides.exec_mode;

  return config;
}

}  // namespace benchmark
}  // namespace sigtekx
