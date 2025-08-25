cmake_minimum_required(VERSION 3.18)
project(ionosense-hpc-lib LANGUAGES CXX CUDA)

# ========= Project-wide =========
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_CUDA_RUNTIME_LIBRARY Shared)
# your arch list — keep as-is
set(CMAKE_CUDA_ARCHITECTURES 75 86 89)

# ========= FetchContent speed knobs (safe) =========
if (POLICY CMP0135)
  cmake_policy(SET CMP0135 NEW)  # avoid timestamp warning for URL zips
endif()
set(FETCHCONTENT_UPDATES_DISCONNECTED ON CACHE BOOL "" FORCE)

# we'll set FULLY_DISCONNECTED automatically later if cache exists

# Trim googletest unless you actually use gmock
set(BUILD_GMOCK   OFF CACHE BOOL "" FORCE)
set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)

# ========= Python / CUDA =========
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter Development Development.Module Development.Embed)
find_package(CUDAToolkit REQUIRED)

# ========= Dependencies (prefer find_package; fallback to FetchContent) =========
include(CMakeDependentOption)
include(FetchContent)

# Try conda/system first (fast path)
find_package(pybind11 CONFIG QUIET)
find_package(GTest CONFIG QUIET) # provides GTest::gtest, GTest::gtest_main

# If missing, fetch (one-time) and then go fully offline automatically
if (NOT pybind11_FOUND OR NOT GTest_FOUND)
  # Where FetchContent will put sources by default
  set(_fc_base "${FETCHCONTENT_BASE_DIR}")
  if(NOT _fc_base)
    set(_fc_base "${CMAKE_BINARY_DIR}/_deps")
  endif()

  # Decls with timestamp flag to silence CMP0135 warnings
  if (NOT pybind11_FOUND)
    FetchContent_Declare(
      pybind11
      URL https://github.com/pybind/pybind11/archive/refs/tags/v2.12.0.zip
      DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    )
  endif()

  if (NOT GTest_FOUND)
    FetchContent_Declare(
      googletest
      URL https://github.com/google/googletest/archive/refs/tags/v1.14.0.zip
      DOWNLOAD_EXTRACT_TIMESTAMP TRUE
    )
  endif()

  # First populate (online if needed)
  if (NOT pybind11_FOUND)
    FetchContent_MakeAvailable(pybind11)   # defines pybind11 targets/macros
  endif()
  if (NOT GTest_FOUND)
    FetchContent_MakeAvailable(googletest) # defines GTest::gtest(_main)
  endif()

  # After the first populate, flip fully offline for subsequent config runs
  if (EXISTS "${_fc_base}/pybind11-src/CMakeLists.txt" AND
      EXISTS "${_fc_base}/googletest-src/CMakeLists.txt")
    set(FETCHCONTENT_FULLY_DISCONNECTED ON CACHE BOOL "" FORCE)
  endif()
endif()

# ========= Core lib =========
add_library(fft_engine STATIC
  src/fft/cuda_fft.cu
  src/fft/cuda_fft.h
)
target_include_directories(fft_engine PUBLIC ${PROJECT_SOURCE_DIR}/src/fft)
target_link_libraries(fft_engine PUBLIC CUDA::cufft CUDA::cudart)

# ========= Python module =========
# pybind11 adds the helper macro when either found or fetched
pybind11_add_module(cuda_lib SHARED src/bindings/bindings.cpp)
target_link_libraries(cuda_lib PRIVATE fft_engine pybind11::module)
set_target_properties(cuda_lib PROPERTIES OUTPUT_NAME "cuda_lib")

# ========= Tests (optional toggle; default ON to preserve behavior) =========
option(IONO_BUILD_TESTS "Build unit tests" ON)
if (IONO_BUILD_TESTS)
  enable_testing()
  add_executable(run_cpp_tests tests/test_fft.cpp)
  target_link_libraries(run_cpp_tests PRIVATE
    fft_engine
    GTest::gtest_main  # available whether we found or fetched
  )
  include(GoogleTest)
  gtest_discover_tests(run_cpp_tests)
endif()
