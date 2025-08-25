cmake_minimum_required(VERSION 3.18)
project(ionosense-hpc-lib LANGUAGES CXX CUDA)

# ============================================================================
# 1. PROJECT-WIDE SETTINGS
# ============================================================================
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_ARCHITECTURES 75 86 89)
if(MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
endif()

# ============================================================================
# 2. PYTHON CONFIGURATION
# ============================================================================
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter Development)

# ============================================================================
# 3. CUDA TOOLKIT CONFIGURATION
# ============================================================================
if (DEFINED ENV{CONDA_PREFIX})
    # Add the conda environment to CMake's search path
    list(APPEND CMAKE_PREFIX_PATH $ENV{CONDA_PREFIX})
    message(STATUS "Conda environment detected at: $ENV{CONDA_PREFIX}")
endif()

# Find the CUDA Toolkit - this will set CUDAToolkit_INCLUDE_DIRS correctly
find_package(CUDAToolkit REQUIRED)
message(STATUS "CUDAToolkit include dirs: ${CUDAToolkit_INCLUDE_DIRS}")
message(STATUS "CUDAToolkit library dir: ${CUDAToolkit_LIBRARY_DIR}")

# Manually find cuFFT library since Conda's package doesn't create the imported target
find_library(CUFFT_LIBRARY
    NAMES cufft
    PATHS ${CUDAToolkit_LIBRARY_DIR}
          $ENV{CONDA_PREFIX}/lib
          $ENV{CONDA_PREFIX}/lib64
    REQUIRED
)
message(STATUS "Found cuFFT library: ${CUFFT_LIBRARY}")

# Find CUDA runtime library as well
find_library(CUDART_LIBRARY
    NAMES cudart
    PATHS ${CUDAToolkit_LIBRARY_DIR}
          $ENV{CONDA_PREFIX}/lib
          $ENV{CONDA_PREFIX}/lib64
    REQUIRED
)
message(STATUS "Found CUDA runtime library: ${CUDART_LIBRARY}")

# ============================================================================
# 4. EXTERNAL DEPENDENCIES (pybind11)
# ============================================================================
include(FetchContent)
FetchContent_Declare(
  pybind11
  GIT_REPOSITORY https://github.com/pybind/pybind11
  GIT_TAG        v2.12.0
)
FetchContent_MakeAvailable(pybind11)

# ============================================================================
# 5. CORE FFT ENGINE (CUDA)
# ============================================================================
add_library(fft_engine STATIC
    src/fft/cuda_fft.cu
    src/fft/cuda_fft.h
)

# Use the include directories found by CUDAToolkit
target_include_directories(fft_engine PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src/fft
    ${CUDAToolkit_INCLUDE_DIRS}  # This is the key fix
)

# Link against CUDA libraries properly
target_link_libraries(fft_engine 
    PUBLIC
        ${CUDART_LIBRARY}
        ${CUFFT_LIBRARY}
)

# ============================================================================
# 6. PYTHON BINDINGS (pybind11)
# ============================================================================
pybind11_add_module(cuda_lib SHARED
    src/bindings/bindings.cpp
)
target_link_libraries(cuda_lib PRIVATE
    fft_engine
    pybind11::module
)
set_target_properties(cuda_lib PROPERTIES
    PREFIX ""
)

# ============================================================================
# 7. TESTING SETUP
# ============================================================================
enable_testing()
FetchContent_Declare(
    googletest
    URL https://github.com/google/googletest/archive/03597a01ee50ed33e9dfd640b249b4be3799d395.zip
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
FetchContent_MakeAvailable(googletest)

add_executable(run_cpp_tests
    tests/test_fft.cpp
)
target_link_libraries(run_cpp_tests PRIVATE
    GTest::gtest_main
    fft_engine
)
include(GoogleTest)
gtest_discover_tests(run_cpp_tests)