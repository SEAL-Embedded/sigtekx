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

# Target SMs
set(CMAKE_CUDA_ARCHITECTURES 75 86 89)

# --- Hard-disable IPO globally (some toolchains auto-enable) ---
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION OFF)

# --- Strip out Conda toolchain's -flto=auto that gets appended after target opts ---
foreach(var CMAKE_CXX_FLAGS_RELEASE CMAKE_CXX_FLAGS_RELWITHDEBINFO
            CMAKE_CUDA_FLAGS_RELEASE CMAKE_CUDA_FLAGS_RELWITHDEBINFO)
  if(DEFINED ${var})
    string(REPLACE "-flto=auto" "" _tmp "${${var}}")
    set(${var} "${_tmp}" CACHE STRING "" FORCE)
  endif()
endforeach()

# ============================================================================
# Deps
# ============================================================================
find_package(CUDAToolkit REQUIRED)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter Development)
find_package(GTest REQUIRED)
find_package(pybind11 REQUIRED)

# ============================================================================
# Core static lib with CUDA kernels
# ============================================================================
add_library(ion_engine STATIC
    src/fft_engine.cpp
    src/ops_fft.cu
)

target_include_directories(ion_engine PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

set_target_properties(ion_engine PROPERTIES
    CUDA_SEPARABLE_COMPILATION ON
    INTERPROCEDURAL_OPTIMIZATION OFF
)

# Be explicit: no LTO anywhere on this target
target_compile_options(ion_engine PRIVATE
    $<$<COMPILE_LANGUAGE:CXX>:-fno-lto>
    $<$<COMPILE_LANGUAGE:CUDA>:-Xcompiler=-fno-lto>
)
target_link_options(ion_engine PRIVATE
    $<$<LINK_LANGUAGE:CXX>:-fno-lto>
    $<$<LINK_LANGUAGE:CUDA>:-fno-lto>            # <— NOTE: plain -fno-lto for link; CMake/NVCC will wrap as needed
)

target_link_libraries(ion_engine PUBLIC CUDA::cufft)

# ============================================================================
# Python module (pybind11)
# ============================================================================
if(IONO_WITH_PYTHON)
    pybind11_add_module(cuda_lib SHARED
        bindings/bindings.cpp
    )

    set_target_properties(cuda_lib PROPERTIES
        CUDA_SEPARABLE_COMPILATION ON
        CUDA_RESOLVE_DEVICE_SYMBOLS ON           # ensure device link on final .so
        INTERPROCEDURAL_OPTIMIZATION OFF
    )

    # No LTO during compile or link
    target_compile_options(cuda_lib PRIVATE
        $<$<COMPILE_LANGUAGE:CXX>:-fno-lto>
        $<$<COMPILE_LANGUAGE:CUDA>:-Xcompiler=-fno-lto>
    )
    target_link_options(cuda_lib PRIVATE
        $<$<LINK_LANGUAGE:CXX>:-fno-lto>
        $<$<LINK_LANGUAGE:CUDA>:-fno-lto>       # <— plain form; avoids "-Xcompiler=-Xcompiler=..."
    )

    # Pull in ALL objects from ion_engine so device fatbins can't be dropped
    target_link_libraries(cuda_lib PRIVATE
        $<LINK_LIBRARY:WHOLE_ARCHIVE,ion_engine>
        pybind11::module
        CUDA::cudart_static
    )
endif()

# ============================================================================
# Tests
# ============================================================================
if(IONO_WITH_TESTS)
    enable_testing()

    add_executable(test_fft
        tests/test_fft_engine.cpp
    )

    set_target_properties(test_fft PROPERTIES
        CUDA_RESOLVE_DEVICE_SYMBOLS ON
        INTERPROCEDURAL_OPTIMIZATION OFF
    )

    target_compile_options(test_fft PRIVATE
        $<$<COMPILE_LANGUAGE:CXX>:-fno-lto>
        $<$<COMPILE_LANGUAGE:CUDA>:-Xcompiler=-fno-lto>
    )
    target_link_options(test_fft PRIVATE
        $<$<LINK_LANGUAGE:CXX>:-fno-lto>
        $<$<LINK_LANGUAGE:CUDA>:-fno-lto>
    )

    target_link_libraries(test_fft PRIVATE
        $<LINK_LIBRARY:WHOLE_ARCHIVE,ion_engine>
        GTest::gtest_main
        CUDA::cudart_static
    )

    include(GoogleTest)
    gtest_discover_tests(test_fft)
endif()
