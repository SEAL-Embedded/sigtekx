/**
 * @file profiling_nvtx.cu
 *
 * NVTX implementation - keeps all CUDA/NVTX headers isolated to .cu
 */

#include "ionosense/core/profiling_macros.hpp"

#ifdef IONOSENSE_ENABLE_PROFILING
#define NVTX3_CPP_REQUIRE_EXPLICIT_VERSION
#include <nvtx3/nvtx3.hpp>
#undef NVTX3_CPP_REQUIRE_EXPLICIT_VERSION
#endif

namespace ionosense {
namespace profiling {

#ifdef IONOSENSE_ENABLE_PROFILING
// Single runtime toggle shared across all TUs
static bool g_profiling_enabled = true;

bool profiling_enabled() { return g_profiling_enabled; }
void set_profiling_enabled(bool enable) { g_profiling_enabled = enable; }
// Convert 0xAARRGGBB to nvtx3::argb
static inline nvtx3::v1::argb to_argb(uint32_t argb) {
  return nvtx3::v1::argb{static_cast<unsigned char>((argb >> 24) & 0xFF),
                         static_cast<unsigned char>((argb >> 16) & 0xFF),
                         static_cast<unsigned char>((argb >> 8) & 0xFF),
                         static_cast<unsigned char>((argb >> 0) & 0xFF)};
}

// Opaque impl for RAII range
struct ScopedRange::Impl {
  nvtx3::v1::scoped_range range;
  explicit Impl(const char* name, uint32_t color)
      : range(nvtx3::v1::event_attributes{nvtx3::v1::message{name},
                                          to_argb(color)}) {}
};

ScopedRange::ScopedRange(const char* name, uint32_t color) : pImpl(nullptr) {
  if (g_profiling_enabled) {
    pImpl = new Impl(name, color);
  }
}

ScopedRange::~ScopedRange() { delete pImpl; }

void nvtx_mark(const char* message, uint32_t color) {
  if (g_profiling_enabled) {
    nvtx3::v1::mark(nvtx3::v1::event_attributes{nvtx3::v1::message{message},
                                                to_argb(color)});
  }
}
#endif  // IONOSENSE_ENABLE_PROFILING

}  // namespace profiling
}  // namespace ionosense
