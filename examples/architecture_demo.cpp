/**
 * @file architecture_demo.cpp
 * @brief Demonstrates the new v0.9.3 composable architecture.
 *
 * This example shows how to use the refactored architecture with:
 * - PipelineBuilder for custom pipelines
 * - Different executor types (Batch vs Realtime)
 * - Specialized engines (RealtimeIonoEngine)
 */

#include <iostream>
#include <vector>

#include "ionosense/core/executor_config.hpp"
#include "ionosense/core/pipeline_builder.hpp"
#include "ionosense/engines/realtime_iono_engine.hpp"
#include "ionosense/engines/research_engine_v2.hpp"
#include "ionosense/executors/batch_executor.hpp"

using namespace ionosense;

void demo_research_engine_v2() {
  std::cout << "=== ResearchEngineV2 Demo ===\n";

  // Create engine with default configuration
  ResearchEngineV2 engine;

  EngineConfig config;
  config.nfft = 1024;
  config.batch = 2;
  config.overlap = 0.5f;
  config.stream_count = 3;

  engine.initialize(config);

  // Generate test signal
  std::vector<float> input(config.nfft * config.batch, 1.0f);
  std::vector<float> output(config.num_output_bins() * config.batch);

  // Process
  engine.process(input.data(), output.data(), input.size());

  auto stats = engine.get_stats();
  std::cout << "Latency: " << stats.latency_us << " us\n";
  std::cout << "Throughput: " << stats.throughput_gbps << " GB/s\n\n";
}

void demo_realtime_iono_engine() {
  std::cout << "=== RealtimeIonoEngine Demo ===\n";

  // Create ionosphere-optimized configuration
  auto config = IonosphereConfig::create_realtime(2048, 48000);

  // Create specialized engine
  RealtimeIonoEngine engine(config);

  // Generate test HF signal
  std::vector<float> input(config.nfft * config.batch);
  for (size_t i = 0; i < input.size(); ++i) {
    input[i] = std::sin(2.0f * 3.14159f * 10000.0f * i / 48000.0f);
  }

  std::vector<float> output(config.num_output_bins() * config.batch);

  // Process
  engine.process(input.data(), output.data(), input.size());

  auto stats = engine.get_stats();
  std::cout << "Ionosphere processing latency: " << stats.latency_us << " us\n";
  std::cout << "Throughput: " << stats.throughput_gbps << " GB/s\n\n";
}

void demo_custom_pipeline() {
  std::cout << "=== Custom Pipeline Demo ===\n";

  // Build custom pipeline
  PipelineBuilder builder;
  StageConfig stage_config;
  stage_config.nfft = 4096;
  stage_config.batch = 8;
  stage_config.overlap = 0.75f;

  auto stages = builder.with_config(stage_config)
                    .add_window(StageConfig::WindowType::BLACKMAN)
                    .add_fft()
                    .add_magnitude()
                    .build();

  std::cout << "Built pipeline with " << stages.size() << " stages\n";

  // Create executor
  ExecutorConfig exec_config;
  exec_config.nfft = 4096;
  exec_config.batch = 8;
  exec_config.overlap = 0.75f;
  exec_config.mode = ExecutorConfig::ExecutionMode::BATCH;
  exec_config.stream_count = 3;
  exec_config.pinned_buffer_count = 2;

  BatchExecutor executor;
  executor.initialize(exec_config, std::move(stages));

  // Process data
  std::vector<float> input(exec_config.nfft * exec_config.batch, 1.0f);
  std::vector<float> output(exec_config.num_output_bins() * exec_config.batch);

  executor.submit(input.data(), output.data(), input.size());

  auto stats = executor.get_stats();
  std::cout << "Custom pipeline latency: " << stats.latency_us << " us\n";
  std::cout << "Memory usage: " << executor.get_memory_usage() / (1024 * 1024)
            << " MB\n\n";
}

int main() {
  std::cout << "Ionosense HPC Architecture Demo (v0.9.3)\n";
  std::cout << "=========================================\n\n";

  try {
    demo_research_engine_v2();
    demo_realtime_iono_engine();
    demo_custom_pipeline();

    std::cout << "All demos completed successfully!\n";
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "Error: " << e.what() << "\n";
    return 1;
  }
}
