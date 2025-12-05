/**
 * @file ring_buffer.hpp
 * @version 0.9.5
 * @date 2025-11-07
 * @author [Kevin Rahsaz]
 *
 * @brief Circular ring buffer for continuous streaming input accumulation.
 *
 * Provides a thread-safe, single-producer/single-consumer ring buffer
 * optimized for STFT streaming applications with overlapping frame extraction.
 * Uses CUDA pinned memory for faster H2D transfers and lock-free atomic operations.
 */

#pragma once

#include <algorithm>
#include <atomic>
#include <cstring>
#include <stdexcept>

#include "cuda_wrappers.hpp"

namespace sigtekx {

/**
 * @class RingBuffer
 * @brief Circular buffer for continuous sample accumulation and frame
 * extraction.
 *
 * Designed for streaming STFT applications where samples arrive incrementally
 * and overlapping frames must be extracted efficiently. Handles wraparound
 * transparently.
 *
 * @tparam T Element type (typically float for audio samples).
 *
 * **Usage Pattern:**
 * ```cpp
 * RingBuffer<float> buffer(1024 + 512);  // nfft + extra for overlap
 * buffer.push(samples, 256);             // Add new samples
 * if (buffer.available() >= 1024) {
 *   buffer.extract_batch(output, 1024, 2, 512);  // Extract 2 frames, hop=512
 *   buffer.advance(512);                          // Advance read pointer
 * }
 * ```
 *
 * **Thread Safety:**
 * Lock-free thread-safe for concurrent single-producer/single-consumer access
 * using atomic operations with memory_order_acquire/release semantics.
 * Producer (push) and consumer (extract/advance) can operate concurrently
 * without any mutex overhead.
 *
 * **Memory:**
 * Uses CUDA pinned memory (page-locked) for faster H2D transfers via DMA.
 * Allocates memory at construction time (fixed capacity).
 */
template <typename T>
class RingBuffer {
 public:
  /**
   * @brief Constructs a ring buffer with specified capacity using pinned memory.
   * @param capacity Maximum number of elements to store.
   * @throws std::invalid_argument if capacity is 0.
   *
   * Allocates CUDA pinned (page-locked) host memory for optimal H2D transfer
   * performance. For STFT with temporal frame processing, recommended size:
   * `capacity = nfft + (num_frames - 1) * hop_size + nfft` (extra for safety)
   * where num_frames is the number of temporal frames to extract at once.
   */
  explicit RingBuffer(size_t capacity)
      : capacity_(capacity),
        buffer_(capacity),
        write_pos_{0},
        read_pos_{0},
        available_{0} {
    if (capacity == 0) {
      throw std::invalid_argument("Ring buffer capacity must be > 0");
    }
  }

  /**
   * @brief Pushes samples into the ring buffer (lock-free thread-safe).
   * @param data Pointer to input samples.
   * @param count Number of samples to push.
   * @throws std::overflow_error if buffer capacity would be exceeded.
   *
   * Samples are appended at the write position, wrapping around if necessary.
   * Uses atomic operations with memory_order_release for thread safety.
   * Producer can run concurrently with consumer without any locking overhead.
   */
  void push(const T* data, size_t count) {
    if (count == 0) return;

    // Load available count (acquire semantics for consumer updates)
    size_t current_available = available_.load(std::memory_order_acquire);

    // Check capacity
    if (current_available + count > capacity_) {
      throw std::overflow_error("Ring buffer overflow: insufficient capacity");
    }

    // Load write position (relaxed - only modified by producer)
    size_t current_write = write_pos_.load(std::memory_order_relaxed);

    // Handle wraparound in write
    size_t write_end = current_write + count;
    if (write_end <= capacity_) {
      // Contiguous write
      std::memcpy(buffer_.get() + current_write, data, count * sizeof(T));
    } else {
      // Split write (wraparound)
      size_t first_part = capacity_ - current_write;
      std::memcpy(buffer_.get() + current_write, data, first_part * sizeof(T));
      std::memcpy(buffer_.get(), data + first_part,
                  (count - first_part) * sizeof(T));
    }

    // Update positions (release semantics for consumer visibility)
    write_pos_.store(write_end % capacity_, std::memory_order_release);
    available_.fetch_add(count, std::memory_order_release);
  }

  /**
   * @brief Checks if enough samples are available to extract a frame (lock-free).
   * @param frame_size Size of the frame to extract (e.g., nfft).
   * @return True if frame can be extracted, false otherwise.
   *
   * Uses atomic load with acquire semantics for thread safety.
   */
  bool can_extract_frame(size_t frame_size) const {
    return available_.load(std::memory_order_acquire) >= frame_size;
  }

  /**
   * @brief Extracts a single frame from the ring buffer (lock-free thread-safe).
   * @param output Destination buffer (must have space for frame_size elements).
   * @param frame_size Number of samples in one frame (e.g., nfft).
   * @throws std::underflow_error if insufficient samples available.
   *
   * Reads from current read position without advancing the pointer.
   * Call advance() after extraction to move the read position.
   * Uses atomic load with acquire semantics for thread safety.
   */
  void extract_frame(T* output, size_t frame_size) const {
    // Load available count (acquire semantics for producer updates)
    size_t current_available = available_.load(std::memory_order_acquire);

    if (current_available < frame_size) {
      throw std::underflow_error(
          "Ring buffer underflow: insufficient samples for frame");
    }

    // Load read position (relaxed - only modified by consumer)
    size_t current_read = read_pos_.load(std::memory_order_relaxed);

    // Handle wraparound in read
    size_t read_end = current_read + frame_size;
    if (read_end <= capacity_) {
      // Contiguous read
      std::memcpy(output, buffer_.get() + current_read, frame_size * sizeof(T));
    } else {
      // Split read (wraparound)
      size_t first_part = capacity_ - current_read;
      std::memcpy(output, buffer_.get() + current_read, first_part * sizeof(T));
      std::memcpy(output + first_part, buffer_.get(),
                  (frame_size - first_part) * sizeof(T));
    }
  }

