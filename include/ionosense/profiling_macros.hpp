/**
 * @file profiling_macros.hpp
 * @version 1.0
 * @date 2025-09-07
 *
 * @brief NVTX profiling macros with CUDA/NVTX isolated to .cu
 *
 * Header exposes only plain C++ types and lightweight macros. All NVTX/CUDA
 * implementation details live in src/profiling_nvtx.cu so regular .cpp files
 * never include CUDA or NVTX headers.
 */

#pragma once

#include <cstdint>
#include <string>
#include <cstdio>

namespace ionosense {
namespace profiling {

// -----------------------------------------------------------------------------
// Runtime toggle
// -----------------------------------------------------------------------------
// Implemented in src/profiling_nvtx.cu when profiling is enabled.
#ifdef IONOSENSE_ENABLE_PROFILING
bool profiling_enabled();
void set_profiling_enabled(bool enable);
#else
inline bool profiling_enabled() { return false; }
inline void set_profiling_enabled(bool /*enable*/) {}
#endif

// -----------------------------------------------------------------------------
// Colors (ARGB)
// -----------------------------------------------------------------------------
namespace colors {
// Use 0xAARRGGBB ARGB encoding; safe plain uint32_t in headers.
constexpr uint32_t NVIDIA_BLUE = 0xFF0070E0u;
constexpr uint32_t PURPLE      = 0xFF9B59B6u;
constexpr uint32_t GREEN       = 0xFF27AE60u;
constexpr uint32_t ORANGE      = 0xFFE67E22u;
constexpr uint32_t DARK_GRAY   = 0xFF34495Eu;
constexpr uint32_t RED         = 0xFFE74C3Cu;
constexpr uint32_t YELLOW      = 0xFFF1C40Fu;
constexpr uint32_t LIGHT_GRAY  = 0xFF95A5A6u;
constexpr uint32_t CYAN        = 0xFF1ABC9Cu;
constexpr uint32_t MAGENTA     = 0xFF8E44ADu;
} // namespace colors

// -----------------------------------------------------------------------------
// RAII wrapper (opaque in headers)
// -----------------------------------------------------------------------------
class ScopedRange {
 public:
  ScopedRange(const char* name, uint32_t color);
  ~ScopedRange();
  ScopedRange(const ScopedRange&) = delete;
  ScopedRange& operator=(const ScopedRange&) = delete;
  ScopedRange(ScopedRange&&) = delete;
  ScopedRange& operator=(ScopedRange&&) = delete;

 private:
  struct Impl; // defined in .cu when profiling is enabled
  Impl* pImpl; // opaque to C++ translation units
};

// Lightweight marker
#ifdef IONOSENSE_ENABLE_PROFILING
void nvtx_mark(const char* message, uint32_t color);
#else
inline void nvtx_mark(const char* /*message*/, uint32_t /*color*/) {}
#endif

// -----------------------------------------------------------------------------
// Helper formatting utilities (header-only, no NVTX/CUDA deps)
// -----------------------------------------------------------------------------
inline std::string format_stage_range(const std::string& stage_name,
                                      int batch_size,
                                      int nfft) {
  return stage_name + " [B:" + std::to_string(batch_size) +
         ",N:" + std::to_string(nfft) + "]";
}

inline std::string format_memory_range(const std::string& operation,
                                       size_t bytes) {
  const double mb = static_cast<double>(bytes) / (1024.0 * 1024.0);
  char buf[128];
  std::snprintf(buf, sizeof(buf), "%s [%.2f MB]", operation.c_str(), mb);
  return std::string(buf);
}

// -----------------------------------------------------------------------------
// Unique-ID helper for macros
// -----------------------------------------------------------------------------
#define IONO_DETAIL_CONCAT_INNER(x, y) x##y
#define IONO_DETAIL_CONCAT(x, y) IONO_DETAIL_CONCAT_INNER(x, y)
#ifdef _MSC_VER
#  define IONO_UNIQUE_ID(prefix) IONO_DETAIL_CONCAT(prefix, __COUNTER__)
#else
#  define IONO_UNIQUE_ID(prefix) IONO_DETAIL_CONCAT(prefix, __LINE__)
#endif

// -----------------------------------------------------------------------------
// Public Macros
// -----------------------------------------------------------------------------
#ifdef IONOSENSE_ENABLE_PROFILING
  #define IONO_NVTX_RANGE(name, color_argb) \
    ionosense::profiling::ScopedRange IONO_UNIQUE_ID(_nvtx_range_){ (name), (color_argb) }
  #define IONO_NVTX_RANGE_FUNCTION(color_argb) \
    ionosense::profiling::ScopedRange IONO_UNIQUE_ID(_nvtx_fn_range_){ __FUNCTION__, (color_argb) }
  #define IONO_NVTX_MARK(message, color_argb) \
    do { if (ionosense::profiling::profiling_enabled()) \
      ionosense::profiling::nvtx_mark((message), (color_argb)); } while(0)
#else
  // No-op implementations when profiling is disabled at compile time
  inline ScopedRange::ScopedRange(const char*, uint32_t) : pImpl(nullptr) {}
  inline ScopedRange::~ScopedRange() {}
  #define IONO_NVTX_RANGE(name, color_argb)           ((void)0)
  #define IONO_NVTX_RANGE_FUNCTION(color_argb)        ((void)0)
  #define IONO_NVTX_MARK(message, color_argb)         ((void)0)
#endif

}  // namespace profiling
}  // namespace ionosense
