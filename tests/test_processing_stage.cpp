// tests/test_processing_stage.cpp
#include <gtest/gtest.h>
#include "ionosense/processing_stage.hpp"
#include "ionosense/cuda_wrappers.hpp"
#include <vector>
#include <cmath>
#include <complex>
#include <numeric>
#include <algorithm>

using namespace ionosense;

class ProcessingStageTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Ensure CUDA is available
        int device_count = 0;
        cudaError_t err = cudaGetDeviceCount(&device_count);
        if (err != cudaSuccess || device_count == 0) {
            GTEST_SKIP() << "No CUDA devices available";
        }
        
        // Create stream for testing
        stream_ = std::make_unique<CudaStream>();
        
        // Default configuration
        config_.nfft = 256;
        config_.batch = 2;
        config_.overlap = 0.5f;
        config_.sample_rate_hz = 48000;
    }
    
    void TearDown() override {
        if (stream_) {
            stream_->synchronize();
        }
    }
    
    // Helper to generate test signal
    std::vector<float> generate_test_signal(int size, float frequency = 1.0f) {
        std::vector<float> signal(size);
        const float pi = 3.14159265358979323846f;
        for (int i = 0; i < size; ++i) {
            signal[i] = std::sin(2.0f * pi * frequency * i / size);
        }
        return signal;
    }
    
    // Helper to verify Hann window
    bool verify_hann_window(const std::vector<float>& windowed, 
                           const std::vector<float>& original,
                           int size) {
        const float pi = 3.14159265358979323846f;
        const float tolerance = 1e-5f;
        
        for (int i = 0; i < size; ++i) {
            float expected_window = 0.5f * (1.0f - std::cos(2.0f * pi * i / (size - 1)));
            float expected = original[i] * expected_window;
            if (std::abs(windowed[i] - expected) > tolerance) {
                return false;
            }
        }
        return true;
    }

protected:
    std::unique_ptr<CudaStream> stream_;
    StageConfig config_;
};

// ============================================================================
// WindowStage Tests
// ============================================================================

TEST_F(ProcessingStageTest, WindowStageInitialization) {
    WindowStage stage;
    EXPECT_NO_THROW(stage.initialize(config_, stream_->get()));
    EXPECT_EQ(stage.name(), "WindowStage");
    EXPECT_TRUE(stage.supports_inplace());
    EXPECT_GT(stage.get_workspace_size(), 0);
}

TEST_F(ProcessingStageTest, WindowStageProcess) {
    WindowStage stage;
    stage.initialize(config_, stream_->get());
    
    // Generate test signal
    const size_t total_samples = config_.nfft * config_.batch;
    auto host_input = generate_test_signal(total_samples);
    
    // Allocate device buffers
    DeviceBuffer<float> d_input(total_samples);
    DeviceBuffer<float> d_output(total_samples);
    
    // Copy to device
    d_input.copy_from_host(host_input.data(), total_samples, stream_->get());
    
    // Process
    EXPECT_NO_THROW(stage.process(
        d_input.get(), d_output.get(), total_samples, stream_->get()
    ));
    
    // Copy back
    std::vector<float> host_output(total_samples);
    d_output.copy_to_host(host_output.data(), total_samples, stream_->get());
    stream_->synchronize();
    
    // Verify windowing was applied (output should be different from input)
    bool all_same = true;
    for (size_t i = 0; i < total_samples; ++i) {
        if (std::abs(host_output[i] - host_input[i]) > 1e-6f) {
            all_same = false;
            break;
        }
    }
    EXPECT_FALSE(all_same);
    
    // Verify window shape (edges should be near zero)
    EXPECT_NEAR(host_output[0], 0.0f, 1e-3f);
    EXPECT_NEAR(host_output[config_.nfft - 1], 0.0f, 1e-3f);
}

