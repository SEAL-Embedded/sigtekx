/**
 * @file benchmark_formatters.hpp
 * @brief Output formatting for benchmark results.
 *
 * Provides formatted output (table, CSV, JSON) for all benchmark types
 * including latency, throughput, realtime, and accuracy.
 */

#pragma once

#include <iomanip>
#include <iostream>
#include <string>

#include "../benchmarks/core/config.hpp"
#include "../benchmarks/core/persistence.hpp"
#include "../benchmarks/core/results.hpp"
#include "ionosense/executors/batch_executor.hpp"

namespace ionosense {
namespace benchmark {

// ============================================================================
// Safe Print Helpers (ASCII fallback for profiling/redirects)
// ============================================================================

/**
 * @brief Get microsecond unit string (safe for profiling).
 *
 * @param safe_print If true, returns ASCII "us"; otherwise UTF-8 "µs"
 * @return Unit string
 */
inline const char* get_us_unit(bool safe_print) {
  return safe_print ? "us" : "\xC2\xB5s";  // µs in UTF-8
}

/**
 * @brief Get box drawing horizontal line (safe for profiling).
 *
 * @param safe_print If true, returns ASCII "="; otherwise UTF-8 box drawing
 * @return Line character string (repeated to form line)
 */
inline const char* get_hline_char(bool safe_print) {
  return safe_print ? "=" : "\xE2\x94\x80";  // ─ in UTF-8
}

// ============================================================================
// Performance Tier Classification
// ============================================================================

enum class PerformanceTier {
  EXCELLENT,  // Well above target
  GOOD,       // Meets target
  ADEQUATE,   // Close to target
  POOR        // Below target
};

/**
 * @brief Classify latency performance tier.
 *
 * @param latency_us P95 latency in microseconds
 * @param target_us Target latency (default: 200µs for ionosphere)
 * @return Performance tier
 */
inline PerformanceTier classify_latency_tier(float latency_us, float target_us = 200.0f) {
  if (latency_us < target_us * 0.5f) return PerformanceTier::EXCELLENT;
  if (latency_us < target_us * 0.75f) return PerformanceTier::GOOD;
  if (latency_us < target_us) return PerformanceTier::ADEQUATE;
  return PerformanceTier::POOR;
}

/**
 * @brief Classify throughput performance tier.
 *
 * @param fps Frames per second
 * @param target_fps Target FPS (default: 1000)
 * @return Performance tier
 */
inline PerformanceTier classify_throughput_tier(float fps, float target_fps = 1000.0f) {
  if (fps > target_fps * 2.0f) return PerformanceTier::EXCELLENT;
  if (fps > target_fps * 1.5f) return PerformanceTier::GOOD;
  if (fps > target_fps) return PerformanceTier::ADEQUATE;
  return PerformanceTier::POOR;
}

/**
 * @brief Classify realtime compliance tier.
 *
 * @param compliance_rate Deadline compliance rate (0-1)
 * @return Performance tier
 */
inline PerformanceTier classify_realtime_tier(float compliance_rate) {
  if (compliance_rate >= 0.999f) return PerformanceTier::EXCELLENT;
  if (compliance_rate >= 0.99f) return PerformanceTier::GOOD;
  if (compliance_rate >= 0.95f) return PerformanceTier::ADEQUATE;
  return PerformanceTier::POOR;
}

/**
 * @brief Get performance tier symbol.
 *
 * @param tier Performance tier
 * @param safe_print If true, returns ASCII; otherwise UTF-8 symbols
 * @return Symbol (✓/⚠/✗ or OK/WARN/FAIL)
 */
inline const char* get_tier_symbol(PerformanceTier tier, bool safe_print = false) {
  if (safe_print) {
    // ASCII fallback for profiling/redirect
    switch (tier) {
      case PerformanceTier::EXCELLENT:
      case PerformanceTier::GOOD:
        return "OK";
      case PerformanceTier::ADEQUATE:
        return "WARN";
      case PerformanceTier::POOR:
        return "FAIL";
      default:
        return "?";
    }
  } else {
    // UTF-8 symbols for normal output
    switch (tier) {
      case PerformanceTier::EXCELLENT:
      case PerformanceTier::GOOD:
        return "\xE2\x9C\x93";  // ✓ (UTF-8)
      case PerformanceTier::ADEQUATE:
        return "\xE2\x9A\xA0";  // ⚠ (UTF-8)
      case PerformanceTier::POOR:
        return "\xE2\x9C\x97";  // ✗ (UTF-8)
      default:
        return "?";
    }
  }
}

/**
 * @brief Get performance tier label.
 *
 * @param tier Performance tier
 * @return Label string
 */
inline const char* get_tier_label(PerformanceTier tier) {
  switch (tier) {
    case PerformanceTier::EXCELLENT:
      return "EXCELLENT";
    case PerformanceTier::GOOD:
      return "GOOD";
    case PerformanceTier::ADEQUATE:
      return "ADEQUATE";
    case PerformanceTier::POOR:
      return "POOR";
    default:
      return "UNKNOWN";
  }
}

/**
 * @brief Classify stability tier.
 *
 * @param cv Coefficient of variation
 * @return Performance tier
 */
inline PerformanceTier classify_stability_tier(float cv) {
  if (cv < 0.03f) return PerformanceTier::EXCELLENT;  // <3% CV
  if (cv < 0.07f) return PerformanceTier::GOOD;       // <7% CV
  if (cv < 0.10f) return PerformanceTier::ADEQUATE;   // <10% CV
  return PerformanceTier::POOR;
}

/**
 * @brief Compute percent change from baseline.
 *
 * @param current Current value
 * @param baseline Baseline value
 * @return Percent change (positive = improvement for latency, regression for throughput)
 */
inline float compute_percent_change(float current, float baseline) {
  if (baseline == 0.0f) return 0.0f;
  return ((current - baseline) / baseline) * 100.0f;
}

// ============================================================================
// Latency Results Formatting
// ============================================================================

/**
 * @brief Print formatted latency benchmark results.
 *
 * @param config Benchmark configuration
 * @param results Latency results
 * @param runtime_info Runtime information from engine
 */
inline void print_latency_results(const BenchmarkConfig& config,
                                   const LatencyResults& results,
                                   const RuntimeInfo& runtime_info) {
  // Load baseline if it exists
  LatencyResults baseline;
  bool has_baseline = load_latency_baseline(config, baseline);

  if (config.output_format == OutputFormat::TABLE && !config.quiet) {
    std::cout << "\n";
    std::cout << "========================================\n";
    std::cout << "  Latency Benchmark Results\n";
    std::cout << "========================================\n\n";

    std::cout << "Configuration:\n";
    std::cout << "  Preset      : " << preset_to_string(config.preset);
    if (config.iono_variant == IonoVariant::IONO)
      std::cout << " (iono)";
    else if (config.iono_variant == IonoVariant::IONOX)
      std::cout << " (ionox)";
    std::cout << "\n";
    std::cout << "  Run Mode    : " << mode_to_string(config.run_mode) << "\n";
    std::cout << "  NFFT        : " << config.nfft << "\n";
    std::cout << "  Channels    : " << config.channels << "\n";
    std::cout << "  Exec Mode   : " << exec_mode_to_string(config.exec_mode) << "\n";
    std::cout << "  Overlap     : " << config.overlap << "\n";
    std::cout << "  Iterations  : " << config.iterations << "\n\n";

    std::cout << "Runtime:\n";
    std::cout << "  Device      : " << runtime_info.device_name << "\n";
    std::cout << "  CUDA        : " << runtime_info.cuda_version << "\n\n";

    std::cout << std::fixed << std::setprecision(2);
    std::cout << "Latency (" << get_us_unit(config.safe_print) << "):\n";
    std::cout << "  Mean        : " << results.mean_latency_us << "\n";
    std::cout << "  Median      : " << results.median_latency_us << "\n";
    std::cout << "  P50         : " << results.p50_latency_us << "\n";
    std::cout << "  P95         : " << results.p95_latency_us << "\n";
    std::cout << "  P99         : " << results.p99_latency_us << "\n";
    std::cout << "  Min         : " << results.min_latency_us << "\n";
    std::cout << "  Max         : " << results.max_latency_us << "\n";
    std::cout << "  Std Dev     : " << results.std_latency_us << "\n";
    std::cout << "  IQR         : " << results.iqr_latency_us << "\n\n";

    // Statistical Validation
    std::cout << "Stability:\n";
    std::cout << "  CV          : " << (results.coefficient_of_variation * 100.0f) << "%\n";
    std::cout << "  95% CI      : [" << results.confidence_interval_95_lower
              << ", " << results.confidence_interval_95_upper << "]\n";
    std::cout << "  Stable      : " << (results.is_stable ? "Yes" : "No") << "\n";
    if (results.outliers_trimmed > 0) {
      std::cout << "  Outliers    : " << results.outliers_trimmed << " trimmed (1% each tail)\n";
    }
    if (results.warmup_effectiveness != 0.0f) {
      std::cout << "  Warmup Eff  : " << results.warmup_effectiveness << " " << get_us_unit(config.safe_print);
      if (results.warmup_effectiveness > 0.0f) {
        std::cout << " (effective)";
      } else {
        std::cout << " (ineffective - increase warmup!)";
      }
      std::cout << "\n";
    }
    std::cout << "\n";

    // Performance Card - draw horizontal lines
    const char* hline = get_hline_char(config.safe_print);
    for (int i = 0; i < 32; ++i) std::cout << hline;
    std::cout << "\n";
    std::cout << "Performance Card\n";
    for (int i = 0; i < 32; ++i) std::cout << hline;
    std::cout << "\n";

    auto latency_tier = classify_latency_tier(results.p95_latency_us);
    auto stability_tier = classify_stability_tier(results.coefficient_of_variation);

    std::cout << "Latency (P95): " << std::setw(8) << results.p95_latency_us << " " << get_us_unit(config.safe_print) << "  ["
              << get_tier_symbol(latency_tier, config.safe_print) << " " << get_tier_label(latency_tier) << "]\n";
    std::cout << "Stability:     CV=" << std::setw(5) << (results.coefficient_of_variation * 100.0f) << "%  ["
              << get_tier_symbol(stability_tier, config.safe_print) << " " << get_tier_label(stability_tier) << "]\n";

    if (has_baseline) {
      float change = compute_percent_change(results.p95_latency_us, baseline.p95_latency_us);
      std::cout << "vs Baseline:   " << std::setw(6) << std::showpos << change << std::noshowpos << "%     [";
      if (std::abs(change) < 2.0f) {
        std::cout << get_tier_symbol(PerformanceTier::GOOD, config.safe_print) << " NO CHANGE";
      } else if (change < 0.0f) {
        std::cout << get_tier_symbol(PerformanceTier::EXCELLENT, config.safe_print) << " IMPROVED";
      } else if (change < 5.0f) {
        std::cout << get_tier_symbol(PerformanceTier::ADEQUATE, config.safe_print) << " SLIGHT REGRESSION";
      } else {
        std::cout << get_tier_symbol(PerformanceTier::POOR, config.safe_print) << " REGRESSION";
      }
      std::cout << "]\n";
    }

    for (int i = 0; i < 32; ++i) std::cout << hline;
    std::cout << "\n\n";
  }

  if (config.output_format == OutputFormat::CSV ||
      (config.output_format == OutputFormat::TABLE && !config.quiet)) {
    if (config.output_format == OutputFormat::TABLE) {
      std::cout << "CSV Output:\n";
    }
    std::cout << "preset,mode,ionosphere,nfft,channels,exec_mode,iterations,mean_us,p50_"
                 "us,p95_us,p99_us,min_us,max_us,std_us\n";
    std::cout << preset_to_string(config.preset) << ","
              << mode_to_string(config.run_mode) << ","
              << (config.iono_variant == IonoVariant::IONO ? "iono" : config.iono_variant == IonoVariant::IONOX ? "ionox" : "none") << ","
              << config.nfft << "," << config.channels << ","
              << exec_mode_to_string(config.exec_mode) << "," << config.iterations
              << "," << results.mean_latency_us << "," << results.p50_latency_us
              << "," << results.p95_latency_us << "," << results.p99_latency_us
              << "," << results.min_latency_us << "," << results.max_latency_us
              << "," << results.std_latency_us << "\n";
  }
}

// ============================================================================
// Throughput Results Formatting
// ============================================================================

/**
 * @brief Print formatted throughput benchmark results.
 *
 * @param config Benchmark configuration
 * @param results Throughput results
 * @param runtime_info Runtime information from engine
 */
inline void print_throughput_results(const BenchmarkConfig& config,
                                      const ThroughputResults& results,
                                      const RuntimeInfo& runtime_info) {
  // Load baseline if it exists
  ThroughputResults baseline;
  bool has_baseline = load_throughput_baseline(config, baseline);

  if (config.output_format == OutputFormat::TABLE && !config.quiet) {
    std::cout << "\n";
    std::cout << "========================================\n";
    std::cout << "  Throughput Benchmark Results\n";
    std::cout << "========================================\n\n";

    std::cout << "Configuration:\n";
    std::cout << "  Preset      : " << preset_to_string(config.preset);
    if (config.iono_variant == IonoVariant::IONO)
      std::cout << " (iono)";
    else if (config.iono_variant == IonoVariant::IONOX)
      std::cout << " (ionox)";
    std::cout << "\n";
    std::cout << "  Run Mode    : " << mode_to_string(config.run_mode) << "\n";
    std::cout << "  NFFT        : " << config.nfft << "\n";
    std::cout << "  Channels    : " << config.channels << "\n";
    std::cout << "  Exec Mode   : " << exec_mode_to_string(config.exec_mode) << "\n";
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

    // Performance Card - draw horizontal lines
    const char* hline = get_hline_char(config.safe_print);
    for (int i = 0; i < 32; ++i) std::cout << hline;
    std::cout << "\n";
    std::cout << "Performance Card\n";
    for (int i = 0; i < 32; ++i) std::cout << hline;
    std::cout << "\n";

    auto throughput_tier = classify_throughput_tier(results.frames_per_second);

    std::cout << "Throughput:    " << std::setw(8) << results.frames_per_second << " FPS  ["
              << get_tier_symbol(throughput_tier, config.safe_print) << " " << get_tier_label(throughput_tier) << "]\n";
    std::cout << "Bandwidth:     " << std::setw(8) << results.gb_per_second << " GB/s\n";

    if (has_baseline) {
      float change = compute_percent_change(results.frames_per_second, baseline.frames_per_second);
      std::cout << "vs Baseline:   " << std::setw(6) << std::showpos << change << std::noshowpos << "%     [";
      if (std::abs(change) < 2.0f) {
        std::cout << get_tier_symbol(PerformanceTier::GOOD, config.safe_print) << " NO CHANGE";
      } else if (change > 0.0f) {
        std::cout << get_tier_symbol(PerformanceTier::EXCELLENT, config.safe_print) << " IMPROVED";
      } else if (change > -5.0f) {
        std::cout << get_tier_symbol(PerformanceTier::ADEQUATE, config.safe_print) << " SLIGHT REGRESSION";
      } else {
        std::cout << get_tier_symbol(PerformanceTier::POOR, config.safe_print) << " REGRESSION";
      }
      std::cout << "]\n";
    }

    for (int i = 0; i < 32; ++i) std::cout << hline;
    std::cout << "\n\n";
  }

  if (config.output_format == OutputFormat::CSV ||
      (config.output_format == OutputFormat::TABLE && !config.quiet)) {
    if (config.output_format == OutputFormat::TABLE) {
      std::cout << "CSV Output:\n";
    }
    std::cout << "preset,mode,ionosphere,nfft,channels,exec_mode,duration_s,fps,gb_per_s,"
                 "samples_per_s,total_frames\n";
    std::cout << preset_to_string(config.preset) << ","
              << mode_to_string(config.run_mode) << ","
              << (config.iono_variant == IonoVariant::IONO ? "iono" : config.iono_variant == IonoVariant::IONOX ? "ionox" : "none") << ","
              << config.nfft << "," << config.channels << ","
              << exec_mode_to_string(config.exec_mode) << ","
              << results.test_duration_s << "," << results.frames_per_second
              << "," << results.gb_per_second << ","
              << results.samples_per_second << "," << results.total_frames
              << "\n";
  }
}

// ============================================================================
// Realtime Results Formatting
// ============================================================================

/**
 * @brief Print formatted realtime benchmark results.
 *
 * @param config Benchmark configuration
 * @param results Realtime results
 * @param runtime_info Runtime information from engine
 */
inline void print_realtime_results(const BenchmarkConfig& config,
                                    const RealtimeResults& results,
                                    const RuntimeInfo& runtime_info) {
  // Load baseline if it exists
  RealtimeResults baseline;
  bool has_baseline = load_realtime_baseline(config, baseline);

  if (config.output_format == OutputFormat::TABLE && !config.quiet) {
    std::cout << "\n";
    std::cout << "========================================\n";
    std::cout << "  Realtime Benchmark Results\n";
    std::cout << "========================================\n\n";

    std::cout << "Configuration:\n";
    std::cout << "  Preset      : " << preset_to_string(config.preset);
    if (config.iono_variant == IonoVariant::IONO)
      std::cout << " (iono)";
    else if (config.iono_variant == IonoVariant::IONOX)
      std::cout << " (ionox)";
    std::cout << "\n";
    std::cout << "  Run Mode    : " << mode_to_string(config.run_mode) << "\n";
    std::cout << "  NFFT        : " << config.nfft << "\n";
    std::cout << "  Channels    : " << config.channels << "\n";
    std::cout << "  Exec Mode   : " << exec_mode_to_string(config.exec_mode) << "\n";
    std::cout << "  Duration    : " << config.duration_seconds << "s\n\n";

    std::cout << "Runtime:\n";
    std::cout << "  Device      : " << runtime_info.device_name << "\n";
    std::cout << "  CUDA        : " << runtime_info.cuda_version << "\n\n";

    std::cout << std::fixed << std::setprecision(2);
    std::cout << "Real-time Performance:\n";
    std::cout << "  Compliance  : " << (results.compliance_rate * 100.0f) << "%\n";
    std::cout << "  Mean Lat    : " << results.mean_latency_ms << " ms\n";
    std::cout << "  P99 Lat     : " << results.p99_latency_ms << " ms\n";
    std::cout << "  Mean Jitter : " << results.mean_jitter_ms << " ms\n";
    std::cout << "  CV          : " << (results.coefficient_of_variation * 100.0f) << "%\n";
    std::cout << "  Frames      : " << results.frames_processed << "\n";
    std::cout << "  Misses      : " << results.deadline_misses << "\n\n";

    // Performance Card - draw horizontal lines
    const char* hline = get_hline_char(config.safe_print);
    for (int i = 0; i < 32; ++i) std::cout << hline;
    std::cout << "\n";
    std::cout << "Performance Card\n";
    for (int i = 0; i < 32; ++i) std::cout << hline;
    std::cout << "\n";

    auto compliance_tier = classify_realtime_tier(results.compliance_rate);
    auto stability_tier = classify_stability_tier(results.coefficient_of_variation);

    std::cout << "Compliance:    " << std::setw(8) << (results.compliance_rate * 100.0f) << "%   ["
              << get_tier_symbol(compliance_tier, config.safe_print) << " " << get_tier_label(compliance_tier) << "]\n";
    std::cout << "Stability:     CV=" << std::setw(5) << (results.coefficient_of_variation * 100.0f) << "%  ["
              << get_tier_symbol(stability_tier, config.safe_print) << " " << get_tier_label(stability_tier) << "]\n";

    if (has_baseline) {
      float change = compute_percent_change(results.compliance_rate, baseline.compliance_rate);
      std::cout << "vs Baseline:   " << std::setw(6) << std::showpos << change << std::noshowpos << "%     [";
      if (std::abs(change) < 1.0f) {
        std::cout << get_tier_symbol(PerformanceTier::GOOD, config.safe_print) << " NO CHANGE";
      } else if (change > 0.0f) {
        std::cout << get_tier_symbol(PerformanceTier::EXCELLENT, config.safe_print) << " IMPROVED";
      } else {
        std::cout << get_tier_symbol(PerformanceTier::POOR, config.safe_print) << " REGRESSION";
      }
      std::cout << "]\n";
    }

    for (int i = 0; i < 32; ++i) std::cout << hline;
    std::cout << "\n\n";
  }

  if (config.output_format == OutputFormat::CSV ||
      (config.output_format == OutputFormat::TABLE && !config.quiet)) {
    if (config.output_format == OutputFormat::TABLE) {
      std::cout << "CSV Output:\n";
    }
    std::cout << "preset,mode,ionosphere,nfft,channels,exec_mode,compliance_rate,mean_lat_"
                 "ms,p99_lat_ms,jitter_ms,frames,misses\n";
    std::cout << preset_to_string(config.preset) << ","
              << mode_to_string(config.run_mode) << ","
              << (config.iono_variant == IonoVariant::IONO ? "iono" : config.iono_variant == IonoVariant::IONOX ? "ionox" : "none") << ","
              << config.nfft << "," << config.channels << ","
              << exec_mode_to_string(config.exec_mode) << ","
              << results.compliance_rate << "," << results.mean_latency_ms
              << "," << results.p99_latency_ms << "," << results.mean_jitter_ms
              << "," << results.frames_processed << ","
              << results.deadline_misses << "\n";
  }
}

// ============================================================================
// Accuracy Results Formatting
// ============================================================================

/**
 * @brief Print formatted accuracy benchmark results.
 *
 * @param config Benchmark configuration
 * @param results Accuracy results
 * @param runtime_info Runtime information from engine
 */
inline void print_accuracy_results(const BenchmarkConfig& config,
                                    const AccuracyResults& results,
                                    const RuntimeInfo& runtime_info) {
  if (config.output_format == OutputFormat::TABLE && !config.quiet) {
    std::cout << "\n";
    std::cout << "========================================\n";
    std::cout << "  Accuracy Benchmark Results\n";
    std::cout << "========================================\n\n";

    std::cout << "Configuration:\n";
    std::cout << "  Preset      : " << preset_to_string(config.preset);
    if (config.iono_variant == IonoVariant::IONO)
      std::cout << " (iono)";
    else if (config.iono_variant == IonoVariant::IONOX)
      std::cout << " (ionox)";
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
              << (config.iono_variant == IonoVariant::IONO ? "iono" : config.iono_variant == IonoVariant::IONOX ? "ionox" : "none") << ","
              << config.nfft << "," << config.num_test_signals << ","
              << results.pass_rate << "," << results.tests_passed << ","
              << results.tests_total << "," << results.mean_snr_db << ","
              << results.mean_mae << "," << results.mean_rmse << ","
              << results.mean_relative_error << "," << results.max_error << "\n";
  }
}

}  // namespace benchmark
}  // namespace ionosense
