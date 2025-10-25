/**
 * @file realtime_runner.hpp
 * @brief Realtime benchmark runner.
 *
 * Provides deadline compliance tracking for realtime performance validation.
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
#include "../benchmarks/utils/signal_generator.hpp"
#include "ionosense/profiling/nvtx.hpp"

namespace ionosense {
namespace benchmark {

/**
 * @brief Run realtime benchmark with deadline compliance tracking.
 *
 * Measures real-time performance including deadline compliance rate,
 * latency, and jitter. Validates that processing meets timing constraints
 * for continuous streaming applications.
 *
 * @tparam ExecutorT Executor type (BatchExecutor or StreamingExecutor)
 * @param executor Executor instance
 * @param config Benchmark configuration
 * @return RealtimeResults with all computed metrics
 */
template<typename ExecutorT>
inline RealtimeResults run_realtime_benchmark(ExecutorT& executor,
                                               const BenchmarkConfig& config) {
  IONO_NVTX_RANGE("Realtime Benchmark", profiling::colors::ORANGE);

  RealtimeResults results;

  // Calculate frame deadline if not specified
  float frame_deadline_ms = config.frame_deadline_ms;
  if (frame_deadline_ms == 0.0f) {
    // Calculate based on hop size
    int hop_size = static_cast<int>(config.nfft * (1.0f - config.overlap));
    frame_deadline_ms =
        (static_cast<float>(hop_size) / static_cast<float>(config.sample_rate_hz)) * 1000.0f;
  }

  const size_t input_size = static_cast<size_t>(config.nfft) * config.channels;
  const size_t output_size =
      static_cast<size_t>(config.nfft / 2 + 1) * config.channels;

  std::vector<float> input =
      generate_test_signal(config.nfft, config.channels, config.random_seed);
  std::vector<float> output(output_size);

  std::vector<float> frame_latencies_ms;
  size_t frame_count = 0;
  size_t deadline_misses = 0;

  auto start = std::chrono::high_resolution_clock::now();
  auto end = start + std::chrono::duration<float>(config.duration_seconds);

  while (std::chrono::high_resolution_clock::now() < end) {
    const std::string iter_name = "Frame " + std::to_string(frame_count + 1);
    IONO_NVTX_RANGE(iter_name.c_str(), profiling::colors::ORANGE);

    // Use CPU-side timing for realtime benchmark
    // For high-frequency measurements (>5000 FPS), CPU timing provides better
    // stability than CUDA events due to lower per-frame overhead
    auto frame_start = std::chrono::high_resolution_clock::now();
    executor.submit(input.data(), output.data(), input_size);
    executor.synchronize();
    auto frame_end = std::chrono::high_resolution_clock::now();

    float frame_latency_ms =
        std::chrono::duration<float, std::milli>(frame_end - frame_start)
            .count();
    frame_latencies_ms.push_back(frame_latency_ms);

    if (config.strict_timing && frame_latency_ms > frame_deadline_ms) {
      deadline_misses++;
    }

    frame_count++;
  }

  // Compute statistics
  results.frames_processed = frame_count;
  results.deadline_misses = deadline_misses;
  results.frames_dropped = 0;  // Not tracking frame drops in this implementation
  results.compliance_rate = 1.0f - (static_cast<float>(deadline_misses) /
                                    static_cast<float>(frame_count));

  if (!frame_latencies_ms.empty()) {
    results.mean_latency_ms =
        std::accumulate(frame_latencies_ms.begin(), frame_latencies_ms.end(),
                        0.0f) /
        static_cast<float>(frame_latencies_ms.size());

    std::vector<float> sorted_latencies = frame_latencies_ms;
    std::sort(sorted_latencies.begin(), sorted_latencies.end());
    results.p99_latency_ms =
        sorted_latencies[sorted_latencies.size() * 99 / 100];

    // Calculate jitter (standard deviation of latencies)
    float variance = 0.0f;
    for (float lat : frame_latencies_ms) {
      float diff = lat - results.mean_latency_ms;
      variance += diff * diff;
    }
    results.mean_jitter_ms =
        std::sqrt(variance / static_cast<float>(frame_latencies_ms.size()));

    // Coefficient of variation for jitter (stability metric)
    if (results.mean_latency_ms > 0.0f) {
      results.coefficient_of_variation = results.mean_jitter_ms / results.mean_latency_ms;
    }

    // Realtime stability check (CV < 15% is considered stable for realtime)
    results.is_stable = (results.coefficient_of_variation < 0.15f);
  }

  return results;
}

}  // namespace benchmark
}  // namespace ionosense
