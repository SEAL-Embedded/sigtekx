/**
 * @file benchmark_config.hpp
 * @brief Configuration presets and structures for C++ standalone benchmarks.
 *
 * This header defines the preset system for benchmarking, matching Python
 * benchmark configurations. Provides clean separation between preset definitions
 * and benchmark execution logic.
 */

#pragma once

#include <string>
#include <vector>

#include "sigtekx/core/executor_config.hpp"

namespace sigtekx {
namespace benchmark {

// ============================================================================
// Benchmark Types and Presets
// ============================================================================

enum class BenchmarkPreset {
  DEV,         // Quick development validation (default)
  LATENCY,     // Latency measurement with iteration-based statistics
  THROUGHPUT,  // Throughput measurement with time-based statistics
  REALTIME,    // Real-time streaming with deadline compliance
  ACCURACY     // Accuracy validation with multi-signal testing
};

enum class RunMode {
  QUICK,    // Fast validation (~10-30s)
  PROFILE,  // Profile-ready (~30s-1min)
  FULL      // Production equivalent (1-10min)
};

enum class OutputFormat {
  TABLE,  // Formatted table output (default)
  CSV,    // CSV line only
  JSON    // JSON output
};

// ============================================================================
// Ionosphere Variant Types
// ============================================================================

enum class IonoVariant {
  NONE,   // Standard benchmarks (100kHz)
  IONO,   // Ionosphere standard (48kHz, 4096/16384 NFFT, 0.75 overlap)
  IONOX   // Ionosphere extreme (48kHz, 8192/32768 NFFT, 0.9/0.9375 overlap)
};

// ============================================================================
// Core Configuration Structure
// ============================================================================

struct BenchmarkConfig {
  // Preset and mode
  BenchmarkPreset preset = BenchmarkPreset::DEV;
  RunMode run_mode = RunMode::FULL;
  IonoVariant iono_variant = IonoVariant::NONE;
  ExecutorConfig::ExecutionMode exec_mode = ExecutorConfig::ExecutionMode::STREAMING;

  // Engine parameters
  int nfft = 2048;
  int channels = 4;
  float overlap = 0.625f;
  int sample_rate_hz = 48000;
  int stream_count = 3;
  int pinned_buffer_count = 2;

  // Benchmark parameters
  int iterations = 20;           // For iteration-based benchmarks
  int warmup_iterations = 5;     // Warmup iterations
  float duration_seconds = 10.0f;  // For time-based benchmarks

  // Latency-specific
  float deadline_us = 200.0f;
  bool analyze_jitter = true;

  // Throughput-specific
  bool measure_bandwidth = false;

  // Realtime-specific
  float frame_deadline_ms = 0.0f;  // Auto-calculated if 0
  bool strict_timing = true;
  int buffer_ahead_frames = 2;

  // Accuracy-specific
  float absolute_tolerance = 1.0e-6f;
  float relative_tolerance = 1.0e-5f;
  float snr_threshold_db = 60.0f;
  int num_test_signals = 8;

  // Output control
  OutputFormat output_format = OutputFormat::TABLE;
  bool quiet = false;
  bool safe_print = false;  // Use ASCII-only output (for profiling/redirect)
  int random_seed = 42;

