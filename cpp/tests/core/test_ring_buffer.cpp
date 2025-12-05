/**
 * @file test_ring_buffer.cpp
 * @version 0.9.4
 * @date 2025-10-23
 * @author [Kevin Rahsaz]
 *
 * @brief Unit tests for the RingBuffer class.
 *
 * Tests circular buffer operations including wraparound, STFT overlap
 * extraction, and error handling.
 */

#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "sigtekx/core/ring_buffer.hpp"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

using namespace sigtekx;

/**
 * @class RingBufferTest
 * @brief Test fixture for RingBuffer tests.
 */
class RingBufferTest : public ::testing::Test {
 protected:
  // Helper: Generate a ramp sequence for testing (1, 2, 3, ...)
  std::vector<float> generate_ramp(size_t size, float start = 1.0f) {
    std::vector<float> data(size);
    for (size_t i = 0; i < size; ++i) {
      data[i] = start + static_cast<float>(i);
    }
    return data;
  }

  // Helper: Generate sinusoid for realistic testing
  std::vector<float> generate_sinusoid(size_t size, float frequency) {
    std::vector<float> signal(size);
    for (size_t i = 0; i < size; ++i) {
      signal[i] =
          std::sin(2.0f * static_cast<float>(M_PI) * frequency * i / size);
    }
    return signal;
  }
};

// ============================================================================
//  Construction and Basic Operations
// ============================================================================

TEST_F(RingBufferTest, Construction) {
  EXPECT_NO_THROW(RingBuffer<float> buffer(1024));

  RingBuffer<float> buffer(512);
  EXPECT_EQ(buffer.capacity(), 512);
  EXPECT_EQ(buffer.available(), 0);
  EXPECT_TRUE(buffer.empty());
  EXPECT_FALSE(buffer.full());
}

TEST_F(RingBufferTest, ConstructionZeroCapacityThrows) {
  EXPECT_THROW(RingBuffer<float> buffer(0), std::invalid_argument);
}

TEST_F(RingBufferTest, PushAndAvailable) {
  RingBuffer<float> buffer(1024);
  auto data = generate_ramp(256);

  buffer.push(data.data(), 256);
  EXPECT_EQ(buffer.available(), 256);
  EXPECT_FALSE(buffer.empty());
  EXPECT_FALSE(buffer.full());

  buffer.push(data.data(), 256);
  EXPECT_EQ(buffer.available(), 512);
}

TEST_F(RingBufferTest, PushUntilFull) {
  RingBuffer<float> buffer(512);
  auto data = generate_ramp(512);

  buffer.push(data.data(), 512);
  EXPECT_EQ(buffer.available(), 512);
  EXPECT_TRUE(buffer.full());
}

TEST_F(RingBufferTest, PushOverflowThrows) {
  RingBuffer<float> buffer(256);
  auto data = generate_ramp(512);

  EXPECT_THROW(buffer.push(data.data(), 512), std::overflow_error);
}

TEST_F(RingBufferTest, Reset) {
  RingBuffer<float> buffer(512);
  auto data = generate_ramp(256);

  buffer.push(data.data(), 256);
  EXPECT_EQ(buffer.available(), 256);

  buffer.reset();
  EXPECT_EQ(buffer.available(), 0);
  EXPECT_TRUE(buffer.empty());

  // Can push again after reset
  buffer.push(data.data(), 256);
  EXPECT_EQ(buffer.available(), 256);
}

// ============================================================================
//  Frame Extraction Tests
// ============================================================================

TEST_F(RingBufferTest, ExtractSingleFrame) {
  RingBuffer<float> buffer(1024);
  auto input = generate_ramp(512, 1.0f);  // 1, 2, 3, ..., 512

  buffer.push(input.data(), 512);
  EXPECT_TRUE(buffer.can_extract_frame(256));

  std::vector<float> output(256);
  buffer.extract_frame(output.data(), 256);

  // Verify extracted data (first 256 elements)
  for (size_t i = 0; i < 256; ++i) {
    EXPECT_FLOAT_EQ(output[i], static_cast<float>(i + 1));
  }

  // Available count should not change (extract doesn't advance)
  EXPECT_EQ(buffer.available(), 512);
}

