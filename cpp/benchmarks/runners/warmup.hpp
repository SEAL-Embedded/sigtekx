/**
 * @file warmup.hpp
 * @brief Warmup functionality for benchmark runners.
 *
 * Provides warmup iterations to stabilize GPU state before benchmarking.
 */

#pragma once

#include <string>
#include <vector>

#include "../benchmarks/core/config.hpp"
#include "sigtekx/profiling/nvtx.hpp"

namespace sigtekx {
namespace benchmark {

/**
 * @brief Run warmup iterations to stabilize GPU state.
 *
 * Executes warmup iterations to ensure GPU clocks are stable, memory is
 * allocated, and driver state is initialized before running benchmarks.
 *
 * @tparam ExecutorT Executor type (BatchExecutor or StreamingExecutor)
 * @param executor Executor instance
 * @param config Benchmark configuration
 */
template<typename ExecutorT>
inline void run_warmup(ExecutorT& executor, const BenchmarkConfig& config) {
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

}  // namespace benchmark
}  // namespace sigtekx
