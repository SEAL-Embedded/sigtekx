/**
 * @file dataset_comparison.hpp
 * @brief Statistical comparison engine for regression detection.
 *
 * Provides comparison functions for detecting performance regressions
 * between dataset snapshots. Includes:
 * - Delta and percent change calculation
 * - Threshold-based classification (no change, slight regression, etc.)
 * - Formatted output with color-coded indicators
 */

#pragma once

#include <cmath>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "../benchmarks/core/results.hpp"

namespace sigtekx {
namespace benchmark {

// ============================================================================
// Comparison Result Structures
// ============================================================================

/**
 * @brief Status of a metric comparison.
 */
enum class ComparisonStatus {
  NO_CHANGE,         // |delta| < 1%
  SLIGHT_REGRESSION, // 1-5% worse
  REGRESSION,        // 5-10% worse
  MAJOR_REGRESSION,  // >10% worse
  IMPROVEMENT        // Better
};

/**
 * @brief Single metric comparison result.
 */
struct ComparisonResult {
  std::string metric_name;
  float dataset_value;
  float current_value;
  float delta;
  float percent_change;
  ComparisonStatus status;
  bool lower_is_better;  // Directionality (latency vs throughput)
};

/**
 * @brief Complete comparison summary.
 */
struct ComparisonSummary {
  std::string dataset_name;
  std::string current_name;
  std::vector<ComparisonResult> metrics;
  bool overall_regression;  // True if any metric regressed
};

// ============================================================================
// Comparison Logic
// ============================================================================

/**
 * @brief Compare two metric values and classify the result.
 *
 * @param metric_name Name of metric (for display)
 * @param dataset_val Dataset value
 * @param current_val Current value
 * @param lower_is_better True if lower values are better (latency), false otherwise (throughput)
 * @return Comparison result
 */
inline ComparisonResult compare_metric(const std::string& metric_name,
                                       float dataset_val,
                                       float current_val,
                                       bool lower_is_better) {
  ComparisonResult result;
  result.metric_name = metric_name;
  result.dataset_value = dataset_val;
  result.current_value = current_val;
  result.lower_is_better = lower_is_better;

  // Calculate delta and percent change
  result.delta = current_val - dataset_val;
  result.percent_change = (dataset_val != 0.0f)
      ? (result.delta / dataset_val) * 100.0f
      : 0.0f;

  // Classify change
  float abs_pct = std::abs(result.percent_change);
  bool worse = lower_is_better ? (current_val > dataset_val) : (current_val < dataset_val);

  if (abs_pct < 1.0f) {
    result.status = ComparisonStatus::NO_CHANGE;
  } else if (worse) {
    if (abs_pct < 5.0f) {
      result.status = ComparisonStatus::SLIGHT_REGRESSION;
    } else if (abs_pct < 10.0f) {
      result.status = ComparisonStatus::REGRESSION;
    } else {
      result.status = ComparisonStatus::MAJOR_REGRESSION;
    }
  } else {
    result.status = ComparisonStatus::IMPROVEMENT;
  }

  return result;
}

/**
 * @brief Compare two latency datasets.
 *
 * @param dataset Dataset latency results
 * @param current Current latency results
 * @param dataset_name Name of dataset
 * @param current_name Name of current
 * @return Comparison summary
 */
inline ComparisonSummary compare_latency(const LatencyResults& dataset,
                                         const LatencyResults& current,
                                         const std::string& dataset_name,
                                         const std::string& current_name) {
  ComparisonSummary summary;
  summary.dataset_name = dataset_name;
  summary.current_name = current_name;
  summary.overall_regression = false;

  // Compare key metrics (lower is better for latency)
  summary.metrics.push_back(
      compare_metric("Mean Latency (µs)", dataset.mean_latency_us, current.mean_latency_us, true));
  summary.metrics.push_back(
      compare_metric("P95 Latency (µs)", dataset.p95_latency_us, current.p95_latency_us, true));
  summary.metrics.push_back(
      compare_metric("P99 Latency (µs)", dataset.p99_latency_us, current.p99_latency_us, true));
  summary.metrics.push_back(
      compare_metric("Coefficient of Variation", dataset.coefficient_of_variation,
                     current.coefficient_of_variation, true));

  // Check for regressions
  for (const auto& metric : summary.metrics) {
    if (metric.status == ComparisonStatus::SLIGHT_REGRESSION ||
        metric.status == ComparisonStatus::REGRESSION ||
        metric.status == ComparisonStatus::MAJOR_REGRESSION) {
      summary.overall_regression = true;
      break;
    }
  }

  return summary;
}

/**
 * @brief Compare two throughput datasets.
 *
 * @param dataset Dataset throughput results
 * @param current Current throughput results
 * @param dataset_name Name of dataset
 * @param current_name Name of current
 * @return Comparison summary
 */
inline ComparisonSummary compare_throughput(const ThroughputResults& dataset,
                                            const ThroughputResults& current,
                                            const std::string& dataset_name,
                                            const std::string& current_name) {
  ComparisonSummary summary;
  summary.dataset_name = dataset_name;
  summary.current_name = current_name;
  summary.overall_regression = false;

  // Compare key metrics (higher is better for throughput)
  summary.metrics.push_back(
      compare_metric("Frames per Second", dataset.frames_per_second,
                     current.frames_per_second, false));
  summary.metrics.push_back(
      compare_metric("GB per Second", dataset.gb_per_second, current.gb_per_second, false));
  summary.metrics.push_back(
      compare_metric("Samples per Second", dataset.samples_per_second,
                     current.samples_per_second, false));

  // Check for regressions
  for (const auto& metric : summary.metrics) {
    if (metric.status == ComparisonStatus::SLIGHT_REGRESSION ||
        metric.status == ComparisonStatus::REGRESSION ||
        metric.status == ComparisonStatus::MAJOR_REGRESSION) {
      summary.overall_regression = true;
      break;
    }
  }

  return summary;
}

/**
 * @brief Compare two realtime datasets.
 *
 * @param dataset Dataset realtime results
 * @param current Current realtime results
 * @param dataset_name Name of dataset
 * @param current_name Name of current
 * @return Comparison summary
 */
inline ComparisonSummary compare_realtime(const RealtimeResults& dataset,
                                          const RealtimeResults& current,
                                          const std::string& dataset_name,
                                          const std::string& current_name) {
  ComparisonSummary summary;
  summary.dataset_name = dataset_name;
  summary.current_name = current_name;
  summary.overall_regression = false;

  // Compare key metrics
  summary.metrics.push_back(
      compare_metric("Compliance Rate", dataset.compliance_rate,
                     current.compliance_rate, false));  // Higher is better
  summary.metrics.push_back(
      compare_metric("Mean Latency (ms)", dataset.mean_latency_ms,
                     current.mean_latency_ms, true));   // Lower is better
  summary.metrics.push_back(
      compare_metric("P99 Latency (ms)", dataset.p99_latency_ms,
                     current.p99_latency_ms, true));    // Lower is better
  summary.metrics.push_back(
      compare_metric("Mean Jitter (ms)", dataset.mean_jitter_ms,
                     current.mean_jitter_ms, true));    // Lower is better

  // Check for regressions
  for (const auto& metric : summary.metrics) {
    if (metric.status == ComparisonStatus::SLIGHT_REGRESSION ||
        metric.status == ComparisonStatus::REGRESSION ||
        metric.status == ComparisonStatus::MAJOR_REGRESSION) {
      summary.overall_regression = true;
      break;
    }
  }

  return summary;
}

/**
 * @brief Compare two accuracy datasets.
 *
 * @param dataset Dataset accuracy results
 * @param current Current accuracy results
 * @param dataset_name Name of dataset
 * @param current_name Name of current
 * @return Comparison summary
 */
inline ComparisonSummary compare_accuracy(const AccuracyResults& dataset,
                                          const AccuracyResults& current,
                                          const std::string& dataset_name,
                                          const std::string& current_name) {
  ComparisonSummary summary;
  summary.dataset_name = dataset_name;
  summary.current_name = current_name;
  summary.overall_regression = false;

  // Compare key metrics
  summary.metrics.push_back(
      compare_metric("Pass Rate", dataset.pass_rate, current.pass_rate, false));  // Higher is better
  summary.metrics.push_back(
      compare_metric("Mean SNR (dB)", dataset.mean_snr_db, current.mean_snr_db, false));  // Higher is better
  summary.metrics.push_back(
      compare_metric("Mean MAE", dataset.mean_mae, current.mean_mae, true));  // Lower is better
  summary.metrics.push_back(
      compare_metric("Mean RMSE", dataset.mean_rmse, current.mean_rmse, true));  // Lower is better

  // Check for regressions
  for (const auto& metric : summary.metrics) {
    if (metric.status == ComparisonStatus::SLIGHT_REGRESSION ||
        metric.status == ComparisonStatus::REGRESSION ||
        metric.status == ComparisonStatus::MAJOR_REGRESSION) {
      summary.overall_regression = true;
      break;
    }
  }

  return summary;
}

// ============================================================================
// Formatted Output
// ============================================================================

/**
 * @brief Get status indicator string.
 *
 * @param status Comparison status
 * @param use_color Use ANSI color codes (default: true)
 * @return Status indicator string
 */
inline std::string get_status_indicator(ComparisonStatus status, bool use_color = true) {
  switch (status) {
    case ComparisonStatus::NO_CHANGE:
      return use_color ? "\033[90m=\033[0m" : "=";  // Gray
    case ComparisonStatus::IMPROVEMENT:
      return use_color ? "\033[32m↑\033[0m" : "↑";  // Green
    case ComparisonStatus::SLIGHT_REGRESSION:
      return use_color ? "\033[33m⚠\033[0m" : "⚠";  // Yellow
    case ComparisonStatus::REGRESSION:
      return use_color ? "\033[31m↓\033[0m" : "↓";  // Red
    case ComparisonStatus::MAJOR_REGRESSION:
      return use_color ? "\033[91m🔴\033[0m" : "X";  // Bright red
    default:
      return "?";
  }
}

/**
 * @brief Print comparison summary to stdout.
 *
 * @param summary Comparison summary
 * @param use_color Use ANSI color codes (default: true)
 */
inline void print_comparison(const ComparisonSummary& summary, bool use_color = true) {
  std::cout << "\n";
  std::cout << "========================================\n";
  std::cout << "  Dataset Comparison\n";
  std::cout << "========================================\n";
  std::cout << "\n";
  std::cout << "Dataset: " << summary.dataset_name << "\n";
  std::cout << "Current:  " << summary.current_name << "\n";
  std::cout << "\n";

  // Table header
  std::cout << std::left << std::setw(30) << "Metric"
            << std::right << std::setw(12) << "Dataset"
            << std::right << std::setw(12) << "Current"
            << std::right << std::setw(12) << "Delta"
            << std::right << std::setw(10) << "% Change"
            << std::right << std::setw(8) << "Status" << "\n";
  std::cout << std::string(84, '-') << "\n";

  // Metrics
  for (const auto& metric : summary.metrics) {
    std::cout << std::left << std::setw(30) << metric.metric_name
              << std::right << std::setw(12) << std::fixed << std::setprecision(2) << metric.dataset_value
              << std::right << std::setw(12) << std::fixed << std::setprecision(2) << metric.current_value
              << std::right << std::setw(12) << std::fixed << std::setprecision(2) << metric.delta
              << std::right << std::setw(9) << std::fixed << std::setprecision(1) << metric.percent_change << "%"
              << std::right << std::setw(8) << get_status_indicator(metric.status, use_color) << "\n";
  }

  std::cout << "\n";

  // Overall summary
  if (summary.overall_regression) {
    if (use_color) {
      std::cout << "\033[31m⚠ Performance regression detected\033[0m\n";
    } else {
      std::cout << "⚠ Performance regression detected\n";
    }
  } else {
    if (use_color) {
      std::cout << "\033[32m✓ No significant regressions\033[0m\n";
    } else {
      std::cout << "✓ No significant regressions\n";
    }
  }

  std::cout << "\n";
}

}  // namespace benchmark
}  // namespace sigtekx
