/**
 * @file test_window_functions.cpp
 * @version 1.0
 * @date 2025-10-06
 * @author [Kevin Rahsaz]
 *
 * @brief Unit tests for window function validation and IEEE-754 compliance.
 *
 * This test suite validates:
 * - Input bounds checking and validation
 * - IEEE-754 compliance (finite outputs)
 * - Edge case handling (size=0, size=1, negative indices)
 * - Numerical stability across different window sizes
 * - Error signaling behavior on CPU and GPU
 *
 * Tests ensure that the window functions safely handle invalid inputs and
 * prevent NaN/Inf propagation, which is critical for reliable signal processing.
 */

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

#include "ionosense/core/window_functions.hpp"

// IEEE Std 1003.1-2001 compliance for mathematical constants
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

using namespace ionosense::window_functions;

// ============================================================================
// Bounds Validation Tests
// ============================================================================

/**
 * @test WindowFunctionsTest.HannBaseInvalidSize
 * @brief Verifies that hann_base throws on invalid size.
 */
TEST(WindowFunctionsTest, HannBaseInvalidSize) {
    EXPECT_THROW(hann_base(0, 0), std::invalid_argument);
    EXPECT_THROW(hann_base(0, -1), std::invalid_argument);
    EXPECT_THROW(hann_base(10, -100), std::invalid_argument);
}

/**
 * @test WindowFunctionsTest.HannBaseNegativeIndex
 * @brief Verifies that hann_base throws on negative index.
 */
TEST(WindowFunctionsTest, HannBaseNegativeIndex) {
    EXPECT_THROW(hann_base(-1, 1024), std::invalid_argument);
    EXPECT_THROW(hann_base(-10, 1024), std::invalid_argument);
    EXPECT_THROW(hann_base(-1, 1), std::invalid_argument);
}

/**
 * @test WindowFunctionsTest.HannBaseOutOfBounds
 * @brief Verifies that hann_base throws on out-of-bounds index.
 */
TEST(WindowFunctionsTest, HannBaseOutOfBounds) {
    EXPECT_THROW(hann_base(1024, 1024), std::invalid_argument);
    EXPECT_THROW(hann_base(100, 10), std::invalid_argument);
    EXPECT_THROW(hann_base(2, 1), std::invalid_argument);
}

/**
 * @test WindowFunctionsTest.BlackmanBaseInvalidSize
 * @brief Verifies that blackman_base throws on invalid size.
 */
TEST(WindowFunctionsTest, BlackmanBaseInvalidSize) {
    EXPECT_THROW(blackman_base(0, 0), std::invalid_argument);
    EXPECT_THROW(blackman_base(0, -1), std::invalid_argument);
    EXPECT_THROW(blackman_base(10, -100), std::invalid_argument);
}

/**
 * @test WindowFunctionsTest.BlackmanBaseNegativeIndex
 * @brief Verifies that blackman_base throws on negative index.
 */
TEST(WindowFunctionsTest, BlackmanBaseNegativeIndex) {
    EXPECT_THROW(blackman_base(-1, 1024), std::invalid_argument);
    EXPECT_THROW(blackman_base(-10, 1024), std::invalid_argument);
}

/**
 * @test WindowFunctionsTest.BlackmanBaseOutOfBounds
 * @brief Verifies that blackman_base throws on out-of-bounds index.
 */
TEST(WindowFunctionsTest, BlackmanBaseOutOfBounds) {
    EXPECT_THROW(blackman_base(1024, 1024), std::invalid_argument);
    EXPECT_THROW(blackman_base(100, 10), std::invalid_argument);
}

/**
 * @test WindowFunctionsTest.RectangularInvalidParams
 * @brief Verifies that rectangular window validates parameters.
 */
TEST(WindowFunctionsTest, RectangularInvalidParams) {
    EXPECT_THROW(base(WindowKind::RECTANGULAR, -1, 1024), std::invalid_argument);
    EXPECT_THROW(base(WindowKind::RECTANGULAR, 0, 0), std::invalid_argument);
    EXPECT_THROW(base(WindowKind::RECTANGULAR, 1024, 1024), std::invalid_argument);
}

// ============================================================================
// IEEE-754 Compliance Tests
// ============================================================================