  // Baseline control
  bool save_baseline = false;
};

// ============================================================================
// Preset Factories
// ============================================================================

inline BenchmarkConfig get_dev_config() {
  BenchmarkConfig config;
  config.preset = BenchmarkPreset::DEV;
  config.exec_mode = ExecutorConfig::ExecutionMode::STREAMING;
  config.nfft = 2048;
  config.channels = 2;
  config.overlap = 0.5f;
  config.sample_rate_hz = 100000;  // 100kHz for regular benchmarks
  config.iterations = 20;
  config.warmup_iterations = 5;
  return config;
}

inline BenchmarkConfig get_latency_config(RunMode mode = RunMode::FULL) {
  BenchmarkConfig config;
  config.preset = BenchmarkPreset::LATENCY;
  config.run_mode = mode;
  // BATCH mode for single-frame latency measurement (discrete processing)
  // Use --exec-mode streaming for continuous stream latency profiling
  config.exec_mode = ExecutorConfig::ExecutionMode::BATCH;
  config.nfft = 2048;
  config.channels = 2;  // Low channel count for minimal latency
  config.overlap = 0.5f;  // 50% overlap for regular benchmarks
  config.sample_rate_hz = 100000;  // 100kHz
  config.deadline_us = 200.0f;
  config.analyze_jitter = true;

  // Adjust iterations based on run mode
  switch (mode) {
    case RunMode::QUICK:
      config.iterations = 20;
      config.warmup_iterations = 5;
      break;
    case RunMode::PROFILE:
      config.iterations = 100;
      config.warmup_iterations = 30;  // 30% warmup for stability
      break;
    case RunMode::FULL:
      config.iterations = 5000;
      config.warmup_iterations = 1500;  // 30% warmup for production stability
      break;
  }

  return config;
}

inline BenchmarkConfig get_throughput_config(RunMode mode = RunMode::FULL) {
  BenchmarkConfig config;
  config.preset = BenchmarkPreset::THROUGHPUT;
  config.run_mode = mode;
  config.exec_mode = ExecutorConfig::ExecutionMode::BATCH;
  config.nfft = 4096;
  config.channels = 32;  // Large channel count for throughput
  config.overlap = 0.5f;  // 50% overlap
  config.sample_rate_hz = 100000;  // 100kHz
  config.measure_bandwidth = false;

  // Adjust duration based on run mode
  switch (mode) {
    case RunMode::QUICK:
      config.duration_seconds = 3.0f;
      config.warmup_iterations = 10;  // More warmup for streaming stability
      break;
    case RunMode::PROFILE:
      config.duration_seconds = 5.0f;
      config.warmup_iterations = 30;
      break;
    case RunMode::FULL:
      config.duration_seconds = 10.0f;
      config.warmup_iterations = 50;  // Increased for thermal/frequency stabilization
      break;
  }

  return config;
}

inline BenchmarkConfig get_realtime_config(RunMode mode = RunMode::FULL) {
  BenchmarkConfig config;
  config.preset = BenchmarkPreset::REALTIME;
  config.run_mode = mode;
  config.exec_mode = ExecutorConfig::ExecutionMode::STREAMING;
  config.nfft = 2048;
  config.channels = 2;  // Low channel count for streaming latency
  config.overlap = 0.5f;  // 50% overlap
  config.sample_rate_hz = 100000;  // 100kHz
  config.strict_timing = true;
  config.buffer_ahead_frames = 2;
  config.frame_deadline_ms = 0.0f;  // Auto-calculated based on sample rate

  // Adjust duration based on run mode
  switch (mode) {
    case RunMode::QUICK:
      config.duration_seconds = 3.0f;
      config.warmup_iterations = 10;  // More warmup for streaming stability
      break;
    case RunMode::PROFILE:
      config.duration_seconds = 5.0f;
      config.warmup_iterations = 30;
      break;
    case RunMode::FULL:
      config.duration_seconds = 10.0f;
      config.warmup_iterations = 50;  // Increased for thermal/frequency stabilization
      break;
  }

  return config;
}

inline BenchmarkConfig get_accuracy_config(RunMode mode = RunMode::FULL) {
  BenchmarkConfig config;
  config.preset = BenchmarkPreset::ACCURACY;
  config.run_mode = mode;
  config.exec_mode = ExecutorConfig::ExecutionMode::STREAMING;
  config.nfft = 2048;
  config.channels = 1;  // Single channel for reference test
  config.overlap = 0.0f;  // 0% overlap
  config.sample_rate_hz = 100000;  // 100kHz

  // NOTE: This is a SINGLE PIPELINE-MATCHING REFERENCE TEST.
  // Compares engine output against CPU reference that exactly mirrors pipeline:
  // - Window: Hann, PERIODIC symmetry, UNITY normalization
  // - FFT: cuFFT R2C
  // - Magnitude: sqrt(real^2 + imag^2) * (1/N) scaling
  //
  // Validates actual numerical correctness with tight tolerance (max error < 1e-4).
  // Hardcoded to current pipeline - if pipeline changes, update reference_compute.hpp.
  //
  // For comprehensive cross-platform accuracy validation, use Python:
  //   pytest tests/test_accuracy.py
  config.iterations = 1;         // Ignored (single test only)
  config.num_test_signals = 1;   // Ignored (single test only)
  config.warmup_iterations = 0;  // No warmup needed for reference test

  // Validation thresholds (used in run_accuracy_benchmark)
  config.absolute_tolerance = 1.0e-4f;  // Max absolute error
  config.relative_tolerance = 1.0e-4f;  // Max relative RMS error
  config.snr_threshold_db = 60.0f;      // Expected SNR (not enforced)

  return config;
}

// ============================================================================
// Ionosphere Variants
// ============================================================================

inline void apply_iono_variant(BenchmarkConfig& config) {
  // Iono standard: 48kHz sample rate, 75% overlap, 4096/16384 NFFT
  config.sample_rate_hz = 48000;
  config.overlap = 0.75f;

  switch (config.preset) {
    case BenchmarkPreset::LATENCY:
      // Iono latency: 4096 NFFT, low channel count for minimal latency
      config.nfft = 4096;
      config.channels = 2;
      break;

    case BenchmarkPreset::THROUGHPUT:
      // Iono throughput: 16384 NFFT, large channel count for ULF/VLF detection
      config.nfft = 16384;
      config.channels = 32;
      break;

    case BenchmarkPreset::REALTIME:
      // Iono realtime: 4096 NFFT, low channel count for streaming latency
      config.nfft = 4096;
      config.channels = 2;
      config.strict_timing = true;
      break;

    case BenchmarkPreset::ACCURACY:
      // Iono accuracy: 4096 NFFT, single channel
      config.nfft = 4096;
      config.channels = 1;
      break;

    case BenchmarkPreset::DEV:
      // Dev mode doesn't have iono variant
      break;
  }
}

inline void apply_ionox_variant(BenchmarkConfig& config) {
  // Ionox extreme: 48kHz sample rate, extreme overlap, 8192/32768 NFFT
  config.sample_rate_hz = 48000;

  switch (config.preset) {
    case BenchmarkPreset::LATENCY:
      // Ionox latency: 8192 NFFT, 90% overlap, low channel count
      config.nfft = 8192;
      config.channels = 2;
      config.overlap = 0.9f;
      break;

    case BenchmarkPreset::THROUGHPUT:
      // Ionox throughput: 32768 NFFT, 93.75% overlap for extreme missile detection
      config.nfft = 32768;
      config.channels = 32;
      config.overlap = 0.9375f;
      break;

    case BenchmarkPreset::REALTIME:
      // Ionox realtime: 8192 NFFT, 90% overlap, low channel count
      config.nfft = 8192;
      config.channels = 2;
      config.overlap = 0.9f;
      config.strict_timing = true;
      break;

    case BenchmarkPreset::ACCURACY:
      // Ionox accuracy: 8192 NFFT, 90% overlap, single batch
      config.nfft = 8192;
      config.channels = 1;
      config.overlap = 0.9f;
      break;

    case BenchmarkPreset::DEV:
      // Dev mode doesn't have ionox variant
      break;
  }
}

// ============================================================================
// Preset Name Conversion
// ============================================================================

inline std::string preset_to_string(BenchmarkPreset preset) {
  switch (preset) {
    case BenchmarkPreset::DEV:
      return "dev";
    case BenchmarkPreset::LATENCY:
      return "latency";
    case BenchmarkPreset::THROUGHPUT:
      return "throughput";
    case BenchmarkPreset::REALTIME:
      return "realtime";
    case BenchmarkPreset::ACCURACY:
      return "accuracy";
    default:
      return "unknown";
  }
}

inline BenchmarkPreset string_to_preset(const std::string& str) {
  if (str == "dev")
    return BenchmarkPreset::DEV;
  if (str == "latency")
    return BenchmarkPreset::LATENCY;
  if (str == "throughput")
    return BenchmarkPreset::THROUGHPUT;
  if (str == "realtime")
    return BenchmarkPreset::REALTIME;
  if (str == "accuracy")
    return BenchmarkPreset::ACCURACY;
  return BenchmarkPreset::DEV;  // Default
}

inline std::string mode_to_string(RunMode mode) {
  switch (mode) {
    case RunMode::QUICK:
      return "quick";
    case RunMode::PROFILE:
      return "profile";
    case RunMode::FULL:
      return "full";
    default:
      return "unknown";
  }
}

inline RunMode string_to_mode(const std::string& str) {
  if (str == "quick")
    return RunMode::QUICK;
  if (str == "profile")
    return RunMode::PROFILE;
  if (str == "full")
    return RunMode::FULL;
  return RunMode::FULL;  // Default
}

inline std::string exec_mode_to_string(ExecutorConfig::ExecutionMode mode) {
  switch (mode) {
    case ExecutorConfig::ExecutionMode::BATCH:
      return "BATCH";
    case ExecutorConfig::ExecutionMode::STREAMING:
      return "STREAMING";
    default:
      return "UNKNOWN";
  }
}

inline ExecutorConfig::ExecutionMode string_to_exec_mode(const std::string& str) {
  if (str == "batch" || str == "BATCH")
    return ExecutorConfig::ExecutionMode::BATCH;
  if (str == "streaming" || str == "STREAMING")
    return ExecutorConfig::ExecutionMode::STREAMING;
  return ExecutorConfig::ExecutionMode::STREAMING;  // Default
}

}  // namespace benchmark
}  // namespace sigtekx
