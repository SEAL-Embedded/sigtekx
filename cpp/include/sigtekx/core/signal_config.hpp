/**
 * @file signal_config.hpp
 * @version 0.9.4
 * @date 2025-10-23
 * @author [Kevin Rahsaz]
 *
 * @brief Core configuration structures for signal processing.
 *
 * Defines SignalConfig and utility functions used across the library.
 *
 * ⚠️  BREAKING CHANGE (v0.9.4): Terminology refactor for industry standards.
 * - 'batch' → 'channels' (spatial dimension: independent signal streams)
 * - Established 'frames' terminology (temporal dimension: FFT windows)
 * - Clarified spatial vs temporal vs spectral dimensions
 * - Renamed engine_config → signal_config (no "engine" abstraction in C++)
 */

#pragma once

#include <string>
#include <vector>

namespace sigtekx {

/**
 * @struct SignalConfig
 * @brief Core configuration for signal processing parameters.
 *
 * Contains fundamental signal processing parameters used by all executors.
 * For executor-specific settings (e.g., execution mode), see ExecutorConfig.
 */
struct SignalConfig {
  // Signal Parameters
  int nfft = 1024;
  int channels = 2;  // Renamed from 'batch' in v0.9.4 for clarity
  float overlap = 0.5f;
  int sample_rate_hz = 48000;

  // Pipeline Parameters (added for unified config)
  int window_type = 1;      // 0=RECTANGULAR, 1=HANN, 2=BLACKMAN
  int window_symmetry = 0;  // 0=PERIODIC, 1=SYMMETRIC
  int window_norm = 0;      // 0=UNITY, 1=SQRT
  int scale_policy = 1;     // 0=NONE, 1=ONE_OVER_N, 2=ONE_OVER_SQRT_N
  int output_mode = 0;      // 0=MAGNITUDE, 1=COMPLEX_PASSTHROUGH

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
 * @namespace signal_utils
 * @brief Utility functions for signal processing config and CUDA environment.
 */
namespace signal_utils {
std::vector<std::string> get_available_devices();
int select_best_device();
bool validate_config(const SignalConfig& config, std::string& error_msg);
size_t estimate_memory_usage(const SignalConfig& config);
}  // namespace signal_utils

}  // namespace sigtekx
