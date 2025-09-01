// tests/test_cuda_wrappers.cpp
#include <gtest/gtest.h>
#include "ionosense/cuda_wrappers.hpp"
#include <vector>
#include <numeric>

using namespace ionosense;

class CudaWrappersTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Ensure CUDA is available
        int device_count = 0;
        cudaError_t err = cudaGetDeviceCount(&device_count);
        if (err != cudaSuccess || device_count == 0) {
            GTEST_SKIP() << "No CUDA devices available";
        }
    }
};

TEST_F(CudaWrappersTest, CudaStreamCreation) {
    CudaStream stream;
    EXPECT_NE(stream.get(), nullptr);
    
    // Test synchronization
    EXPECT_NO_THROW(stream.synchronize());
    
    // Test query
    EXPECT_TRUE(stream.query());
}

TEST_F(CudaWrappersTest, CudaStreamMove) {
    CudaStream stream1;
    cudaStream_t original = stream1.get();
    
    // Move construction
    CudaStream stream2(std::move(stream1));
    EXPECT_EQ(stream2.get(), original);
    EXPECT_EQ(stream1.get(), nullptr);
    
    // Move assignment
    CudaStream stream3;
    stream3 = std::move(stream2);
    EXPECT_EQ(stream3.get(), original);
    EXPECT_EQ(stream2.get(), nullptr);
}

TEST_F(CudaWrappersTest, CudaEventCreation) {
    CudaEvent event;
    EXPECT_NE(event.get(), nullptr);
    
    // Test recording
    EXPECT_NO_THROW(event.record());
    
    // Test synchronization
    EXPECT_NO_THROW(event.synchronize());
    
    // Test query
    EXPECT_TRUE(event.query());
}

TEST_F(CudaWrappersTest, CudaEventTiming) {
    CudaEvent start(0);  // Enable timing
    CudaEvent end(0);
    
    start.record();
    // Small kernel or operation
    end.record();
    end.synchronize();
    
    float elapsed = end.elapsed_ms(start);
    EXPECT_GE(elapsed, 0.0f);
}

TEST_F(CudaWrappersTest, DeviceBufferAllocation) {
    const size_t size = 1024;
    DeviceBuffer<float> buffer(size);
    
    EXPECT_NE(buffer.get(), nullptr);
    EXPECT_EQ(buffer.size(), size);
    EXPECT_EQ(buffer.bytes(), size * sizeof(float));
}

TEST_F(CudaWrappersTest, DeviceBufferMemset) {
    const size_t size = 256;
    DeviceBuffer<int> buffer(size);
    
    // Set to zero
    EXPECT_NO_THROW(buffer.memset(0));
    
    // Copy back and verify
    std::vector<int> host_data(size);
    buffer.copy_to_host(host_data.data(), size);
    
    for (int val : host_data) {
        EXPECT_EQ(val, 0);
    }
}

TEST_F(CudaWrappersTest, DeviceBufferCopy) {
    const size_t size = 512;
    std::vector<float> host_input(size);
    std::iota(host_input.begin(), host_input.end(), 0.0f);
    
    DeviceBuffer<float> buffer(size);
    
    // Copy to device
    EXPECT_NO_THROW(buffer.copy_from_host(host_input.data(), size));
    
    // Copy back to host
    std::vector<float> host_output(size);
    EXPECT_NO_THROW(buffer.copy_to_host(host_output.data(), size));
    
    // Verify
    for (size_t i = 0; i < size; ++i) {
        EXPECT_FLOAT_EQ(host_output[i], host_input[i]);
    }
}

TEST_F(CudaWrappersTest, DeviceBufferResize) {
    DeviceBuffer<float> buffer(100);
    EXPECT_EQ(buffer.size(), 100);
    
    buffer.resize(200);
    EXPECT_EQ(buffer.size(), 200);
    
    buffer.resize(50);
    EXPECT_EQ(buffer.size(), 50);
    
    buffer.resize(0);
    EXPECT_EQ(buffer.size(), 0);
    EXPECT_EQ(buffer.get(), nullptr);
}

