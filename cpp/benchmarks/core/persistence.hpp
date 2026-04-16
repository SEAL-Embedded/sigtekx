/**
 * @file benchmark_persistence.hpp
 * @brief Production-grade dataset storage with concurrency safety.
 *
 * Provides directory-based dataset storage system with:
 * - File-locked manifest for concurrent saves
 * - Comprehensive metadata (git, hardware, config)
 * - CSV export for analysis
 * - Statistical comparison tools
 *
 * Datasets are stored in datasets/cpp/ directory (persistent, survives `sigx clean`).
 *
 * C++ datasets live under datasets/cpp/ and are fully decoupled from the
 * Python benchmark pipeline. The `sigxc` tool manages this subtree; the
 * Python-side `sigx dataset` CLI writes to `datasets/<name>/` directly and
 * never touches datasets/cpp/.
 */

#pragma once

#include <chrono>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

#include "../benchmarks/core/config.hpp"
#include "../benchmarks/core/results.hpp"
#include "../benchmarks/utils/file_lock.hpp"
#include "../benchmarks/utils/hardware_info.hpp"
#include "../benchmarks/utils/git_info.hpp"
#include "../benchmarks/utils/csv_writer.hpp"

namespace sigtekx {
namespace benchmark {

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * @brief Get current timestamp in ISO 8601 format.
 *
 * @return Timestamp string (e.g., "2025-01-20T10:30:00Z")
 */
inline std::string get_timestamp() {
  auto now = std::chrono::system_clock::now();
  auto time_t_now = std::chrono::system_clock::to_time_t(now);
  std::tm tm_now;

#ifdef _WIN32
  gmtime_s(&tm_now, &time_t_now);
#else
  gmtime_r(&time_t_now, &tm_now);
#endif

  std::ostringstream oss;
  oss << std::put_time(&tm_now, "%Y-%m-%dT%H:%M:%SZ");
  return oss.str();
}

// ============================================================================
// Manifest Management
// ============================================================================

/**
 * @brief Dataset manifest entry.
 */
struct ManifestEntry {
  std::string name;
  std::string created;
  std::string preset;
  std::string mode;
  std::string iono_variant;
  std::string message;  // Optional description of dataset significance
};

/**
 * @brief Dataset manifest (tracks all datasets).
 */
struct Manifest {
  std::vector<ManifestEntry> datasets;
};

/**
 * @brief Get dataset root directory.
 */
inline std::filesystem::path get_dataset_root() {
  return std::filesystem::current_path() / "datasets" / "cpp";
}

/**
 * @brief Get manifest file path.
 */
inline std::filesystem::path get_manifest_path() {
  return get_dataset_root() / ".dataset_manifest.json";
}

/**
 * @brief Get manifest lock file path.
 */
inline std::filesystem::path get_manifest_lock_path() {
  return get_dataset_root() / ".dataset_manifest.json.lock";
}

/**
 * @brief Get .last_run root directory (temporary storage for most recent benchmark).
 */
inline std::filesystem::path get_last_run_root() {
  return get_dataset_root() / ".last_run";
}

/**
 * @brief Get .last_run directory for a specific preset.
 *
 * @param preset_name Preset name (latency, throughput, realtime, accuracy)
 * @return Path to .last_run/{preset}/
 */
inline std::filesystem::path get_last_run_directory(const std::string& preset_name) {
  return get_last_run_root() / preset_name;
}

/**
 * @brief Load manifest from disk.
 *
 * @return Manifest (empty if file doesn't exist)
 */
inline Manifest load_manifest() {
  Manifest manifest;
  auto path = get_manifest_path();

  if (!std::filesystem::exists(path)) {
    return manifest;
  }

  std::ifstream file(path);
  if (!file.is_open()) {
    return manifest;
  }

  // Simple JSON parsing (datasets array)
  std::string line;
  ManifestEntry current_entry;
  bool in_entry = false;

  while (std::getline(file, line)) {
    if (line.find("{") != std::string::npos && line.find("\"datasets\"") == std::string::npos) {
      in_entry = true;
      current_entry = ManifestEntry{};
    } else if (in_entry && line.find("}") != std::string::npos) {
      manifest.datasets.push_back(current_entry);
      in_entry = false;
    } else if (in_entry) {
      // Parse fields
      if (line.find("\"name\"") != std::string::npos) {
        size_t start = line.find(":") + 1;
        size_t quote_start = line.find("\"", start) + 1;
        size_t quote_end = line.find("\"", quote_start);
        current_entry.name = line.substr(quote_start, quote_end - quote_start);
      } else if (line.find("\"created\"") != std::string::npos) {
        size_t start = line.find(":") + 1;
        size_t quote_start = line.find("\"", start) + 1;
        size_t quote_end = line.find("\"", quote_start);
        current_entry.created = line.substr(quote_start, quote_end - quote_start);
      } else if (line.find("\"preset\"") != std::string::npos) {
        size_t start = line.find(":") + 1;
        size_t quote_start = line.find("\"", start) + 1;
        size_t quote_end = line.find("\"", quote_start);
        current_entry.preset = line.substr(quote_start, quote_end - quote_start);
      } else if (line.find("\"mode\"") != std::string::npos) {
        size_t start = line.find(":") + 1;
        size_t quote_start = line.find("\"", start) + 1;
        size_t quote_end = line.find("\"", quote_start);
        current_entry.mode = line.substr(quote_start, quote_end - quote_start);
      } else if (line.find("\"iono_variant\"") != std::string::npos) {
        size_t start = line.find(":") + 1;
        size_t quote_start = line.find("\"", start) + 1;
        size_t quote_end = line.find("\"", quote_start);
        current_entry.iono_variant = line.substr(quote_start, quote_end - quote_start);
      } else if (line.find("\"message\"") != std::string::npos) {
        size_t start = line.find(":") + 1;
        size_t quote_start = line.find("\"", start) + 1;
        size_t quote_end = line.find("\"", quote_start);
        if (quote_end != std::string::npos) {
          current_entry.message = line.substr(quote_start, quote_end - quote_start);
        }
      }
    }
  }

  file.close();
  return manifest;
}

/**
 * @brief Save manifest to disk (atomic write).
 *
 * @param manifest Manifest to save
 */
inline void save_manifest(const Manifest& manifest) {
  auto path = get_manifest_path();
  auto temp_path = path.string() + ".tmp";

  // Write to temp file
  std::ofstream file(temp_path);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write manifest temp file: " + temp_path);
  }