/**
 * @test WindowFunctionsTest.HannFiniteOutputs
 * @brief Verifies that hann_base produces finite outputs for valid inputs.
 */
TEST(WindowFunctionsTest, HannFiniteOutputs) {
    const std::vector<int> sizes{1, 2, 16, 64, 256, 1024, 4096};

    for (int size : sizes) {
        for (int i = 0; i < size; ++i) {
            double value = hann_base(i, size);
            EXPECT_TRUE(std::isfinite(value))
                << "Non-finite at size=" << size << ", i=" << i;
            EXPECT_GE(value, 0.0) << "Negative value at size=" << size << ", i=" << i;
            EXPECT_LE(value, 1.0) << "Value > 1.0 at size=" << size << ", i=" << i;
        }
    }
}

/**
 * @test WindowFunctionsTest.BlackmanFiniteOutputs
 * @brief Verifies that blackman_base produces finite outputs for valid inputs.
 */
TEST(WindowFunctionsTest, BlackmanFiniteOutputs) {
    const std::vector<int> sizes{1, 2, 16, 64, 256, 1024, 4096};

    for (int size : sizes) {
        for (int i = 0; i < size; ++i) {
            double value = blackman_base(i, size);
            EXPECT_TRUE(std::isfinite(value))
                << "Non-finite at size=" << size << ", i=" << i;
            EXPECT_GE(value, -0.1) << "Unexpectedly negative at size=" << size << ", i=" << i;
            EXPECT_LE(value, 1.1) << "Unexpectedly large at size=" << size << ", i=" << i;
        }
    }
}

/**
 * @test WindowFunctionsTest.RectangularFiniteOutputs
 * @brief Verifies that rectangular window produces finite outputs.
 */
TEST(WindowFunctionsTest, RectangularFiniteOutputs) {
    const std::vector<int> sizes{1, 2, 16, 64, 256, 1024};

    for (int size : sizes) {
        for (int i = 0; i < size; ++i) {
            double value = base(WindowKind::RECTANGULAR, i, size);
            EXPECT_TRUE(std::isfinite(value))
                << "Non-finite at size=" << size << ", i=" << i;
            EXPECT_EQ(value, 1.0) << "Rectangular window should always be 1.0";
        }
    }
}

/**
 * @test WindowFunctionsTest.WindowValueFiniteOutputs
 * @brief Verifies that window_value produces finite outputs with normalization.
 */
TEST(WindowFunctionsTest, WindowValueFiniteOutputs) {
    const std::vector<int> sizes{1, 2, 16, 64, 256, 1024};
    const std::vector<WindowKind> kinds{
        WindowKind::RECTANGULAR,
        WindowKind::HANN,
        WindowKind::BLACKMAN
    };
    const std::vector<bool> sqrt_norms{false, true};

    for (WindowKind kind : kinds) {
        for (int size : sizes) {
            for (bool sqrt_norm : sqrt_norms) {
                for (int i = 0; i < size; ++i) {
                    float value = window_value(kind, i, size, sqrt_norm);
                    EXPECT_TRUE(std::isfinite(value))
                        << "Non-finite at kind=" << static_cast<int>(kind)
                        << ", size=" << size << ", i=" << i
                        << ", sqrt_norm=" << sqrt_norm;
                }
            }
        }
    }
}

// ============================================================================
// Edge Case Tests
// ============================================================================

/**
 * @test WindowFunctionsTest.SinglePointWindow
 * @brief Tests window functions with size=1.
 */
TEST(WindowFunctionsTest, SinglePointWindow) {
    // Single-point windows are valid and should work
    EXPECT_NO_THROW({
        double hann_val = hann_base(0, 1);
        EXPECT_TRUE(std::isfinite(hann_val));
    });

    EXPECT_NO_THROW({
        double blackman_val = blackman_base(0, 1);
        EXPECT_TRUE(std::isfinite(blackman_val));
    });

    EXPECT_NO_THROW({
        double rect_val = base(WindowKind::RECTANGULAR, 0, 1);
        EXPECT_EQ(rect_val, 1.0);
    });
}

/**
 * @test WindowFunctionsTest.TwoPointWindow
 * @brief Tests window functions with size=2.
 */
