/**
 * @file test_nvtx_profiling.cpp
 * @brief Validates NVTX instrumentation by exercising engine phases.
 */

#include <gtest/gtest.h>

// Enable NVTX macros in this TU (definitions live in profiling_nvtx.cu)
#define IONOSENSE_ENABLE_PROFILING 1

#include <algorithm>
#include <chrono>
#include <cmath>
#include <numeric>
#include <random>
#include <string>
#include <vector>

#include "ionosense/core/cuda_wrappers.hpp"
#include "ionosense/core/processing_stage.hpp"  // for ProcessingStats definition
#include "ionosense/core/profiling_macros.hpp"
#include "ionosense/engines/research_engine.hpp"

using namespace ionosense;

static std::vector<float> generate_test_signal(int nfft, int batch) {
  IONO_NVTX_RANGE("Generate Test Signal", profiling::colors::CYAN);
  std::vector<float> signal(static_cast<size_t>(nfft) * batch);
  std::mt19937 gen(12345);
  std::normal_distribution<float> dist(0.0f, 1.0f);
  for (auto& s : signal) s = dist(gen);
  return signal;
}

static void run_warmup(ResearchEngine& engine, int warmup_iters, int nfft,
                       int batch) {
  IONO_NVTX_RANGE("Warmup Phase", profiling::colors::LIGHT_GRAY);
  std::vector<float> warmup_input(static_cast<size_t>(nfft) * batch, 0.0f);
  std::vector<float> warmup_output(static_cast<size_t>(nfft / 2 + 1) * batch);
  for (int i = 0; i < warmup_iters; ++i) {
    const std::string name = "Warmup " + std::to_string(i);
    IONO_NVTX_RANGE(name.c_str(), profiling::colors::LIGHT_GRAY);
    engine.process(warmup_input.data(), warmup_output.data(),
                   warmup_input.size());
  }
  {
    IONO_NVTX_RANGE("Warmup Sync", profiling::colors::YELLOW);
    engine.synchronize();
  }
}

TEST(NvtxProfilingTest, BenchmarkPhasesRun) {
  int device_count = 0;
  if (cudaGetDeviceCount(&device_count) != cudaSuccess || device_count == 0) {
    GTEST_SKIP() << "No CUDA devices available for NVTX profiling test.";
  }

  const int nfft = 1024;
  const int batch = 2;
  const int iterations = 20;
  const int warmup_iters = 5;

  ResearchEngine engine;

  EngineConfig cfg;
  cfg.nfft = nfft;
  cfg.batch = batch;
  cfg.overlap = 0.5f;
  cfg.sample_rate_hz = 48000;
  cfg.stream_count = 3;
  cfg.pinned_buffer_count = 2;
  cfg.warmup_iters = 0;  // manual warmup below
  cfg.enable_profiling = true;

  {
    IONO_NVTX_RANGE("Engine Initialization", profiling::colors::DARK_GRAY);
    EXPECT_NO_THROW(engine.initialize(cfg));
    EXPECT_TRUE(engine.is_initialized());
  }

  // Runtime info (sanity)
  {
    IONO_NVTX_RANGE("Query Runtime Info", profiling::colors::CYAN);
    auto info = engine.get_runtime_info();
    EXPECT_FALSE(info.device_name.empty());
    EXPECT_GT(info.cuda_runtime_version, 0);
  }

  // Warmup
  run_warmup(engine, warmup_iters, nfft, batch);

  // Benchmark
  std::vector<float> input = generate_test_signal(nfft, batch);
  std::vector<float> output(static_cast<size_t>(nfft / 2 + 1) * batch);
  std::vector<float> latencies;
  latencies.reserve(iterations);

  {
    IONO_NVTX_RANGE("Benchmark Phase", profiling::colors::NVIDIA_BLUE);
    for (int i = 0; i < iterations; ++i) {
      const std::string iter_name = "Benchmark Iteration " + std::to_string(i);
      IONO_NVTX_RANGE(iter_name.c_str(), profiling::colors::NVIDIA_BLUE);
      auto t0 = std::chrono::high_resolution_clock::now();
      EXPECT_NO_THROW(
          engine.process(input.data(), output.data(), input.size()));
      auto t1 = std::chrono::high_resolution_clock::now();
      latencies.push_back(
          std::chrono::duration<float, std::micro>(t1 - t0).count());
    }
  }

  // Sync and analyze
  {
    IONO_NVTX_RANGE("Results Analysis", profiling::colors::CYAN);
    engine.synchronize();
    ASSERT_EQ(latencies.size(), static_cast<size_t>(iterations));
    const float mean =
        std::accumulate(latencies.begin(), latencies.end(), 0.0f) /
        static_cast<float>(latencies.size());
    EXPECT_GT(mean, 0.0f);
    const auto stats = engine.get_stats();
    EXPECT_GT(stats.frames_processed, 0u);
  }

  // Cleanup
  {
    IONO_NVTX_RANGE("Cleanup Phase", profiling::colors::RED);
    engine.reset();
    EXPECT_FALSE(engine.is_initialized());
  }
}