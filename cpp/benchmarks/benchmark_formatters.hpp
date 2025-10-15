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

#include "benchmark_config.hpp"
#include "benchmark_results.hpp"
#include "ionosense/engines/research_engine.hpp"

namespace ionosense {
namespace benchmark {

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

}  // namespace benchmark
}  // namespace ionosense
