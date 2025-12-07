/**
 * @file cuda_wrappers.hpp
 * @version 1.0
 * @date 2025-09-01
 * @author [Kevin Rahsaz]
 *
 * @brief Provides robust, RAII-compliant C++ wrappers for CUDA and cuFFT
 * resources.
 *
 * This header defines a set of move-only, exception-safe classes for managing
 * CUDA streams, events, device buffers, pinned host buffers, and cuFFT plans.
 * It adheres to Research Software Engineering (RSE) best practices by ensuring
 * automatic resource cleanup (preventing leaks) and converting CUDA error codes
 * into C++ exceptions for reliable error handling, which is critical for
 * reproducible engineering (RE). The documentation style follows IEEE
 * standards.
 */

#pragma once

#include <cuda_runtime.h>
#include <cufft.h>

// Tame problematic Windows macros that can collide with C++ identifiers
#ifdef _WIN32
#ifdef small
#undef small
#endif
#ifdef min
#undef min
#endif
#ifdef max
#undef max
#endif
#ifdef near
#undef near
#endif
#ifdef far
#undef far
#endif
#ifdef interface
#undef interface
#endif
#ifdef ERROR
#undef ERROR
#endif
#ifdef string
#undef string
#endif
#ifdef byte
#undef byte
#endif
#ifdef hyper
#undef hyper
#endif
#endif

#include <cstring>  // For std::memset
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