  file << "{\n";
  file << "  \"datasets\": [\n";

  for (size_t i = 0; i < manifest.datasets.size(); ++i) {
    const auto& entry = manifest.datasets[i];
    file << "    {\n";
    file << "      \"name\": \"" << entry.name << "\",\n";
    file << "      \"created\": \"" << entry.created << "\",\n";
    file << "      \"preset\": \"" << entry.preset << "\",\n";
    file << "      \"mode\": \"" << entry.mode << "\",\n";
    file << "      \"iono_variant\": \"" << entry.iono_variant << "\",\n";
    file << "      \"message\": \"" << entry.message << "\"\n";
    file << "    }";
    if (i < manifest.datasets.size() - 1) {
      file << ",";
    }
    file << "\n";
  }

  file << "  ]\n";
  file << "}\n";
  file.close();

  // Atomic rename (replaces existing file)
  std::filesystem::rename(temp_path, path);
}

/**
 * @brief Update manifest with new dataset (file-locked).
 *
 * @param name Dataset name
 * @param config Benchmark configuration
 */
inline void update_manifest(const std::string& name, const BenchmarkConfig& config) {
  FileLock lock(get_manifest_lock_path());

  // Load existing manifest
  auto manifest = load_manifest();

  // Check if dataset already exists (update timestamp)
  bool found = false;
  for (auto& entry : manifest.datasets) {
    if (entry.name == name) {
      entry.created = get_timestamp();
      found = true;
      break;
    }
  }

  // Add new entry if not found
  if (!found) {
    ManifestEntry entry;
    entry.name = name;
    entry.created = get_timestamp();
    entry.preset = preset_to_string(config.preset);
    entry.mode = mode_to_string(config.run_mode);

    if (config.iono_variant == IonoVariant::IONO) {
      entry.iono_variant = "iono";
    } else if (config.iono_variant == IonoVariant::IONOX) {
      entry.iono_variant = "ionox";
    } else {
      entry.iono_variant = "none";
    }

    manifest.datasets.push_back(entry);
  }

  // Save manifest
  save_manifest(manifest);
}

/**
 * @brief Remove dataset from manifest (file-locked).
 *
 * @param name Dataset name
 */
inline void remove_from_manifest(const std::string& name) {
  FileLock lock(get_manifest_lock_path());

  // Load existing manifest
  auto manifest = load_manifest();

  // Remove entry
  manifest.datasets.erase(
      std::remove_if(manifest.datasets.begin(), manifest.datasets.end(),
                     [&name](const ManifestEntry& entry) { return entry.name == name; }),
      manifest.datasets.end());

  // Save manifest
  save_manifest(manifest);
}

// ============================================================================
// Metadata Generation
// ============================================================================

/**
 * @brief Serialize metadata to JSON string.
 *
 * Includes: name, timestamp, config, git info, hardware info, metrics summary
 *
 * @param name Dataset name
 * @param config Benchmark configuration
 * @param results Results (for metrics summary) - generic float pointer
 * @param results_type Type of results ("latency", "throughput", etc.)
 * @return JSON string
 */
inline std::string serialize_metadata(const std::string& name,
                                       const BenchmarkConfig& config,
                                       const void* results,
                                       const std::string& results_type) {
  std::ostringstream json;

  // Get hardware and git info
  auto hardware = get_hardware_info();
  auto git = get_git_info();

  json << "{\n";
  json << "  \"name\": \"" << name << "\",\n";
  json << "  \"created\": \"" << get_timestamp() << "\",\n";
  json << "\n";

  // Config section
  json << "  \"config\": {\n";
  json << "    \"preset\": \"" << preset_to_string(config.preset) << "\",\n";
  json << "    \"run_mode\": \"" << mode_to_string(config.run_mode) << "\",\n";

  if (config.iono_variant == IonoVariant::IONO) {
    json << "    \"iono_variant\": \"iono\",\n";
  } else if (config.iono_variant == IonoVariant::IONOX) {
    json << "    \"iono_variant\": \"ionox\",\n";
  } else {
    json << "    \"iono_variant\": \"none\",\n";
  }

  json << "    \"nfft\": " << config.nfft << ",\n";
  json << "    \"channels\": " << config.channels << ",\n";
  json << "    \"overlap\": " << config.overlap << ",\n";
  json << "    \"sample_rate_hz\": " << config.sample_rate_hz << ",\n";
  json << "    \"exec_mode\": \"" << (config.exec_mode == ExecutorConfig::ExecutionMode::BATCH ? "batch" : "streaming") << "\"\n";
  json << "  },\n";
  json << "\n";

  // Git section
  json << "  \"git\": {\n";
  json << "    \"commit\": \"" << git.commit << "\",\n";
  json << "    \"branch\": \"" << git.branch << "\",\n";
  json << "    \"dirty\": " << (git.dirty ? "true" : "false") << "\n";
  json << "  },\n";
  json << "\n";

  // Hardware section
  json << "  \"hardware\": {\n";
  json << "    \"gpu\": {\n";
  json << "      \"name\": \"" << hardware.gpu.name << "\",\n";
  json << "      \"memory_gb\": " << hardware.gpu.memory_gb << ",\n";
  json << "      \"compute_capability\": \"" << hardware.gpu.compute_capability << "\",\n";
  json << "      \"cuda_runtime\": \"" << hardware.gpu.cuda_runtime << "\",\n";
  json << "      \"cuda_driver\": \"" << hardware.gpu.cuda_driver << "\"\n";
  json << "    },\n";
  json << "    \"cpu\": {\n";
  json << "      \"model\": \"" << hardware.cpu.model << "\",\n";
  json << "      \"cores\": " << hardware.cpu.cores << ",\n";
  json << "      \"threads\": " << hardware.cpu.threads << "\n";
  json << "    },\n";
  json << "    \"system\": {\n";
  json << "      \"os\": \"" << hardware.system.os << "\",\n";
  json << "      \"os_version\": \"" << hardware.system.os_version << "\",\n";
  json << "      \"ram_gb\": " << hardware.system.ram_gb << "\n";
  json << "    }\n";
  json << "  },\n";
  json << "\n";

  // Metrics summary (type-specific)
  json << "  \"metrics\": {\n";
  json << "    \"type\": \"" << results_type << "\"";

  if (results_type == "latency" && results) {
    const auto* latency = static_cast<const LatencyResults*>(results);
    json << ",\n";
    json << "    \"mean_latency_us\": " << latency->mean_latency_us << ",\n";
    json << "    \"p95_latency_us\": " << latency->p95_latency_us << ",\n";
    json << "    \"p99_latency_us\": " << latency->p99_latency_us << ",\n";
    json << "    \"cv\": " << latency->coefficient_of_variation << ",\n";
    json << "    \"frames_processed\": " << latency->frames_processed << "\n";
  } else if (results_type == "throughput" && results) {
    const auto* throughput = static_cast<const ThroughputResults*>(results);
    json << ",\n";
    json << "    \"frames_per_second\": " << throughput->frames_per_second << ",\n";
    json << "    \"gb_per_second\": " << throughput->gb_per_second << ",\n";
    json << "    \"samples_per_second\": " << throughput->samples_per_second << ",\n";
    json << "    \"total_frames\": " << throughput->total_frames << "\n";
  } else if (results_type == "realtime" && results) {
    const auto* realtime = static_cast<const RealtimeResults*>(results);
    json << ",\n";
    json << "    \"compliance_rate\": " << realtime->compliance_rate << ",\n";
    json << "    \"mean_latency_ms\": " << realtime->mean_latency_ms << ",\n";
    json << "    \"p99_latency_ms\": " << realtime->p99_latency_ms << ",\n";
    json << "    \"frames_processed\": " << realtime->frames_processed << "\n";
  } else if (results_type == "accuracy" && results) {
    const auto* accuracy = static_cast<const AccuracyResults*>(results);
    json << ",\n";
    json << "    \"pass_rate\": " << accuracy->pass_rate << ",\n";
    json << "    \"mean_snr_db\": " << accuracy->mean_snr_db << ",\n";
    json << "    \"mean_mae\": " << accuracy->mean_mae << ",\n";
    json << "    \"tests_passed\": " << accuracy->tests_passed << "\n";
  } else {
    json << "\n";
  }

  json << "  }\n";
  json << "}\n";

  return json.str();
}

// ============================================================================
// Dataset Naming and Paths
// ============================================================================

/**
 * @brief Generate dataset directory name from config.
 *
 * Format: <preset>_<variant>_<mode>
 * Examples: "latency_iono_full", "throughput_ionox_full"
 *
 * @param config Benchmark configuration
 * @return Dataset directory name
 */
inline std::string get_dataset_dirname(const BenchmarkConfig& config) {
  std::string dirname = preset_to_string(config.preset);
  if (config.iono_variant == IonoVariant::IONO) {
    dirname += "_iono";
  } else if (config.iono_variant == IonoVariant::IONOX) {
    dirname += "_ionox";
  }
  dirname += "_" + mode_to_string(config.run_mode);
  return dirname;
}

/**
 * @brief Get full path to dataset directory.
 *
 * @param config Benchmark configuration
 * @return Full path to dataset directory
 */
inline std::filesystem::path get_dataset_path(const BenchmarkConfig& config) {
  auto dataset_dir = get_dataset_root() / get_dataset_dirname(config);
  std::filesystem::create_directories(dataset_dir);
  return dataset_dir;
}

/**
 * @brief Get full path to dataset directory by name.
 *
 * @param name Dataset name
 * @return Full path to dataset directory
 */
inline std::filesystem::path get_dataset_path_by_name(const std::string& name) {
  return get_dataset_root() / name;
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
// Dataset Storage
// ============================================================================

/**
 * @brief Save latency dataset to disk (directory + manifest + metadata + CSV).
 *
 * @param config Benchmark configuration
 * @param results Latency results
 */
inline void save_latency_dataset(const BenchmarkConfig& config,
                                   const LatencyResults& results) {
  // Get dataset directory
  auto dataset_dir = get_dataset_path(config);
  std::string dataset_name = get_dataset_dirname(config);

  // Get timestamp and git info (shared across files)
  std::string timestamp = get_timestamp();
  std::string git_commit = get_git_info().commit;

  // Save results JSON
  auto results_file = dataset_dir / "results.json";
  std::ofstream file(results_file);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write dataset results: " + results_file.string());
  }
  file << serialize_latency_results(results);
  file.close();

  // Save metadata JSON
  auto metadata_file = dataset_dir / "metadata.json";
  std::ofstream meta_file(metadata_file);
  if (!meta_file.is_open()) {
    throw std::runtime_error("Failed to write dataset metadata: " + metadata_file.string());
  }
  meta_file << serialize_metadata(dataset_name, config, &results, "latency");
  meta_file.close();

  // Save CSV
  auto csv_file = dataset_dir / "results.csv";
  write_latency_csv(csv_file, config, results, timestamp, git_commit);

  // Update manifest (file-locked)
  update_manifest(dataset_name, config);
}

/**
 * @brief Save throughput dataset to disk (directory + manifest + metadata + CSV).
 *
 * @param config Benchmark configuration
 * @param results Throughput results
 */
inline void save_throughput_dataset(const BenchmarkConfig& config,
                                      const ThroughputResults& results) {
  // Get dataset directory
  auto dataset_dir = get_dataset_path(config);
  std::string dataset_name = get_dataset_dirname(config);

  // Get timestamp and git info (shared across files)
  std::string timestamp = get_timestamp();
  std::string git_commit = get_git_info().commit;

  // Save results JSON
  auto results_file = dataset_dir / "results.json";
  std::ofstream file(results_file);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write dataset results: " + results_file.string());
  }
  file << serialize_throughput_results(results);
  file.close();

