/**
 * @file benchmark_runners.hpp
 * @brief Benchmark execution logic for all preset types.
 *
 * Provides benchmark runner functions for latency, throughput, realtime,
 * and accuracy presets. Includes warmup functionality.
 */

#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <numeric>
#include <string>
#include <vector>

#include "../benchmarks/core/config.hpp"
#include "../benchmarks/core/results.hpp"
#include "../benchmarks/utils/reference_compute.hpp"
#include "../benchmarks/utils/signal_generator.hpp"
#include "sigtekx/profiling/nvtx.hpp"
#include "sigtekx/executors/batch_executor.hpp"

namespace sigtekx {
namespace benchmark {

// ============================================================================
// Warmup
// ============================================================================

/**
 * @brief Run warmup iterations to stabilize GPU state.
 *
 * @param executor BatchExecutor instance
 * @param config Benchmark configuration
 */
inline void run_warmup(BatchExecutor& executor, const BenchmarkConfig& config) {
  IONO_NVTX_RANGE("Warmup Phase", profiling::colors::LIGHT_GRAY);

  std::vector<float> warmup_input(static_cast<size_t>(config.nfft) *
                                   config.channels);
  std::vector<float> warmup_output(
      static_cast<size_t>(config.nfft / 2 + 1) * config.channels);

  for (int i = 0; i < config.warmup_iterations; ++i) {
    const std::string name = "Warmup " + std::to_string(i);
    IONO_NVTX_RANGE(name.c_str(), profiling::colors::LIGHT_GRAY);
    executor.submit(warmup_input.data(), warmup_output.data(),
                    warmup_input.size());
  }

  {
    IONO_NVTX_RANGE("Warmup Sync", profiling::colors::YELLOW);
    executor.synchronize();
  }
}
