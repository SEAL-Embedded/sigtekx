cmake_minimum_required(VERSION 3.24)
project(ionosense_hpc LANGUAGES CXX CUDA)

# ============================================================================
# Global setup
# ============================================================================
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(IONO_WITH_TESTS   "Build tests"            ON)
option(IONO_WITH_GRAPHS  "Enable CUDA Graphs"     ON)
option(IONO_WITH_PYTHON  "Build Python bindings"  ON)

set(CMAKE_CUDA_ARCHITECTURES 75 86 89)
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION OFF)

# ============================================================================
# Deps (Python/pybind11, CUDA, GTest)
# ============================================================================
set(Python3_FIND_VIRTUALENV FIRST)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter Development)
find_package(CUDAToolkit REQUIRED)

# --- Robust pybind11 discovery ---
find_package(pybind11 CONFIG QUIET)
if (NOT pybind11_FOUND)
  execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c "import pybind11, sys; sys.stdout.write(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE pybind11_CMAKE_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
  )
  if (EXISTS "${pybind11_CMAKE_DIR}")
    list(APPEND CMAKE_PREFIX_PATH "${pybind11_CMAKE_DIR}")
    find_package(pybind11 CONFIG REQUIRED)
  else()
    message(FATAL_ERROR "pybind11 not found in ${Python3_EXECUTABLE}")
  endif()
endif()

# --- Build GTest from source using FetchContent ---
include(FetchContent)
FetchContent_Declare(
  googletest
  GIT_REPOSITORY https://github.com/google/googletest.git
  GIT_TAG    v1.14.0
)
# For Windows: Prevent overriding the parent project's compiler options
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

# ============================================================================
# Core static lib with CUDA kernels
# ============================================================================
add_library(ion_engine STATIC
    src/fft_engine.cpp
    src/ops_fft.cu
)
target_include_directories(ion_engine PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CUDAToolkit_INCLUDE_DIRS}
)
set_target_properties(ion_engine PROPERTIES CUDA_SEPARABLE_COMPILATION ON)
target_link_libraries(ion_engine PUBLIC CUDA::cufft)

# ============================================================================
# Python module (pybind11)
# ============================================================================
if(IONO_WITH_PYTHON)
    pybind11_add_module(cuda_lib SHARED bindings/bindings.cpp)
    target_include_directories(cuda_lib PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
    set_target_properties(cuda_lib PROPERTIES
        CUDA_SEPARABLE_COMPILATION ON
        CUDA_RESOLVE_DEVICE_SYMBOLS ON
    )
    if(MSVC)
        set_target_properties(cuda_lib PROPERTIES LINK_FLAGS "/WHOLEARCHIVE:ion_engine")
    else()
        target_link_libraries(cuda_lib PRIVATE "-Wl,--whole-archive" ion_engine "-Wl,--no-whole-archive")
    endif()
    target_link_libraries(cuda_lib PRIVATE ion_engine pybind11::module CUDA::cudart_static CUDA::cufft)
endif()

# ============================================================================
# Tests
# ============================================================================
if(IONO_WITH_TESTS)
    enable_testing()
    add_executable(test_fft tests/test_fft_engine.cpp)
    target_include_directories(test_fft PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
    set_target_properties(test_fft PROPERTIES CUDA_RESOLVE_DEVICE_SYMBOLS ON)
    if(MSVC)
        set_target_properties(test_fft PROPERTIES LINK_FLAGS "/WHOLEARCHIVE:ion_engine")
    else()
        target_link_libraries(test_fft PRIVATE "-Wl,--whole-archive" ion_engine "-Wl,--no-whole-archive")
    endif()
    target_link_libraries(test_fft PRIVATE ion_engine GTest::gtest_main CUDA::cudart_static CUDA::cufft)
    include(GoogleTest)
    gtest_discover_tests(test_fft)
endif()
