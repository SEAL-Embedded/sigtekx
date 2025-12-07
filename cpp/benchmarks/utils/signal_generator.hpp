/**
 * @file signal_generator.hpp
 * @brief Test signal generation for benchmark validation and accuracy testing.
 *
 * Provides deterministic signal generation for various signal types including
 * white noise, pure sine waves, multi-tone signals, and chirps.
 */

#pragma once

#include <cmath>
#include <random>
#include <vector>

#include "sigtekx/profiling/nvtx.hpp"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace sigtekx {
namespace benchmark {

// ============================================================================
// Signal Types
// ============================================================================

/**
 * @brief Types of test signals for benchmarking and validation.
 */
enum class SignalType {
  WHITE_NOISE,  ///< Gaussian white noise (mean=0, std=1)
  PURE_SINE,    ///< Single sine wave at known frequency
  MULTI_TONE,   ///< Sum of multiple sine waves
  CHIRP         ///< Linear frequency sweep
};

// ============================================================================
// Signal Generation
// ============================================================================

/**
 * @brief Generate test signal with specified type and parameters.
 *
 * @param nfft FFT size (samples per frame)
 * @param batch Number of frames to generate
 * @param seed Random seed for reproducibility
 * @param type Type of signal to generate
 * @return Vector of floats containing the generated signal
 */
inline std::vector<float> generate_test_signal(
    int nfft, int batch, int seed = 42,
    SignalType type = SignalType::WHITE_NOISE) {
  SIGTEKX_NVTX_RANGE("Generate Test Signal", profiling::colors::CYAN);
  std::vector<float> signal(static_cast<size_t>(nfft) * batch);
  std::mt19937 gen(seed);

  switch (type) {
    case SignalType::WHITE_NOISE: {
      std::normal_distribution<float> dist(0.0f, 1.0f);
      for (auto& s : signal) {
        s = dist(gen);
      }
      break;
    }

    case SignalType::PURE_SINE: {
      // Generate a pure sine wave at a known frequency
      // Frequency bin 10 (arbitrary choice in lower third of spectrum)
      const float freq_bin = 10.0f;
      const float amplitude = 1.0f;
      for (int b = 0; b < batch; ++b) {
        for (int i = 0; i < nfft; ++i) {
          const int idx = b * nfft + i;
          signal[idx] = amplitude * std::sin(2.0f * M_PI * freq_bin * i / nfft);
        }
      }
      break;
    }

    case SignalType::MULTI_TONE: {
      // Generate sum of 3 sine waves at known frequencies
      const std::vector<float> freq_bins = {5.0f, 15.0f, 25.0f};
      const std::vector<float> amplitudes = {0.8f, 0.6f, 0.4f};
      for (int b = 0; b < batch; ++b) {
        for (int i = 0; i < nfft; ++i) {
          const int idx = b * nfft + i;
          signal[idx] = 0.0f;
          for (size_t t = 0; t < freq_bins.size(); ++t) {
            signal[idx] += amplitudes[t] *
                          std::sin(2.0f * M_PI * freq_bins[t] * i / nfft);
          }
        }
      }
      break;
    }

    case SignalType::CHIRP: {
      // Linear frequency sweep
      const float f0 = 5.0f / nfft;   // Start frequency
      const float f1 = 50.0f / nfft;  // End frequency
      const float amplitude = 1.0f;
      for (int b = 0; b < batch; ++b) {
        for (int i = 0; i < nfft; ++i) {
          const int idx = b * nfft + i;
          const float t = static_cast<float>(i) / nfft;
          const float phase = 2.0f * M_PI * (f0 * t + (f1 - f0) * t * t / 2.0f) * nfft;
          signal[idx] = amplitude * std::sin(phase);
        }
      }
      break;
    }
  }

  return signal;
}

}  // namespace benchmark
}  // namespace sigtekx
