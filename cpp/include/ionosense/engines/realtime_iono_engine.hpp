/**
 * @file realtime_iono_engine.hpp
 * @version 0.9.3
 * @date 2025-10-09
 * @author [Kevin Rahsaz]
 *
 * @brief Specialized engine for realtime ionosphere signal processing.
 *
 * This facade combines RealtimeExecutor with an ionosphere-optimized
 * pipeline for continuous HF signal analysis.
 */

#pragma once

#include <memory>

#include "ionosense/core/executor_config.hpp"
#include "ionosense/core/processing_stage.hpp"
#include "ionosense/core/pipeline_executor.hpp"

namespace ionosense {

/**
 * @struct IonosphereConfig
 * @brief Configuration specific to ionosphere signal processing.
 *
 * Extends ExecutorConfig with ionosphere-specific parameters and
 * optimal defaults for HF signal analysis.
 */
struct IonosphereConfig : ExecutorConfig {
  // Ionosphere-specific parameters (future extensions)
  bool enable_doppler_correction = false;
  bool enable_multipath_mitigation = false;

  /**
   * @brief Creates a configuration optimized for realtime ionosphere
   * processing.
   * @param nfft FFT size (typically 2048-8192 for ionosphere work).
   * @param sample_rate Sample rate in Hz (e.g., 48000 for HF).
   * @return IonosphereConfig with optimal settings.
   */
  static IonosphereConfig create_realtime(int nfft = 2048,
                                          int sample_rate = 48000) {
    IonosphereConfig config;
    config.nfft = nfft;
    config.batch = 8;
    config.overlap = 0.625f;  // 62.5% overlap for good time resolution
    config.sample_rate_hz = sample_rate;
    config.stream_count = 3;
    config.pinned_buffer_count = 2;
    config.mode = ExecutionMode::LOW_LATENCY;
    config.max_inflight_batches = 2;
    return config;
  }

  /**
   * @brief Creates a configuration for high-resolution ionosphere analysis.
   * @param nfft FFT size (typically 8192-32768).
   * @param sample_rate Sample rate in Hz.
   * @return IonosphereConfig with high-resolution settings.
   */
  static IonosphereConfig create_hires(int nfft = 8192,
                                       int sample_rate = 48000) {
    IonosphereConfig config;
    config.nfft = nfft;
    config.batch = 16;
    config.overlap = 0.75f;
    config.sample_rate_hz = sample_rate;
    config.stream_count = 3;
    config.pinned_buffer_count = 3;
    config.mode = ExecutionMode::BATCH;
    return config;
  }
};

/**
 * @class RealtimeIonoEngine
 * @brief Specialized engine for realtime ionosphere signal processing.
 *
 * This engine is pre-configured for ionosphere analysis:
 * - Blackman window for better sidelobe suppression
 * - Optimized overlap for time-frequency resolution
 * - Streaming execution with low latency
 * - Optional ionosphere-specific metrics stages (future)
 *
 * Example usage:
 * @code
 *   auto config = IonosphereConfig::create_realtime(2048, 48000);
 *   RealtimeIonoEngine engine(config);
 *   engine.process(hf_signal_data, output, num_samples);
 * @endcode
 */
class RealtimeIonoEngine {
 public:
  /**
   * @brief Constructs the engine with ionosphere-specific configuration.
   * @param config Ionosphere processing configuration.
   */
  explicit RealtimeIonoEngine(const IonosphereConfig& config);

  /**
   * @brief Destructor.
   */
  ~RealtimeIonoEngine();

  // Disable copy, enable move
  RealtimeIonoEngine(const RealtimeIonoEngine&) = delete;
  RealtimeIonoEngine& operator=(const RealtimeIonoEngine&) = delete;
  RealtimeIonoEngine(RealtimeIonoEngine&&) noexcept;
  RealtimeIonoEngine& operator=(RealtimeIonoEngine&&) noexcept;

  /**
   * @brief Processes ionosphere signal data.
   * @param input Pointer to host input data (HF signal samples).
   * @param output Pointer to host output buffer (magnitude spectrum).
   * @param num_samples Total number of float samples in the input.
   */
  void process(const float* input, float* output, size_t num_samples);

  /**
   * @brief Processes data asynchronously with callback.
   * @param input Pointer to host input data.
   * @param num_samples Total number of float samples.
   * @param callback Function to call when processing completes.
   */
  void process_async(const float* input, size_t num_samples,
                    ResultCallback callback);

  /**
   * @brief Synchronizes all pending operations.
   */
  void synchronize();

  /**
   * @brief Resets the engine.
   */
  void reset();

  /**
   * @brief Retrieves performance statistics.
   * @return ProcessingStats structure.
   */
  ProcessingStats get_stats() const;

  /**
   * @brief Checks if engine is initialized.
   * @return True if initialized, false otherwise.
   */
  bool is_initialized() const;

 private:
  class Impl;
  std::unique_ptr<Impl> pImpl;
};

}  // namespace ionosense
