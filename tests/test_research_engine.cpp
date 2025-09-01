// tests/test_research_engine.cpp
#include <gtest/gtest.h>
#include "ionosense/research_engine.hpp"
#include "ionosense/processing_stage.hpp"
#include <vector>
#include <cmath>
#include <chrono>
#include <thread>
#include <algorithm>

using namespace ionosense;

class ResearchEngineTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Ensure CUDA is available
        int device_count = 0;
        cudaError_t err = cudaGetDeviceCount(&device_count);
        if (err != cudaSuccess || device_count == 0) {
            GTEST_SKIP() << "No CUDA devices available";
        }
        
        // Default configuration
        config_.nfft = 512;
        config_.batch = 2;
        config_.overlap = 0.5f;
        config_.sample_rate_hz = 48000;
        config_.stream_count = 3;
        config_.pinned_buffer_count = 2;
        config_.warmup_iters = 1;
    }
    
    // Helper to generate test signal
    std::vector<float> generate_sinusoid(int size, float frequency) {
        std::vector<float> signal(size);
        const float pi = 3.14159265358979323846f;
        for (int i = 0; i < size; ++i) {
            signal[i] = std::sin(2.0f * pi * frequency * i / size);
        }
        return signal;
    }
    
    // Helper to generate white noise
    std::vector<float> generate_noise(int size) {
        std::vector<float> signal(size);
        for (int i = 0; i < size; ++i) {
            signal[i] = (float(rand()) / RAND_MAX) * 2.0f - 1.0f;
        }
        return signal;
    }

protected:
    EngineConfig config_;
};

// ============================================================================
// Basic Functionality Tests
// ============================================================================

TEST_F(ResearchEngineTest, Construction) {
    EXPECT_NO_THROW(ResearchEngine engine);
}

TEST_F(ResearchEngineTest, Initialization) {
    ResearchEngine engine;
    EXPECT_FALSE(engine.is_initialized());
    
    EXPECT_NO_THROW(engine.initialize(config_));
    EXPECT_TRUE(engine.is_initialized());
}

TEST_F(ResearchEngineTest, DoubleInitialization) {
    ResearchEngine engine;
    engine.initialize(config_);
    
    // Should reset and reinitialize
    EXPECT_NO_THROW(engine.initialize(config_));
    EXPECT_TRUE(engine.is_initialized());
}

TEST_F(ResearchEngineTest, Reset) {
    ResearchEngine engine;
    engine.initialize(config_);
    EXPECT_TRUE(engine.is_initialized());
    
    engine.reset();
    EXPECT_FALSE(engine.is_initialized());
}

TEST_F(ResearchEngineTest, MoveSemantics) {
    ResearchEngine engine1;
    engine1.initialize(config_);
    
    // Move construction
    ResearchEngine engine2(std::move(engine1));
    EXPECT_TRUE(engine2.is_initialized());
    
    // Move assignment
    ResearchEngine engine3;
    engine3 = std::move(engine2);
    EXPECT_TRUE(engine3.is_initialized());
}

// ============================================================================
// Processing Tests
// ============================================================================

TEST_F(ResearchEngineTest, BasicProcessing) {
    ResearchEngine engine;
    engine.initialize(config_);
    
    const size_t input_size = config_.nfft * config_.batch;
    const size_t output_size = config_.num_output_bins() * config_.batch;
    
    auto input = generate_sinusoid(input_size, 10.0f);
    std::vector<float> output(output_size);
    
    EXPECT_NO_THROW(engine.process(input.data(), output.data(), input_size));
    
    // Verify output is non-zero
    bool has_nonzero = false;
    for (float val : output) {
        if (val > 1e-6f) {
            has_nonzero = true;
            break;
        }
    }
    EXPECT_TRUE(has_nonzero);
}

TEST_F(ResearchEngineTest, DCSignalProcessing) {
    ResearchEngine engine;
    engine.initialize(config_);
    
    const size_t input_size = config_.nfft * config_.batch;
    const size_t output_size = config_.num_output_bins() * config_.batch;
    
    // DC signal (all ones)
    std::vector<float> input(input_size, 1.0f);
    std::vector<float> output(output_size);
    
    engine.process(input.data(), output.data(), input_size);
    
    // DC bin should have maximum energy
    for (size_t ch = 0; ch < config_.batch; ++ch) {
        size_t offset = ch * config_.num_output_bins();
        float dc_magnitude = output[offset];  // First bin is DC
        
        // DC should be the strongest component
        for (size_t bin = 1; bin < config_.num_output_bins(); ++bin) {
            EXPECT_GT(dc_magnitude, output[offset + bin]);
        }
    }
}