  // Save metadata JSON
  auto metadata_file = dataset_dir / "metadata.json";
  std::ofstream meta_file(metadata_file);
  if (!meta_file.is_open()) {
    throw std::runtime_error("Failed to write dataset metadata: " + metadata_file.string());
  }
  meta_file << serialize_metadata(dataset_name, config, &results, "throughput");
  meta_file.close();

  // Save CSV
  auto csv_file = dataset_dir / "results.csv";
  write_throughput_csv(csv_file, config, results, timestamp, git_commit);

  // Update manifest (file-locked)
  update_manifest(dataset_name, config);
}

/**
 * @brief Save realtime dataset to disk (directory + manifest + metadata + CSV).
 *
 * @param config Benchmark configuration
 * @param results Realtime results
 */
inline void save_realtime_dataset(const BenchmarkConfig& config,
                                    const RealtimeResults& results) {
  // Get dataset directory
  auto dataset_dir = get_dataset_path(config);
  std::string dataset_name = get_dataset_dirname(config);

  // Get timestamp and git info (shared across files)
  std::string timestamp = get_timestamp();
  std::string git_commit = get_git_info().commit;

  // Save results JSON
  auto results_file = dataset_dir / "results.json";
  std::ofstream file(results_file);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write dataset results: " + results_file.string());
  }
  file << serialize_realtime_results(results);
  file.close();

  // Save metadata JSON
  auto metadata_file = dataset_dir / "metadata.json";
  std::ofstream meta_file(metadata_file);
  if (!meta_file.is_open()) {
    throw std::runtime_error("Failed to write dataset metadata: " + metadata_file.string());
  }
  meta_file << serialize_metadata(dataset_name, config, &results, "realtime");
  meta_file.close();

  // Save CSV
  auto csv_file = dataset_dir / "results.csv";
  write_realtime_csv(csv_file, config, results, timestamp, git_commit);

  // Update manifest (file-locked)
  update_manifest(dataset_name, config);
}