TEST_F(ProcessingStageTest, WindowStageInPlace) {
    WindowStage stage;
    stage.initialize(config_, stream_->get());
    
    const size_t total_samples = config_.nfft * config_.batch;
    auto host_data = generate_test_signal(total_samples);
    
    DeviceBuffer<float> d_data(total_samples);
    d_data.copy_from_host(host_data.data(), total_samples, stream_->get());
    
    // Process in-place
    EXPECT_NO_THROW(stage.process(
        d_data.get(), d_data.get(), total_samples, stream_->get()
    ));
    
    std::vector<float> result(total_samples);
    d_data.copy_to_host(result.data(), total_samples, stream_->get());
    stream_->synchronize();
    
    // Verify windowing was applied
    EXPECT_NEAR(result[0], 0.0f, 1e-3f);
    EXPECT_NEAR(result[config_.nfft - 1], 0.0f, 1e-3f);
}

// ============================================================================
// FFTStage Tests
// ============================================================================

TEST_F(ProcessingStageTest, FFTStageInitialization) {
    FFTStage stage;
    EXPECT_NO_THROW(stage.initialize(config_, stream_->get()));
    EXPECT_EQ(stage.name(), "FFTStage");
    EXPECT_TRUE(stage.supports_inplace());
    EXPECT_GE(stage.get_workspace_size(), 0);
}

TEST_F(ProcessingStageTest, FFTStageProcess) {
    FFTStage stage;
    stage.initialize(config_, stream_->get());
    
    // Create DC signal (all ones)
    const size_t total_samples = config_.nfft * config_.batch;
    std::vector<float> host_input(total_samples, 1.0f);
    
    DeviceBuffer<float> d_input(total_samples);
    DeviceBuffer<float2> d_output(total_samples);
    
    d_input.copy_from_host(host_input.data(), total_samples, stream_->get());
    
    // Process
    EXPECT_NO_THROW(stage.process(
        d_input.get(), d_output.get(), total_samples, stream_->get()
    ));
    
    // Copy back complex output
    std::vector<float2> host_output(total_samples);
    d_output.copy_to_host(host_output.data(), total_samples, stream_->get());
    stream_->synchronize();
    
    // For DC signal, first bin should have large magnitude
    float dc_magnitude = std::sqrt(host_output[0].x * host_output[0].x + 
                                  host_output[0].y * host_output[0].y);
    EXPECT_GT(dc_magnitude, config_.nfft * 0.9f);  // Should be close to nfft
}

TEST_F(ProcessingStageTest, FFTStageSinusoid) {
    FFTStage stage;
    stage.initialize(config_, stream_->get());
    
    // Generate sinusoid at specific frequency bin
    const int freq_bin = 10;
    const size_t total_samples = config_.nfft * config_.batch;
    std::vector<float> host_input(total_samples);
    
    const float pi = 3.14159265358979323846f;
    for (size_t ch = 0; ch < config_.batch; ++ch) {
        for (size_t i = 0; i < config_.nfft; ++i) {
            host_input[ch * config_.nfft + i] = 
                std::cos(2.0f * pi * freq_bin * i / config_.nfft);
        }
    }
    
    DeviceBuffer<float> d_input(total_samples);
    const size_t complex_size = (config_.nfft / 2 + 1) * config_.batch;
    DeviceBuffer<float2> d_output(total_samples);
    
    d_input.copy_from_host(host_input.data(), total_samples, stream_->get());
    
    // Process
    stage.process(d_input.get(), d_output.get(), total_samples, stream_->get());
    
    std::vector<float2> host_output(complex_size);
    d_output.copy_to_host(host_output.data(), host_output.size(), stream_->get());
    stream_->synchronize();
    
    // Check that energy is concentrated at the expected frequency bin
    for (size_t ch = 0; ch < config_.batch; ++ch) {
        float max_magnitude = 0.0f;
        int max_bin = -1;
        
        // CHANGE THIS LOOP BOUNDARY
        for (size_t bin = 0; bin < config_.nfft / 2 + 1; ++bin) {
            // CHANGE THE INDEXING
            float2 val = host_output[ch * (config_.nfft / 2 + 1) + bin];
            float mag = std::sqrt(val.x * val.x + val.y * val.y);
            if (mag > max_magnitude) {
                max_magnitude = mag;
                max_bin = bin;
            }
        }
        
        // The check for R2C is simpler - no negative frequency component
        EXPECT_EQ(max_bin, freq_bin);
    }
}