TEST_F(ResearchEngineTest, SinusoidProcessing) {
    ResearchEngine engine;
    engine.initialize(config_);
    
    const size_t input_size = config_.nfft * config_.batch;
    const size_t output_size = config_.num_output_bins() * config_.batch;
    
    // Generate sinusoid at specific frequency bin
    const int freq_bin = 20;
    std::vector<float> input(input_size);
    
    const float pi = 3.14159265358979323846f;
    for (size_t ch = 0; ch < config_.batch; ++ch) {
        for (size_t i = 0; i < config_.nfft; ++i) {
            input[ch * config_.nfft + i] = 
                std::sin(2.0f * pi * freq_bin * i / config_.nfft);
        }
    }
    
    std::vector<float> output(output_size);
    engine.process(input.data(), output.data(), input_size);
    
    // Find peak frequency
    for (size_t ch = 0; ch < config_.batch; ++ch) {
        size_t offset = ch * config_.num_output_bins();
        float max_magnitude = 0.0f;
        int peak_bin = -1;
        
        for (size_t bin = 0; bin < config_.num_output_bins(); ++bin) {
            if (output[offset + bin] > max_magnitude) {
                max_magnitude = output[offset + bin];
                peak_bin = bin;
            }
        }
        
        // Peak should be at the frequency bin we generated
        EXPECT_EQ(peak_bin, freq_bin);
        EXPECT_GT(max_magnitude, 10.0f);
    }
}

TEST_F(ResearchEngineTest, MultipleFrameProcessing) {
    ResearchEngine engine;
    engine.initialize(config_);
    
    const size_t input_size = config_.nfft * config_.batch;
    const size_t output_size = config_.num_output_bins() * config_.batch;
    
    // Process multiple frames
    const int num_frames = 10;
    for (int frame = 0; frame < num_frames; ++frame) {
        auto input = generate_noise(input_size);
        std::vector<float> output(output_size);
        
        EXPECT_NO_THROW(engine.process(input.data(), output.data(), input_size));
    }
    
    auto stats = engine.get_stats();
    EXPECT_EQ(stats.frames_processed, num_frames);
}

// ============================================================================
// Async Processing Tests
// ============================================================================

TEST_F(ResearchEngineTest, AsyncProcessing) {
    ResearchEngine engine;
    engine.initialize(config_);
    
    const size_t input_size = config_.nfft * config_.batch;
    auto input = generate_sinusoid(input_size, 15.0f);
    
    bool callback_called = false;
    size_t received_bins = 0;
    size_t received_batch = 0;
    
    engine.process_async(input.data(), input_size,
        [&](const float* magnitude, size_t num_bins, size_t batch_size,
            const ProcessingStats& stats) {
            callback_called = true;
            received_bins = num_bins;
            received_batch = batch_size;
            EXPECT_NE(magnitude, nullptr);
            EXPECT_GT(stats.latency_us, 0.0f);
        }
    );
    
    EXPECT_TRUE(callback_called);
    EXPECT_EQ(received_bins, config_.num_output_bins());
    EXPECT_EQ(received_batch, config_.batch);
}

// ============================================================================
// Statistics and Runtime Info Tests
// ============================================================================

TEST_F(ResearchEngineTest, ProcessingStatistics) {
    ResearchEngine engine;
    engine.initialize(config_);
    
    const size_t input_size = config_.nfft * config_.batch;
    const size_t output_size = config_.num_output_bins() * config_.batch;
    
    auto input = generate_noise(input_size);
    std::vector<float> output(output_size);
    
    // Process a frame
    engine.process(input.data(), output.data(), input_size);
    
    auto stats = engine.get_stats();
    EXPECT_GT(stats.latency_us, 0.0f);
    EXPECT_LT(stats.latency_us, 10000.0f);  // Should be < 10ms
    EXPECT_GT(stats.throughput_gbps, 0.0f);
    EXPECT_GE(stats.frames_processed, 1);
    EXPECT_FALSE(stats.is_warmup);
}

TEST_F(ResearchEngineTest, RuntimeInfo) {
    ResearchEngine engine;
    engine.initialize(config_);
    
    auto info = engine.get_runtime_info();
    
    EXPECT_FALSE(info.cuda_version.empty());
    EXPECT_FALSE(info.device_name.empty());
    EXPECT_GE(info.device_compute_capability_major, 3);
    EXPECT_GT(info.device_memory_total_mb, 0);
    EXPECT_GT(info.device_memory_free_mb, 0);
    EXPECT_GT(info.cuda_runtime_version, 0);
    EXPECT_GT(info.cuda_driver_version, 0);
}

// ============================================================================
// Configuration Tests
// ============================================================================

TEST_F(ResearchEngineTest, StageConfiguration) {
    ResearchEngine engine;
    
    StageConfig stage_config;
    stage_config.nfft = 1024;
    stage_config.batch = 4;
    stage_config.window_type = StageConfig::WindowType::HANN;
    stage_config.scale_policy = StageConfig::ScalePolicy::ONE_OVER_N;
    
    engine.set_stage_config(stage_config);
    auto retrieved = engine.get_stage_config();
    
    EXPECT_EQ(retrieved.nfft, stage_config.nfft);
    EXPECT_EQ(retrieved.batch, stage_config.batch);
    EXPECT_EQ(retrieved.window_type, stage_config.window_type);
    EXPECT_EQ(retrieved.scale_policy, stage_config.scale_policy);
}

