/**
 * @file cuda_wrappers.hpp
 * @brief RAII wrappers for CUDA resources ensuring automatic cleanup and exception safety.
 */

#pragma once

#include <cuda_runtime.h>
#include <cufft.h>
#include <memory>
#include <stdexcept>
#include <string>
#include <sstream>
#include <vector>
#include <unordered_map>


namespace ionosense {
namespace cuda {

// ============================================================================
// Exception Hierarchy
// ============================================================================

/**
 * @brief Base exception for all ionosense errors
 */
class IonoException : public std::runtime_error {
public:
    explicit IonoException(const std::string& msg) : std::runtime_error(msg) {}
};

/**
 * @brief CUDA-specific errors with detailed diagnostics
 */
class CudaError : public IonoException {
public:
    CudaError(cudaError_t code, const char* file, int line) 
        : IonoException(format_error(code, file, line))
        , error_code_(code) {}
    
    cudaError_t code() const noexcept { return error_code_; }

private:
    cudaError_t error_code_;
    
    static std::string format_error(cudaError_t code, const char* file, int line) {
        std::ostringstream oss;
        oss << "CUDA Error " << code << " (" << cudaGetErrorString(code) 
            << ") at " << file << ":" << line;
        return oss.str();
    }
};

/**
 * @brief cuFFT-specific errors
 */
class CufftError : public IonoException {
public:
    CufftError(cufftResult code, const char* file, int line)
        : IonoException(format_error(code, file, line))
        , error_code_(code) {}
    
    cufftResult code() const noexcept { return error_code_; }

private:
    cufftResult error_code_;
    
    static std::string format_error(cufftResult code, const char* file, int line) {
        std::ostringstream oss;
        // cuFFT does not provide a dedicated error string function
        oss << "cuFFT Error " << code << " at " << file << ":" << line;
        return oss.str();
    }
};

/**
 * @brief Configuration errors (invalid parameters, etc.)
 */
class ConfigurationError : public IonoException {
public:
    explicit ConfigurationError(const std::string& msg) 
        : IonoException("Configuration Error: " + msg) {}
};

/**
 * @brief State errors (invalid operation sequence)
 */
class StateError : public IonoException {
public:
    explicit StateError(const std::string& msg) 
        : IonoException("State Error: " + msg) {}
};

// ============================================================================
// Error Checking Macros
// ============================================================================

#define IONO_CUDA_CHECK(call) \
    do { \
        cudaError_t err = (call); \
        if (err != cudaSuccess) { \
            throw ::ionosense::cuda::CudaError(err, __FILE__, __LINE__); \
        } \
    } while(0)

#define IONO_CUFFT_CHECK(call) \
    do { \
        cufftResult err = (call); \
        if (err != CUFFT_SUCCESS) { \
            throw ::ionosense::cuda::CufftError(err, __FILE__, __LINE__); \
        } \
    } while(0)

// ============================================================================
// RAII Wrapper Classes
// ============================================================================

/**
 * @brief RAII wrapper for CUDA streams
 */
class Stream {
public:
    explicit Stream(unsigned int flags = cudaStreamNonBlocking) {
        IONO_CUDA_CHECK(cudaStreamCreateWithFlags(&stream_, flags));
    }
    
    ~Stream() noexcept {
        if (stream_) {
            // Best-effort cleanup in destructor
            cudaStreamSynchronize(stream_);
            cudaStreamDestroy(stream_);
        }
    }
    
    // Move-only semantics to prevent resource duplication
    Stream(const Stream&) = delete;
    Stream& operator=(const Stream&) = delete;
    Stream(Stream&& other) noexcept : stream_(other.stream_) {
        other.stream_ = nullptr;
    }
    Stream& operator=(Stream&& other) noexcept {
        if (this != &other) {
            if (stream_) cudaStreamDestroy(stream_);
            stream_ = other.stream_;
            other.stream_ = nullptr;
        }
        return *this;
    }
    
    cudaStream_t get() const noexcept { return stream_; }
    operator cudaStream_t() const noexcept { return stream_; }
    
    void synchronize() const {
        IONO_CUDA_CHECK(cudaStreamSynchronize(stream_));
    }
    
    void wait_event(cudaEvent_t event) const {
        IONO_CUDA_CHECK(cudaStreamWaitEvent(stream_, event, 0));
    }

private:
    cudaStream_t stream_ = nullptr;
};

/**
 * @brief RAII wrapper for CUDA events
 */
class Event {
public:
    explicit Event(unsigned int flags = cudaEventDisableTiming) {
        IONO_CUDA_CHECK(cudaEventCreateWithFlags(&event_, flags));
    }
    
