/**
 * @file window_functions.hpp
 * @brief Shared window coefficient helpers with IEEE-754 compliant arithmetic.
 *
 * This header provides robust window function implementations with comprehensive
 * error handling and numerical stability guarantees:
 * - Input validation for bounds checking
 * - IEEE-754 compliant error signaling (NaN on GPU, exceptions on CPU)
 * - Protection against NaN/Inf propagation
 * - Consistent behavior across CPU and GPU code paths
 */

#pragma once

#include <cmath>
#include <stdexcept>
#include <string>

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

enum class WindowSymmetry {
    PERIODIC,   ///< Periodic window (FFT processing, denominator N)
    SYMMETRIC   ///< Symmetric window (signal analysis, denominator N-1)
};

inline constexpr double PI = 3.14159265358979323846264338327950288;

/**
 * @brief Returns a safe denominator for window calculations.
 * @param size The window size.
 * @param symmetry Window symmetry type (PERIODIC for FFT, SYMMETRIC for analysis).
 * @return N or (N-1) based on symmetry, with safety for edge cases.
 */
IONO_HD inline double safe_denominator(int size, WindowSymmetry symmetry) {
    if (symmetry == WindowSymmetry::PERIODIC) {
        return size > 0 ? static_cast<double>(size) : 1.0;
    }
    return size > 1 ? static_cast<double>(size - 1) : 1.0;
}

/**
 * @brief Generates the base Hann window coefficient at a given index.
 * @param index The sample index within the window.
 * @param size The total window size.
 * @param symmetry Window symmetry type (PERIODIC for FFT, SYMMETRIC for analysis).
 * @return The Hann window coefficient, or NaN (GPU) / throws exception (CPU) on error.
 *
 * Error conditions:
 * - size <= 0: Invalid window size
 * - index < 0: Negative index
 * - index >= size: Out-of-bounds index
 * - Non-finite result: Numerical instability detected
 */
IONO_HD inline double hann_base(int index, int size, WindowSymmetry symmetry = WindowSymmetry::PERIODIC) {
    // Input validation
    if (size <= 0 || index < 0 || index >= size) {
#if defined(__CUDA_ARCH__)
        // GPU path: return quiet NaN to signal error
        return __longlong_as_double(0x7FF8000000000000ULL);
#else
        // CPU path: throw exception
        throw std::invalid_argument("Invalid window parameters: size=" +
            std::to_string(size) + ", index=" + std::to_string(index));
#endif
    }

    const double ratio = (2.0 * PI * static_cast<double>(index)) / safe_denominator(size, symmetry);
    const double result = 0.5 * (1.0 - ::cos(ratio));

    // IEEE-754 validation: ensure result is finite
#if defined(__CUDA_ARCH__)
    if (!isfinite(result)) {
        return __longlong_as_double(0x7FF8000000000000ULL);
    }
#else
    if (!std::isfinite(result)) {
        throw std::runtime_error("Window function produced non-finite value");
    }
#endif

    return result;
}

/**
 * @brief Generates the base Blackman window coefficient at a given index.
 * @param index The sample index within the window.
 * @param size The total window size.
 * @param symmetry Window symmetry type (PERIODIC for FFT, SYMMETRIC for analysis).
 * @return The Blackman window coefficient, or NaN (GPU) / throws exception (CPU) on error.
 *
 * Error conditions:
 * - size <= 0: Invalid window size
 * - index < 0: Negative index
 * - index >= size: Out-of-bounds index
 * - Non-finite result: Numerical instability detected
 */
IONO_HD inline double blackman_base(int index, int size, WindowSymmetry symmetry = WindowSymmetry::PERIODIC) {
    // Input validation
    if (size <= 0 || index < 0 || index >= size) {
#if defined(__CUDA_ARCH__)
        // GPU path: return quiet NaN to signal error
        return __longlong_as_double(0x7FF8000000000000ULL);
#else
        // CPU path: throw exception
        throw std::invalid_argument("Invalid window parameters: size=" +
            std::to_string(size) + ", index=" + std::to_string(index));
#endif
    }

    const double ratio = static_cast<double>(index) / safe_denominator(size, symmetry);
    const double two_pi = 2.0 * PI * ratio;
    const double four_pi = 4.0 * PI * ratio;
    const double result = 0.42 - 0.5 * ::cos(two_pi) + 0.08 * ::cos(four_pi);

    // IEEE-754 validation: ensure result is finite
#if defined(__CUDA_ARCH__)
    if (!isfinite(result)) {
        return __longlong_as_double(0x7FF8000000000000ULL);
    }
#else
    if (!std::isfinite(result)) {
        throw std::runtime_error("Window function produced non-finite value");
    }
#endif

    return result;
}

