cmake_minimum_required(VERSION 3.25)
project(ionosense_hpc LANGUAGES CXX CUDA)

# ============================================================================
# Global setup
# ============================================================================
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_ARCHITECTURES 75 86 89) # NVIDIA Turing, Ampere, Ada Lovelace

set(CMAKE_POSITION_INDEPENDENT_CODE ON)     # (PIC) For ion_engine static lib to be used in _engine shared lib - Important for Linux!
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION OFF) # (IPO) Interferes with nvcc's own LTO; Can damage _engine bindings; Do not enable/remove!
set(CMAKE_CUDA_RUNTIME_LIBRARY Static)		# Use static runtime for CUDA; For Windows builds to avoid dependency on cudart64_*.DLL - Important!

# Use the static C-Runtime on MSVC to match CUDA::cudart_static and avoid DLL dependencies
if(MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

option(IONO_WITH_TESTS   "Build tests"            ON)
option(IONO_WITH_GRAPHS  "Enable CUDA Graphs"     ON)
option(IONO_WITH_PYTHON  "Build Python bindings"  ON)


# ============================================================================
# Deps (Python, CUDA, Pybind11, GTest)
# ============================================================================
set(Python3_FIND_VIRTUALENV FIRST)      # Prefer venv/conda over system Python; Important!
find_package(Python3 3.11 REQUIRED      # provides [ Python3_EXECUTABLE, Python3_INCLUDE_DIRS, Python3_LIBRARIES ]
    COMPONENTS Interpreter Development)

find_package(CUDAToolkit REQUIRED)      # provides [ CUDAToolkit_INCLUDE_DIRS, CUDA::cudart_static, CUDA::cufft ]

# --- Robust pybind11 discovery ---     # provides [ pybind11::module, pybind11::embed, ... ]
# 1. lowkey try to find pybind11 via CMake first
find_package(pybind11 CONFIG QUIET)

if (NOT pybind11_FOUND)
    # 2. run a Python command to get the pybind11 cmake dir
    execute_process(
        COMMAND "${Python3_EXECUTABLE}" -c "import pybind11, sys; sys.stdout.write(pybind11.get_cmake_dir())"
        OUTPUT_VARIABLE pybind11_CMAKE_DIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )

    # 3. If the directory exists, add it to CMAKE_PREFIX_PATH and try to find pybind11 again via CMake
    if (EXISTS "${pybind11_CMAKE_DIR}")
        list(APPEND CMAKE_PREFIX_PATH "${pybind11_CMAKE_DIR}")
        find_package(pybind11 CONFIG REQUIRED)
    else()
        message(FATAL_ERROR "pybind11 not found in ${Python3_EXECUTABLE}")
    endif()
endif()

# --- Build GTest from source using FetchContent --- # provides [ GTest::gtest, GTest::gtest_main, ... ]
include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG    v1.14.0
)


# ============================================================================
# Core static lib with CUDA kernels
# ============================================================================
add_library(ion_engine OBJECT
    src/fft_engine.cpp
    src/ops_fft.cu
)
target_include_directories(ion_engine PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CUDAToolkit_INCLUDE_DIRS}
)
set_target_properties(ion_engine PROPERTIES CUDA_SEPARABLE_COMPILATION ON) # Enables device code linking between .cu files - Important!
target_link_libraries(ion_engine PUBLIC CUDA::cufft)