/**
 * @brief Save accuracy dataset to disk (directory + manifest + metadata + CSV).
 *
 * @param config Benchmark configuration
 * @param results Accuracy results
 */
inline void save_accuracy_dataset(const BenchmarkConfig& config,
                                    const AccuracyResults& results) {
  // Get dataset directory
  auto dataset_dir = get_dataset_path(config);
  std::string dataset_name = get_dataset_dirname(config);

  // Get timestamp and git info (shared across files)
  std::string timestamp = get_timestamp();
  std::string git_commit = get_git_info().commit;

  // Save results JSON
  auto results_file = dataset_dir / "results.json";
  std::ofstream file(results_file);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write dataset results: " + results_file.string());
  }
  file << serialize_accuracy_results(results);
  file.close();

  // Save metadata JSON
  auto metadata_file = dataset_dir / "metadata.json";
  std::ofstream meta_file(metadata_file);
  if (!meta_file.is_open()) {
    throw std::runtime_error("Failed to write dataset metadata: " + metadata_file.string());
  }
  meta_file << serialize_metadata(dataset_name, config, &results, "accuracy");
  meta_file.close();

  // Save CSV
  auto csv_file = dataset_dir / "results.csv";
  write_accuracy_csv(csv_file, config, results, timestamp, git_commit);

  // Update manifest (file-locked)
  update_manifest(dataset_name, config);
}