TEST_F(RingBufferTest, ExtractFrameUnderflowThrows) {
  RingBuffer<float> buffer(1024);
  auto input = generate_ramp(256);

  buffer.push(input.data(), 256);

  std::vector<float> output(512);
  EXPECT_THROW(buffer.extract_frame(output.data(), 512), std::underflow_error);
}

TEST_F(RingBufferTest, AdvanceReadPointer) {
  RingBuffer<float> buffer(1024);
  auto input = generate_ramp(512, 1.0f);

  buffer.push(input.data(), 512);
  EXPECT_EQ(buffer.available(), 512);

  // Advance by 256 samples
  buffer.advance(256);
  EXPECT_EQ(buffer.available(), 256);

  // Extract should now get samples [257:513)
  std::vector<float> output(256);
  buffer.extract_frame(output.data(), 256);
  for (size_t i = 0; i < 256; ++i) {
    EXPECT_FLOAT_EQ(output[i], static_cast<float>(257 + i));
  }
}

TEST_F(RingBufferTest, AdvanceBeyondAvailableThrows) {
  RingBuffer<float> buffer(512);
  auto input = generate_ramp(256);

  buffer.push(input.data(), 256);
  EXPECT_THROW(buffer.advance(512), std::underflow_error);
}

// ============================================================================
//  Wraparound Tests
// ============================================================================

TEST_F(RingBufferTest, PushWithWraparound) {
  RingBuffer<float> buffer(512);

  // Push 400 samples
  auto data1 = generate_ramp(400, 1.0f);  // 1..400
  buffer.push(data1.data(), 400);
  EXPECT_EQ(buffer.available(), 400);

  // Advance by 300 (consume most)
  buffer.advance(300);
  EXPECT_EQ(buffer.available(), 100);

  // Push 400 more (will wrap around)
  auto data2 = generate_ramp(400, 401.0f);  // 401..800
  buffer.push(data2.data(), 400);
  EXPECT_EQ(buffer.available(), 500);

  // Extract and verify (should get samples 301..400, then 401..500)
  std::vector<float> output(200);
  buffer.extract_frame(output.data(), 200);

  for (size_t i = 0; i < 100; ++i) {
    EXPECT_FLOAT_EQ(output[i], static_cast<float>(301 + i));  // 301..400
  }
  for (size_t i = 100; i < 200; ++i) {
    EXPECT_FLOAT_EQ(output[i], static_cast<float>(301 + i));  // 401..500
  }
}

TEST_F(RingBufferTest, ExtractWithWraparound) {
  RingBuffer<float> buffer(512);

  // Fill buffer near end
  auto data1 = generate_ramp(450, 1.0f);
  buffer.push(data1.data(), 450);
  buffer.advance(400);  // Leave 50 samples near end

  // Push more to wrap
  auto data2 = generate_ramp(400, 451.0f);
  buffer.push(data2.data(), 400);
  EXPECT_EQ(buffer.available(), 450);

  // Extract frame that spans wraparound boundary
  std::vector<float> output(200);
  buffer.extract_frame(output.data(), 200);

  // First 50 should be from end of first push
  for (size_t i = 0; i < 50; ++i) {
    EXPECT_FLOAT_EQ(output[i], static_cast<float>(401 + i));
  }
  // Next 150 should be from start of second push
  for (size_t i = 50; i < 200; ++i) {
    EXPECT_FLOAT_EQ(output[i], static_cast<float>(451 + (i - 50)));
  }
}

// ============================================================================
//  STFT Batch Extraction Tests (Key Use Case)
// ============================================================================

TEST_F(RingBufferTest, ExtractBatchNoOverlap) {
  RingBuffer<float> buffer(2048);
  auto input = generate_ramp(1024, 1.0f);  // 1..1024

  buffer.push(input.data(), 1024);

  // Extract 2 frames, nfft=512, hop=512 (no overlap)
  size_t nfft = 512;
  size_t batch = 2;
  size_t hop_size = 512;

  std::vector<float> output(nfft * batch);
  buffer.extract_batch(output.data(), nfft, batch, hop_size);

  // Frame 0: samples [1:513)
  for (size_t i = 0; i < nfft; ++i) {
    EXPECT_FLOAT_EQ(output[i], static_cast<float>(1 + i));
  }

  // Frame 1: samples [513:1025)
  for (size_t i = 0; i < nfft; ++i) {
    EXPECT_FLOAT_EQ(output[nfft + i], static_cast<float>(513 + i));
  }
}