TEST_F(ResearchEngineTest, ProfilingToggle) {
    ResearchEngine engine;
    engine.initialize(config_);
    
    EXPECT_NO_THROW(engine.set_profiling_enabled(true));
    EXPECT_NO_THROW(engine.set_profiling_enabled(false));
}

// ============================================================================
// Performance Tests
// ============================================================================

TEST_F(ResearchEngineTest, LatencyRequirement) {
    ResearchEngine engine;
    engine.initialize(config_);
    
    const size_t input_size = config_.nfft * config_.batch;
    const size_t output_size = config_.num_output_bins() * config_.batch;
    
    auto input = generate_noise(input_size);
    std::vector<float> output(output_size);
    
    // Warmup
    for (int i = 0; i < 5; ++i) {
        engine.process(input.data(), output.data(), input_size);
    }
    
    // Measure steady-state latency
    std::vector<float> latencies;
    for (int i = 0; i < 100; ++i) {
        engine.process(input.data(), output.data(), input_size);
        auto stats = engine.get_stats();
        latencies.push_back(stats.latency_us);
    }
    
    // Calculate p50 and p99
    std::sort(latencies.begin(), latencies.end());
    float p50 = latencies[latencies.size() / 2];
    float p99 = latencies[latencies.size() * 99 / 100];
    
    // Should meet latency requirements
    EXPECT_LT(p50, 200.0f);  // Target < 200μs
    EXPECT_LT(p99, 500.0f);  // p99 should be reasonable
}

TEST_F(ResearchEngineTest, Synchronization) {
    ResearchEngine engine;
    engine.initialize(config_);
    
    const size_t input_size = config_.nfft * config_.batch;
    const size_t output_size = config_.num_output_bins() * config_.batch;
    
    // Launch multiple operations
    for (int i = 0; i < 5; ++i) {
        auto input = generate_noise(input_size);
        std::vector<float> output(output_size);
        engine.process(input.data(), output.data(), input_size);
    }
    
    // Synchronize should complete without error
    EXPECT_NO_THROW(engine.synchronize());
}

// ============================================================================
// Factory and Utility Tests
// ============================================================================

TEST_F(ResearchEngineTest, EngineFactory) {
    auto engine = create_engine("research");
    EXPECT_NE(engine, nullptr);
    
    EXPECT_THROW(create_engine("ife"), std::runtime_error);
    EXPECT_THROW(create_engine("obe"), std::runtime_error);
    EXPECT_THROW(create_engine("invalid"), std::invalid_argument);
}

TEST_F(ResearchEngineTest, GetAvailableDevices) {
    auto devices = engine_utils::get_available_devices();
    EXPECT_GT(devices.size(), 0);
    
    for (const auto& device : devices) {
        EXPECT_FALSE(device.empty());
        // Should contain device index and name
        EXPECT_NE(device.find("["), std::string::npos);
        EXPECT_NE(device.find("]"), std::string::npos);
    }
}

TEST_F(ResearchEngineTest, SelectBestDevice) {
    int device = engine_utils::select_best_device();
    EXPECT_GE(device, 0);
    
    int device_count = 0;
    cudaGetDeviceCount(&device_count);
    EXPECT_LT(device, device_count);
}

TEST_F(ResearchEngineTest, ConfigValidation) {
    std::string error_msg;
    
    // Valid config
    EXPECT_TRUE(engine_utils::validate_config(config_, error_msg));
    EXPECT_TRUE(error_msg.empty());
    
    // Invalid nfft (not power of 2)
    EngineConfig bad_config = config_;
    bad_config.nfft = 1000;
    EXPECT_FALSE(engine_utils::validate_config(bad_config, error_msg));
    EXPECT_FALSE(error_msg.empty());
    
    // Invalid batch
    bad_config = config_;
    bad_config.batch = 0;
    EXPECT_FALSE(engine_utils::validate_config(bad_config, error_msg));
    
    // Invalid overlap
    bad_config = config_;
    bad_config.overlap = 1.5f;
    EXPECT_FALSE(engine_utils::validate_config(bad_config, error_msg));
    
    // Invalid stream count
    bad_config = config_;
    bad_config.stream_count = 0;
    EXPECT_FALSE(engine_utils::validate_config(bad_config, error_msg));
}

TEST_F(ResearchEngineTest, MemoryEstimation) {
    size_t estimated = engine_utils::estimate_memory_usage(config_);
    
    // Should be reasonable (> 1KB, < 1GB for typical config)
    EXPECT_GT(estimated, 1024);
    EXPECT_LT(estimated, 1024 * 1024 * 1024);
    
    // Larger config should use more memory
    EngineConfig large_config = config_;
    large_config.nfft = 4096;
    large_config.batch = 8;
    
    size_t large_estimated = engine_utils::estimate_memory_usage(large_config);
    EXPECT_GT(large_estimated, estimated);
}