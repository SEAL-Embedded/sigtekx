cmake_minimum_required(VERSION 3.18)
project(ionosense-hpc-lib LANGUAGES CXX CUDA)

# ============================================================================
# 1. PROJECT-WIDE SETTINGS
# ============================================================================
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_ARCHITECTURES 75 86 89)

# Build all targets as PIC so static libs can be linked into shared modules
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Prefer shared CUDA runtime for Python extensions (avoids static cudart issues)
# Values: Shared | Static | None
set(CMAKE_CUDA_RUNTIME_LIBRARY Shared)

if(MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
endif()

# ============================================================================
# 2. PYTHON CONFIGURATION
# ============================================================================
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter Development Development.Module Development.Embed)

# ============================================================================
# 3. CUDA TOOLKIT
# ============================================================================
find_package(CUDAToolkit REQUIRED)

# ============================================================================
# 4. DEPENDENCIES (pybind11, gtest)
# ============================================================================
include(FetchContent)

# pybind11
FetchContent_Declare(
    pybind11
    URL https://github.com/pybind/pybind11/archive/refs/tags/v2.12.0.zip
)
FetchContent_MakeAvailable(pybind11)

# googletest
FetchContent_Declare(
    googletest
    URL https://github.com/google/googletest/archive/03597a01ee50ed33e9dfd640b249b4be3799d395.zip
)
FetchContent_MakeAvailable(googletest)

# ============================================================================
# 5. CORE LIB (CUDA FFT ENGINE)
# ============================================================================
add_library(fft_engine STATIC
    src/fft/cuda_fft.cu
    src/fft/cuda_fft.h
)

# Export the public include path so consumers (#include "cuda_fft.h") just work
target_include_directories(fft_engine
    PUBLIC ${PROJECT_SOURCE_DIR}/src/fft
)

# Modern, target-based linking (lets CMake handle cudart/cufft variants)
target_link_libraries(fft_engine
    PUBLIC CUDA::cufft CUDA::cudart
)

# ============================================================================
# 6. PYTHON BINDINGS (pybind11)
# ============================================================================
pybind11_add_module(cuda_lib SHARED
    src/bindings/bindings.cpp
)

# Only need to link our engine; pybind11 module target already carries Python
target_link_libraries(cuda_lib PRIVATE
    fft_engine
    pybind11::module
)

# Ensure correct SONAME and rpaths are handled by CMake; no manual flags needed
set_target_properties(cuda_lib PROPERTIES
    OUTPUT_NAME "cuda_lib"
)

# ============================================================================
# 7. TESTS (GoogleTest)
# ============================================================================
enable_testing()

add_executable(run_cpp_tests
    tests/test_fft.cpp
)

# Consumers get fft_engine’s PUBLIC includes & links (fixes "cuda_fft.h" not found)
target_link_libraries(run_cpp_tests PRIVATE
    GTest::gtest_main
    fft_engine
)

include(GoogleTest)
gtest_discover_tests(run_cpp_tests)