namespace sigtekx {

// Forward-declare exception classes for the macros.
class CudaException;
class CufftException;

/**
 * @def SIGTEKX_CUDA_CHECK(call)
 * @brief Macro to check the return value of a CUDA Runtime API call.
 * @param call The CUDA API call to execute.
 * @throws CudaException if the call does not return cudaSuccess.
 */
#define SIGTEKX_CUDA_CHECK(call)                                \
  do {                                                       \
    cudaError_t error = call;                                \
    if (error != cudaSuccess) {                              \
      throw CudaException(error, #call, __FILE__, __LINE__); \
    }                                                        \
  } while (0)

/**
 * @def SIGTEKX_CUFFT_CHECK(call)
 * @brief Macro to check the return value of a cuFFT API call.
 * @param call The cuFFT API call to execute.
 * @throws CufftException if the call does not return CUFFT_SUCCESS.
 */
#define SIGTEKX_CUFFT_CHECK(call)                                 \
  do {                                                         \
    cufftResult result = call;                                 \
    if (result != CUFFT_SUCCESS) {                             \
      throw CufftException(result, #call, __FILE__, __LINE__); \
    }                                                          \
  } while (0)

/**
 * @class CudaException
 * @brief An exception class for CUDA Runtime API errors.
 *
 * Translates cudaError_t codes into a C++ exception, providing a detailed
 * error message that includes the file, line number, and failed API call.
 */
class CudaException : public std::runtime_error {
 public:
  /**
   * @brief Constructs a CudaException object.
   * @param error The cudaError_t code.
   * @param call The string representation of the failed API call.
   * @param file The file where the error occurred.
   * @param line The line number where the error occurred.
   */
  CudaException(cudaError_t error, const char* call, const char* file, int line)
      : std::runtime_error(format_message(error, call, file, line)),
        error_(error) {}

  /**
   * @brief Gets the CUDA error code.
   * @return The cudaError_t code.
   */
  cudaError_t error() const noexcept { return error_; }

 private:
  cudaError_t error_;

  /**
   * @brief Formats the detailed error message.
   * @param error The cudaError_t code.
   * @param call The string representation of the failed API call.
   * @param file The file where the error occurred.
   * @param line The line number where the error occurred.
   * @return A formatted error string.
   */
  static std::string format_message(cudaError_t error, const char* call,
                                    const char* file, int line) {
    return std::string("CUDA error at ") + file + ":" + std::to_string(line) +
           " - " + call + " failed with: " + cudaGetErrorString(error);
  }
};

/**
 * @class CufftException
 * @brief An exception class for cuFFT API errors.
 *
 * Translates cufftResult codes into a C++ exception, providing context.
 */
class CufftException : public std::runtime_error {
 public:
  /**
   * @brief Constructs a CufftException object.
   * @param result The cufftResult code.
   * @param call The string representation of the failed API call.
   * @param file The file where the error occurred.
   * @param line The line number where the error occurred.
   */
  CufftException(cufftResult result, const char* call, const char* file,
                 int line)
      : std::runtime_error(format_message(result, call, file, line)),
        result_(result) {}

  /**
   * @brief Gets the cuFFT result code.
   * @return The cufftResult code.
   */
  cufftResult result() const noexcept { return result_; }

 private:
  cufftResult result_;

  /**
   * @brief Formats the detailed error message for cuFFT errors.
   * @param result The cufftResult code.
   * @param call The string representation of the failed API call.
   * @param file The file where the error occurred.
   * @param line The line number where the error occurred.
   * @return A formatted error string.
   */
  static std::string format_message(cufftResult result, const char* call,
                                    const char* file, int line) {
    // Note: cuFFT does not have a dedicated error string function like CUDA RT.
    return std::string("cuFFT error at ") + file + ":" + std::to_string(line) +
           " - " + call + " failed with code: " + std::to_string(result);
  }
};

/**
 * @class CudaStream
 * @brief RAII wrapper for a CUDA stream (cudaStream_t).
 *
 * Manages the lifetime of a CUDA stream, ensuring cudaStreamDestroy is called
 * automatically upon destruction. This class is move-only to enforce unique
 * ownership.
 */
class CudaStream {
 public:
  /**
   * @brief Default constructor. Creates a new non-blocking CUDA stream.
   */
  CudaStream() : stream_(nullptr) {
    SIGTEKX_CUDA_CHECK(cudaStreamCreateWithFlags(&stream_, cudaStreamNonBlocking));
  }

  /**
   * @brief Explicit constructor to wrap an existing stream (non-owning).
   * @param stream An existing CUDA stream handle.
   */
  explicit CudaStream(cudaStream_t stream) noexcept
      : stream_(stream), owned_(false) {}

  /**
   * @brief Destructor. Destroys the stream if it's owned by this wrapper.
   */
  ~CudaStream() {
    if (stream_ && owned_) {
      // cudaStreamDestroy is a cleanup function and should not throw.
      // In case of an error, it is ignored to comply with no-throw destructor
      // guidelines.
      cudaStreamDestroy(stream_);
    }
  }

  // --- Move-only semantics to prevent copying ---
  CudaStream(const CudaStream&) = delete;
  CudaStream& operator=(const CudaStream&) = delete;

  /**
   * @brief Move constructor. Transfers ownership of the stream.
   * @param other The CudaStream object to move from.
   */
  CudaStream(CudaStream&& other) noexcept
      : stream_(std::exchange(other.stream_, nullptr)),
        owned_(std::exchange(other.owned_, false)) {}

  /**
   * @brief Move assignment operator. Transfers ownership of the stream.
   * @param other The CudaStream object to move from.
   * @return A reference to this object.
   */
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

  /**
   * @brief Gets the underlying CUDA stream handle.
   * @return The cudaStream_t handle.
   */
  cudaStream_t get() const noexcept { return stream_; }

  /**
   * @brief Implicit conversion to cudaStream_t.
   * @return The cudaStream_t handle.
   */
  operator cudaStream_t() const noexcept { return stream_; }

  /**
   * @brief Synchronizes the stream. Blocks the host until all preceding
   * commands in the stream are complete.
   */
  void synchronize() const { SIGTEKX_CUDA_CHECK(cudaStreamSynchronize(stream_)); }

  /**
   * @brief Queries the status of the stream.
   * @return True if all preceding commands in the stream have completed, false
   * otherwise.
   */
  bool query() const {
    cudaError_t status = cudaStreamQuery(stream_);
    if (status == cudaErrorNotReady) return false;
    SIGTEKX_CUDA_CHECK(status);
    return true;
  }

 private:
  cudaStream_t stream_;
  bool owned_ = true;
};

// RAII wrapper for CUDA events (move-only)
/**
 * @class CudaEvent
 * @brief RAII wrapper for a CUDA event (cudaEvent_t).
 *
 * Manages the lifetime of a CUDA event, ensuring automatic destruction.
 * This class is move-only.
 */
class CudaEvent {
 public:
  /**
   * @brief Default constructor. Creates a new event with timing disabled for
   * performance.
   */
  CudaEvent() : event_(nullptr) {
    SIGTEKX_CUDA_CHECK(cudaEventCreateWithFlags(&event_, cudaEventDisableTiming));
  }

  /**
   * @brief Constructor with custom flags.
   * @param flags Flags for cudaEventCreateWithFlags (e.g., 0 for timing).
   */
  explicit CudaEvent(unsigned int flags) : event_(nullptr) {
    SIGTEKX_CUDA_CHECK(cudaEventCreateWithFlags(&event_, flags));
  }

  /**
   * @brief Destructor. Destroys the CUDA event.
   */
  ~CudaEvent() {
    if (event_) {
      cudaEventDestroy(event_);
    }
  }

  // --- Move-only semantics ---
  CudaEvent(const CudaEvent&) = delete;
  CudaEvent& operator=(const CudaEvent&) = delete;

  /**
   * @brief Move constructor. Transfers ownership of the event.
   * @param other The CudaEvent object to move from.
   */
  CudaEvent(CudaEvent&& other) noexcept
      : event_(std::exchange(other.event_, nullptr)) {}

  /**
   * @brief Move assignment operator. Transfers ownership of the event.
   * @param other The CudaEvent object to move from.
   * @return A reference to this object.
   */
  CudaEvent& operator=(CudaEvent&& other) noexcept {
    if (this != &other) {
      if (event_) {
        cudaEventDestroy(event_);
      }
      event_ = std::exchange(other.event_, nullptr);
    }
    return *this;
  }

  /**
   * @brief Gets the underlying CUDA event handle.
   * @return The cudaEvent_t handle.
   */
  cudaEvent_t get() const noexcept { return event_; }

  /**
   * @brief Implicit conversion to cudaEvent_t.
   * @return The cudaEvent_t handle.
   */
  operator cudaEvent_t() const noexcept { return event_; }

  /**
   * @brief Records the event in a specified stream.
   * @param stream The stream to record the event in. Defaults to the legacy
   * default stream (0).
   */
  void record(cudaStream_t stream = 0) {
    SIGTEKX_CUDA_CHECK(cudaEventRecord(event_, stream));
  }

  /**
   * @brief Synchronizes the host thread with this event.
   */
  void synchronize() const { SIGTEKX_CUDA_CHECK(cudaEventSynchronize(event_)); }

  /**
   * @brief Queries the status of the event.
   * @return True if the event has been recorded, false otherwise.
   */
  bool query() const {
    cudaError_t status = cudaEventQuery(event_);
    if (status == cudaErrorNotReady) return false;
    SIGTEKX_CUDA_CHECK(status);
    return true;
  }

  /**
   * @brief Computes the elapsed time in milliseconds between two events.
   * @param start The starting event.
   * @return The elapsed time in milliseconds.
   * @note Both events must be created with timing enabled (flags=0).
   */
  float elapsed_ms(const CudaEvent& start) const {
    float ms = 0.0f;
    SIGTEKX_CUDA_CHECK(cudaEventElapsedTime(&ms, start.event_, event_));
    return ms;
  }

 private:
  cudaEvent_t event_;
};

/**
 * @class DeviceBuffer
 * @brief RAII wrapper for CUDA device memory (move-only).
 * @tparam T The data type of the buffer elements.
 */
template <typename T>
class DeviceBuffer {
 public:
  /** @brief Default constructor, creates an empty buffer. */
  DeviceBuffer() : ptr_(nullptr), size_(0) {}

  /**
   * @brief Allocates a device buffer of a specified size.
   * @param count The number of elements of type T to allocate.
   */
  explicit DeviceBuffer(size_t count) : ptr_(nullptr), size_(0) {
    if (count > 0) {
      size_ = count;
      SIGTEKX_CUDA_CHECK(cudaMalloc(&ptr_, count * sizeof(T)));
    }
  }

  /** @brief Destructor, frees the device memory. */
  ~DeviceBuffer() {
    if (ptr_) {
      cudaFree(ptr_);
    }
  }

  // --- Move-only semantics ---
  DeviceBuffer(const DeviceBuffer&) = delete;
  DeviceBuffer& operator=(const DeviceBuffer&) = delete;

  /** @brief Move constructor. */
  DeviceBuffer(DeviceBuffer&& other) noexcept
      : ptr_(std::exchange(other.ptr_, nullptr)),
        size_(std::exchange(other.size_, 0)) {}

  /** @brief Move assignment operator. */
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

  /** @brief Gets a pointer to the device memory. */
  T* get() noexcept { return ptr_; }
  /** @brief Gets a const pointer to the device memory. */
  const T* get() const noexcept { return ptr_; }
  /** @brief Gets the number of elements in the buffer. */
  size_t size() const noexcept { return size_; }
  /** @brief Gets the total size of the buffer in bytes. */
  size_t bytes() const noexcept { return size_ * sizeof(T); }

  /**
   * @brief Resizes the buffer, reallocating memory. Content is not preserved.
   * @param new_count The new number of elements.
   */
  void resize(size_t new_count) {
    if (new_count != size_) {
      if (ptr_) {
        cudaFree(ptr_);
        ptr_ = nullptr;
      }
      size_ = new_count;
      if (size_ > 0) {
        SIGTEKX_CUDA_CHECK(cudaMalloc(&ptr_, size_ * sizeof(T)));
      }
    }
  }

  /**
   * @brief Sets the buffer memory to a specific byte value.
   * @param value The byte value to set (e.g., 0).
   */
  void memset(int value = 0) {
    if (ptr_ && size_ > 0) {
      SIGTEKX_CUDA_CHECK(cudaMemset(ptr_, value, bytes()));
    }
  }

  /**
   * @brief Asynchronously copies data from the host to this device buffer.
   * @param host_ptr Pointer to the source host memory.
   * @param count Number of elements to copy.
   * @param stream The CUDA stream to perform the copy on.
   */
  void copy_from_host(const T* host_ptr, size_t count,
                      cudaStream_t stream = 0) {
    if (count > size_) {
      throw std::runtime_error("Copy size exceeds buffer capacity");
    }
    SIGTEKX_CUDA_CHECK(cudaMemcpyAsync(ptr_, host_ptr, count * sizeof(T),
                                    cudaMemcpyHostToDevice, stream));
  }

  /**
   * @brief Asynchronously copies data from this device buffer to the host.
   * @param host_ptr Pointer to the destination host memory.
   * @param count Number of elements to copy.
   * @param stream The CUDA stream to perform the copy on.
   */
  void copy_to_host(T* host_ptr, size_t count, cudaStream_t stream = 0) const {
    if (count > size_) {
      throw std::runtime_error("Copy size exceeds buffer capacity");
    }
    SIGTEKX_CUDA_CHECK(cudaMemcpyAsync(host_ptr, ptr_, count * sizeof(T),
                                    cudaMemcpyDeviceToHost, stream));
  }

 private:
  T* ptr_;
  size_t size_;
};

/**
 * @class PinnedHostBuffer
 * @brief RAII wrapper for page-locked (pinned) host memory (move-only).
 * @tparam T The data type of the buffer elements.
 */
template <typename T>
class PinnedHostBuffer {
 public:
  /** @brief Default constructor, creates an empty buffer. */
  PinnedHostBuffer() : ptr_(nullptr), size_(0) {}

  /**
   * @brief Allocates a pinned host buffer of a specified size.
   * @param count The number of elements to allocate.
   */
  explicit PinnedHostBuffer(size_t count) : ptr_(nullptr), size_(0) {
    if (count > 0) {
      size_ = count;
      SIGTEKX_CUDA_CHECK(
          cudaHostAlloc(&ptr_, count * sizeof(T), cudaHostAllocDefault));
    }
  }

  /** @brief Destructor, frees the pinned memory. */
  ~PinnedHostBuffer() {
    if (ptr_) {
      cudaFreeHost(ptr_);
    }
  }

  // --- Move-only semantics ---
  PinnedHostBuffer(const PinnedHostBuffer&) = delete;
  PinnedHostBuffer& operator=(const PinnedHostBuffer&) = delete;

  /** @brief Move constructor. */
  PinnedHostBuffer(PinnedHostBuffer&& other) noexcept
      : ptr_(std::exchange(other.ptr_, nullptr)),
        size_(std::exchange(other.size_, 0)) {}

  /** @brief Move assignment operator. */
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

  /** @brief Gets a pointer to the host memory. */
  T* get() noexcept { return ptr_; }
  /** @brief Gets a const pointer to the host memory. */
  const T* get() const noexcept { return ptr_; }
  /** @brief Gets a pointer to the host memory (alias for get()). */
  T* data() noexcept { return ptr_; }
  /** @brief Gets a const pointer to the host memory (alias for get()). */
  const T* data() const noexcept { return ptr_; }

  /** @brief Gets the number of elements in the buffer. */
  size_t size() const noexcept { return size_; }
  /** @brief Gets the total size of the buffer in bytes. */
  size_t bytes() const noexcept { return size_ * sizeof(T); }

  /** @brief Provides array-like access to the buffer elements. */
  T& operator[](size_t idx) { return ptr_[idx]; }
  /** @brief Provides const array-like access to the buffer elements. */
  const T& operator[](size_t idx) const { return ptr_[idx]; }

  /**
   * @brief Resizes the buffer, reallocating memory. Content is not preserved.
   * @param new_count The new number of elements.
   */
  void resize(size_t new_count) {
    if (new_count != size_) {
      if (ptr_) {
        cudaFreeHost(ptr_);
        ptr_ = nullptr;
      }
      size_ = new_count;
      if (size_ > 0) {
        SIGTEKX_CUDA_CHECK(
            cudaHostAlloc(&ptr_, size_ * sizeof(T), cudaHostAllocDefault));
      }
    }
  }

  /**
   * @brief Sets the buffer memory to a specific byte value.
   * @param value The byte value to set (e.g., 0).
   */
  void memset(int value = 0) {
    if (ptr_ && size_ > 0) {
      std::memset(ptr_, value, bytes());
    }
  }

 private:
  T* ptr_;
  size_t size_;
};

/**
 * @class CufftPlan
 * @brief RAII wrapper for a cuFFT plan (cufftHandle).
 *
 * Manages the lifetime of a cuFFT plan, including its work area. This class is
 * move-only.
 */
class CufftPlan {
 public:
  /** @brief Default constructor, creates an empty plan handle. */
  CufftPlan() : plan_(0), work_size_(0) {}

  /** @brief Destructor, destroys the cuFFT plan. */
  ~CufftPlan() {
    if (plan_) {
      cufftDestroy(plan_);
    }
  }

  // --- Move-only semantics ---
  CufftPlan(const CufftPlan&) = delete;
  CufftPlan& operator=(const CufftPlan&) = delete;

  /** @brief Move constructor. */
  CufftPlan(CufftPlan&& other) noexcept
      : plan_(std::exchange(other.plan_, 0)),
        work_area_(std::move(other.work_area_)),
        work_size_(std::exchange(other.work_size_, 0)) {}

  /** @brief Move assignment operator. */
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

  /** @brief Gets the underlying cuFFT plan handle. */
  cufftHandle get() const noexcept { return plan_; }
  /** @brief Implicit conversion to cufftHandle. */
  operator cufftHandle() const noexcept { return plan_; }

  /**
   * @brief Creates a many-transform cuFFT plan with proper work area
   * management.
   *
   * This method encapsulates the creation, work-area querying, and stream
   * association for a cufftPlanMany operation. It disables auto-allocation to
   * manage the work area buffer explicitly, which is a best practice for
   * performance and graph compatibility.
   *
   * @param rank The dimensionality of the transform (e.g., 1 for 1D FFT).
   * @param n An array of transform dimensions.
   * @param inembed Pointer to input embedding dimensions (or nullptr).
   * @param istride Stride between input elements.
   * @param idist Distance between batched inputs.
   * @param onembed Pointer to output embedding dimensions (or nullptr).
   * @param ostride Stride between output elements.
   * @param odist Distance between batched outputs.
   * @param type The type of transform (e.g., CUFFT_R2C).
   * @param batch The number of transforms in the batch.
   * @param stream The CUDA stream to associate with the plan.
   */
  void create_plan_many(int rank, int* n, int* inembed, int istride, int idist,
                        int* onembed, int ostride, int odist, cufftType type,
                        int batch, cudaStream_t stream) {
    SIGTEKX_CUFFT_CHECK(cufftCreate(&plan_));
    SIGTEKX_CUFFT_CHECK(cufftSetAutoAllocation(plan_, 0));
    SIGTEKX_CUFFT_CHECK(cufftMakePlanMany(plan_, rank, n, inembed, istride, idist,
                                       onembed, ostride, odist, type, batch,
                                       &work_size_));

    if (work_size_ > 0) {
      // Allocate work area if cuFFT requires it
      work_area_.resize(work_size_);
      SIGTEKX_CUFFT_CHECK(cufftSetWorkArea(plan_, work_area_.get()));
    }

    SIGTEKX_CUFFT_CHECK(cufftSetStream(plan_, stream));
  }

  /**
   * @brief Executes a Real-to-Complex (R2C) transform.
   * @param input Pointer to the real input data on the device.
   * @param output Pointer to the complex output data on the device.
   */
  void exec_r2c(cufftReal* input, cufftComplex* output) const {
    SIGTEKX_CUFFT_CHECK(cufftExecR2C(plan_, input, output));
  }

  /**
   * @brief Gets the size of the work area required by the plan.
   * @return The size in bytes.
   */
  size_t work_size() const noexcept { return work_size_; }

 private:
  cufftHandle plan_;
  DeviceBuffer<char> work_area_;  // Use char for byte-level allocation
  size_t work_size_;
};

}  // namespace sigtekx
