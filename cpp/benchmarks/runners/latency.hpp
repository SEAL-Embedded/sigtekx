/**
 * @file latency.hpp
 * @brief Latency benchmark runner.
 */

#pragma once

#include "../benchmarks/core/config.hpp"
#include "../benchmarks/core/results.hpp"
#include "../benchmarks/utils/signal_generator.hpp"
#include "sigtekx/profiling/nvtx.hpp"
#include "sigtekx/executors/batch_executor.hpp"
#include <cuda_runtime.h>

namespace sigtekx {
namespace benchmark {

// ============================================================================
// Latency Benchmark
// ============================================================================

/**
 * @brief Run latency benchmark with iteration-based statistics.
 *
 * Measures per-iteration latency statistics including mean, percentiles,
 * and standard deviation.
 *
 * @param executor BatchExecutor instance
 * @param config Benchmark configuration
 * @return LatencyResults with all computed statistics
 */
inline LatencyResults run_latency_benchmark(BatchExecutor& executor,
                                             const BenchmarkConfig& config) {
  SIGTEKX_NVTX_RANGE("Latency Benchmark", profiling::colors::NVIDIA_BLUE);

  LatencyResults results;

  const size_t input_size = static_cast<size_t>(config.nfft) * config.channels;
  const size_t output_size =
      static_cast<size_t>(config.nfft / 2 + 1) * config.channels;

  std::vector<float> input =
      generate_test_signal(config.nfft, config.channels, config.random_seed);
  std::vector<float> output(output_size);

  results.latencies_us.reserve(config.iterations);

  // Create CUDA events for GPU-side timing (more accurate than CPU-side chrono)
  cudaEvent_t start_event, stop_event;
  cudaEventCreate(&start_event);
  cudaEventCreate(&stop_event);

  for (int i = 0; i < config.iterations; ++i) {
    const std::string iter_name = "Iteration " + std::to_string(i + 1) + "/" +
                                  std::to_string(config.iterations);
    SIGTEKX_NVTX_RANGE(iter_name.c_str(), profiling::colors::NVIDIA_BLUE);

    // Use CUDA events to measure GPU execution time directly
    // This eliminates CPU-side timing overhead and OS scheduler noise
    cudaEventRecord(start_event);
    executor.submit(input.data(), output.data(), input_size);
    cudaEventRecord(stop_event);
    cudaEventSynchronize(stop_event);  // Wait for GPU work to complete

    float latency_ms = 0.0f;
    cudaEventElapsedTime(&latency_ms, start_event, stop_event);
    float latency_us = latency_ms * 1000.0f;  // Convert ms to us
    results.latencies_us.push_back(latency_us);
  }

  // Clean up CUDA events
  cudaEventDestroy(start_event);
  cudaEventDestroy(stop_event);

  // Compute statistics
  SIGTEKX_NVTX_RANGE("Compute Statistics", profiling::colors::CYAN);

  std::vector<float> sorted_latencies = results.latencies_us;
  std::sort(sorted_latencies.begin(), sorted_latencies.end());

  // Trim top/bottom 1% outliers for robust statistics
  // This removes extreme values from OS interrupts, SMI, thermal events
  const size_t trim_count = sorted_latencies.size() / 100;
  if (trim_count > 0 && sorted_latencies.size() > 100) {
    sorted_latencies.erase(sorted_latencies.begin(),
                           sorted_latencies.begin() + trim_count);
    sorted_latencies.erase(sorted_latencies.end() - trim_count,
                           sorted_latencies.end());
    results.outliers_trimmed = trim_count * 2;
  }

  // Mean (after outlier removal)
  results.mean_latency_us =
      std::accumulate(sorted_latencies.begin(), sorted_latencies.end(), 0.0f) /
      static_cast<float>(sorted_latencies.size());

  // Percentiles
  results.median_latency_us = sorted_latencies[sorted_latencies.size() / 2];
  results.p50_latency_us = results.median_latency_us;  // Same as median
  results.p95_latency_us = sorted_latencies[sorted_latencies.size() * 95 / 100];
  results.p99_latency_us = sorted_latencies[sorted_latencies.size() * 99 / 100];
  results.min_latency_us = sorted_latencies.front();
  results.max_latency_us = sorted_latencies.back();

  // Interquartile Range (IQR = Q3 - Q1)
  const float q1 = sorted_latencies[sorted_latencies.size() / 4];
  const float q3 = sorted_latencies[sorted_latencies.size() * 3 / 4];
  results.iqr_latency_us = q3 - q1;

  // Standard deviation
  float variance = 0.0f;
  for (float lat : sorted_latencies) {
    float diff = lat - results.mean_latency_us;
    variance += diff * diff;
  }
  results.std_latency_us =
      std::sqrt(variance / static_cast<float>(sorted_latencies.size()));

  // Coefficient of variation (CV)
  if (results.mean_latency_us > 0.0f) {
    results.coefficient_of_variation = results.std_latency_us / results.mean_latency_us;
  }

  // 95% Confidence interval (assuming normal distribution)
  // CI = mean ± (1.96 * std / sqrt(n))
  const float n = static_cast<float>(sorted_latencies.size());
  const float margin = 1.96f * (results.std_latency_us / std::sqrt(n));
  results.confidence_interval_95_lower = results.mean_latency_us - margin;
  results.confidence_interval_95_upper = results.mean_latency_us + margin;

  // Stability check (CV < 10% is considered stable)
  results.is_stable = (results.coefficient_of_variation < 0.10f);

  // Warmup effectiveness (compare first 10% vs last 10% of samples)
  if (sorted_latencies.size() >= 20) {
    const size_t segment_size = sorted_latencies.size() / 10;
    float first_10_mean = 0.0f;
    float last_10_mean = 0.0f;

    for (size_t i = 0; i < segment_size; ++i) {
      first_10_mean += results.latencies_us[i];
      last_10_mean += results.latencies_us[results.latencies_us.size() - 1 - i];
    }
    first_10_mean /= static_cast<float>(segment_size);
    last_10_mean /= static_cast<float>(segment_size);

    // Positive value means latency decreased (warmup was effective)
    results.warmup_effectiveness = first_10_mean - last_10_mean;
  }

  // Get throughput from engine stats
  auto stats = executor.get_stats();
  results.throughput_gbps = stats.throughput_gbps;
  results.frames_processed = stats.frames_processed;

  return results;
}

}  // namespace benchmark
}  // namespace sigtekx