TEST_F(CudaWrappersTest, PinnedHostBufferAllocation) {
    const size_t size = 1024;
    PinnedHostBuffer<float> buffer(size);
    
    EXPECT_NE(buffer.get(), nullptr);
    EXPECT_EQ(buffer.size(), size);
    EXPECT_EQ(buffer.bytes(), size * sizeof(float));
}

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

TEST_F(CudaWrappersTest, CufftPlanCreation) {
    CufftPlan plan;
    CudaStream stream;
    
    const int nfft = 256;
    const int batch = 2;
    int n[] = {nfft};
    
    EXPECT_NO_THROW(plan.create_plan_many(
        1, n, nullptr, 1, nfft,
        nullptr, 1, nfft,
        CUFFT_C2C, batch, stream.get()
    ));
    
    EXPECT_NE(plan.get(), 0);
    EXPECT_GE(plan.work_size(), 0);
}

TEST_F(CudaWrappersTest, CufftPlanExecute) {
    CufftPlan plan;
    CudaStream stream;

    const int nfft = 128;
    const int batch = 1;
    const int complex_size = nfft / 2 + 1;
    int n[] = {nfft};

    // Create an R2C plan
    plan.create_plan_many(
        1, n, nullptr, 1, nfft,
        nullptr, 1, complex_size,
        CUFFT_R2C, batch, stream.get()
    );

    // Allocate data
    DeviceBuffer<float> real_data(nfft * batch);
    DeviceBuffer<float2> complex_data(complex_size * batch);

    // Initialize with zeros
    std::vector<float> host_data(nfft * batch, 0.0f);
    host_data[0] = 1.0f;  // Impulse

    real_data.copy_from_host(host_data.data(), host_data.size(), stream.get());

    // Execute R2C FFT
    EXPECT_NO_THROW(plan.exec_r2c(
        reinterpret_cast<cufftReal*>(real_data.get()),
        reinterpret_cast<cufftComplex*>(complex_data.get())
    ));

    stream.synchronize();
}

TEST_F(CudaWrappersTest, ErrorHandling) {
    // Test CUDA error exception
    try {
        IONO_CUDA_CHECK(cudaSetDevice(9999));  // Invalid device
        FAIL() << "Expected CudaException";
    } catch (const CudaException& e) {
        EXPECT_NE(e.error(), cudaSuccess);
    }
    
    // Test cuFFT error exception
    CufftPlan plan;
    try {
        int n[] = {-1};  // Invalid size
        plan.create_plan_many(
            1, n, nullptr, 1, 1,
            nullptr, 1, 1,
            CUFFT_C2C, 1, 0
        );
        FAIL() << "Expected CufftException";
    } catch (const CufftException& e) {
        EXPECT_NE(e.result(), CUFFT_SUCCESS);
    }
}

TEST_F(CudaWrappersTest, StreamEventSynchronization) {
    CudaStream stream1, stream2;
    CudaEvent event;
    
    const size_t size = 1024;
    DeviceBuffer<float> buffer1(size), buffer2(size);
    
    std::vector<float> host_data(size, 1.0f);
    
    // Copy on stream1
    buffer1.copy_from_host(host_data.data(), size, stream1.get());
    event.record(stream1.get());
    
    // Wait for stream1 on stream2
    IONO_CUDA_CHECK(cudaStreamWaitEvent(stream2.get(), event.get(), 0));
    
    // Copy on stream2 after stream1 completes
    IONO_CUDA_CHECK(cudaMemcpyAsync(
        buffer2.get(), buffer1.get(), buffer1.bytes(),
        cudaMemcpyDeviceToDevice, stream2.get()
    ));
    
    stream2.synchronize();
    
    // Verify data
    std::vector<float> output(size);
    buffer2.copy_to_host(output.data(), size);
    
    for (size_t i = 0; i < size; ++i) {
        EXPECT_FLOAT_EQ(output[i], 1.0f);
    }
}