    ~Event() noexcept {
        if (event_) {
            cudaEventDestroy(event_);
        }
    }
    
    // Move-only semantics
    Event(const Event&) = delete;
    Event& operator=(const Event&) = delete;
    Event(Event&& other) noexcept : event_(other.event_) {
        other.event_ = nullptr;
    }
    Event& operator=(Event&& other) noexcept {
        if (this != &other) {
            if (event_) cudaEventDestroy(event_);
            event_ = other.event_;
            other.event_ = nullptr;
        }
        return *this;
    }
    
    cudaEvent_t get() const noexcept { return event_; }
    operator cudaEvent_t() const noexcept { return event_; }
    
    void record(cudaStream_t stream) const {
        IONO_CUDA_CHECK(cudaEventRecord(event_, stream));
    }
    
    void synchronize() const {
        IONO_CUDA_CHECK(cudaEventSynchronize(event_));
    }
    
    float elapsed_time(const Event& start) const {
        float ms = 0.0f;
        IONO_CUDA_CHECK(cudaEventElapsedTime(&ms, start.event_, event_));
        return ms;
    }

private:
    cudaEvent_t event_ = nullptr;
};

/**
 * @brief RAII wrapper for device memory
 */
template<typename T>
class DeviceMemory {
public:
    explicit DeviceMemory(size_t count = 0) : count_(count), ptr_(nullptr) {
        if (count_ > 0) {
            IONO_CUDA_CHECK(cudaMalloc(&ptr_, sizeof(T) * count_));
        }
    }
    
    ~DeviceMemory() noexcept {
        if (ptr_) {
            cudaFree(ptr_);
        }
    }
    
    // Move-only semantics
    DeviceMemory(const DeviceMemory&) = delete;
    DeviceMemory& operator=(const DeviceMemory&) = delete;
    DeviceMemory(DeviceMemory&& other) noexcept 
        : ptr_(other.ptr_), count_(other.count_) {
        other.ptr_ = nullptr;
        other.count_ = 0;
    }
    DeviceMemory& operator=(DeviceMemory&& other) noexcept {
        if (this != &other) {
            if (ptr_) cudaFree(ptr_);
            ptr_ = other.ptr_;
            count_ = other.count_;
            other.ptr_ = nullptr;
            other.count_ = 0;
        }
        return *this;
    }
    
    T* get() noexcept { return ptr_; }
    const T* get() const noexcept { return ptr_; }
    operator T*() noexcept { return ptr_; }
    operator const T*() const noexcept { return ptr_; }
    
    size_t size() const noexcept { return count_; }
    size_t bytes() const noexcept { return sizeof(T) * count_; }
    
    void copy_from_host(const T* host_data, cudaStream_t stream = 0) {
        if(count_ > 0)
            IONO_CUDA_CHECK(cudaMemcpyAsync(ptr_, host_data, bytes(), cudaMemcpyHostToDevice, stream));
    }
    
    void copy_to_host(T* host_data, cudaStream_t stream = 0) const {
         if(count_ > 0)
            IONO_CUDA_CHECK(cudaMemcpyAsync(host_data, ptr_, bytes(), cudaMemcpyDeviceToHost, stream));
    }

private:
    T* ptr_ = nullptr;
    size_t count_ = 0;
};

/**
 * @brief RAII wrapper for pinned host memory
 */
template<typename T>
class PinnedMemory {
public:
    explicit PinnedMemory(size_t count = 0, unsigned int flags = cudaHostAllocDefault) 
        : count_(count), ptr_(nullptr) {
        if (count_ > 0) {
            IONO_CUDA_CHECK(cudaHostAlloc(&ptr_, sizeof(T) * count_, flags));
        }
    }
    
    ~PinnedMemory() noexcept {
        if (ptr_) {
            cudaFreeHost(ptr_);
        }
    }
    
    // Move-only semantics
    PinnedMemory(const PinnedMemory&) = delete;
    PinnedMemory& operator=(const PinnedMemory&) = delete;
    PinnedMemory(PinnedMemory&& other) noexcept 
        : ptr_(other.ptr_), count_(other.count_) {
        other.ptr_ = nullptr;
        other.count_ = 0;
    }
    PinnedMemory& operator=(PinnedMemory&& other) noexcept {
        if (this != &other) {
            if (ptr_) cudaFreeHost(ptr_);
            ptr_ = other.ptr_;
            count_ = other.count_;
            other.ptr_ = nullptr;
            other.count_ = 0;
        }
        return *this;
    }
    
    T* get() noexcept { return ptr_; }
    const T* get() const noexcept { return ptr_; }
    operator T*() noexcept { return ptr_; }
    operator const T*() const noexcept { return ptr_; }
    