/**
 * @brief Dispatches to the appropriate window function based on kind.
 * @param kind The type of window function.
 * @param index The sample index within the window.
 * @param size The total window size.
 * @param symmetry Window symmetry type (PERIODIC for FFT, SYMMETRIC for analysis).
 * @return The window coefficient, or NaN (GPU) / throws exception (CPU) on error.
 */
IONO_HD inline double base(WindowKind kind, int index, int size, WindowSymmetry symmetry = WindowSymmetry::PERIODIC) {
    switch (kind) {
        case WindowKind::RECTANGULAR:
            // Rectangular window has simpler validation (same for periodic/symmetric)
            if (size <= 0 || index < 0 || index >= size) {
#if defined(__CUDA_ARCH__)
                return __longlong_as_double(0x7FF8000000000000ULL);
#else
                throw std::invalid_argument("Invalid window parameters: size=" +
                    std::to_string(size) + ", index=" + std::to_string(index));
#endif
            }
            return 1.0;
        case WindowKind::HANN:
            return hann_base(index, size, symmetry);
        case WindowKind::BLACKMAN:
            return blackman_base(index, size, symmetry);
    }
    // Unknown window kind - should never reach here
#if defined(__CUDA_ARCH__)
    return __longlong_as_double(0x7FF8000000000000ULL);
#else
    throw std::invalid_argument("Unknown window kind");
#endif
}

/**
 * @brief Computes the final window value with optional square-root normalization.
 * @param kind The type of window function.
 * @param index The sample index within the window.
 * @param size The total window size.
 * @param sqrt_norm If true, applies square-root normalization.
 * @param symmetry Window symmetry type (PERIODIC for FFT, SYMMETRIC for analysis).
 * @return The final window value, or NaN (GPU) / throws exception (CPU) on error.
 */
IONO_HD inline float window_value(WindowKind kind, int index, int size, bool sqrt_norm, WindowSymmetry symmetry = WindowSymmetry::PERIODIC) {
    const double value = base(kind, index, size, symmetry);

    // Check for NaN propagation from base() - important for GPU error detection
#if defined(__CUDA_ARCH__)
    if (!isfinite(value)) {
        return static_cast<float>(__longlong_as_double(0x7FF8000000000000ULL));
    }
#else
    if (!std::isfinite(value)) {
        // Error already thrown by base(), but check anyway for safety
        throw std::runtime_error("Window base function returned non-finite value");
    }
#endif

    const double sanitized = (sqrt_norm && value < 0.0) ? 0.0 : value;
    const double adjusted = sqrt_norm ? ::sqrt(sanitized) : value;

    // Final validation
#if defined(__CUDA_ARCH__)
    if (!isfinite(adjusted)) {
        return static_cast<float>(__longlong_as_double(0x7FF8000000000000ULL));
    }
#else
    if (!std::isfinite(adjusted)) {
        throw std::runtime_error("Window function produced non-finite value after normalization");
    }
#endif

    return static_cast<float>(adjusted);
}

/**
 * @brief Fills a buffer with window coefficients.
 * @param destination Pointer to the output buffer.
 * @param size The window size.
 * @param kind The type of window function.
 * @param sqrt_norm If true, applies square-root normalization.
 * @param symmetry Window symmetry type (PERIODIC for FFT, SYMMETRIC for analysis).
 *
 * Note: This function validates inputs and may throw exceptions on the CPU path
 * if invalid parameters are provided. On GPU, errors would be signaled via NaN.
 */
inline void fill_window(float* destination, int size, WindowKind kind, bool sqrt_norm, WindowSymmetry symmetry = WindowSymmetry::PERIODIC) {
    if (destination == nullptr) {
        throw std::invalid_argument("Null destination pointer");
    }
    if (size <= 0) {
        throw std::invalid_argument("Invalid window size: " + std::to_string(size));
    }

    for (int i = 0; i < size; ++i) {
        destination[i] = window_value(kind, i, size, sqrt_norm, symmetry);
    }
}

#undef IONO_HD

}  // namespace ionosense::window_functions
