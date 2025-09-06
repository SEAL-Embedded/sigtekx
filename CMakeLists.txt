cmake_minimum_required(VERSION 3.25)
project(ionosense_hpc LANGUAGES CXX)

# ============================================================================
# Global setup
# ============================================================================
set(CMAKE_CXX_STANDARD 17)
## CUDA settings are configured conditionally later when IONO_WITH_CUDA is ON

set(CMAKE_POSITION_INDEPENDENT_CODE ON)     # (PIC) For ion_engine static lib to be used in _engine shared lib - Important for Linux!
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION OFF) # (IPO) Interferes with nvcc's own LTO; Can damage _engine bindings; Do not enable/remove!
# Use the static C-Runtime on MSVC to match CUDA::cudart_static and avoid DLL dependencies
if(MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

option(IONO_WITH_TESTS   "Build tests"            ON)
option(IONO_WITH_GRAPHS  "Enable CUDA Graphs"     ON)
option(IONO_WITH_PYTHON  "Build Python bindings"  ON)
option(IONO_WITH_CUDA    "Enable CUDA components" ON)


# ============================================================================
# Compiler Flags for Release and Debug Builds
# ============================================================================
if(IONO_WITH_CUDA)
  enable_language(CUDA)
  set(CMAKE_CUDA_STANDARD 17)
  set(CMAKE_CUDA_ARCHITECTURES 75 86 89) # NVIDIA Turing, Ampere, Ada Lovelace
  set(CMAKE_CUDA_RUNTIME_LIBRARY Static) # Use static runtime for CUDA on Windows
  # --- CUDA Flags (apply to all platforms) ---
  set(CMAKE_CUDA_FLAGS "${CMAKE_CUDA_FLAGS} -diag-suppress 177") # Suppress unused warnings from nvcc
  set(CMAKE_CUDA_FLAGS_DEBUG "${CMAKE_CUDA_FLAGS_DEBUG} -g -G -O0")
  set(CMAKE_CUDA_FLAGS_RELEASE "${CMAKE_CUDA_FLAGS_RELEASE} -O3 -DNDEBUG")
endif()

# --- C++ Platform-Specific Flags ---
if(MSVC)
  # Flags for Microsoft Visual C++ Compiler (cl.exe)
  set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} /Zi /Od")
  set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} /O2 /DNDEBUG")
else()
  # Flags for GCC/Clang
  set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} -g -O0")
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3 -DNDEBUG")
endif()


# ============================================================================
# C++ Quality-of-Life Tools (Linter, Formatter)
# ============================================================================
find_program(CLANG_FORMAT clang-format)
if(CLANG_FORMAT)
    file(GLOB_RECURSE ALL_CXX_FILES
        "src/*.cpp" "src/*.cu"
        "include/ionosense/*.hpp"
        "tests/*.cpp"
        "bindings/*.cpp"
    )
    add_custom_target(format COMMAND ${CLANG_FORMAT} -i ${ALL_CXX_FILES})
endif()

find_program(CLANG_TIDY clang-tidy)
if(CLANG_TIDY)
    set(CMAKE_CXX_CLANG_TIDY
        ${CLANG_TIDY}
        -checks=-*,readability-*,performance-*,portability-*,modernize-*
        -header-filter=${CMAKE_CURRENT_SOURCE_DIR}/.*
        --extra-arg-before=--driver-mode=cl
        --extra-arg=/EHsc
    )
endif()


# ============================================================================
# Deps (Python, CUDA, Pybind11, GTest)
# ============================================================================
set(Python3_FIND_VIRTUALENV FIRST)      # Prefer venv/conda over system Python;
find_package(Python3 3.11 REQUIRED      # provides [ Python3_EXECUTABLE, Python3_INCLUDE_DIRS, Python3_LIBRARIES ]
    COMPONENTS Interpreter Development)

if(IONO_WITH_CUDA)
find_package(CUDAToolkit REQUIRED)      # provides [ CUDAToolkit_INCLUDE_DIRS, CUDA::cudart_static, CUDA::cufft ]
endif()

# --- Robust pybind11 discovery ---     # provides [ pybind11::module, pybind11::embed, ... ]
# When building with scikit-build-core, the build env already exposes the
# pybind11 CMake package on CMAKE_PREFIX_PATH. Avoid custom Python probing.
if (DEFINED SKBUILD)
    find_package(pybind11 CONFIG REQUIRED)
else()
    # 1) Try CMake config first
    find_package(pybind11 CONFIG QUIET)
    if (NOT pybind11_FOUND)
        # 2) Probe current Python for pybind11's CMake dir
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
endif()

# --- Build GTest from source using FetchContent --- # provides [ GTest::gtest, GTest::gtest_main, ... 
include(FetchContent)
FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG    v1.14.0
)


# ============================================================================
# Core static lib with CUDA kernels
# ============================================================================
if(IONO_WITH_CUDA)
add_library(ion_engine OBJECT
    src/ops_fft.cu
    src/research_engine.cpp
    src/processing_stage.cpp
)
target_include_directories(ion_engine PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CUDAToolkit_INCLUDE_DIRS}
)
set_target_properties(ion_engine PROPERTIES CUDA_SEPARABLE_COMPILATION ON) # Enables device code linking between .cu files - Important!
target_link_libraries(ion_engine PUBLIC CUDA::cufft)
endif()