// ============================================================================
// Last Run Storage (Temporary Benchmark Results)
// ============================================================================

/**
 * @brief Save latency results to .last_run (overwriting previous run).
 *
 * @param config Benchmark configuration
 * @param results Latency results
 */
inline void save_latency_last_run(const BenchmarkConfig& config,
                                   const LatencyResults& results) {
  // Get .last_run directory for this preset
  auto last_run_dir = get_last_run_directory(preset_to_string(config.preset));
  std::filesystem::create_directories(last_run_dir);

  // Get timestamp and git info
  std::string timestamp = get_timestamp();
  std::string git_commit = get_git_info().commit;

  // Save results JSON
  auto results_file = last_run_dir / "results.json";
  std::ofstream file(results_file);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write last run results: " + results_file.string());
  }
  file << serialize_latency_results(results);
  file.close();

  // Save metadata JSON (without name/message since this is temporary)
  auto metadata_file = last_run_dir / "metadata.json";
  std::ofstream meta_file(metadata_file);
  if (!meta_file.is_open()) {
    throw std::runtime_error("Failed to write last run metadata: " + metadata_file.string());
  }
  meta_file << serialize_metadata("last_run", config, &results, "latency");
  meta_file.close();

  // Save CSV
  auto csv_file = last_run_dir / "results.csv";
  write_latency_csv(csv_file, config, results, timestamp, git_commit);

  // No manifest update for temporary storage
}

