/**
 * @file test_cuda_wrappers.cpp
 * @version 1.0
 * @date 2025-09-01
 * @author [Kevin Rahsaz]
 *
 * @brief Unit tests for the CUDA RAII wrappers.
 *
 * This test suite validates the functionality and safety of the RAII wrappers
 * for fundamental CUDA objects like streams, events, and buffers. It uses the
 * Google Test framework.
 */

#include <gtest/gtest.h>

#include <numeric>
#include <vector>

#include "sigtekx/core/cuda_wrappers.hpp"

using namespace sigtekx;

/**
 * @class CudaWrappersTest
 * @brief Test fixture for CUDA wrapper tests.
 *
 * This fixture ensures that tests are skipped if no CUDA-capable device is
 * present, preventing test failures in environments without GPUs.
 */
class CudaWrappersTest : public ::testing::Test {
 protected:
  /**
   * @brief Skips the test fixture if no CUDA devices are available.
   */
  void SetUp() override {
    int device_count = 0;
    cudaError_t err = cudaGetDeviceCount(&device_count);
    if (err != cudaSuccess || device_count == 0) {
      GTEST_SKIP() << "No CUDA devices available for testing.";
    }
  }
};

// ============================================================================
// CudaStream Tests
// ============================================================================

/**
 * @test CudaWrappersTest.CudaStreamCreation
 * @brief Verifies that a CudaStream object is created, is valid, and can be
 * synchronized.
 */
TEST_F(CudaWrappersTest, CudaStreamCreation) {
  CudaStream stream;
  EXPECT_NE(stream.get(), nullptr);
  EXPECT_NO_THROW(stream.synchronize());
  EXPECT_TRUE(stream.query());
}

/**
 * @test CudaWrappersTest.CudaStreamMove
 * @brief Validates the move constructor and move assignment operator for
 * CudaStream.
 */
TEST_F(CudaWrappersTest, CudaStreamMove) {
  CudaStream stream1;
  cudaStream_t original_handle = stream1.get();

  // Test move construction
  CudaStream stream2(std::move(stream1));
  EXPECT_EQ(stream2.get(), original_handle);
  EXPECT_EQ(stream1.get(), nullptr);

  // Test move assignment
  CudaStream stream3;
  stream3 = std::move(stream2);
  EXPECT_EQ(stream3.get(), original_handle);
  EXPECT_EQ(stream2.get(), nullptr);
}

// ============================================================================
// CudaEvent Tests
// ============================================================================

/**
 * @test CudaWrappersTest.CudaEventCreation
 * @brief Verifies that a CudaEvent object is created, can be recorded, and
 * synchronized.
 */
TEST_F(CudaWrappersTest, CudaEventCreation) {
  CudaEvent event;
  EXPECT_NE(event.get(), nullptr);
  EXPECT_NO_THROW(event.record());
  EXPECT_NO_THROW(event.synchronize());
  EXPECT_TRUE(event.query());
}

/**
 * @test CudaWrappersTest.CudaEventTiming
 * @brief Checks the elapsed time measurement between two events.
 */
TEST_F(CudaWrappersTest, CudaEventTiming) {
  CudaEvent start(0);  // Enable timing
  CudaEvent end(0);

  start.record();
  // A minimal delay or dummy operation could be here.
  end.record();
  end.synchronize();

  float elapsed_ms = end.elapsed_ms(start);
  EXPECT_GE(elapsed_ms, 0.0f);
}

// ============================================================================
// DeviceBuffer Tests
// ============================================================================

/**
 * @test CudaWrappersTest.DeviceBufferAllocation
 * @brief Validates that DeviceBuffer allocates the correct amount of memory.
 */
TEST_F(CudaWrappersTest, DeviceBufferAllocation) {
  const size_t count = 1024;
  DeviceBuffer<float> buffer(count);

  EXPECT_NE(buffer.get(), nullptr);
  EXPECT_EQ(buffer.size(), count);
  EXPECT_EQ(buffer.bytes(), count * sizeof(float));
}

