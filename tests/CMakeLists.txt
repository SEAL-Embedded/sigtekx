# ============================================================================
# C++ Test Suite Configuration
# ============================================================================

# 1. Add the executable for our tests.
add_executable(run_tests
    test_fft.cpp
)

# 2. Link the test executable against our libraries.
target_link_libraries(run_tests PRIVATE
    fft_engine
    GTest::gtest_main
    CUDA::cudart
)

# 3. Set the include directories for the test executable.
include(GoogleTest)
gtest_discover_tests(run_tests)