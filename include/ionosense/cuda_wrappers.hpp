// include/ionosense/cuda_wrappers.hpp
#pragma once

#include <cuda_runtime.h>
#include <cufft.h>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

namespace ionosense {

// CUDA error checking macro following NVIDIA best practices
#define IONO_CUDA_CHECK(call)                                                  \
    do {                                                                        \
        cudaError_t error = call;                                              \
        if (error != cudaSuccess) {                                            \
            throw CudaException(error, #call, __FILE__, __LINE__);             \
        }                                                                       \
    } while (0)

#define IONO_CUFFT_CHECK(call)                                                 \
    do {                                                                        \
        cufftResult result = call;                                             \
        if (result != CUFFT_SUCCESS) {                                         \
            throw CufftException(result, #call, __FILE__, __LINE__);           \
        }                                                                       \
    } while (0)

// Exception classes for proper error translation
class CudaException : public std::runtime_error {
public:
    CudaException(cudaError_t error, const char* call, const char* file, int line)
        : std::runtime_error(format_message(error, call, file, line)),
          error_(error) {}
    
    cudaError_t error() const noexcept { return error_; }

private:
    cudaError_t error_;
    
    static std::string format_message(cudaError_t error, const char* call, 
                                     const char* file, int line) {
        return std::string("CUDA error at ") + file + ":" + std::to_string(line) +
               " - " + call + " failed with: " + cudaGetErrorString(error);
    }
};

class CufftException : public std::runtime_error {
public:
    CufftException(cufftResult result, const char* call, const char* file, int line)
        : std::runtime_error(format_message(result, call, file, line)),
          result_(result) {}
    
    cufftResult result() const noexcept { return result_; }

private:
    cufftResult result_;
    
    static std::string format_message(cufftResult result, const char* call,
                                     const char* file, int line) {
        return std::string("cuFFT error at ") + file + ":" + std::to_string(line) +
               " - " + call + " failed with code: " + std::to_string(result);
    }
};

// RAII wrapper for CUDA streams (move-only, following C++17 best practices)
class CudaStream {
public:
    CudaStream() : stream_(nullptr) {
        IONO_CUDA_CHECK(cudaStreamCreateWithFlags(&stream_, cudaStreamNonBlocking));
    }
    
    explicit CudaStream(cudaStream_t stream) noexcept : stream_(stream) {}
    
    ~CudaStream() {
        if (stream_ && owned_) {
            cudaStreamDestroy(stream_);  // No throw in destructor
        }
    }
    
    // Move-only semantics
    CudaStream(const CudaStream&) = delete;
    CudaStream& operator=(const CudaStream&) = delete;
    
    CudaStream(CudaStream&& other) noexcept 
        : stream_(std::exchange(other.stream_, nullptr)),
          owned_(std::exchange(other.owned_, false)) {}
    
    CudaStream& operator=(CudaStream&& other) noexcept {
        if (this != &other) {
            if (stream_ && owned_) {
                cudaStreamDestroy(stream_);
            }
            stream_ = std::exchange(other.stream_, nullptr);
            owned_ = std::exchange(other.owned_, false);
        }
        return *this;
    }
    
    cudaStream_t get() const noexcept { return stream_; }
    operator cudaStream_t() const noexcept { return stream_; }
    
    void synchronize() const {
        IONO_CUDA_CHECK(cudaStreamSynchronize(stream_));
    }
    
    bool query() const {
        cudaError_t status = cudaStreamQuery(stream_);
        if (status == cudaErrorNotReady) return false;
        IONO_CUDA_CHECK(status);
        return true;
    }

private:
    cudaStream_t stream_;
    bool owned_ = true;
};

// RAII wrapper for CUDA events
class CudaEvent {
public:
    CudaEvent() : event_(nullptr) {
        IONO_CUDA_CHECK(cudaEventCreateWithFlags(&event_, cudaEventDisableTiming));
    }
    
    explicit CudaEvent(unsigned int flags) : event_(nullptr) {
        IONO_CUDA_CHECK(cudaEventCreateWithFlags(&event_, flags));
    }
    
    ~CudaEvent() {
        if (event_) {
            cudaEventDestroy(event_);
        }
    }
    
    // Move-only semantics
    CudaEvent(const CudaEvent&) = delete;
    CudaEvent& operator=(const CudaEvent&) = delete;
    
    CudaEvent(CudaEvent&& other) noexcept
        : event_(std::exchange(other.event_, nullptr)) {}
    
    CudaEvent& operator=(CudaEvent&& other) noexcept {
        if (this != &other) {
            if (event_) {
                cudaEventDestroy(event_);
            }
            event_ = std::exchange(other.event_, nullptr);
        }
        return *this;
    }
    
    cudaEvent_t get() const noexcept { return event_; }
    operator cudaEvent_t() const noexcept { return event_; }
    
    void record(cudaStream_t stream = 0) {
        IONO_CUDA_CHECK(cudaEventRecord(event_, stream));
    }
    
    void synchronize() const {
        IONO_CUDA_CHECK(cudaEventSynchronize(event_));
    }
    
    bool query() const {
        cudaError_t status = cudaEventQuery(event_);
        if (status == cudaErrorNotReady) return false;
        IONO_CUDA_CHECK(status);
        return true;
    }
    
    float elapsed_ms(const CudaEvent& start) const {
        float ms = 0.0f;
        IONO_CUDA_CHECK(cudaEventElapsedTime(&ms, start.event_, event_));
        return ms;
    }

private:
    cudaEvent_t event_;
};

// RAII wrapper for device memory with proper alignment
template<typename T>
class DeviceBuffer {
public:
    DeviceBuffer() : ptr_(nullptr), size_(0) {}
    
    explicit DeviceBuffer(size_t count) : size_(count) {
        if (count > 0) {
            IONO_CUDA_CHECK(cudaMalloc(&ptr_, count * sizeof(T)));
        }
    }
    
    ~DeviceBuffer() {
        if (ptr_) {
            cudaFree(ptr_);  // No throw in destructor
        }
    }
    
    // Move-only semantics
    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;
    
    DeviceBuffer(DeviceBuffer&& other) noexcept
        : ptr_(std::exchange(other.ptr_, nullptr)),
          size_(std::exchange(other.size_, 0)) {}
    
    DeviceBuffer& operator=(DeviceBuffer&& other) noexcept {
        if (this != &other) {
            if (ptr_) {
                cudaFree(ptr_);
            }
            ptr_ = std::exchange(other.ptr_, nullptr);
            size_ = std::exchange(other.size_, 0);
        }
        return *this;
    }
    
    T* get() noexcept { return ptr_; }
    const T* get() const noexcept { return ptr_; }
    size_t size() const noexcept { return size_; }
    size_t bytes() const noexcept { return size_ * sizeof(T); }
    
    void resize(size_t new_count) {
        if (new_count != size_) {
            T* new_ptr = nullptr;
            if (new_count > 0) {
                IONO_CUDA_CHECK(cudaMalloc(&new_ptr, new_count * sizeof(T)));
            }
            if (ptr_) {
                cudaFree(ptr_);
            }
            ptr_ = new_ptr;
            size_ = new_count;
        }
    }
    
    void memset(int value = 0) {
        if (ptr_ && size_ > 0) {
            IONO_CUDA_CHECK(cudaMemset(ptr_, value, bytes()));
        }
    }
    
    void copy_from_host(const T* host_ptr, size_t count, cudaStream_t stream = 0) {
        if (count > size_) {
            throw std::runtime_error("Copy size exceeds buffer capacity");
        }
        IONO_CUDA_CHECK(cudaMemcpyAsync(ptr_, host_ptr, count * sizeof(T),
                                        cudaMemcpyHostToDevice, stream));
    }
    
    void copy_to_host(T* host_ptr, size_t count, cudaStream_t stream = 0) const {
        if (count > size_) {
            throw std::runtime_error("Copy size exceeds buffer capacity");
        }
        IONO_CUDA_CHECK(cudaMemcpyAsync(host_ptr, ptr_, count * sizeof(T),
                                        cudaMemcpyDeviceToHost, stream));
    }

private:
    T* ptr_;
    size_t size_;
};

// RAII wrapper for pinned host memory (page-locked for fast transfers)
template<typename T>
class PinnedHostBuffer {
public:
    PinnedHostBuffer() : ptr_(nullptr), size_(0) {}
    
    explicit PinnedHostBuffer(size_t count) : size_(count) {
        if (count > 0) {
            IONO_CUDA_CHECK(cudaHostAlloc(&ptr_, count * sizeof(T), 
                                          cudaHostAllocDefault));
        }
    }
    
    ~PinnedHostBuffer() {
        if (ptr_) {
            cudaFreeHost(ptr_);  // No throw in destructor
        }
    }
    
    // Move-only semantics
    PinnedHostBuffer(const PinnedHostBuffer&) = delete;
    PinnedHostBuffer& operator=(const PinnedHostBuffer&) = delete;
    
    PinnedHostBuffer(PinnedHostBuffer&& other) noexcept
        : ptr_(std::exchange(other.ptr_, nullptr)),
          size_(std::exchange(other.size_, 0)) {}
    
    PinnedHostBuffer& operator=(PinnedHostBuffer&& other) noexcept {
        if (this != &other) {
            if (ptr_) {
                cudaFreeHost(ptr_);
            }
            ptr_ = std::exchange(other.ptr_, nullptr);
            size_ = std::exchange(other.size_, 0);
        }
        return *this;
    }
    
    T* get() noexcept { return ptr_; }
    const T* get() const noexcept { return ptr_; }
    T* data() noexcept { return ptr_; }
    const T* data() const noexcept { return ptr_; }
    
    size_t size() const noexcept { return size_; }
    size_t bytes() const noexcept { return size_ * sizeof(T); }
    
    T& operator[](size_t idx) { return ptr_[idx]; }
    const T& operator[](size_t idx) const { return ptr_[idx]; }
    
    void resize(size_t new_count) {
        if (new_count != size_) {
            T* new_ptr = nullptr;
            if (new_count > 0) {
                IONO_CUDA_CHECK(cudaHostAlloc(&new_ptr, new_count * sizeof(T),
                                             cudaHostAllocDefault));
            }
            if (ptr_) {
                cudaFreeHost(ptr_);
            }
            ptr_ = new_ptr;
            size_ = new_count;
        }
    }
    
    void memset(int value = 0) {
        if (ptr_ && size_ > 0) {
            std::memset(ptr_, value, bytes());
        }
    }

private:
    T* ptr_;
    size_t size_;
};

// RAII wrapper for cuFFT plans
class CufftPlan {
public:
    CufftPlan() : plan_(0) {}
    
    ~CufftPlan() {
        if (plan_) {
            cufftDestroy(plan_);  // No throw in destructor
        }
    }
    
    // Move-only semantics
    CufftPlan(const CufftPlan&) = delete;
    CufftPlan& operator=(const CufftPlan&) = delete;
    
    CufftPlan(CufftPlan&& other) noexcept
        : plan_(std::exchange(other.plan_, 0)),
          work_area_(std::move(other.work_area_)),
          work_size_(std::exchange(other.work_size_, 0)) {}
    
    CufftPlan& operator=(CufftPlan&& other) noexcept {
        if (this != &other) {
            if (plan_) {
                cufftDestroy(plan_);
            }
            plan_ = std::exchange(other.plan_, 0);
            work_area_ = std::move(other.work_area_);
            work_size_ = std::exchange(other.work_size_, 0);
        }
        return *this;
    }
    
    cufftHandle get() const noexcept { return plan_; }
    operator cufftHandle() const noexcept { return plan_; }
    
    // Initialize plan with proper work area management
    void create_plan_many(int rank, int* n, int* inembed, int istride, int idist,
                         int* onembed, int ostride, int odist, cufftType type,
                         int batch, cudaStream_t stream) {
        // Create plan
        IONO_CUFFT_CHECK(cufftCreate(&plan_));
        
        // Disable auto-allocation for better control
        IONO_CUFFT_CHECK(cufftSetAutoAllocation(plan_, 0));
        
        // Make the plan
        IONO_CUFFT_CHECK(cufftPlanMany(&plan_, rank, n, inembed, istride, idist,
                                       onembed, ostride, odist, type, batch));
        
        // Query work area size
        IONO_CUFFT_CHECK(cufftGetSize(plan_, &work_size_));
        
        // Allocate work area if needed
        if (work_size_ > 0) {
            work_area_.resize((work_size_ + sizeof(float) - 1) / sizeof(float));
            IONO_CUFFT_CHECK(cufftSetWorkArea(plan_, work_area_.get()));
        }
        
        // Associate with stream
        IONO_CUFFT_CHECK(cufftSetStream(plan_, stream));
    }
    
    // Execute R2C transform (out-of-place)
    void exec_r2c(cufftReal* input, cufftComplex* output) const {
        IONO_CUFFT_CHECK(cufftExecR2C(plan_, input, output));
    }
    
    size_t work_size() const noexcept { return work_size_; }

private:
    cufftHandle plan_;
    DeviceBuffer<float> work_area_;
    size_t work_size_ = 0;
};

}  // namespace ionosense