/**
 * @test CudaWrappersTest.DeviceBufferMemset
 * @brief Verifies the memset functionality of the DeviceBuffer.
 */
TEST_F(CudaWrappersTest, DeviceBufferMemset) {
  const size_t count = 256;
  DeviceBuffer<int> buffer(count);

  buffer.memset(0);

  std::vector<int> host_data(count, -1);  // Fill with non-zero
  buffer.copy_to_host(host_data.data(), count);

  for (int val : host_data) {
    EXPECT_EQ(val, 0);
  }
}

/**
 * @test CudaWrappersTest.DeviceBufferCopy
 * @brief Tests asynchronous host-to-device and device-to-host copies.
 */
TEST_F(CudaWrappersTest, DeviceBufferCopy) {
  const size_t count = 512;
  std::vector<float> host_input(count);
  std::iota(host_input.begin(), host_input.end(), 0.0f);

  DeviceBuffer<float> buffer(count);
  buffer.copy_from_host(host_input.data(), count);

  std::vector<float> host_output(count);
  buffer.copy_to_host(host_output.data(), count);

  // Explicit synchronization needed as copies are async.
  cudaDeviceSynchronize();

  EXPECT_EQ(host_input, host_output);
}

/**
 * @test CudaWrappersTest.DeviceBufferResize
 * @brief Checks if resizing the buffer works correctly.
 */
TEST_F(CudaWrappersTest, DeviceBufferResize) {
  DeviceBuffer<char> buffer(100);
  EXPECT_EQ(buffer.size(), 100);

  buffer.resize(200);
  EXPECT_EQ(buffer.size(), 200);

  buffer.resize(0);
  EXPECT_EQ(buffer.size(), 0);
  EXPECT_EQ(buffer.get(), nullptr);
}

// ============================================================================
// PinnedHostBuffer Tests
// ============================================================================

/**
 * @test CudaWrappersTest.PinnedHostBufferAllocation
 * @brief Verifies allocation of pinned (page-locked) host memory.
 */
TEST_F(CudaWrappersTest, PinnedHostBufferAllocation) {
  const size_t count = 1024;
  PinnedHostBuffer<int> buffer(count);

  EXPECT_NE(buffer.get(), nullptr);
  EXPECT_EQ(buffer.size(), count);
}

/**
 * @test CudaWrappersTest.PinnedHostBufferAccess
 * @brief Tests direct element access on a pinned host buffer. This test was
 * restored.
 */
TEST_F(CudaWrappersTest, PinnedHostBufferAccess) {
  const size_t size = 256;
  PinnedHostBuffer<int> buffer(size);

  // Write values
  for (size_t i = 0; i < size; ++i) {
    buffer[i] = static_cast<int>(i);
  }

  // Read and verify
  for (size_t i = 0; i < size; ++i) {
    EXPECT_EQ(buffer[i], static_cast<int>(i));
  }
}

/**
 * @test CudaWrappersTest.PinnedHostBufferMemset
 * @brief Verifies memset functionality for pinned host buffers. This test was
 * restored.
 */
TEST_F(CudaWrappersTest, PinnedHostBufferMemset) {
  const size_t size = 128;
  PinnedHostBuffer<float> buffer(size);

  // Fill with non-zero values
  for (size_t i = 0; i < size; ++i) {
    buffer[i] = 1.0f;
  }

  // Memset to zero
  buffer.memset(0);

  // Verify
  for (size_t i = 0; i < size; ++i) {
    EXPECT_EQ(buffer[i], 0.0f);
  }
}

// ============================================================================
// CufftPlan Tests
// ============================================================================

/**
 * @test CudaWrappersTest.CufftPlanCreation
 * @brief Verifies the creation of a simple cuFFT plan.
 */
