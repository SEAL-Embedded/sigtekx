/**
 * @file csv_writer.hpp
 * @brief CSV export for dataset analysis.
 *
 * Provides CSV export functions for each benchmark type, enabling
 * easy analysis in Excel, Python, or other tools.
 *
 * CSV Format: C++-specific (separate from Python experiment CSVs)
 * - Header row with column names
 * - Single data row with results
 * - Includes config, timestamp, git commit for traceability
 */

#pragma once

#include <fstream>
#include <sstream>
#include <string>

#include "../benchmarks/core/config.hpp"
#include "../benchmarks/core/results.hpp"
#include "../benchmarks/utils/git_info.hpp"

namespace sigtekx {
namespace benchmark {

// ============================================================================
// CSV Escaping Utilities
// ============================================================================

/**
 * @brief Escape CSV string (quotes and commas).
 *
 * @param str Input string
 * @return Escaped string
 */
inline std::string escape_csv(const std::string& str) {
  if (str.find(',') != std::string::npos ||
      str.find('"') != std::string::npos ||
      str.find('\n') != std::string::npos) {
    // Need to escape - wrap in quotes and double any internal quotes
    std::string escaped = "\"";
    for (char c : str) {
      if (c == '"') {
        escaped += "\"\"";  // Double quotes
      } else {
        escaped += c;
      }
    }
    escaped += "\"";
    return escaped;
  }
  return str;
}

/**
 * @brief Convert IonoVariant to string.
 *
 * @param variant Ionosphere variant
 * @return String representation
 */
inline std::string iono_variant_to_string(IonoVariant variant) {
  switch (variant) {
    case IonoVariant::IONO: return "iono";
    case IonoVariant::IONOX: return "ionox";
    default: return "none";
  }
}

// ============================================================================
// CSV Writers (Type-Specific)
// ============================================================================

/**
 * @brief Write latency results to CSV file.
 *
 * @param path Output CSV file path
 * @param config Benchmark configuration
 * @param results Latency results
 * @param timestamp Timestamp string
 * @param git_commit Git commit hash
 */
inline void write_latency_csv(const std::filesystem::path& path,
                               const BenchmarkConfig& config,
                               const LatencyResults& results,
                               const std::string& timestamp,
                               const std::string& git_commit) {
  std::ofstream file(path);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write CSV: " + path.string());
  }

  // Header
  file << "preset,iono_variant,mode,nfft,channels,overlap,sample_rate_hz,"
       << "mean_latency_us,p50_latency_us,p95_latency_us,p99_latency_us,"
       << "min_latency_us,max_latency_us,std_latency_us,cv,"
       << "frames_processed,timestamp,git_commit\n";

  // Data row
  file << escape_csv(preset_to_string(config.preset)) << ","
       << escape_csv(iono_variant_to_string(config.iono_variant)) << ","
       << escape_csv(mode_to_string(config.run_mode)) << ","
       << config.nfft << ","
       << config.channels << ","
       << config.overlap << ","
       << config.sample_rate_hz << ","
       << results.mean_latency_us << ","
       << results.p50_latency_us << ","
       << results.p95_latency_us << ","
       << results.p99_latency_us << ","
       << results.min_latency_us << ","
       << results.max_latency_us << ","
       << results.std_latency_us << ","
       << results.coefficient_of_variation << ","
       << results.frames_processed << ","
       << escape_csv(timestamp) << ","
       << escape_csv(git_commit) << "\n";

  file.close();
}

/**
 * @brief Write throughput results to CSV file.
 *
 * @param path Output CSV file path
 * @param config Benchmark configuration
 * @param results Throughput results
 * @param timestamp Timestamp string
 * @param git_commit Git commit hash
 */
inline void write_throughput_csv(const std::filesystem::path& path,
                                  const BenchmarkConfig& config,
                                  const ThroughputResults& results,
                                  const std::string& timestamp,
                                  const std::string& git_commit) {
  std::ofstream file(path);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write CSV: " + path.string());
  }