  /**
   * @brief Extracts multiple overlapping temporal frames for STFT processing (lock-free).
   * @param output Destination buffer (must have space for nfft * num_frames
   * elements).
   * @param nfft Frame size (window size for FFT).
   * @param num_frames Number of temporal frames to extract.
   * @param hop_size Stride between consecutive frames (samples to advance).
   * @throws std::underflow_error if insufficient samples available.
   *
   * Extracts `num_frames` temporal frames, each of size `nfft`, with `hop_size`
   * samples between frame starts. Handles STFT overlap (e.g., hop_size = nfft *
   * (1 - overlap)). Uses atomic load with acquire semantics for thread safety.
   *
   * Note: This extracts frames in the temporal dimension. Each frame represents
   * one FFT window in time. For multi-channel processing, maintain one ring
   * buffer per spatial channel.
   *
   * Example: nfft=1024, num_frames=2, hop_size=512 (50% overlap)
   *   Frame 0: samples [0:1024)
   *   Frame 1: samples [512:1536)
   *   Total samples needed: 1024 + 512 = 1536
   */
  void extract_batch(T* output, size_t nfft, size_t num_frames,
                     size_t hop_size) const {
    // Load available count (acquire semantics for producer updates)
    size_t current_available = available_.load(std::memory_order_acquire);

    // Calculate total samples needed
    size_t total_needed = nfft + (num_frames - 1) * hop_size;
    if (current_available < total_needed) {
      throw std::underflow_error(
          "Ring buffer underflow: insufficient samples for temporal frames");
    }

    // Load read position (relaxed - only modified by consumer)
    size_t current_read = read_pos_.load(std::memory_order_relaxed);

    // Extract each frame
    for (size_t i = 0; i < num_frames; ++i) {
      size_t frame_start = (current_read + i * hop_size) % capacity_;
      T* frame_output = output + i * nfft;

      // Handle wraparound for this frame
      if (frame_start + nfft <= capacity_) {
        // Contiguous copy
        std::memcpy(frame_output, buffer_.get() + frame_start, nfft * sizeof(T));
      } else {
        // Split copy (wraparound)
        size_t first_part = capacity_ - frame_start;
        std::memcpy(frame_output, buffer_.get() + frame_start,
                    first_part * sizeof(T));
        std::memcpy(frame_output + first_part, buffer_.get(),
                    (nfft - first_part) * sizeof(T));
      }
    }
  }

  /**
   * @brief Advances the read pointer by a specified number of samples (lock-free).
   * @param samples Number of samples to advance (typically hop_size).
   *
   * After extracting frames, call this to move the read position forward
   * and mark samples as consumed. For STFT with overlap, advance by hop_size.
   * Uses atomic operations with release semantics for thread safety.
   */
  void advance(size_t samples) {
    // Load available count (acquire semantics for producer updates)
    size_t current_available = available_.load(std::memory_order_acquire);

    if (samples > current_available) {
      throw std::underflow_error(
          "Cannot advance beyond available samples in ring buffer");
    }

    // Load read position (relaxed - only modified by consumer)
    size_t current_read = read_pos_.load(std::memory_order_relaxed);

    // Update positions (release semantics for producer visibility)
    read_pos_.store((current_read + samples) % capacity_, std::memory_order_release);
    available_.fetch_sub(samples, std::memory_order_release);
  }

  /**
   * @brief Returns the number of samples available for reading (lock-free).
   * @return Number of samples that can be extracted.
   *
   * Uses atomic load with acquire semantics for thread safety.
   */
  size_t available() const {
    return available_.load(std::memory_order_acquire);
  }

  /**
   * @brief Returns the total capacity of the ring buffer.
   * @return Maximum number of elements that can be stored.
   */
  size_t capacity() const { return capacity_; }

  /**
   * @brief Resets the ring buffer to empty state (lock-free).
   *
   * Clears read/write positions and available count. Does not deallocate
   * memory. Uses atomic stores with release semantics for thread safety.
   *
   * NOTE: Should only be called when no concurrent push/extract operations
   * are in progress (e.g., during initialization or teardown).
   */
  void reset() {
    write_pos_.store(0, std::memory_order_release);
    read_pos_.store(0, std::memory_order_release);
    available_.store(0, std::memory_order_release);
  }

  /**
   * @brief Checks if the ring buffer is empty (lock-free).
   * @return True if no samples are available.
   *
   * Uses atomic load with acquire semantics for thread safety.
   */
  bool empty() const {
    return available_.load(std::memory_order_acquire) == 0;
  }

  /**
   * @brief Checks if the ring buffer is full (lock-free).
   * @return True if no more samples can be pushed.
   *
   * Uses atomic load with acquire semantics for thread safety.
   */
  bool full() const {
    return available_.load(std::memory_order_acquire) == capacity_;
  }

 private:
  size_t capacity_;                     ///< Maximum number of elements
  PinnedHostBuffer<T> buffer_;          ///< CUDA pinned memory storage
  std::atomic<size_t> write_pos_;       ///< Current write position (lock-free)
  std::atomic<size_t> read_pos_;        ///< Current read position (lock-free)
  std::atomic<size_t> available_;       ///< Number of samples available (lock-free)
};

}  // namespace sigtekx