// ============================================================================
// MagnitudeStage Tests
// ============================================================================

TEST_F(ProcessingStageTest, MagnitudeStageInitialization) {
    MagnitudeStage stage;
    EXPECT_NO_THROW(stage.initialize(config_, stream_->get()));
    EXPECT_EQ(stage.name(), "MagnitudeStage");
    EXPECT_FALSE(stage.supports_inplace());
    EXPECT_EQ(stage.get_workspace_size(), 0);
}

TEST_F(ProcessingStageTest, MagnitudeStageProcess) {
    MagnitudeStage stage;
    stage.initialize(config_, stream_->get());
    
    // Create complex test data (3+4i = magnitude 5)
    const size_t num_bins = config_.nfft / 2 + 1;
    const size_t total_complex = num_bins * config_.batch;
    std::vector<float2> host_input(total_complex);
    
    for (size_t i = 0; i < total_complex; ++i) {
        host_input[i] = {3.0f, 4.0f};  // 3+4i
    }
    
    DeviceBuffer<float2> d_input(total_complex);
    DeviceBuffer<float> d_output(total_complex);
    
    d_input.copy_from_host(host_input.data(), total_complex, stream_->get());
    
    // Process
    EXPECT_NO_THROW(stage.process(
        d_input.get(), d_output.get(), total_complex, stream_->get()
    ));
    
    std::vector<float> host_output(total_complex);
    d_output.copy_to_host(host_output.data(), total_complex, stream_->get());
    stream_->synchronize();
    
    // Verify magnitude calculation
    for (size_t i = 0; i < total_complex; ++i) {
        EXPECT_NEAR(host_output[i], 5.0f, 1e-5f);  // sqrt(3^2 + 4^2) = 5
    }
}

TEST_F(ProcessingStageTest, MagnitudeStageScaling) {
    config_.scale_policy = StageConfig::ScalePolicy::ONE_OVER_N;
    
    MagnitudeStage stage;
    stage.initialize(config_, stream_->get());
    
    const size_t num_bins = config_.nfft / 2 + 1;
    const size_t total_complex = num_bins * config_.batch;
    std::vector<float2> host_input(total_complex);
    
    // Create unit complex values
    for (size_t i = 0; i < total_complex; ++i) {
        host_input[i] = {float(config_.nfft), 0.0f};
    }
    
    DeviceBuffer<float2> d_input(total_complex);
    DeviceBuffer<float> d_output(total_complex);
    
    d_input.copy_from_host(host_input.data(), total_complex, stream_->get());
    stage.process(d_input.get(), d_output.get(), total_complex, stream_->get());
    
    std::vector<float> host_output(total_complex);
    d_output.copy_to_host(host_output.data(), total_complex, stream_->get());
    stream_->synchronize();
    
    // With 1/N scaling, output should be 1.0
    for (size_t i = 0; i < total_complex; ++i) {
        EXPECT_NEAR(host_output[i], 1.0f, 1e-5f);
    }
}

// ============================================================================
// StageFactory Tests
// ============================================================================

TEST_F(ProcessingStageTest, StageFactoryCreate) {
    auto window_stage = StageFactory::create(StageFactory::StageType::WINDOW);
    EXPECT_NE(window_stage, nullptr);
    EXPECT_EQ(window_stage->name(), "WindowStage");
    
    auto fft_stage = StageFactory::create(StageFactory::StageType::FFT);
    EXPECT_NE(fft_stage, nullptr);
    EXPECT_EQ(fft_stage->name(), "FFTStage");
    
    auto mag_stage = StageFactory::create(StageFactory::StageType::MAGNITUDE);
    EXPECT_NE(mag_stage, nullptr);
    EXPECT_EQ(mag_stage->name(), "MagnitudeStage");
}

TEST_F(ProcessingStageTest, StageFactoryDefaultPipeline) {
    auto stages = StageFactory::create_default_pipeline();
    
    EXPECT_EQ(stages.size(), 3);
    EXPECT_EQ(stages[0]->name(), "WindowStage");
    EXPECT_EQ(stages[1]->name(), "FFTStage");
    EXPECT_EQ(stages[2]->name(), "MagnitudeStage");
}