TEST_F(CudaWrappersTest, CufftPlanCreation) {
  CufftPlan plan;
  CudaStream stream;

  const int nfft = 256;
  const int batch = 2;
  int n[] = {nfft};

  EXPECT_NO_THROW(plan.create_plan_many(1, n, nullptr, 1, nfft, nullptr, 1,
                                        nfft, CUFFT_C2C, batch, stream.get()));
  EXPECT_NE(plan.get(), 0);
  EXPECT_GE(plan.work_size(), 0);
}

/**
 * @test CudaWrappersTest.CufftPlanExecute
 * @brief Tests the execution of a real-to-complex FFT plan.
 */
TEST_F(CudaWrappersTest, CufftPlanExecute) {
  CufftPlan plan;
  CudaStream stream;

  const int nfft = 128;
  const int batch = 1;
  const int complex_size = nfft / 2 + 1;
  int n[] = {nfft};

  plan.create_plan_many(1, n, nullptr, 1, nfft, nullptr, 1, complex_size,
                        CUFFT_R2C, batch, stream.get());

  DeviceBuffer<float> real_data(nfft * batch);
  DeviceBuffer<float2> complex_data(complex_size * batch);

  std::vector<float> host_data(nfft * batch, 0.0f);
  host_data[0] = 1.0f;  // Impulse signal

  real_data.copy_from_host(host_data.data(), host_data.size(), stream.get());

  EXPECT_NO_THROW(
      plan.exec_r2c(reinterpret_cast<cufftReal*>(real_data.get()),
                    reinterpret_cast<cufftComplex*>(complex_data.get())));
  stream.synchronize();
}

// ============================================================================
// Error Handling Tests
// ============================================================================

/**
 * @test CudaWrappersTest.ErrorHandling
 * @brief Verifies that the CUDA and cuFFT exception wrappers work correctly.
 */
TEST_F(CudaWrappersTest, ErrorHandling) {
  // Test that an invalid CUDA call throws the correct exception.
  try {
    IONO_CUDA_CHECK(cudaSetDevice(9999));  // Invalid device ID
    FAIL() << "Expected CudaException was not thrown.";
  } catch (const CudaException& e) {
    EXPECT_EQ(e.error(), cudaErrorInvalidDevice);
  }

  // Test that an invalid cuFFT call throws the correct exception.
  CufftPlan plan;
  try {
    int n[] = {-1};  // Invalid FFT size
    plan.create_plan_many(1, n, nullptr, 1, 1, nullptr, 1, 1, CUFFT_C2C, 1, 0);
    FAIL() << "Expected CufftException was not thrown.";
  } catch (const CufftException& e) {
    EXPECT_EQ(e.result(), CUFFT_INVALID_SIZE);
  }
}

// ============================================================================
// Interoperability Tests
// ============================================================================

/**
 * @test CudaWrappersTest.StreamEventSynchronization
 * @brief Tests synchronization between two different streams using a CudaEvent.
 */
TEST_F(CudaWrappersTest, StreamEventSynchronization) {
  CudaStream stream1, stream2;
  CudaEvent event;

  const size_t size = 1024;
  DeviceBuffer<float> buffer1(size), buffer2(size);

  std::vector<float> host_data(size, 1.0f);

  // Operation in stream 1, followed by event record
  buffer1.copy_from_host(host_data.data(), size, stream1.get());
  event.record(stream1.get());

  // Stream 2 waits for the event from stream 1
  IONO_CUDA_CHECK(cudaStreamWaitEvent(stream2.get(), event.get(), 0));

  // Operation in stream 2 can now proceed
  IONO_CUDA_CHECK(cudaMemcpyAsync(buffer2.get(), buffer1.get(), buffer1.bytes(),
                                  cudaMemcpyDeviceToDevice, stream2.get()));

  stream2.synchronize();

  std::vector<float> output(size, 0.0f);
  buffer2.copy_to_host(output.data(), size);
  stream2.synchronize();

  EXPECT_EQ(host_data, output);
}