/**
 * @brief Save throughput results to .last_run (overwriting previous run).
 *
 * @param config Benchmark configuration
 * @param results Throughput results
 */
inline void save_throughput_last_run(const BenchmarkConfig& config,
                                      const ThroughputResults& results) {
  auto last_run_dir = get_last_run_directory(preset_to_string(config.preset));
  std::filesystem::create_directories(last_run_dir);

  std::string timestamp = get_timestamp();
  std::string git_commit = get_git_info().commit;

  auto results_file = last_run_dir / "results.json";
  std::ofstream file(results_file);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write last run results: " + results_file.string());
  }
  file << serialize_throughput_results(results);
  file.close();

  auto metadata_file = last_run_dir / "metadata.json";
  std::ofstream meta_file(metadata_file);
  if (!meta_file.is_open()) {
    throw std::runtime_error("Failed to write last run metadata: " + metadata_file.string());
  }
  meta_file << serialize_metadata("last_run", config, &results, "throughput");
  meta_file.close();

  auto csv_file = last_run_dir / "results.csv";
  write_throughput_csv(csv_file, config, results, timestamp, git_commit);
}

/**
 * @brief Save realtime results to .last_run (overwriting previous run).
 *
 * @param config Benchmark configuration
 * @param results Realtime results
 */