# ============================================================================
# Python module (pybind11)
# ============================================================================
if(IONO_WITH_PYTHON)
    pybind11_add_module(_engine SHARED bindings/bindings.cpp) # produces [ _engine.pyd (Win) / _engine.so (linux) ]

    # Where the Python extension should live at build time
    set(_ION_PY_OUT "${CMAKE_CURRENT_SOURCE_DIR}/python/ionosense_hpc/core")

    set_target_properties(_engine PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY  "${_ION_PY_OUT}"
        RUNTIME_OUTPUT_DIRECTORY  "${_ION_PY_OUT}"
        CUDA_SEPARABLE_COMPILATION ON
        CUDA_RESOLVE_DEVICE_SYMBOLS ON
    )

    target_include_directories(_engine PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include) # Add include dirs - Important!

    # Link against the object files from ion_engine directly + pybind11 + CUDA
    target_link_libraries(_engine PRIVATE
        "$<TARGET_OBJECTS:ion_engine>"
        pybind11::module
        CUDA::cudart_static
        CUDA::cufft
    )

    # ---------------- Windows: stage NVIDIA runtime DLLs beside the .pyd ----------------
    if(WIN32)
        set(_LIBS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/python/ionosense_hpc/.libs/windows")
        file(MAKE_DIRECTORY ${_LIBS_DIR})

        # --- Step 1: Verify Conda Environment and Set the Correct Path ---
        if(NOT DEFINED ENV{CONDA_PREFIX})
            message(FATAL_ERROR "[ionosense] FATAL: CONDA_PREFIX environment variable not set.")
        endif()
        
        # Set the precise, user-provided path for the DLLs
        set(_CONDA_BIN_DIR "$ENV{CONDA_PREFIX}/Library/bin/x64")
        message(STATUS "[ionosense] Searching for CUDA DLLs in the correct path: ${_CONDA_BIN_DIR}")

        # --- Step 2: Locate DLLs using a controlled GLOB ---
        file(GLOB CUFFT_DLLS "${_CONDA_BIN_DIR}/cufft*.dll")
        file(GLOB CUDART_DLLS "${_CONDA_BIN_DIR}/cudart*.dll")

        # --- Step 3: Verify the DLLs were found ---
        if(NOT CUFFT_DLLS OR NOT CUDART_DLLS)
            message(FATAL_ERROR "[ionosense] FATAL: Could not locate CUDA runtime DLLs in the specific path '${_CONDA_BIN_DIR}'.\n"
                            "    Please manually verify the files exist in that exact folder.")
        endif()

        message(STATUS "[ionosense] Found cuFFT DLL(s):  ${CUFFT_DLLS}")
        message(STATUS "[ionosense] Found CUDArt DLL(s): ${CUDART_DLLS}")

        set(_REQUIRED_DLLS ${CUFFT_DLLS} ${CUDART_DLLS})

        # --- Step 4: Add post-build commands for staging and validation ---
        add_custom_command(TARGET _engine POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different ${_REQUIRED_DLLS} "${_LIBS_DIR}"
            COMMENT "[ionosense] Staging CUDA DLLs to '${_LIBS_DIR}'"
            COMMAND_EXPAND_LISTS
        )

        add_custom_command(TARGET _engine POST_BUILD
            COMMAND ${Python3_EXECUTABLE} -c "import sys; sys.path.insert(0, '${CMAKE_CURRENT_SOURCE_DIR}/python'); import ionosense_hpc; print('[ionosense] Python extension import validated successfully.')"
            COMMENT "[ionosense] Validating Python extension import"
            WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        )
    endif()

endif()


# ============================================================================
# Unit Tests (CTest, GTest)
# ============================================================================
if(IONO_WITH_TESTS)
    enable_testing()

    FetchContent_MakeAvailable(googletest)

    add_executable(test_engine tests/test_fft_engine.cpp)
    set_target_properties(test_engine PROPERTIES CUDA_SEPARABLE_COMPILATION ON CUDA_RESOLVE_DEVICE_SYMBOLS ON)

    # Add include dirs and set CUDA properties for the test executable - Important!
    target_include_directories(test_engine PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)

    # Link against the object files from ion_engine directly + GTest + CUDA
    target_link_libraries(test_engine PRIVATE
        "$<TARGET_OBJECTS:ion_engine>"
        GTest::gtest_main
        CUDA::cudart_static
        CUDA::cufft
    )

    include(GoogleTest)
    gtest_discover_tests(test_engine)
endif()