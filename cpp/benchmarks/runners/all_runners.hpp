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

namespace ionosense {
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
  IONO_NVTX_RANGE("Latency Benchmark", profiling::colors::NVIDIA_BLUE);

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
    IONO_NVTX_RANGE(iter_name.c_str(), profiling::colors::NVIDIA_BLUE);

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
  IONO_NVTX_RANGE("Compute Statistics", profiling::colors::CYAN);

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

// ============================================================================
// Throughput Benchmark
// ============================================================================

/**
 * @brief Run throughput benchmark with time-based statistics.
 *
 * Measures frames per second, GB/s, and samples per second over a fixed
 * time duration.
 *
 * @param executor BatchExecutor instance
 * @param config Benchmark configuration
 * @return ThroughputResults with all computed metrics
 */
inline ThroughputResults run_throughput_benchmark(BatchExecutor& executor,
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

// ============================================================================
// Realtime Benchmark
// ============================================================================

/**
 * @brief Run realtime benchmark with deadline compliance tracking.
 *
 * Measures real-time performance including deadline compliance rate,
 * latency, and jitter.
 *
 * @param executor BatchExecutor instance
 * @param config Benchmark configuration
 * @return RealtimeResults with all computed metrics
 */
inline RealtimeResults run_realtime_benchmark(BatchExecutor& executor,
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

// ============================================================================
// Accuracy Benchmark
// ============================================================================

/**
 * @brief Run accuracy benchmark with pipeline-matching reference.
 *
 * **Single hardcoded test** - validates pipeline produces correct numerical output.
 *
 * Compares engine output against CPU reference that EXACTLY mirrors pipeline:
 * - Window: Hann, PERIODIC symmetry, UNITY normalization
 * - FFT: cuFFT R2C
 * - Magnitude: sqrt(real^2 + imag^2) * (1/N) scaling
 *
 * This validates actual correctness, not just "something happened".
 *
 * **Limitation:** Hardcoded to current pipeline. If pipeline changes (add stage,
 * change scaling), update reference_compute.hpp to match.
 *
 * For comprehensive cross-platform validation with scipy, use Python tests:
 *   pytest tests/test_accuracy.py
 *
 * @param executor BatchExecutor instance
 * @param config Benchmark configuration
 * @return AccuracyResults with pass/fail based on numerical agreement
 */
inline AccuracyResults run_accuracy_benchmark(BatchExecutor& executor,
                                               const BenchmarkConfig& config) {
  IONO_NVTX_RANGE("Accuracy Benchmark", profiling::colors::PURPLE);

  AccuracyResults results;

  const size_t input_size = static_cast<size_t>(config.nfft) * config.channels;
  const size_t output_size =
      static_cast<size_t>(config.nfft / 2 + 1) * config.channels;

  // Single test: Pure sine wave with full pipeline validation
  {
    IONO_NVTX_RANGE("Pipeline Reference Test", profiling::colors::PURPLE);

    // Generate pure sine at frequency bin 10
    std::vector<float> input = generate_test_signal(
        config.nfft, config.channels, config.random_seed, SignalType::PURE_SINE);
    std::vector<float> output(output_size);

    // Run engine processing
    executor.submit(input.data(), output.data(), input_size);
    executor.synchronize();

    // Compute reference that EXACTLY matches pipeline
    std::vector<float> reference = compute_pipeline_reference(
        input, config.nfft, config.channels);

    // Compare numerically
    float max_error = compute_max_error(output, reference);
    float relative_error = compute_relative_error(output, reference);

    // Pass criteria: tight numerical agreement
    const float max_abs_error_threshold = 1e-4f;  // Floating point tolerance
    const float max_rel_error_threshold = 1e-4f;  // 0.01% relative error

    bool test_passed = (max_error < max_abs_error_threshold) &&
                       (relative_error < max_rel_error_threshold) &&
                       std::isfinite(max_error);

    // Populate results
    results.tests_passed = test_passed ? 1 : 0;
    results.tests_total = 1;
    results.pass_rate = test_passed ? 1.0f : 0.0f;

    // Report error metrics
    results.max_error = max_error;
    results.mean_relative_error = relative_error;
    results.mean_mae = max_error;  // Max absolute error
    results.mean_rmse = relative_error;  // Relative RMS error

    // Compute SNR for reporting (signal power / error power)
    if (relative_error > 0.0f) {
      const float snr_linear = 1.0f / (relative_error * relative_error);
      results.mean_snr_db = 10.0f * std::log10(snr_linear);
    } else {
      results.mean_snr_db = 200.0f;  // Perfect match
    }
  }

  return results;
}

}  // namespace benchmark
}  // namespace ionosense
