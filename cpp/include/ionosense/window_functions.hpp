/**
 * @file window_functions.hpp
 * @brief Shared window coefficient helpers with IEEE-754 compliant arithmetic.
 */

#pragma once

#include <cmath>

namespace ionosense::window_functions {

#if defined(__CUDACC__)
#define IONO_HD __host__ __device__
#else
#define IONO_HD
#endif

enum class WindowKind {
    RECTANGULAR,
    HANN,
    BLACKMAN
};

inline constexpr double PI = 3.14159265358979323846264338327950288;

IONO_HD inline double safe_denominator(int size) {
    return size > 1 ? static_cast<double>(size - 1) : 1.0;
}

IONO_HD inline double hann_base(int index, int size) {
    if (size <= 0) {
        return 0.0;
    }
    const double ratio = (2.0 * PI * static_cast<double>(index)) / safe_denominator(size);
    return 0.5 * (1.0 - ::cos(ratio));
}

IONO_HD inline double blackman_base(int index, int size) {
    if (size <= 0) {
        return 0.0;
    }
    const double ratio = static_cast<double>(index) / safe_denominator(size);
    const double two_pi = 2.0 * PI * ratio;
    const double four_pi = 4.0 * PI * ratio;
    return 0.42 - 0.5 * ::cos(two_pi) + 0.08 * ::cos(four_pi);
}

IONO_HD inline double base(WindowKind kind, int index, int size) {
    switch (kind) {
        case WindowKind::RECTANGULAR:
            return (size <= 0) ? 0.0 : 1.0;
        case WindowKind::HANN:
            return hann_base(index, size);
        case WindowKind::BLACKMAN:
            return blackman_base(index, size);
    }
    return 0.0;
}

IONO_HD inline float window_value(WindowKind kind, int index, int size, bool sqrt_norm) {
    const double value = base(kind, index, size);
    const double sanitized = (sqrt_norm && value < 0.0) ? 0.0 : value;
    const double adjusted = sqrt_norm ? ::sqrt(sanitized) : value;
    return static_cast<float>(adjusted);
}

inline void fill_window(float* destination, int size, WindowKind kind, bool sqrt_norm) {
    if (size <= 0 || destination == nullptr) {
        return;
    }
    for (int i = 0; i < size; ++i) {
        destination[i] = window_value(kind, i, size, sqrt_norm);
    }
}

#undef IONO_HD

}  // namespace ionosense::window_functions