TEST(WindowFunctionsTest, TwoPointWindow) {
    // Two-point windows should work
    for (int i = 0; i < 2; ++i) {
        EXPECT_NO_THROW({
            double hann_val = hann_base(i, 2);
            EXPECT_TRUE(std::isfinite(hann_val));
        });

        EXPECT_NO_THROW({
            double blackman_val = blackman_base(i, 2);
            EXPECT_TRUE(std::isfinite(blackman_val));
        });
    }
}

/**
 * @test WindowFunctionsTest.LargeWindowSize
 * @brief Tests window functions with very large sizes.
 */
TEST(WindowFunctionsTest, LargeWindowSize) {
    const int large_size = 32768;  // Common FFT size for ionosphere research

    // Test a few sample points in a large window
    const std::vector<int> sample_indices{0, 1, large_size / 4, large_size / 2,
                                          3 * large_size / 4, large_size - 2, large_size - 1};

    for (int i : sample_indices) {
        EXPECT_NO_THROW({
            double hann_val = hann_base(i, large_size);
            EXPECT_TRUE(std::isfinite(hann_val));
        });

        EXPECT_NO_THROW({
            double blackman_val = blackman_base(i, large_size);
            EXPECT_TRUE(std::isfinite(blackman_val));
        });
    }
}

// ============================================================================
// Numerical Correctness Tests
// ============================================================================

/**
 * @test WindowFunctionsTest.HannSymmetry
 * @brief Verifies that Hann window is symmetric in SYMMETRIC mode.
 *
 * SYMMETRIC mode ensures perfect symmetry around the center, which is
 * important for non-periodic signal analysis applications.
 */
TEST(WindowFunctionsTest, HannSymmetry) {
    const int size = 64;

    // Test SYMMETRIC mode - should have perfect symmetry
    for (int i = 0; i < size / 2; ++i) {
        double left = hann_base(i, size, WindowSymmetry::SYMMETRIC);
        double right = hann_base(size - 1 - i, size, WindowSymmetry::SYMMETRIC);
        EXPECT_NEAR(left, right, 1e-10)
            << "Symmetry violation in SYMMETRIC mode at i=" << i;
    }
}

/**
 * @test WindowFunctionsTest.HannBoundaryValues
 * @brief Verifies that Hann window has correct boundary values in SYMMETRIC mode.
 *
 * SYMMETRIC mode is tested because it guarantees exact zeros at endpoints.
 */
TEST(WindowFunctionsTest, HannBoundaryValues) {
    const int size = 64;

    // Test SYMMETRIC mode - has exact zeros at endpoints
    double first = hann_base(0, size, WindowSymmetry::SYMMETRIC);
    double last = hann_base(size - 1, size, WindowSymmetry::SYMMETRIC);
    double center = hann_base(size / 2, size, WindowSymmetry::SYMMETRIC);

    EXPECT_NEAR(first, 0.0, 1e-6) << "Hann window (SYMMETRIC) should be ~0 at start";
    EXPECT_NEAR(last, 0.0, 1e-6) << "Hann window (SYMMETRIC) should be ~0 at end";
    EXPECT_NEAR(center, 1.0, 0.1) << "Hann window should be ~1 at center";
}

/**
 * @test WindowFunctionsTest.BlackmanSymmetry
 * @brief Verifies that Blackman window is symmetric in SYMMETRIC mode.
 *
 * SYMMETRIC mode ensures perfect symmetry around the center, which is
 * important for non-periodic signal analysis applications.
 */
TEST(WindowFunctionsTest, BlackmanSymmetry) {
    const int size = 64;

    // Test SYMMETRIC mode - should have perfect symmetry
    for (int i = 0; i < size / 2; ++i) {
        double left = blackman_base(i, size, WindowSymmetry::SYMMETRIC);
        double right = blackman_base(size - 1 - i, size, WindowSymmetry::SYMMETRIC);
        EXPECT_NEAR(left, right, 1e-10)
            << "Symmetry violation in SYMMETRIC mode at i=" << i;
    }
}

// ============================================================================
// fill_window() Function Tests
// ============================================================================

/**
 * @test WindowFunctionsTest.FillWindowNullPointer
 * @brief Verifies that fill_window throws on null pointer.
 */
TEST(WindowFunctionsTest, FillWindowNullPointer) {
    EXPECT_THROW(fill_window(nullptr, 64, WindowKind::HANN, false), std::invalid_argument);
}

