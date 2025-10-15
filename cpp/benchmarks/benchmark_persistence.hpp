/**
 * @file benchmark_persistence.hpp
 * @brief Simple JSON-based baseline storage for performance tracking.
 *
 * Provides minimal baseline storage system for detecting performance regressions
 * over time. Baselines are stored in artifacts/benchmarks/baselines/ directory.
 */

#pragma once

#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

#include "benchmark_config.hpp"
#include "benchmark_results.hpp"

namespace ionosense {
namespace benchmark {

// ============================================================================
// Baseline Naming and Paths
// ============================================================================

/**
 * @brief Generate baseline filename from config.
 *
 * Format: <preset>_<variant>_<mode>.json
 * Example: "latency_ionosphere_full.json"
 *
 * @param config Benchmark configuration
 * @return Baseline filename
 */
inline std::string get_baseline_filename(const BenchmarkConfig& config) {
  std::string filename = preset_to_string(config.preset);
  if (config.ionosphere_variant) {
    filename += "_ionosphere";
  }
  filename += "_" + mode_to_string(config.run_mode);
  filename += ".json";
  return filename;
}

/**
 * @brief Get full path to baseline file.
 *
 * @param config Benchmark configuration
 * @return Full path to baseline JSON file
 */
inline std::string get_baseline_path(const BenchmarkConfig& config) {
  namespace fs = std::filesystem;
  fs::path baseline_dir = fs::current_path() / "artifacts" / "benchmarks" / "baselines";
  fs::create_directories(baseline_dir);
  return (baseline_dir / get_baseline_filename(config)).string();
}

// ============================================================================
// JSON Serialization (Minimal, no external dependencies)
// ============================================================================

/**
 * @brief Serialize latency results to JSON string.
 *
 * @param results Latency results
 * @return JSON string
 */
inline std::string serialize_latency_results(const LatencyResults& results) {
  std::ostringstream json;
  json << "{\n";
  json << "  \"mean_latency_us\": " << results.mean_latency_us << ",\n";
  json << "  \"p50_latency_us\": " << results.p50_latency_us << ",\n";
  json << "  \"p95_latency_us\": " << results.p95_latency_us << ",\n";
  json << "  \"p99_latency_us\": " << results.p99_latency_us << ",\n";
  json << "  \"min_latency_us\": " << results.min_latency_us << ",\n";
  json << "  \"max_latency_us\": " << results.max_latency_us << ",\n";
  json << "  \"std_latency_us\": " << results.std_latency_us << ",\n";
  json << "  \"coefficient_of_variation\": " << results.coefficient_of_variation << ",\n";
  json << "  \"frames_processed\": " << results.frames_processed << "\n";
  json << "}";
  return json.str();
}

/**
 * @brief Serialize throughput results to JSON string.
 *
 * @param results Throughput results
 * @return JSON string
 */
inline std::string serialize_throughput_results(const ThroughputResults& results) {
  std::ostringstream json;
  json << "{\n";
  json << "  \"frames_per_second\": " << results.frames_per_second << ",\n";
  json << "  \"gb_per_second\": " << results.gb_per_second << ",\n";
  json << "  \"samples_per_second\": " << results.samples_per_second << ",\n";
  json << "  \"total_frames\": " << results.total_frames << ",\n";
  json << "  \"test_duration_s\": " << results.test_duration_s << "\n";
  json << "}";
  return json.str();
}

/**
 * @brief Serialize realtime results to JSON string.
 *
 * @param results Realtime results
 * @return JSON string
 */
inline std::string serialize_realtime_results(const RealtimeResults& results) {
  std::ostringstream json;
  json << "{\n";
  json << "  \"compliance_rate\": " << results.compliance_rate << ",\n";
  json << "  \"mean_latency_ms\": " << results.mean_latency_ms << ",\n";
  json << "  \"p99_latency_ms\": " << results.p99_latency_ms << ",\n";
  json << "  \"mean_jitter_ms\": " << results.mean_jitter_ms << ",\n";
  json << "  \"frames_processed\": " << results.frames_processed << ",\n";
  json << "  \"deadline_misses\": " << results.deadline_misses << "\n";
  json << "}";
  return json.str();
}

/**
 * @brief Serialize accuracy results to JSON string.
 *
 * @param results Accuracy results
 * @return JSON string
 */
inline std::string serialize_accuracy_results(const AccuracyResults& results) {
  std::ostringstream json;
  json << "{\n";
  json << "  \"pass_rate\": " << results.pass_rate << ",\n";
  json << "  \"mean_snr_db\": " << results.mean_snr_db << ",\n";
  json << "  \"mean_mae\": " << results.mean_mae << ",\n";
  json << "  \"mean_rmse\": " << results.mean_rmse << ",\n";
  json << "  \"max_error\": " << results.max_error << ",\n";
  json << "  \"tests_passed\": " << results.tests_passed << ",\n";
  json << "  \"tests_total\": " << results.tests_total << "\n";
  json << "}";
  return json.str();
}

// ============================================================================
// Baseline Storage
// ============================================================================

/**
 * @brief Save latency baseline to disk.
 *
 * @param config Benchmark configuration
 * @param results Latency results
 */
inline void save_latency_baseline(const BenchmarkConfig& config,
                                   const LatencyResults& results) {
  std::string path = get_baseline_path(config);
  std::ofstream file(path);
  if (file.is_open()) {
    file << serialize_latency_results(results);
    file.close();
  }
}

/**
 * @brief Save throughput baseline to disk.
 *
 * @param config Benchmark configuration
 * @param results Throughput results
 */
inline void save_throughput_baseline(const BenchmarkConfig& config,
                                      const ThroughputResults& results) {
  std::string path = get_baseline_path(config);
  std::ofstream file(path);
  if (file.is_open()) {
    file << serialize_throughput_results(results);
    file.close();
  }
}

/**
 * @brief Save realtime baseline to disk.
 *
 * @param config Benchmark configuration
 * @param results Realtime results
 */
inline void save_realtime_baseline(const BenchmarkConfig& config,
                                    const RealtimeResults& results) {
  std::string path = get_baseline_path(config);
  std::ofstream file(path);
  if (file.is_open()) {
    file << serialize_realtime_results(results);
    file.close();
  }
}

/**
 * @brief Save accuracy baseline to disk.
 *
 * @param config Benchmark configuration
 * @param results Accuracy results
 */
inline void save_accuracy_baseline(const BenchmarkConfig& config,
                                    const AccuracyResults& results) {
  std::string path = get_baseline_path(config);
  std::ofstream file(path);
  if (file.is_open()) {
    file << serialize_accuracy_results(results);
    file.close();
  }
}

// ============================================================================
// Baseline Loading (Simple string parsing)
// ============================================================================

/**
 * @brief Parse float value from JSON line.
 *
 * Format: "  \"key\": value,\n"
 *
 * @param line JSON line
 * @return Parsed float value, or 0.0f if parse fails
 */
inline float parse_json_float(const std::string& line) {
  size_t colon = line.find(':');
  if (colon != std::string::npos) {
    std::string value_str = line.substr(colon + 1);
    // Remove trailing comma and whitespace
    size_t comma = value_str.find(',');
    if (comma != std::string::npos) {
      value_str = value_str.substr(0, comma);
    }
    try {
      return std::stof(value_str);
    } catch (...) {
      return 0.0f;
    }
  }
  return 0.0f;
}

/**
 * @brief Parse size_t value from JSON line.
 *
 * @param line JSON line
 * @return Parsed size_t value
 */
inline size_t parse_json_size_t(const std::string& line) {
  return static_cast<size_t>(parse_json_float(line));
}

/**
 * @brief Load latency baseline from disk.
 *
 * @param config Benchmark configuration
 * @param results Output latency results (populated if baseline exists)
 * @return True if baseline was loaded successfully
 */
inline bool load_latency_baseline(const BenchmarkConfig& config,
                                   LatencyResults& results) {
  std::string path = get_baseline_path(config);
  std::ifstream file(path);
  if (!file.is_open()) {
    return false;
  }

  std::string line;
  while (std::getline(file, line)) {
    if (line.find("mean_latency_us") != std::string::npos) {
      results.mean_latency_us = parse_json_float(line);
    } else if (line.find("p50_latency_us") != std::string::npos) {
      results.p50_latency_us = parse_json_float(line);
    } else if (line.find("p95_latency_us") != std::string::npos) {
      results.p95_latency_us = parse_json_float(line);
    } else if (line.find("p99_latency_us") != std::string::npos) {
      results.p99_latency_us = parse_json_float(line);
    } else if (line.find("std_latency_us") != std::string::npos) {
      results.std_latency_us = parse_json_float(line);
    } else if (line.find("coefficient_of_variation") != std::string::npos) {
      results.coefficient_of_variation = parse_json_float(line);
    }
  }

  file.close();
  return true;
}

/**
 * @brief Load throughput baseline from disk.
 *
 * @param config Benchmark configuration
 * @param results Output throughput results
 * @return True if baseline was loaded successfully
 */
inline bool load_throughput_baseline(const BenchmarkConfig& config,
                                      ThroughputResults& results) {
  std::string path = get_baseline_path(config);
  std::ifstream file(path);
  if (!file.is_open()) {
    return false;
  }

  std::string line;
  while (std::getline(file, line)) {
    if (line.find("frames_per_second") != std::string::npos) {
      results.frames_per_second = parse_json_float(line);
    } else if (line.find("gb_per_second") != std::string::npos) {
      results.gb_per_second = parse_json_float(line);
    } else if (line.find("samples_per_second") != std::string::npos) {
      results.samples_per_second = parse_json_float(line);
    }
  }

  file.close();
  return true;
}

/**
 * @brief Load realtime baseline from disk.
 *
 * @param config Benchmark configuration
 * @param results Output realtime results
 * @return True if baseline was loaded successfully
 */
inline bool load_realtime_baseline(const BenchmarkConfig& config,
                                    RealtimeResults& results) {
  std::string path = get_baseline_path(config);
  std::ifstream file(path);
  if (!file.is_open()) {
    return false;
  }

  std::string line;
  while (std::getline(file, line)) {
    if (line.find("compliance_rate") != std::string::npos) {
      results.compliance_rate = parse_json_float(line);
    } else if (line.find("mean_latency_ms") != std::string::npos) {
      results.mean_latency_ms = parse_json_float(line);
    } else if (line.find("p99_latency_ms") != std::string::npos) {
      results.p99_latency_ms = parse_json_float(line);
    } else if (line.find("mean_jitter_ms") != std::string::npos) {
      results.mean_jitter_ms = parse_json_float(line);
    }
  }

  file.close();
  return true;
}

/**
 * @brief Load accuracy baseline from disk.
 *
 * @param config Benchmark configuration
 * @param results Output accuracy results
 * @return True if baseline was loaded successfully
 */
inline bool load_accuracy_baseline(const BenchmarkConfig& config,
                                    AccuracyResults& results) {
  std::string path = get_baseline_path(config);
  std::ifstream file(path);
  if (!file.is_open()) {
    return false;
  }

  std::string line;
  while (std::getline(file, line)) {
    if (line.find("pass_rate") != std::string::npos) {
      results.pass_rate = parse_json_float(line);
    } else if (line.find("mean_snr_db") != std::string::npos) {
      results.mean_snr_db = parse_json_float(line);
    } else if (line.find("mean_mae") != std::string::npos) {
      results.mean_mae = parse_json_float(line);
    } else if (line.find("max_error") != std::string::npos) {
      results.max_error = parse_json_float(line);
    }
  }

  file.close();
  return true;
}

/**
 * @brief Check if baseline exists for given config.
 *
 * @param config Benchmark configuration
 * @return True if baseline file exists
 */
inline bool baseline_exists(const BenchmarkConfig& config) {
  namespace fs = std::filesystem;
  return fs::exists(get_baseline_path(config));
}

}  // namespace benchmark
}  // namespace ionosense
