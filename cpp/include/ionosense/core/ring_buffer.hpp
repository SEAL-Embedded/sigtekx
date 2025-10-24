/**
 * @file ring_buffer.hpp
 * @version 0.9.4
 * @date 2025-10-18
 * @author [Kevin Rahsaz]
 *
 * @brief Circular ring buffer for continuous streaming input accumulation.
 *
 * Provides a thread-safe, single-producer/single-consumer ring buffer
 * optimized for STFT streaming applications with overlapping frame extraction.
 */

#pragma once

#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <vector>

namespace ionosense {

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
 * Single-producer/single-consumer safe (one thread pushes, one extracts).
 * Multi-producer or multi-consumer requires external synchronization.
 */
template <typename T>
class RingBuffer {
 public:
  /**
   * @brief Constructs a ring buffer with specified capacity.
   * @param capacity Maximum number of elements to store.
   *
   * For STFT with batch processing, recommended size is:
   * `capacity = nfft + (batch - 1) * hop_size + nfft` (extra for safety)
   */
  explicit RingBuffer(size_t capacity)
      : capacity_(capacity),
        buffer_(capacity),
        write_pos_(0),
        read_pos_(0),
        available_(0) {
    if (capacity == 0) {
      throw std::invalid_argument("Ring buffer capacity must be > 0");
    }
  }

  /**
   * @brief Pushes samples into the ring buffer.
   * @param data Pointer to input samples.
   * @param count Number of samples to push.
   * @throws std::overflow_error if buffer capacity would be exceeded.
   *
   * Samples are appended at the write position, wrapping around if necessary.
   */
  void push(const T* data, size_t count) {
    if (count == 0) return;

    // Check capacity
    if (available_ + count > capacity_) {
      throw std::overflow_error("Ring buffer overflow: insufficient capacity");
    }

    // Handle wraparound in write
    size_t write_end = write_pos_ + count;
    if (write_end <= capacity_) {
      // Contiguous write
      std::memcpy(&buffer_[write_pos_], data, count * sizeof(T));
    } else {
      // Split write (wraparound)
      size_t first_part = capacity_ - write_pos_;
      std::memcpy(&buffer_[write_pos_], data, first_part * sizeof(T));
      std::memcpy(&buffer_[0], data + first_part,
                  (count - first_part) * sizeof(T));
    }

    write_pos_ = write_end % capacity_;
    available_ += count;
  }

  /**
   * @brief Checks if enough samples are available to extract a frame.
   * @param frame_size Size of the frame to extract (e.g., nfft).
   * @return True if frame can be extracted, false otherwise.
   */
  bool can_extract_frame(size_t frame_size) const {
    return available_ >= frame_size;
  }

  /**
   * @brief Extracts a single frame from the ring buffer.
   * @param output Destination buffer (must have space for frame_size elements).
   * @param frame_size Number of samples in one frame (e.g., nfft).
   * @throws std::underflow_error if insufficient samples available.
   *
   * Reads from current read position without advancing the pointer.
   * Call advance() after extraction to move the read position.
   */
  void extract_frame(T* output, size_t frame_size) const {
    if (available_ < frame_size) {
      throw std::underflow_error(
          "Ring buffer underflow: insufficient samples for frame");
    }

    // Handle wraparound in read
    size_t read_end = read_pos_ + frame_size;
    if (read_end <= capacity_) {
      // Contiguous read
      std::memcpy(output, &buffer_[read_pos_], frame_size * sizeof(T));
    } else {
      // Split read (wraparound)
      size_t first_part = capacity_ - read_pos_;
      std::memcpy(output, &buffer_[read_pos_], first_part * sizeof(T));
      std::memcpy(output + first_part, &buffer_[0],
                  (frame_size - first_part) * sizeof(T));
    }
  }

  /**
   * @brief Extracts a batch of overlapping frames for STFT processing.
   * @param output Destination buffer (must have space for nfft * batch
   * elements).
   * @param nfft Frame size (window size for FFT).
   * @param batch Number of frames to extract.
   * @param hop_size Stride between consecutive frames (samples to advance).
   * @throws std::underflow_error if insufficient samples available.
   *
   * Extracts `batch` frames, each of size `nfft`, with `hop_size` samples
   * between frame starts. Handles STFT overlap (e.g., hop_size = nfft * (1 -
   * overlap)).
   *
   * Example: nfft=1024, batch=2, hop_size=512 (50% overlap)
   *   Frame 0: samples [0:1024)
   *   Frame 1: samples [512:1536)
   *   Total samples needed: 1024 + 512 = 1536
   */
  void extract_batch(T* output, size_t nfft, size_t batch,
                     size_t hop_size) const {
    // Calculate total samples needed
    size_t total_needed = nfft + (batch - 1) * hop_size;
    if (available_ < total_needed) {
      throw std::underflow_error(
          "Ring buffer underflow: insufficient samples for batch");
    }

    // Extract each frame
    for (size_t i = 0; i < batch; ++i) {
      size_t frame_start = (read_pos_ + i * hop_size) % capacity_;
      T* frame_output = output + i * nfft;

      // Handle wraparound for this frame
      if (frame_start + nfft <= capacity_) {
        // Contiguous copy
        std::memcpy(frame_output, &buffer_[frame_start], nfft * sizeof(T));
      } else {
        // Split copy (wraparound)
        size_t first_part = capacity_ - frame_start;
        std::memcpy(frame_output, &buffer_[frame_start],
                    first_part * sizeof(T));
        std::memcpy(frame_output + first_part, &buffer_[0],
                    (nfft - first_part) * sizeof(T));
      }
    }
  }

  /**
   * @brief Advances the read pointer by a specified number of samples.
   * @param samples Number of samples to advance (typically hop_size).
   *
   * After extracting frames, call this to move the read position forward
   * and mark samples as consumed. For STFT with overlap, advance by hop_size.
   */
  void advance(size_t samples) {
    if (samples > available_) {
      throw std::underflow_error(
          "Cannot advance beyond available samples in ring buffer");
    }

    read_pos_ = (read_pos_ + samples) % capacity_;
    available_ -= samples;
  }

  /**
   * @brief Returns the number of samples available for reading.
   * @return Number of samples that can be extracted.
   */
  size_t available() const { return available_; }

  /**
   * @brief Returns the total capacity of the ring buffer.
   * @return Maximum number of elements that can be stored.
   */
  size_t capacity() const { return capacity_; }

  /**
   * @brief Resets the ring buffer to empty state.
   *
   * Clears read/write positions and available count. Does not deallocate
   * memory.
   */
  void reset() {
    write_pos_ = 0;
    read_pos_ = 0;
    available_ = 0;
  }

  /**
   * @brief Checks if the ring buffer is empty.
   * @return True if no samples are available.
   */
  bool empty() const { return available_ == 0; }

  /**
   * @brief Checks if the ring buffer is full.
   * @return True if no more samples can be pushed.
   */
  bool full() const { return available_ == capacity_; }

 private:
  size_t capacity_;        ///< Maximum number of elements
  std::vector<T> buffer_;  ///< Underlying storage
  size_t write_pos_;       ///< Current write position (insertion point)
  size_t read_pos_;        ///< Current read position (extraction point)
  size_t available_;       ///< Number of samples available for reading
};

}  // namespace ionosense