/**
 * @test WindowFunctionsTest.FillWindowInvalidSize
 * @brief Verifies that fill_window throws on invalid size.
 */
TEST(WindowFunctionsTest, FillWindowInvalidSize) {
    std::vector<float> buffer(64);
    EXPECT_THROW(fill_window(buffer.data(), 0, WindowKind::HANN, false), std::invalid_argument);
    EXPECT_THROW(fill_window(buffer.data(), -1, WindowKind::HANN, false), std::invalid_argument);
}

/**
 * @test WindowFunctionsTest.FillWindowValidOperation
 * @brief Verifies that fill_window correctly populates a buffer.
 *
 * Tests SYMMETRIC mode where endpoints should reach exactly zero.
 */
TEST(WindowFunctionsTest, FillWindowValidOperation) {
    const int size = 64;
    std::vector<float> buffer(size);

    // Use SYMMETRIC mode for this test (endpoints are exactly 0)
    EXPECT_NO_THROW(fill_window(buffer.data(), size, WindowKind::HANN, false, WindowSymmetry::SYMMETRIC));

    // Verify all values are finite
    for (int i = 0; i < size; ++i) {
        EXPECT_TRUE(std::isfinite(buffer[i]))
            << "Non-finite value at index " << i;
    }

    // Verify boundary values (SYMMETRIC mode has exact zeros at endpoints)
    EXPECT_NEAR(buffer[0], 0.0f, 1e-5f);
    EXPECT_NEAR(buffer[size - 1], 0.0f, 1e-5f);
}

/**
 * @test WindowFunctionsTest.FillWindowWithSqrtNorm
 * @brief Verifies that fill_window works with square-root normalization.
 */
TEST(WindowFunctionsTest, FillWindowWithSqrtNorm) {
    const int size = 64;
    std::vector<float> buffer(size);

    EXPECT_NO_THROW(fill_window(buffer.data(), size, WindowKind::HANN, true));

    // Verify all values are finite and non-negative
    for (int i = 0; i < size; ++i) {
        EXPECT_TRUE(std::isfinite(buffer[i]))
            << "Non-finite value at index " << i;
        EXPECT_GE(buffer[i], 0.0f)
            << "Negative value at index " << i;
    }
}

/**
 * @test WindowFunctionsTest.FillWindowAllTypes
 * @brief Verifies fill_window works for all window types.
 */
TEST(WindowFunctionsTest, FillWindowAllTypes) {
    const int size = 64;
    std::vector<float> buffer(size);

    const std::vector<WindowKind> kinds{
        WindowKind::RECTANGULAR,
        WindowKind::HANN,
        WindowKind::BLACKMAN
    };

    for (WindowKind kind : kinds) {
        EXPECT_NO_THROW(fill_window(buffer.data(), size, kind, false))
            << "Failed for kind=" << static_cast<int>(kind);

        // Verify all values are finite
        for (int i = 0; i < size; ++i) {
            EXPECT_TRUE(std::isfinite(buffer[i]))
                << "Non-finite at kind=" << static_cast<int>(kind) << ", i=" << i;
        }
    }
}

// ============================================================================
// Numerical Correctness Tests (Symmetry Modes)
// ============================================================================

/**
 * @test WindowFunctionsTest.PeriodicModeNumericalCorrectness
 * @brief Verifies PERIODIC mode produces correct results (default for FFT processing).
 *
 * PERIODIC mode uses denominator N (size), which is appropriate for FFT-based
 * spectral analysis where the window is applied to periodic signals.
 */
TEST(WindowFunctionsTest, PeriodicModeNumericalCorrectness) {
    const int size = 256;

    // Test PERIODIC mode (default): denominator = N
    for (int i = 0; i < size; ++i) {
        double expected_hann = 0.5 * (1.0 - std::cos(2.0 * M_PI * i / size));
        double actual_hann = hann_base(i, size);  // Default is PERIODIC
        EXPECT_NEAR(actual_hann, expected_hann, 1e-10)
            << "PERIODIC mode correctness broken at i=" << i;
    }
}