inline void save_realtime_last_run(const BenchmarkConfig& config,
                                    const RealtimeResults& results) {
  auto last_run_dir = get_last_run_directory(preset_to_string(config.preset));
  std::filesystem::create_directories(last_run_dir);

  std::string timestamp = get_timestamp();
  std::string git_commit = get_git_info().commit;

  auto results_file = last_run_dir / "results.json";
  std::ofstream file(results_file);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write last run results: " + results_file.string());
  }
  file << serialize_realtime_results(results);
  file.close();

  auto metadata_file = last_run_dir / "metadata.json";
  std::ofstream meta_file(metadata_file);
  if (!meta_file.is_open()) {
    throw std::runtime_error("Failed to write last run metadata: " + metadata_file.string());
  }
  meta_file << serialize_metadata("last_run", config, &results, "realtime");
  meta_file.close();

  auto csv_file = last_run_dir / "results.csv";
  write_realtime_csv(csv_file, config, results, timestamp, git_commit);
}

/**
 * @brief Save accuracy results to .last_run (overwriting previous run).
 *
 * @param config Benchmark configuration
 * @param results Accuracy results
 */
inline void save_accuracy_last_run(const BenchmarkConfig& config,
                                    const AccuracyResults& results) {
  auto last_run_dir = get_last_run_directory(preset_to_string(config.preset));
  std::filesystem::create_directories(last_run_dir);

  std::string timestamp = get_timestamp();
  std::string git_commit = get_git_info().commit;

  auto results_file = last_run_dir / "results.json";
  std::ofstream file(results_file);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to write last run results: " + results_file.string());
  }
  file << serialize_accuracy_results(results);
  file.close();

  auto metadata_file = last_run_dir / "metadata.json";
  std::ofstream meta_file(metadata_file);
  if (!meta_file.is_open()) {
    throw std::runtime_error("Failed to write last run metadata: " + metadata_file.string());
  }
  meta_file << serialize_metadata("last_run", config, &results, "accuracy");
  meta_file.close();

  auto csv_file = last_run_dir / "results.csv";
  write_accuracy_csv(csv_file, config, results, timestamp, git_commit);
}

// ============================================================================
// Dataset Loading (Simple string parsing)
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
 * @brief Parse int value from JSON line.
 *
 * @param line JSON line
 * @return Parsed int value
 */
inline int parse_json_int(const std::string& line) {
  return static_cast<int>(parse_json_float(line));
}

/**
 * @brief Load latency dataset from disk.
 *
 * @param config Benchmark configuration
 * @param results Output latency results (populated if dataset exists)
 * @return True if dataset was loaded successfully
 */
