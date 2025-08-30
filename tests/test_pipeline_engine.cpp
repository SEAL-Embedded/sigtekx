/**
 * @file test_pipeline_engine.cpp
 * @brief Unit tests for the modern PipelineEngine.
 *
 * These tests validate the core functionality of the pipeline orchestrator,
 * including its lifecycle (prepare, execute, sync), multi-stream handling,
 * and statistics collection.
 */

#include <gtest/gtest.h>
#include "ionosense/pipeline_engine.hpp"
#include <vector>
#include <numeric>

using namespace ionosense;

// Test fixture for PipelineEngine tests
class PipelineEngineTest : public ::testing::Test {
protected:
    void SetUp() override {
        // A common configuration for most tests
        builder = std::make_unique<PipelineBuilder>();
        builder->with_fft(1024, 4)
               .with_streams(3)
               .with_graphs(true)
               .with_profiling(true);
    }

    std::unique_ptr<PipelineBuilder> builder;
};

TEST_F(PipelineEngineTest, ConstructionAndConfiguration) {
    auto engine = builder->build();
    ASSERT_NE(engine, nullptr);
    EXPECT_EQ(engine->config().num_streams, 3);
    EXPECT_TRUE(engine->config().use_graphs);
    EXPECT_TRUE(engine->config().enable_profiling);
    ASSERT_NE(engine->stage(), nullptr);
    EXPECT_EQ(engine->stage()->name(), "FFT");
}

TEST_F(PipelineEngineTest, PrepareStateChange) {
    auto engine = builder->build();
    ASSERT_FALSE(engine->is_prepared());
    engine->prepare();
    ASSERT_TRUE(engine->is_prepared());
    // Calling prepare again should throw a state error
    EXPECT_THROW(engine->prepare(), cuda::StateError);
}

TEST_F(PipelineEngineTest, ExecuteBeforePrepare) {
    auto engine = builder->build();
    // Executing before preparing should throw a state error
    EXPECT_THROW(engine->execute_async(), cuda::StateError);
}

TEST_F(PipelineEngineTest, BasicExecutionAndSync) {
    auto engine = builder->build();
    engine->prepare();

    const int stream_idx = 0;
    auto* input_buf = engine->get_input_buffer(stream_idx);
    ASSERT_NE(input_buf, nullptr);

    // Fill with some data
    std::vector<float> test_data(engine->stage()->input_size());
    std::iota(test_data.begin(), test_data.end(), 1.0f);
    std::copy(test_data.begin(), test_data.end(), input_buf);

    ASSERT_NO_THROW(engine->execute_async(stream_idx));
    ASSERT_NO_THROW(engine->sync_stream(stream_idx));

    // Simple check on output
    auto* output_buf = engine->get_output_buffer(stream_idx);
    ASSERT_NE(output_buf, nullptr);
    // A non-zero input should produce some non-zero output
    double sum = 0;
    for(size_t i=0; i < engine->stage()->output_size(); ++i) {
        sum += output_buf[i];
    }
    EXPECT_GT(sum, 0.0);
}

TEST_F(PipelineEngineTest, StatisticsUpdate) {
    auto engine = builder->build();
    engine->prepare();

    EXPECT_EQ(engine->stats().total_executions, 0);

    int stream_idx = engine->execute_async();
    engine->sync_stream(stream_idx);

    const auto& stats = engine->stats();
    EXPECT_EQ(stats.total_executions, 1);
    EXPECT_GT(stats.avg_latency_ms, 0.0);
    EXPECT_LE(stats.min_latency_ms, stats.max_latency_ms);

    engine->reset_stats();
    EXPECT_EQ(engine->stats().total_executions, 0);
}

TEST_F(PipelineEngineTest, AutoStreamCycling) {
    auto engine = builder->build();
    engine->prepare();
    
    int idx0 = engine->execute_async();
    int idx1 = engine->execute_async();
    int idx2 = engine->execute_async();
    int idx3 = engine->execute_async();

    EXPECT_EQ(idx0, 0);
    EXPECT_EQ(idx1, 1);
    EXPECT_EQ(idx2, 2);
    EXPECT_EQ(idx3, 0); // Wraps around
    engine->synchronize_all();
}

TEST_F(PipelineEngineTest, GraphToggle) {
    auto engine = builder->with_graphs(false)->build();
    EXPECT_FALSE(engine->config().use_graphs);
    engine->prepare();
    // After prepare, enabling graphs should re-prepare/capture
    ASSERT_NO_THROW(engine->set_use_graphs(true));
    EXPECT_TRUE(engine->config().use_graphs);
}
