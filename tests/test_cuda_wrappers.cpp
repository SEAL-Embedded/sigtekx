/**
 * @file test_cuda_wrappers.cpp
 * @brief Unit tests for the RAII CUDA resource wrappers.
 *
 * These tests ensure that the wrappers correctly manage resource lifetimes
 * (construction, destruction, move semantics) and that the error-checking
 * macros throw exceptions as expected.
 */

#include <gtest/gtest.h>
#include "ionosense/cuda_wrappers.hpp"

using namespace ionosense::cuda;

TEST(CudaWrappersTest, StreamLifecycle) {
    // Test that a stream can be created and destroyed without error
    ASSERT_NO_THROW({
        Stream s;
        SUCCEED();
    });
}

TEST(CudaWrappersTest, EventLifecycle) {
    ASSERT_NO_THROW({
        Event e;
        SUCCEED();
    });
}

TEST(CudaWrappersTest, DeviceMemoryLifecycle) {
    ASSERT_NO_THROW({
        DeviceMemory<float> mem(1024);
        EXPECT_NE(mem.get(), nullptr);
        EXPECT_EQ(mem.size(), 1024);
    });
}

TEST(CudaWrappersTest, PinnedMemoryLifecycle) {
     ASSERT_NO_THROW({
        PinnedMemory<float> mem(1024);
        EXPECT_NE(mem.get(), nullptr);
        EXPECT_EQ(mem.size(), 1024);
    });
}

TEST(CudaWrappersTest, FftPlanLifecycle) {
    ASSERT_NO_THROW({
        FftPlan plan;
        SUCCEED();
    });
}

TEST(CudaWrappersTest, StreamMoveSemantics) {
    Stream s1;
    cudaStream_t handle1 = s1.get();
    ASSERT_NE(handle1, nullptr);

    Stream s2 = std::move(s1);
    EXPECT_EQ(s1.get(), nullptr); // s1 should be null after move
    EXPECT_EQ(s2.get(), handle1); // s2 should now own the handle
}

TEST(CudaWrappersTest, DeviceMemoryMoveSemantics) {
    DeviceMemory<int> mem1(128);
    int* ptr1 = mem1.get();
    ASSERT_NE(ptr1, nullptr);

    DeviceMemory<int> mem2 = std::move(mem1);
    EXPECT_EQ(mem1.get(), nullptr);
    EXPECT_EQ(mem2.get(), ptr1);
    EXPECT_EQ(mem2.size(), 128);
}

TEST(CudaWrappersTest, CudaCheckThrows) {
    // An invalid device ID should cause cudaSetDevice to fail
    EXPECT_THROW(IONO_CUDA_CHECK(cudaSetDevice(-1)), CudaError);
}

TEST(CudaWrappersTest, CufftCheckThrows) {
    // Creating a plan with invalid parameters should fail
    cufftHandle plan;
    // cufftCreate itself is unlikely to fail, but cufftPlan1d with bad args will
    IONO_CUFFT_CHECK(cufftCreate(&plan));
    EXPECT_THROW(IONO_CUFFT_CHECK(cufftPlan1d(&plan, -1, CUFFT_C2C, 1)), CufftError);
    cufftDestroy(plan);
}

TEST(CudaWrappersTest, ZeroSizeAllocations) {
    // Allocating zero elements should not throw and result in a null pointer.
    ASSERT_NO_THROW({
        DeviceMemory<float> d_mem(0);
        EXPECT_EQ(d_mem.get(), nullptr);
        EXPECT_EQ(d_mem.size(), 0);

        PinnedMemory<char> h_mem(0);
        EXPECT_EQ(h_mem.get(), nullptr);
        EXPECT_EQ(h_mem.size(), 0);
    });
}