/**
 * @test WindowFunctionsTest.SymmetricModeNumericalCorrectness
 * @brief Verifies SYMMETRIC mode produces correct results (for signal analysis).
 *
 * SYMMETRIC mode uses denominator (N-1), which is appropriate for non-periodic
 * signal analysis where the window endpoints should reach exactly 0.
 */
TEST(WindowFunctionsTest, SymmetricModeNumericalCorrectness) {
    const int size = 256;

    // Test SYMMETRIC mode (explicit parameter): denominator = N-1
    for (int i = 0; i < size; ++i) {
        double expected_hann = 0.5 * (1.0 - std::cos(2.0 * M_PI * i / (size - 1)));
        double actual_hann = hann_base(i, size, WindowSymmetry::SYMMETRIC);
        EXPECT_NEAR(actual_hann, expected_hann, 1e-10)
            << "SYMMETRIC mode correctness broken at i=" << i;
    }

    // Test Blackman in SYMMETRIC mode as well
    for (int i = 0; i < size; ++i) {
        double ratio = static_cast<double>(i) / (size - 1);
        double expected_blackman = 0.42 - 0.5 * std::cos(2.0 * M_PI * ratio) +
                                   0.08 * std::cos(4.0 * M_PI * ratio);
        double actual_blackman = blackman_base(i, size, WindowSymmetry::SYMMETRIC);
        EXPECT_NEAR(actual_blackman, expected_blackman, 1e-10)
            << "SYMMETRIC mode correctness broken for Blackman at i=" << i;
    }
}

/**
 * @test WindowFunctionsTest.WindowSymmetryModes
 * @brief Verifies that PERIODIC and SYMMETRIC modes produce different results.
 *
 * This test ensures that:
 * 1. Both symmetry modes work correctly for all window types
 * 2. The modes produce measurably different outputs (policy is effective)
 * 3. The difference is most significant near window edges
 *
 * Usage guidelines:
 * - PERIODIC: Use for FFT-based spectral analysis (default)
 * - SYMMETRIC: Use for time-domain signal analysis
 */
TEST(WindowFunctionsTest, WindowSymmetryModes) {
    const int size = 128;

    // Test Hann window with both modes
    for (int i = 0; i < size; ++i) {
        double periodic = hann_base(i, size, WindowSymmetry::PERIODIC);
        double symmetric = hann_base(i, size, WindowSymmetry::SYMMETRIC);

        // Both should be finite and valid
        EXPECT_TRUE(std::isfinite(periodic));
        EXPECT_TRUE(std::isfinite(symmetric));
        EXPECT_GE(periodic, 0.0);
        EXPECT_GE(symmetric, 0.0);
        EXPECT_LE(periodic, 1.0);
        EXPECT_LE(symmetric, 1.0);

        // Near the edges, the modes should produce different values
        // (except at i=0 where both are ~0)
        if (i > 10 && i < size - 10) {
            EXPECT_NE(periodic, symmetric)
                << "PERIODIC and SYMMETRIC should differ at i=" << i;
        }
    }

    // Test Blackman window with both modes
    for (int i = 0; i < size; ++i) {
        double periodic = blackman_base(i, size, WindowSymmetry::PERIODIC);
        double symmetric = blackman_base(i, size, WindowSymmetry::SYMMETRIC);

        EXPECT_TRUE(std::isfinite(periodic));
        EXPECT_TRUE(std::isfinite(symmetric));

        // Modes should produce different values
        if (i > 10 && i < size - 10) {
            EXPECT_NE(periodic, symmetric)
                << "PERIODIC and SYMMETRIC should differ for Blackman at i=" << i;
        }
    }

    // Test via fill_window() interface
    std::vector<float> periodic_buffer(size);
    std::vector<float> symmetric_buffer(size);

    fill_window(periodic_buffer.data(), size, WindowKind::HANN, false, WindowSymmetry::PERIODIC);
    fill_window(symmetric_buffer.data(), size, WindowKind::HANN, false, WindowSymmetry::SYMMETRIC);

    // Verify the buffers differ
    bool buffers_differ = false;
    for (int i = 0; i < size; ++i) {
        if (std::abs(periodic_buffer[i] - symmetric_buffer[i]) > 1e-6f) {
            buffers_differ = true;
            break;
        }
    }
    EXPECT_TRUE(buffers_differ)
        << "fill_window() should produce different results for different symmetry modes";
}
