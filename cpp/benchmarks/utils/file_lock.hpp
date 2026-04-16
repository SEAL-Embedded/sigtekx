/**
 * @file file_lock.hpp
 * @brief Cross-platform file locking for concurrent dataset saves.
 *
 * Provides RAII-based file locking to prevent race conditions during
 * concurrent dataset operations. Automatically releases locks on
 * destruction, even if exceptions occur.
 *
 * Platform Support:
 * - Windows: CreateFile + LockFileEx
 * - Linux/Unix: open + flock
 */

#pragma once

#include <chrono>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <thread>

#ifdef _WIN32
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#endif

namespace sigtekx {
namespace benchmark {

/**
 * @brief RAII-based file lock for concurrent access control.
 *
 * Usage:
 * @code
 * {
 *   FileLock lock("/path/to/file.lock", 10.0f);
 *   // Critical section - lock held here
 *   // ... modify shared resource ...
 * } // Lock automatically released
 * @endcode
 *
 * Features:
 * - Automatic lock release on destruction (RAII)
 * - Configurable timeout
 * - Works across processes (not just threads)
 * - Survives crashes (OS releases file locks)
 */
class FileLock {
 public:
  /**
   * @brief Acquire file lock with timeout.
   *
   * @param lock_path Path to lock file
   * @param timeout_s Timeout in seconds (default: 10.0)
   * @throws std::runtime_error if lock cannot be acquired within timeout
   */
  explicit FileLock(const std::filesystem::path& lock_path,
                    float timeout_s = 10.0f)
      : lock_path_(lock_path), locked_(false) {
    // Ensure lock directory exists
    auto parent = lock_path_.parent_path();
    if (!parent.empty()) {
      std::filesystem::create_directories(parent);
    }

    acquire_lock(timeout_s);
  }

  /**
   * @brief Release lock automatically (RAII).
   */
  ~FileLock() {
    if (locked_) {
      release_lock();
    }
  }

  // Non-copyable, non-movable (lock is tied to file handle)
  FileLock(const FileLock&) = delete;
  FileLock& operator=(const FileLock&) = delete;
  FileLock(FileLock&&) = delete;
  FileLock& operator=(FileLock&&) = delete;

  /**
   * @brief Check if lock is currently held.
   */
  bool is_locked() const { return locked_; }

 private:
  void acquire_lock(float timeout_s) {
    auto start = std::chrono::steady_clock::now();
    auto timeout = std::chrono::duration<float>(timeout_s);

    while (true) {
      if (try_acquire_lock()) {
        locked_ = true;
        return;
      }

      // Check timeout
      auto elapsed = std::chrono::steady_clock::now() - start;
      if (elapsed >= timeout) {
        throw std::runtime_error(
            "Failed to acquire file lock: timeout after " +
            std::to_string(timeout_s) + "s (file: " + lock_path_.string() +
            ")");
      }

      // Wait before retry (100ms)
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
  }

  bool try_acquire_lock() {
#ifdef _WIN32
    // Windows: CreateFile + LockFileEx
    handle_ = CreateFileW(
        lock_path_.c_str(),
        GENERIC_READ | GENERIC_WRITE,  // Need both for locking
        0,                              // Exclusive access
        nullptr,                        // Default security
        OPEN_ALWAYS,                    // Create if doesn't exist
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_DELETE_ON_CLOSE,
        nullptr);

    if (handle_ == INVALID_HANDLE_VALUE) {
      return false;  // File in use or other error
    }

    // Try to acquire lock (non-blocking)
    OVERLAPPED overlapped = {0};
    BOOL locked = LockFileEx(
        handle_,
        LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY,  // Non-blocking
        0,             // Reserved
        MAXDWORD,      // Lock entire file
        MAXDWORD,      // Lock entire file
        &overlapped);

    if (!locked) {
      CloseHandle(handle_);
      handle_ = INVALID_HANDLE_VALUE;
      return false;
    }

    return true;

#else
    // Linux/Unix: open + flock
    fd_ = open(lock_path_.c_str(), O_CREAT | O_RDWR, 0666);
    if (fd_ == -1) {
      return false;
    }

    // Try to acquire lock (non-blocking)
    if (flock(fd_, LOCK_EX | LOCK_NB) == -1) {
      close(fd_);
      fd_ = -1;
      return false;
    }

    return true;
#endif
  }

  void release_lock() {
#ifdef _WIN32
    if (handle_ != INVALID_HANDLE_VALUE) {
      // Unlock file
      OVERLAPPED overlapped = {0};
      UnlockFileEx(handle_, 0, MAXDWORD, MAXDWORD, &overlapped);

      // Close handle (deletes file due to FILE_FLAG_DELETE_ON_CLOSE)
      CloseHandle(handle_);
      handle_ = INVALID_HANDLE_VALUE;
    }
#else
    if (fd_ != -1) {
      // Release lock
      flock(fd_, LOCK_UN);
      close(fd_);
      fd_ = -1;

      // Delete lock file
      std::error_code ec;
      std::filesystem::remove(lock_path_, ec);
      // Ignore errors (file may already be deleted)
    }
#endif

    locked_ = false;
  }

  std::filesystem::path lock_path_;
  bool locked_;

#ifdef _WIN32
  HANDLE handle_ = INVALID_HANDLE_VALUE;
#else
  int fd_ = -1;
#endif
};

}  // namespace benchmark
}  // namespace sigtekx