inline bool load_latency_dataset(const BenchmarkConfig& config,
                                   LatencyResults& results) {
  auto dataset_dir = get_dataset_path(config);
  auto results_file = dataset_dir / "results.json";

  std::ifstream file(results_file);
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
 * @brief Load throughput dataset from disk.
 *
 * @param config Benchmark configuration
 * @param results Output throughput results
 * @return True if dataset was loaded successfully
 */
inline bool load_throughput_dataset(const BenchmarkConfig& config,
                                      ThroughputResults& results) {
  auto dataset_dir = get_dataset_path(config);
  auto results_file = dataset_dir / "results.json";

  std::ifstream file(results_file);
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
 * @brief Load realtime dataset from disk.
 *
 * @param config Benchmark configuration
 * @param results Output realtime results
 * @return True if dataset was loaded successfully
 */
inline bool load_realtime_dataset(const BenchmarkConfig& config,
                                    RealtimeResults& results) {
  auto dataset_dir = get_dataset_path(config);
  auto results_file = dataset_dir / "results.json";

  std::ifstream file(results_file);
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
 * @brief Load accuracy dataset from disk.
 *
 * @param config Benchmark configuration
 * @param results Output accuracy results
 * @return True if dataset was loaded successfully
 */
inline bool load_accuracy_dataset(const BenchmarkConfig& config,
                                    AccuracyResults& results) {
  auto dataset_dir = get_dataset_path(config);
  auto results_file = dataset_dir / "results.json";

  std::ifstream file(results_file);
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
 * @brief Check if dataset exists for given config.
 *
 * @param config Benchmark configuration
 * @return True if dataset directory and results file exist
 */
inline bool dataset_exists(const BenchmarkConfig& config) {
  auto dataset_dir = get_dataset_path(config);
  auto results_file = dataset_dir / "results.json";
  return std::filesystem::exists(results_file);
}

// ============================================================================
// Direct Load Functions (for CLI tools)
// ============================================================================

/**
 * @brief Load latency results from dataset directory.
 *
 * @param dataset_path Path to dataset directory
 * @return Latency results
 * @throws std::runtime_error if load fails
 */
inline LatencyResults load_latency_from_directory(const std::filesystem::path& dataset_path) {
  auto results_file = dataset_path / "results.json";

  std::ifstream file(results_file);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to open: " + results_file.string());
  }

  LatencyResults results{};
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
    } else if (line.find("min_latency_us") != std::string::npos) {
      results.min_latency_us = parse_json_float(line);
    } else if (line.find("max_latency_us") != std::string::npos) {
      results.max_latency_us = parse_json_float(line);
    } else if (line.find("std_latency_us") != std::string::npos) {
      results.std_latency_us = parse_json_float(line);
    } else if (line.find("coefficient_of_variation") != std::string::npos) {
      results.coefficient_of_variation = parse_json_float(line);
    } else if (line.find("frames_processed") != std::string::npos) {
      results.frames_processed = parse_json_int(line);
    }
  }

  file.close();
  return results;
}

/**
 * @brief Load throughput results from dataset directory.
 *
 * @param dataset_path Path to dataset directory
 * @return Throughput results
 * @throws std::runtime_error if load fails
 */
inline ThroughputResults load_throughput_from_directory(const std::filesystem::path& dataset_path) {
  auto results_file = dataset_path / "results.json";

  std::ifstream file(results_file);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to open: " + results_file.string());
  }

  ThroughputResults results{};
  std::string line;
  while (std::getline(file, line)) {
    if (line.find("frames_per_second") != std::string::npos) {
      results.frames_per_second = parse_json_float(line);
    } else if (line.find("gb_per_second") != std::string::npos) {
      results.gb_per_second = parse_json_float(line);
    } else if (line.find("samples_per_second") != std::string::npos) {
      results.samples_per_second = parse_json_float(line);
    } else if (line.find("total_frames") != std::string::npos) {
      results.total_frames = parse_json_int(line);
    } else if (line.find("test_duration_s") != std::string::npos) {
      results.test_duration_s = parse_json_float(line);
    }
  }

  file.close();
  return results;
}

/**
 * @brief Load realtime results from dataset directory.
 *
 * @param dataset_path Path to dataset directory
 * @return Realtime results
 * @throws std::runtime_error if load fails
 */
inline RealtimeResults load_realtime_from_directory(const std::filesystem::path& dataset_path) {
  auto results_file = dataset_path / "results.json";

  std::ifstream file(results_file);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to open: " + results_file.string());
  }

  RealtimeResults results{};
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
    } else if (line.find("frames_processed") != std::string::npos) {
      results.frames_processed = parse_json_int(line);
    } else if (line.find("deadline_misses") != std::string::npos) {
      results.deadline_misses = parse_json_int(line);
    }
  }

  file.close();
  return results;
}

/**
 * @brief Load accuracy results from dataset directory.
 *
 * @param dataset_path Path to dataset directory
 * @return Accuracy results
 * @throws std::runtime_error if load fails
 */
inline AccuracyResults load_accuracy_from_directory(const std::filesystem::path& dataset_path) {
  auto results_file = dataset_path / "results.json";

  std::ifstream file(results_file);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to open: " + results_file.string());
  }

  AccuracyResults results{};
  std::string line;
  while (std::getline(file, line)) {
    if (line.find("pass_rate") != std::string::npos) {
      results.pass_rate = parse_json_float(line);
    } else if (line.find("mean_snr_db") != std::string::npos) {
      results.mean_snr_db = parse_json_float(line);
    } else if (line.find("mean_mae") != std::string::npos) {
      results.mean_mae = parse_json_float(line);
    } else if (line.find("mean_rmse") != std::string::npos) {
      results.mean_rmse = parse_json_float(line);
    } else if (line.find("max_error") != std::string::npos) {
      results.max_error = parse_json_float(line);
    } else if (line.find("tests_passed") != std::string::npos) {
      results.tests_passed = parse_json_int(line);
    } else if (line.find("tests_total") != std::string::npos) {
      results.tests_total = parse_json_int(line);
    }
  }

  file.close();
  return results;
}

}  // namespace benchmark
}  // namespace sigtekx
