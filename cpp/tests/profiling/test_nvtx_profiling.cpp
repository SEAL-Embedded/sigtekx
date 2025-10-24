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
#include "ionosense/executors/batch_executor.hpp"
#include "ionosense/profiling/nvtx.hpp"

using namespace ionosense;

static std::vector<float> generate_test_signal(int nfft, int batch) {
  IONO_NVTX_RANGE("Generate Test Signal", profiling::colors::CYAN);
  std::vector<float> signal(static_cast<size_t>(nfft) * batch);
  std::mt19937 gen(12345);
  std::normal_distribution<float> dist(0.0f, 1.0f);
  for (auto& s : signal) s = dist(gen);
  return signal;
}

static void run_warmup(BatchExecutor& executor, int warmup_iters, int nfft,
                       int batch) {
  IONO_NVTX_RANGE("Warmup Phase", profiling::colors::LIGHT_GRAY);
  std::vector<float> warmup_input(static_cast<size_t>(nfft) * batch, 0.0f);
  std::vector<float> warmup_output(static_cast<size_t>(nfft / 2 + 1) * batch);
  for (int i = 0; i < warmup_iters; ++i) {
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

TEST(NvtxProfilingTest, BenchmarkPhasesRun) {
  int device_count = 0;
  if (cudaGetDeviceCount(&device_count) != cudaSuccess || device_count == 0) {
    GTEST_SKIP() << "No CUDA devices available for NVTX profiling test.";
  }

  const int nfft = 1024;
  const int batch = 2;
  const int iterations = 20;
  const int warmup_iters = 5;

  BatchExecutor executor;

  ExecutorConfig cfg;
  cfg.nfft = nfft;
  cfg.channels = batch;
  cfg.overlap = 0.5f;
  cfg.sample_rate_hz = 48000;
  cfg.stream_count = 3;
  cfg.pinned_buffer_count = 2;
  cfg.warmup_iters = 0;  // manual warmup below
  cfg.mode = ExecutorConfig::ExecutionMode::BATCH;
  cfg.device_id = -1;  // auto-select

  {
    IONO_NVTX_RANGE("Executor Initialization", profiling::colors::DARK_GRAY);
    auto stages = StageFactory::create_default_pipeline();
    EXPECT_NO_THROW(executor.initialize(cfg, std::move(stages)));
    EXPECT_TRUE(executor.is_initialized());
  }

  // Warmup
  run_warmup(executor, warmup_iters, nfft, batch);

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
          executor.submit(input.data(), output.data(), input.size()));
      auto t1 = std::chrono::high_resolution_clock::now();
      latencies.push_back(
          std::chrono::duration<float, std::micro>(t1 - t0).count());
    }
  }

  // Sync and analyze
  {
    IONO_NVTX_RANGE("Results Analysis", profiling::colors::CYAN);
    executor.synchronize();
    ASSERT_EQ(latencies.size(), static_cast<size_t>(iterations));
    const float mean =
        std::accumulate(latencies.begin(), latencies.end(), 0.0f) /
        static_cast<float>(latencies.size());
    EXPECT_GT(mean, 0.0f);
    const auto stats = executor.get_stats();
    EXPECT_GT(stats.frames_processed, 0u);
  }

  // Cleanup
  {
    IONO_NVTX_RANGE("Cleanup Phase", profiling::colors::RED);
    executor.reset();
    EXPECT_FALSE(executor.is_initialized());
  }
}