TEST_F(RingBufferTest, ExtractBatch50PercentOverlap) {
  RingBuffer<float> buffer(2048);
  auto input = generate_ramp(1536, 1.0f);  // 1..1536

  buffer.push(input.data(), 1536);

  // Extract 2 frames, nfft=1024, hop=512 (50% overlap)
  size_t nfft = 1024;
  size_t batch = 2;
  size_t hop_size = 512;

  std::vector<float> output(nfft * batch);
  buffer.extract_batch(output.data(), nfft, batch, hop_size);

  // Frame 0: samples [1:1025)
  for (size_t i = 0; i < nfft; ++i) {
    EXPECT_FLOAT_EQ(output[i], static_cast<float>(1 + i));
  }

  // Frame 1: samples [513:1537) - overlaps with frame 0
  for (size_t i = 0; i < nfft; ++i) {
    EXPECT_FLOAT_EQ(output[nfft + i], static_cast<float>(513 + i));
  }
}

TEST_F(RingBufferTest, ExtractBatch75PercentOverlap) {
  RingBuffer<float> buffer(2048);

  // For 75% overlap: hop_size = nfft * 0.25
  size_t nfft = 1024;
  size_t batch = 3;
  size_t hop_size = 256;  // 75% overlap

  // Total samples needed: nfft + (batch-1)*hop = 1024 + 2*256 = 1536
  auto input = generate_ramp(1536, 1.0f);
  buffer.push(input.data(), 1536);

  std::vector<float> output(nfft * batch);
  buffer.extract_batch(output.data(), nfft, batch, hop_size);

  // Frame 0: [1:1025)
  EXPECT_FLOAT_EQ(output[0], 1.0f);
  EXPECT_FLOAT_EQ(output[nfft - 1], 1024.0f);

  // Frame 1: [257:1281)
  EXPECT_FLOAT_EQ(output[nfft], 257.0f);
  EXPECT_FLOAT_EQ(output[2 * nfft - 1], 1280.0f);

  // Frame 2: [513:1537)
  EXPECT_FLOAT_EQ(output[2 * nfft], 513.0f);
  EXPECT_FLOAT_EQ(output[3 * nfft - 1], 1536.0f);
}

TEST_F(RingBufferTest, ExtractBatchUnderflowThrows) {
  RingBuffer<float> buffer(2048);
  auto input = generate_ramp(1000);

  buffer.push(input.data(), 1000);

  // Try to extract batch that needs 1536 samples (only 1000 available)
  size_t nfft = 1024;
  size_t batch = 2;
  size_t hop_size = 512;

  std::vector<float> output(nfft * batch);
  EXPECT_THROW(buffer.extract_batch(output.data(), nfft, batch, hop_size),
               std::underflow_error);
}

TEST_F(RingBufferTest, ExtractBatchWithWraparound) {
  RingBuffer<float> buffer(1024);

  // Push data near end of buffer
  auto data1 = generate_ramp(900, 1.0f);
  buffer.push(data1.data(), 900);
  buffer.advance(700);  // Leave 200 samples near end

  // Push more to wrap
  auto data2 = generate_ramp(600, 901.0f);
  buffer.push(data2.data(), 600);
  EXPECT_EQ(buffer.available(), 800);

  // Extract batch that spans wraparound (nfft=512, batch=2, hop=256)
  size_t nfft = 512;
  size_t batch = 2;
  size_t hop_size = 256;

  std::vector<float> output(nfft * batch);
  buffer.extract_batch(output.data(), nfft, batch, hop_size);

  // Frame 0 should span wraparound: 200 from end + 312 from start
  EXPECT_FLOAT_EQ(output[0], 701.0f);          // First of remaining 200
  EXPECT_FLOAT_EQ(output[199], 900.0f);        // Last of remaining 200
  EXPECT_FLOAT_EQ(output[200], 901.0f);        // First of new data
  EXPECT_FLOAT_EQ(output[nfft - 1], 1212.0f);  // 901 + 311

  // Frame 1 should be mostly in wrapped region
  EXPECT_FLOAT_EQ(output[nfft], 957.0f);  // 701 + 256
}

