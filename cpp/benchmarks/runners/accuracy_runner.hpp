/**
 * @file accuracy_runner.hpp
 * @brief Accuracy benchmark runner.
 *
 * Provides numerical accuracy validation against pipeline-matching reference.
 */

#pragma once

#include <cmath>
#include <string>
#include <vector>

#include "../benchmarks/core/config.hpp"
#include "../benchmarks/core/results.hpp"
#include "../benchmarks/utils/reference_compute.hpp"
#include "../benchmarks/utils/signal_generator.hpp"
#include "sigtekx/profiling/nvtx.hpp"

namespace sigtekx {
namespace benchmark {

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
 * @tparam ExecutorT Executor type (BatchExecutor or StreamingExecutor)
 * @param executor Executor instance
 * @param config Benchmark configuration
 * @return AccuracyResults with pass/fail based on numerical agreement
 */
template<typename ExecutorT>
inline AccuracyResults run_accuracy_benchmark(ExecutorT& executor,
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
}  // namespace sigtekx
