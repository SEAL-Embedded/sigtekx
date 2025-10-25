/**
 * @file throughput_runner.hpp
 * @brief Throughput benchmark runner.
 *
 * Provides time-based throughput benchmarking for measuring peak performance.
 */

#pragma once

#include <chrono>
#include <string>
#include <vector>

#include "../benchmarks/core/config.hpp"
#include "../benchmarks/core/results.hpp"
#include "../benchmarks/utils/signal_generator.hpp"
#include "ionosense/profiling/nvtx.hpp"

namespace ionosense {
namespace benchmark {

/**
 * @brief Run throughput benchmark with time-based statistics.
 *
 * Measures frames per second, GB/s, and samples per second over a fixed
 * time duration. Optimized for maximum throughput measurement.
 *
 * @tparam ExecutorT Executor type (BatchExecutor or StreamingExecutor)
 * @param executor Executor instance
 * @param config Benchmark configuration
 * @return ThroughputResults with all computed metrics
 */
template<typename ExecutorT>
inline ThroughputResults run_throughput_benchmark(ExecutorT& executor,
                                                   const BenchmarkConfig& config) {
  IONO_NVTX_RANGE("Throughput Benchmark", profiling::colors::GREEN);

  ThroughputResults results;

  const size_t input_size = static_cast<size_t>(config.nfft) * config.channels;
  const size_t output_size =
      static_cast<size_t>(config.nfft / 2 + 1) * config.channels;

  std::vector<float> input =
      generate_test_signal(config.nfft, config.channels, config.random_seed);
  std::vector<float> output(output_size);

  size_t frame_count = 0;

  auto start = std::chrono::high_resolution_clock::now();
  auto end = start + std::chrono::duration<float>(config.duration_seconds);

  while (std::chrono::high_resolution_clock::now() < end) {
    const std::string iter_name = "Frame " + std::to_string(frame_count + 1);
    IONO_NVTX_RANGE(iter_name.c_str(), profiling::colors::GREEN);

    executor.submit(input.data(), output.data(), input_size);
    frame_count++;
  }

  executor.synchronize();
  auto actual_end = std::chrono::high_resolution_clock::now();

  float actual_duration =
      std::chrono::duration<float>(actual_end - start).count();

  results.total_frames = frame_count;
  results.test_duration_s = actual_duration;
  results.frames_per_second =
      static_cast<float>(frame_count) / actual_duration;

  // Calculate data rates
  size_t bytes_per_frame = input_size * sizeof(float) + output_size * sizeof(float);
  float total_gb = (static_cast<float>(bytes_per_frame * frame_count)) / (1024.0f * 1024.0f * 1024.0f);
  results.gb_per_second = total_gb / actual_duration;
  results.samples_per_second = results.frames_per_second * static_cast<float>(input_size);

  return results;
}

}  // namespace benchmark
}  // namespace ionosense