# ============================================================================
# Python module (pybind11)
# ============================================================================
if(IONO_WITH_PYTHON AND IONO_WITH_CUDA)
    pybind11_add_module(_engine SHARED bindings/bindings.cpp) # produces [ _engine.pyd (Win) / _engine.so (linux) ]

    target_include_directories(_engine PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
    target_link_libraries(_engine PRIVATE
        "$<TARGET_OBJECTS:ion_engine>"
        pybind11::module
        CUDA::cudart_static
        CUDA::cufft
    )

    # If building via scikit-build-core, install into the package path
    if(DEFINED SKBUILD)
        # scikit-build-core provides ${SKBUILD_PLATLIB_DIR}
        install(TARGETS _engine
            LIBRARY DESTINATION ${SKBUILD_PLATLIB_DIR}/ionosense_hpc/core
            RUNTIME DESTINATION ${SKBUILD_PLATLIB_DIR}/ionosense_hpc/core
            ARCHIVE DESTINATION ${SKBUILD_PLATLIB_DIR}/ionosense_hpc/core
        )

        # If pre-staged runtime libs exist, include them in the wheel (optional)
        if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/python/src/ionosense_hpc/.libs/windows")
            install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/python/src/ionosense_hpc/.libs/windows/
                    DESTINATION ${SKBUILD_PLATLIB_DIR}/ionosense_hpc/.libs/windows)
        endif()
        if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/python/src/ionosense_hpc/.libs/linux")
            install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/python/src/ionosense_hpc/.libs/linux/
                    DESTINATION ${SKBUILD_PLATLIB_DIR}/ionosense_hpc/.libs/linux)
        endif()
    else()
        # Developer builds: drop beside the python package tree
        set(_ION_PY_OUT "${CMAKE_CURRENT_SOURCE_DIR}/python/src/ionosense_hpc/core")
        set_target_properties(_engine PROPERTIES
            LIBRARY_OUTPUT_DIRECTORY  "${_ION_PY_OUT}"
            RUNTIME_OUTPUT_DIRECTORY  "${_ION_PY_OUT}"
            CUDA_SEPARABLE_COMPILATION ON
            CUDA_RESOLVE_DEVICE_SYMBOLS ON
        )

        # ---------------- Windows: optionally stage NVIDIA runtime DLLs beside the .pyd ----------------
        if(WIN32)
            set(_LIBS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/python/src/ionosense_hpc/.libs/windows")
            file(MAKE_DIRECTORY ${_LIBS_DIR})

            # Prefer Conda bin, else CUDA_PATH, else skip
            set(_CANDIDATE_DIRS)
            if(DEFINED ENV{CONDA_PREFIX})
                list(APPEND _CANDIDATE_DIRS "$ENV{CONDA_PREFIX}/Library/bin/x64")
                list(APPEND _CANDIDATE_DIRS "$ENV{CONDA_PREFIX}/Library/bin")
            endif()
            if(DEFINED ENV{CUDA_PATH})
                list(APPEND _CANDIDATE_DIRS "$ENV{CUDA_PATH}/bin")
            endif()

            set(_FOUND_DIR "")
            foreach(_D IN LISTS _CANDIDATE_DIRS)
                if(EXISTS "${_D}")
                    set(_FOUND_DIR "${_D}")
                    break()
                endif()
            endforeach()

            if(_FOUND_DIR)
                message(STATUS "[ionosense] Staging CUDA DLLs from: ${_FOUND_DIR}")
                file(GLOB CUFFT_DLLS "${_FOUND_DIR}/cufft*.dll")
                file(GLOB CUDART_DLLS "${_FOUND_DIR}/cudart*.dll")

                if(CUFFT_DLLS OR CUDART_DLLS)
                    add_custom_command(TARGET _engine POST_BUILD
                        COMMAND ${CMAKE_COMMAND} -E copy_if_different
                            ${CUFFT_DLLS}
                            ${CUDART_DLLS}
                            ${_LIBS_DIR}
                        COMMENT "[ionosense] Staging CUDA runtime DLLs to ${_LIBS_DIR}"
                    )
                else()
                    message(WARNING "[ionosense] CUDA runtime DLLs not found in ${_FOUND_DIR}. Runtime may rely on system PATH.")
                endif()
            else()
                message(STATUS "[ionosense] No CUDA bin directory found for DLL staging; skipping.")
            endif()

            # Optional: import validation only for dev builds
            add_custom_command(TARGET _engine POST_BUILD
                COMMAND ${Python3_EXECUTABLE} -c "import sys; sys.path.insert(0, '${CMAKE_CURRENT_SOURCE_DIR}/python'); import ionosense_hpc; print('[ionosense] Python extension import validated successfully.')"
                COMMENT "[ionosense] Validating Python extension import"
                WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
            )
        endif()
    endif()
endif()


# ============================================================================
# Unit Tests (CTest, GTest)
# ============================================================================
if(IONO_WITH_TESTS AND IONO_WITH_CUDA)
    enable_testing()

    FetchContent_MakeAvailable(googletest)

    add_executable(test_engine
        tests/test_research_engine.cpp
        tests/test_processing_stage.cpp
        tests/test_cuda_wrappers.cpp
    )
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