  // Header
  file << "preset,iono_variant,mode,nfft,channels,overlap,sample_rate_hz,"
       << "frames_per_second,gb_per_second,samples_per_second,"
       << "total_frames,test_duration_s,timestamp,git_commit\n";

  // Data row
  file << escape_csv(preset_to_string(config.preset)) << ","
       << escape_csv(iono_variant_to_string(config.iono_variant)) << ","
       << escape_csv(mode_to_string(config.run_mode)) << ","
       << config.nfft << ","
       << config.channels << ","
       << config.overlap << ","
       << config.sample_rate_hz << ","
       << results.frames_per_second << ","
       << results.gb_per_second << ","
       << results.samples_per_second << ","
       << results.total_frames << ","
       << results.test_duration_s << ","
       << escape_csv(timestamp) << ","
       << escape_csv(git_commit) << "\n";

  file.close();
}

/**
 * @brief Write realtime results to CSV file.
 *
 * @param path Output CSV file path
 * @param config Benchmark configuration
 * @param results Realtime results
 * @param timestamp Timestamp string
 * @param git_commit Git commit hash
 */
inline void write_realtime_csv(const std::filesystem::path& path,
                                const BenchmarkConfig& config,
                                const RealtimeResults& results,
                                const std::string& timestamp,
                                const std::string& git_commit) {
  std::ofstream file(path);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write CSV: " + path.string());
  }

  // Header
  file << "preset,iono_variant,mode,nfft,channels,overlap,sample_rate_hz,"
       << "compliance_rate,mean_latency_ms,p99_latency_ms,mean_jitter_ms,"
       << "frames_processed,deadline_misses,timestamp,git_commit\n";

  // Data row
  file << escape_csv(preset_to_string(config.preset)) << ","
       << escape_csv(iono_variant_to_string(config.iono_variant)) << ","
       << escape_csv(mode_to_string(config.run_mode)) << ","
       << config.nfft << ","
       << config.channels << ","
       << config.overlap << ","
       << config.sample_rate_hz << ","
       << results.compliance_rate << ","
       << results.mean_latency_ms << ","
       << results.p99_latency_ms << ","
       << results.mean_jitter_ms << ","
       << results.frames_processed << ","
       << results.deadline_misses << ","
       << escape_csv(timestamp) << ","
       << escape_csv(git_commit) << "\n";

  file.close();
}

/**
 * @brief Write accuracy results to CSV file.
 *
 * @param path Output CSV file path
 * @param config Benchmark configuration
 * @param results Accuracy results
 * @param timestamp Timestamp string
 * @param git_commit Git commit hash
 */
inline void write_accuracy_csv(const std::filesystem::path& path,
                                const BenchmarkConfig& config,
                                const AccuracyResults& results,
                                const std::string& timestamp,
                                const std::string& git_commit) {
  std::ofstream file(path);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write CSV: " + path.string());
  }

  // Header
  file << "preset,iono_variant,mode,nfft,channels,overlap,sample_rate_hz,"
       << "pass_rate,mean_snr_db,mean_mae,mean_rmse,max_error,"
       << "tests_passed,tests_total,timestamp,git_commit\n";

  // Data row
  file << escape_csv(preset_to_string(config.preset)) << ","
       << escape_csv(iono_variant_to_string(config.iono_variant)) << ","
       << escape_csv(mode_to_string(config.run_mode)) << ","
       << config.nfft << ","
       << config.channels << ","
       << config.overlap << ","
       << config.sample_rate_hz << ","
       << results.pass_rate << ","
       << results.mean_snr_db << ","
       << results.mean_mae << ","
       << results.mean_rmse << ","
       << results.max_error << ","
       << results.tests_passed << ","
       << results.tests_total << ","
       << escape_csv(timestamp) << ","
       << escape_csv(git_commit) << "\n";

  file.close();
}

}  // namespace benchmark
}  // namespace sigtekx
