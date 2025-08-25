cmake_minimum_required(VERSION 3.18)
project(ionosense-hpc-lib LANGUAGES CXX CUDA)

# ========= Project-wide =========
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_CUDA_RUNTIME_LIBRARY Shared)
set(CMAKE_CUDA_ARCHITECTURES 86 89)

# ========= FetchContent knobs (safe) =========
if (POLICY CMP0135)
  cmake_policy(SET CMP0135 NEW)  # avoid timestamp warning for URL zips
endif()
set(FETCHCONTENT_UPDATES_DISCONNECTED ON CACHE BOOL "" FORCE)

# ========= Python / CUDA =========
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter Development Development.Module Development.Embed)
find_package(CUDAToolkit REQUIRED)

# ========= Dependencies (prefer find_package; fallback to FetchContent) =========
include(CMakeDependentOption)
include(FetchContent)

# Fast path: use preinstalled packages (Conda/system)
find_package(pybind11 CONFIG QUIET)   # provides pybind11_add_module + targets
find_package(GTest CONFIG QUIET)      # provides GTest::gtest, GTest::gtest_main

# Fallback only if missing
if (NOT pybind11_FOUND OR NOT GTest_FOUND)
  # Where FetchContent will put sources by default
  set(_fc_base "${FETCHCONTENT_BASE_DIR}")
  if(NOT _fc_base)
    set(_fc_base "${CMAKE_BINARY_DIR}/_deps")
  endif()

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
    # Trim extras
    set(BUILD_GMOCK   OFF CACHE BOOL "" FORCE)
    set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
  endif()

  if (NOT pybind11_FOUND)
    FetchContent_MakeAvailable(pybind11)
  endif()
  if (NOT GTest_FOUND)
    FetchContent_MakeAvailable(googletest)
  endif()

  # After first populate, go fully offline next time to speed up configure
  if (EXISTS "${_fc_base}/pybind11-src/CMakeLists.txt")
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
pybind11_add_module(cuda_lib SHARED src/bindings/bindings.cpp)
target_link_libraries(cuda_lib PRIVATE fft_engine pybind11::module)
set_target_properties(cuda_lib PROPERTIES OUTPUT_NAME "cuda_lib")

# ========= Tests (default ON to keep behavior the same) =========
option(IONO_BUILD_TESTS "Build unit tests" ON)
if (IONO_BUILD_TESTS)
  enable_testing()
  add_executable(run_cpp_tests tests/test_fft.cpp)
  target_link_libraries(run_cpp_tests PRIVATE
    fft_engine
    GTest::gtest_main
  )
  include(GoogleTest)
  gtest_discover_tests(run_cpp_tests)
endif()