    size_t size() const noexcept { return count_; }
    size_t bytes() const noexcept { return sizeof(T) * count_; }

private:
    T* ptr_ = nullptr;
    size_t count_ = 0;
};

/**
 * @brief RAII wrapper for cuFFT plans
 */
class FftPlan {
public:
    FftPlan() = default;
    
    ~FftPlan() noexcept {
        if (plan_) {
            cufftDestroy(plan_);
        }
    }
    
    // Move-only semantics
    FftPlan(const FftPlan&) = delete;
    FftPlan& operator=(const FftPlan&) = delete;
    FftPlan(FftPlan&& other) noexcept : plan_(other.plan_) {
        other.plan_ = 0;
    }
    FftPlan& operator=(FftPlan&& other) noexcept {
        if (this != &other) {
            if (plan_) cufftDestroy(plan_);
            plan_ = other.plan_;
            other.plan_ = 0;
        }
        return *this;
    }
    
    void create_1d_r2c(int nfft, int batch) {
        if (plan_) {
            cufftDestroy(plan_);
            plan_ = 0;
        }
        
        IONO_CUFFT_CHECK(cufftCreate(&plan_));
        
        const int rank = 1;
        int n[] = { nfft };
        int istride = 1, ostride = 1;
        int idist = nfft;
        int odist = nfft / 2 + 1;
        
        IONO_CUFFT_CHECK(cufftPlanMany(&plan_, rank, n, 
                                       nullptr, istride, idist,
                                       nullptr, ostride, odist,
                                       CUFFT_R2C, batch));
    }
    
    void set_stream(cudaStream_t stream) {
        IONO_CUFFT_CHECK(cufftSetStream(plan_, stream));
    }
    
    void set_work_area(void* workspace) {
        IONO_CUFFT_CHECK(cufftSetAutoAllocation(plan_, 0));
        IONO_CUFFT_CHECK(cufftSetWorkArea(plan_, workspace));
    }
    
    size_t get_work_size() const {
        size_t size = 0;
        if(plan_) IONO_CUFFT_CHECK(cufftGetSize(plan_, &size));
        return size;
    }
    
    // FIX: This method doesn't modify the FftPlan object's state,
    // so it should be marked 'const'.
    void execute_r2c(cufftReal* input, cufftComplex* output) const {
        IONO_CUFFT_CHECK(cufftExecR2C(plan_, input, output));
    }
    
    cufftHandle get() const noexcept { return plan_; }
    operator cufftHandle() const noexcept { return plan_; }

private:
    cufftHandle plan_ = 0;
};

/**
 * @brief RAII wrapper for CUDA graphs
 */
class Graph {
public:
    Graph() = default;
    
    ~Graph() noexcept {
        destroy();
    }
    
    // Move-only semantics
    Graph(const Graph&) = delete;
    Graph& operator=(const Graph&) = delete;
    Graph(Graph&& other) noexcept 
        : graph_(other.graph_), exec_(other.exec_) {
        other.graph_ = nullptr;
        other.exec_ = nullptr;
    }
    Graph& operator=(Graph&& other) noexcept {
        if (this != &other) {
            destroy();
            graph_ = other.graph_;
            exec_ = other.exec_;
            other.graph_ = nullptr;
            other.exec_ = nullptr;
        }
        return *this;
    }
    
    void begin_capture(cudaStream_t stream) {
        destroy();
        IONO_CUDA_CHECK(cudaStreamBeginCapture(stream, cudaStreamCaptureModeGlobal));
    }
    
    void end_capture(cudaStream_t stream) {
        IONO_CUDA_CHECK(cudaStreamEndCapture(stream, &graph_));
        IONO_CUDA_CHECK(cudaGraphInstantiate(&exec_, graph_, nullptr, nullptr, 0));
    }
    
    void launch(cudaStream_t stream) const {
        if (!exec_) {
            throw StateError("Graph not instantiated");
        }
        IONO_CUDA_CHECK(cudaGraphLaunch(exec_, stream));
    }
    
    bool is_captured() const noexcept { return graph_ != nullptr; }
    bool is_instantiated() const noexcept { return exec_ != nullptr; }

private:
    cudaGraph_t graph_ = nullptr;
    cudaGraphExec_t exec_ = nullptr;
    
    void destroy() noexcept {
        if (exec_) {
            cudaGraphExecDestroy(exec_);
            exec_ = nullptr;
        }
        if (graph_) {
            cudaGraphDestroy(graph_);
            graph_ = nullptr;
        }
    }
};

} // namespace cuda
} // namespace ionosense
