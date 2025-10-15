/**
 * @file benchmark_results.hpp
 * @brief Result structures and error metrics for benchmark analysis.
 *
 * This header defines all result types and error computation functions used
 * across different benchmark presets (latency, throughput, realtime, accuracy).
 */

#pragma once

#include <algorithm>
#include <cmath>
#include <vector>

namespace ionosense {
namespace benchmark {

// ============================================================================
// Results Structures
// ============================================================================

/**
 * @brief Results from latency benchmark (iteration-based statistics).
 */
struct LatencyResults {
  std::vector<float> latencies_us;
  float mean_latency_us = 0.0f;
  float p50_latency_us = 0.0f;
  float p95_latency_us = 0.0f;
  float p99_latency_us = 0.0f;
  float min_latency_us = 0.0f;
  float max_latency_us = 0.0f;
  float std_latency_us = 0.0f;
  float throughput_gbps = 0.0f;
  size_t frames_processed = 0;

  // Statistical validation
  float coefficient_of_variation = 0.0f;  // CV = std_dev / mean
  float confidence_interval_95_lower = 0.0f;  // 95% CI lower bound
  float confidence_interval_95_upper = 0.0f;  // 95% CI upper bound
  bool is_stable = true;  // True if CV < 10%
  float warmup_effectiveness = 0.0f;  // Mean latency reduction after warmup
};

/**
 * @brief Results from throughput benchmark (time-based statistics).
 */
struct ThroughputResults {
  float frames_per_second = 0.0f;
  float gb_per_second = 0.0f;
  float samples_per_second = 0.0f;
  size_t total_frames = 0;
  float test_duration_s = 0.0f;

  // Statistical validation
  bool is_stable = true;  // Always stable for throughput (time-based)
};

/**
 * @brief Results from realtime benchmark (deadline compliance).
 */
struct RealtimeResults {
  float compliance_rate = 0.0f;
  float mean_latency_ms = 0.0f;
  float p99_latency_ms = 0.0f;
  float mean_jitter_ms = 0.0f;
  size_t frames_processed = 0;
  size_t deadline_misses = 0;
  size_t frames_dropped = 0;

  // Statistical validation
  float coefficient_of_variation = 0.0f;  // CV for jitter
  bool is_stable = true;  // True if jitter CV < 15%
};

/**
 * @brief Results from accuracy benchmark (validation metrics).
 */
struct AccuracyResults {
  float pass_rate = 0.0f;
  float mean_snr_db = 0.0f;
  float mean_mae = 0.0f;         // Mean Absolute Error
  float mean_rmse = 0.0f;        // Root Mean Square Error
  float max_error = 0.0f;        // Peak Error
  float mean_relative_error = 0.0f;  // Mean relative error
  int tests_passed = 0;
  int tests_total = 0;
};

// ============================================================================
// Error Metrics
// ============================================================================

/**
 * @brief Error metrics for comparing output against reference.
 */
struct ErrorMetrics {
  float mae = 0.0f;          // Mean Absolute Error
  float rmse = 0.0f;         // Root Mean Square Error
  float peak_error = 0.0f;   // Maximum absolute error
  float snr_db = 0.0f;       // Signal-to-Noise Ratio in dB
  float relative_error = 0.0f;  // Relative error (normalized by reference magnitude)
};

/**
 * @brief Compute error metrics by comparing output against reference.
 *
 * @param output Test output to validate
 * @param reference Reference output (ground truth)
 * @return ErrorMetrics structure with all computed metrics
 */
inline ErrorMetrics compute_error_metrics(const std::vector<float>& output,
                                          const std::vector<float>& reference) {
  ErrorMetrics metrics;

  if (output.size() != reference.size()) {
    return metrics;  // Return zeros if size mismatch
  }

  const size_t n = output.size();
  double sum_abs_error = 0.0;
  double sum_sq_error = 0.0;
  double sum_sq_signal = 0.0;
  float max_error = 0.0f;

  for (size_t i = 0; i < n; ++i) {
    const float error = std::abs(output[i] - reference[i]);
    const float signal = std::abs(reference[i]);

    sum_abs_error += error;
    sum_sq_error += error * error;
    sum_sq_signal += signal * signal;
    max_error = std::max(max_error, error);
  }

  metrics.mae = static_cast<float>(sum_abs_error / n);
  metrics.rmse = std::sqrt(static_cast<float>(sum_sq_error / n));
  metrics.peak_error = max_error;

  // Compute SNR: 10 * log10(signal_power / noise_power)
  const double noise_power = sum_sq_error / n;
  const double signal_power = sum_sq_signal / n;

  if (noise_power > 1e-20) {  // Avoid division by zero
    metrics.snr_db = 10.0f * std::log10(static_cast<float>(signal_power / noise_power));
  } else {
    metrics.snr_db = 200.0f;  // Effectively perfect match
  }

  // Compute relative error
  const double ref_magnitude = std::sqrt(signal_power);
  if (ref_magnitude > 1e-10) {
    metrics.relative_error = static_cast<float>(std::sqrt(sum_sq_error / n) / ref_magnitude);
  }

  return metrics;
}

}  // namespace benchmark
}  // namespace ionosense