// ============================================================================
//  Streaming Use Case Simulation
// ============================================================================

TEST_F(RingBufferTest, StreamingProcessingLoop) {
  // Simulate continuous streaming: push 256 samples at a time,
  // extract and process 1024-sample frames with 50% overlap

  size_t nfft = 1024;
  size_t batch = 2;
  size_t hop_size = 512;  // 50% overlap
  size_t chunk_size = 256;

  RingBuffer<float> buffer(nfft + batch * hop_size);

  // Initial fill (need 1536 samples for first batch)
  size_t total_pushed = 0;
  while (!buffer.can_extract_frame(nfft + (batch - 1) * hop_size)) {
    auto chunk = generate_ramp(chunk_size, total_pushed + 1.0f);
    buffer.push(chunk.data(), chunk_size);
    total_pushed += chunk_size;
  }

  EXPECT_GE(buffer.available(), nfft + (batch - 1) * hop_size);

  // Process first batch
  std::vector<float> output(nfft * batch);
  buffer.extract_batch(output.data(), nfft, batch, hop_size);
  buffer.advance(hop_size * batch);  // Advance by 2*hop for 2 frames

  // Continue streaming
  for (int iter = 0; iter < 10; ++iter) {
    // Push more data
    auto chunk = generate_ramp(chunk_size, total_pushed + 1.0f);
    buffer.push(chunk.data(), chunk_size);
    total_pushed += chunk_size;

    // Extract if possible
    while (buffer.available() >= nfft + (batch - 1) * hop_size) {
      buffer.extract_batch(output.data(), nfft, batch, hop_size);
      buffer.advance(hop_size * batch);
    }
  }

  SUCCEED() << "Streaming loop completed without errors";
}

// ============================================================================
//  Sinusoid Correctness Test (Realistic Data)
// ============================================================================

TEST_F(RingBufferTest, SinusoidDataIntegrity) {
  // Verify that a sinusoid remains intact through wraparound
  RingBuffer<float> buffer(1024);

  // Generate long sinusoid
  auto signal = generate_sinusoid(2048, 10.0f);

  // Push in chunks with wraparound
  buffer.push(signal.data(), 800);
  buffer.advance(600);
  buffer.push(signal.data() + 800, 800);

  // Extract and verify continuity
  std::vector<float> extracted(1000);
  buffer.extract_frame(extracted.data(), 1000);

  // Should match signal[600:1600)
  for (size_t i = 0; i < 1000; ++i) {
    EXPECT_FLOAT_EQ(extracted[i], signal[600 + i]);
  }
}

// ============================================================================
//  Edge Cases
// ============================================================================

TEST_F(RingBufferTest, PushZeroSamples) {
  RingBuffer<float> buffer(512);
  auto data = generate_ramp(256);

  EXPECT_NO_THROW(buffer.push(data.data(), 0));
  EXPECT_EQ(buffer.available(), 0);
}

TEST_F(RingBufferTest, CanExtractWhenExactlyEnough) {
  RingBuffer<float> buffer(512);
  auto data = generate_ramp(256);

  buffer.push(data.data(), 256);
  EXPECT_TRUE(buffer.can_extract_frame(256));
  EXPECT_FALSE(buffer.can_extract_frame(257));
}

TEST_F(RingBufferTest, MultipleExtractionsWithoutAdvance) {
  RingBuffer<float> buffer(512);
  auto input = generate_ramp(256, 1.0f);

  buffer.push(input.data(), 256);

  std::vector<float> output1(256);
  std::vector<float> output2(256);

  buffer.extract_frame(output1.data(), 256);
  buffer.extract_frame(output2.data(), 256);

  // Both extractions should return same data
  for (size_t i = 0; i < 256; ++i) {
    EXPECT_FLOAT_EQ(output1[i], output2[i]);
  }
}