// ============================================================================
// Window Utils Tests
// ============================================================================

TEST_F(ProcessingStageTest, WindowUtilsHannGeneration) {
    const int size = 64;
    std::vector<float> window(size);
    
    window_utils::generate_hann_window(window.data(), size, false);
    
    // Verify Hann window properties
    const float pi = 3.14159265358979323846f;
    for (int i = 0; i < size; ++i) {
        float expected = 0.5f * (1.0f - std::cos(2.0f * pi * i / (size - 1)));
        EXPECT_NEAR(window[i], expected, 1e-5f);
    }
    
    // Check symmetry
    for (int i = 0; i < size / 2; ++i) {
        EXPECT_NEAR(window[i], window[size - 1 - i], 1e-6f);
    }
    
    // Check edges
    EXPECT_NEAR(window[0], 0.0f, 1e-6f);
    EXPECT_NEAR(window[size - 1], 0.0f, 1e-6f);
    
    // Check center
    EXPECT_NEAR(window[size / 2], 1.0f, 0.1f);
}

TEST_F(ProcessingStageTest, WindowUtilsNormalization) {
    const int size = 128;
    std::vector<float> window(size, 1.0f);  // All ones
    
    window_utils::normalize_window(window.data(), size, StageConfig::WindowNorm::UNITY);
    
    // After unity normalization, average should be 1.0
    float sum = std::accumulate(window.begin(), window.end(), 0.0f);
    EXPECT_NEAR(sum / size, 1.0f, 1e-5f);
}

// ============================================================================
// Integration Test
// ============================================================================

TEST_F(ProcessingStageTest, FullPipelineIntegration) {
    // Create all stages
    WindowStage window_stage;
    FFTStage fft_stage;
    MagnitudeStage mag_stage;
    
    // Initialize
    window_stage.initialize(config_, stream_->get());
    fft_stage.initialize(config_, stream_->get());
    mag_stage.initialize(config_, stream_->get());
    
    // Generate test signal with known frequency
    const size_t total_samples = config_.nfft * config_.batch;
    const int test_freq_bin = 8;
    std::vector<float> host_input(total_samples);
    
    const float pi = 3.14159265358979323846f;
    for (size_t ch = 0; ch < config_.batch; ++ch) {
        for (size_t i = 0; i < config_.nfft; ++i) {
            host_input[ch * config_.nfft + i] = 
                std::sin(2.0f * pi * test_freq_bin * i / config_.nfft);
        }
    }
    
    // Allocate buffers
    DeviceBuffer<float> d_input(total_samples);
    DeviceBuffer<float> d_windowed(total_samples);
    DeviceBuffer<float2> d_fft(total_samples);
    DeviceBuffer<float> d_magnitude((config_.nfft / 2 + 1) * config_.batch);
    
    // Upload input
    d_input.copy_from_host(host_input.data(), total_samples, stream_->get());
    
    // Process through pipeline
    window_stage.process(d_input.get(), d_windowed.get(), total_samples, stream_->get());
    fft_stage.process(d_windowed.get(), d_fft.get(), total_samples, stream_->get());
    mag_stage.process(d_fft.get(), d_magnitude.get(), 
                     (config_.nfft / 2 + 1) * config_.batch, stream_->get());
    
    // Get results
    std::vector<float> magnitude((config_.nfft / 2 + 1) * config_.batch);
    d_magnitude.copy_to_host(magnitude.data(), magnitude.size(), stream_->get());
    stream_->synchronize();
    
    // Verify peak is at expected frequency
    for (size_t ch = 0; ch < config_.batch; ++ch) {
        float max_mag = 0.0f;
        int peak_bin = -1;
        
        for (size_t bin = 0; bin <= config_.nfft / 2; ++bin) {
            float mag = magnitude[ch * (config_.nfft / 2 + 1) + bin];
            if (mag > max_mag) {
                max_mag = mag;
                peak_bin = bin;
            }
        }
        
        // Peak should be at test frequency bin
        EXPECT_EQ(peak_bin, test_freq_bin);
        EXPECT_GT(max_mag, 10.0f);  // Should have significant magnitude
    }
}