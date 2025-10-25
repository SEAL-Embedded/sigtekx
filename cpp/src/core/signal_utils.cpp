/**
 * @file signal_utils.cpp
 * @version 0.9.4
 * @date 2025-10-23
 * @author [Kevin Rahsaz]
 *
 * @brief Utility functions for signal processing config and CUDA environment.
 *
 * Provides helper functions for device selection, configuration validation,
 * and memory estimation.
 */

#include <sstream>
#include <stdexcept>

#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/core/signal_config.hpp"
#include "ionosense/profiling/nvtx.hpp"

namespace ionosense {
namespace signal_utils {

std::vector<std::string> get_available_devices() {
  IONO_NVTX_RANGE_FUNCTION(profiling::colors::CYAN);
  std::vector<std::string> devices;
  int device_count = 0;
  if (cudaGetDeviceCount(&device_count) == cudaSuccess) {
    for (int i = 0; i < device_count; ++i) {
      cudaDeviceProp prop{};
      if (cudaGetDeviceProperties(&prop, i) == cudaSuccess) {
        std::ostringstream oss;
        oss << "[" << i << "] " << prop.name << " (CC " << prop.major << "."
            << prop.minor << ")";
        devices.push_back(oss.str());
      }
    }
  }
  return devices;
}

int select_best_device() {
  IONO_NVTX_RANGE_FUNCTION(profiling::colors::CYAN);
  int device_count = 0;
  IONO_CUDA_CHECK(cudaGetDeviceCount(&device_count));
  if (device_count == 0) {
    throw std::runtime_error("No CUDA devices found for selection.");
  }

  int best_device = 0;
  int best_sm_count = -1;
  for (int i = 0; i < device_count; ++i) {
    cudaDeviceProp prop{};
    IONO_CUDA_CHECK(cudaGetDeviceProperties(&prop, i));
    if (prop.multiProcessorCount > best_sm_count) {
      best_sm_count = prop.multiProcessorCount;
      best_device = i;
    }
  }
  return best_device;
}

bool validate_config(const SignalConfig& cfg, std::string& error_msg) {
  IONO_NVTX_RANGE_FUNCTION(profiling::colors::CYAN);
  if (cfg.nfft <= 0 || (cfg.nfft & (cfg.nfft - 1)) != 0) {
    error_msg = "nfft must be a positive power of 2.";
    return false;
  }
  if (cfg.channels <= 0) {
    error_msg = "channels must be positive.";
    return false;
  }
  if (cfg.overlap < 0.0f || cfg.overlap >= 1.0f) {
    error_msg = "overlap must be in the range [0.0, 1.0).";
    return false;
  }
  if (cfg.sample_rate_hz <= 0) {
    error_msg = "sample_rate_hz must be positive.";
    return false;
  }
  if (cfg.stream_count <= 0) {
    error_msg = "stream_count must be positive.";
    return false;
  }
  if (cfg.pinned_buffer_count < 2) {
    error_msg = "pinned_buffer_count must be at least 2 for double buffering.";
    return false;
  }
  error_msg.clear();
  return true;
}

size_t estimate_memory_usage(const SignalConfig& cfg) {
  IONO_NVTX_RANGE_FUNCTION(profiling::colors::CYAN);
  size_t total = 0;
  const size_t input_bytes =
      static_cast<size_t>(cfg.nfft) * cfg.channels * sizeof(float);
  const size_t output_bytes =
      static_cast<size_t>(cfg.num_output_bins()) * cfg.channels * sizeof(float);
  const size_t complex_bytes = output_bytes * 2;

  total +=
      cfg.pinned_buffer_count * (input_bytes + output_bytes + complex_bytes);
  total += static_cast<size_t>(cfg.nfft) * sizeof(float);  // window

  // A rough estimate for cuFFT workspace.
  total += static_cast<size_t>(cfg.nfft) * cfg.channels * sizeof(float) * 2;

  return total;
}

}  // namespace engine_utils
}  // namespace ionosense
