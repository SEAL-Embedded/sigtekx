/**
 * @file engine_config.hpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Core configuration structures for the processing engine.
 *
 * Defines EngineConfig and utility functions used across the library.
 */

#pragma once

#include <string>
#include <vector>

namespace ionosense {

/**
 * @struct EngineConfig
 * @brief Configuration structure for the processing engine.
 */
struct EngineConfig {
  // Signal Parameters
  int nfft = 1024;
  int batch = 2;
  float overlap = 0.5f;
  int sample_rate_hz = 48000;

  // Execution Parameters
  int stream_count = 3;
  int pinned_buffer_count = 2;
  int warmup_iters = 1;
  int timeout_ms = 1000;

  // Performance Tuning
  bool use_cuda_graphs = false;
  bool enable_profiling = false;

  int hop_size() const { return static_cast<int>(nfft * (1.0f - overlap)); }
  int num_output_bins() const { return nfft / 2 + 1; }
};

/**
 * @namespace engine_utils
 * @brief Utility functions for engine and CUDA environment.
 */
namespace engine_utils {
std::vector<std::string> get_available_devices();
int select_best_device();
bool validate_config(const EngineConfig& config, std::string& error_msg);
size_t estimate_memory_usage(const EngineConfig& config);
}  // namespace engine_utils

}  // namespace ionosense
