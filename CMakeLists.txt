cmake_minimum_required(VERSION 3.25)
project(sigtekx LANGUAGES CXX)

# ============================================================================
# Global setup
# ============================================================================
set(CMAKE_CXX_STANDARD 17)
## CUDA settings are configured conditionally later when SIGTEKX_WITH_CUDA is ON

set(CMAKE_POSITION_INDEPENDENT_CODE ON)     # (PIC) For sigtekx_core static lib to be used in _native shared lib - Important for Linux!
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION OFF) # (IPO) Interferes with nvcc's own LTO; Can damage _native bindings; Do not enable/remove!
# Use the static C-Runtime on MSVC to match CUDA::cudart_static and avoid DLL dependencies
if(MSVC)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    # Narrow Windows headers and avoid macro collisions with std::min/max
    add_compile_definitions(WIN32_LEAN_AND_MEAN NOMINMAX)
endif()

option(SIGTEKX_WITH_TESTS      "Build tests"            ON)
option(SIGTEKX_WITH_GRAPHS     "Enable CUDA Graphs"     ON)
option(SIGTEKX_WITH_PYTHON     "Build Python bindings"  ON)
option(SIGTEKX_WITH_CUDA       "Enable CUDA components" ON)
option(SIGTEKX_WITH_NVTX       "Enable NVTX profiling"  ON)
option(SIGTEKX_ENABLE_COVERAGE "Enable code coverage"   OFF)


# ============================================================================
# Compiler Flags for Release and Debug Builds
# ============================================================================
if(SIGTEKX_WITH_CUDA)
  enable_language(CUDA)
  set(CMAKE_CUDA_STANDARD 17)
  set(CMAKE_CUDA_ARCHITECTURES 75 86 89) # NVIDIA Turing, Ampere, Ada Lovelace
  set(CMAKE_CUDA_RUNTIME_LIBRARY Static) # Use static runtime for CUDA on Windows

  # --- IEEE-754 Compliance Flags ---
  # --fmad=false: Disable fused multiply-add for deterministic rounding (IEEE-754 strict)
  # --ftz=false: Preserve denormal numbers (do not flush to zero)
  set(IEEE754_FLAGS "--fmad=false --ftz=false")

  # --- CUDA Flags (apply to all platforms) ---
  set(CMAKE_CUDA_FLAGS "${CMAKE_CUDA_FLAGS} -diag-suppress 177 ${IEEE754_FLAGS}") # Suppress unused warnings from nvcc
  set(CMAKE_CUDA_FLAGS_DEBUG "${CMAKE_CUDA_FLAGS_DEBUG} -g -G -lineinfo -O0")
  set(CMAKE_CUDA_FLAGS_RELEASE "${CMAKE_CUDA_FLAGS_RELEASE} -O3 -DNDEBUG")
endif()

# --- C++ Platform-Specific Flags ---
if(MSVC)
  # Flags for Microsoft Visual C++ Compiler (cl.exe)
  set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} /Zi /Od")
  set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} /O2 /DNDEBUG")

  # Code coverage flags for MSVC (use with windows-coverage preset)
  if(SIGTEKX_ENABLE_COVERAGE)
    message(STATUS "[sigtekx] Enabling code coverage instrumentation (MSVC)")
    # MSVC: gcovr uses PDB debug symbols for coverage analysis
    # /Zi and /Od are already set in CMAKE_CXX_FLAGS_DEBUG, just ensure full debug info
    set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} /DEBUG:FULL")
    set(CMAKE_EXE_LINKER_FLAGS_DEBUG "${CMAKE_EXE_LINKER_FLAGS_DEBUG} /DEBUG:FULL")
  endif()
else()
  # Flags for GCC/Clang
  set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} -g -O0")
  set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3 -DNDEBUG")

  # Code coverage flags for GCC/Clang (gcov/llvm-cov)
  if(SIGTEKX_ENABLE_COVERAGE)
    message(STATUS "[sigtekx] Enabling code coverage instrumentation (GCC/Clang)")
    set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} --coverage -fprofile-arcs -ftest-coverage")
    set(CMAKE_EXE_LINKER_FLAGS_DEBUG "${CMAKE_EXE_LINKER_FLAGS_DEBUG} --coverage")
  endif()
endif()


# ============================================================================
# C++ Quality-of-Life Tools (Linter, Formatter)
# ============================================================================
find_program(CLANG_FORMAT clang-format)
if(CLANG_FORMAT)
    file(GLOB_RECURSE ALL_CXX_FILES
        "cpp/src/*.cpp" "src/*.cu"
        "cpp/include/sigtekx/*.hpp"
        "cpp/tests/*.cpp"
        "cpp/bindings/*.cpp"
    )
    add_custom_target(format COMMAND ${CLANG_FORMAT} -i ${ALL_CXX_FILES})
endif()

option(SIGTEKX_WITH_TIDY "Run clang-tidy static analysis" OFF)
find_program(CLANG_TIDY clang-tidy)
if(SIGTEKX_WITH_TIDY AND CLANG_TIDY)
    # Keep checks focused and exclude noisy modernize ones by default
    set(CMAKE_CXX_CLANG_TIDY
        ${CLANG_TIDY}
        -checks=-*,readability-*,performance-*,portability-*,modernize-*,-modernize-use-trailing-return-type,-modernize-use-nodiscard
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

if(SIGTEKX_WITH_CUDA)
  # Modern CUDA discovery (NVTX3 is header-only and ships with toolkit)
  find_package(CUDAToolkit 13.0 REQUIRED)
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
if(SIGTEKX_WITH_CUDA)
add_library(sigtekx_core OBJECT
    # CUDA kernels (STFT pipeline operations)
    cpp/src/kernels/fft_wrapper.cu

    # Profiling
    cpp/src/profiling/nvtx.cu

    # Core infrastructure
    cpp/src/core/processing_stage.cpp
    cpp/src/core/pipeline_builder.cpp
    cpp/src/core/signal_utils.cpp

    # Executors
    cpp/src/executors/batch_executor.cpp
    cpp/src/executors/streaming_executor.cpp
)
target_include_directories(sigtekx_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/cpp/include
    ${CUDAToolkit_INCLUDE_DIRS}
)
set_target_properties(sigtekx_core PROPERTIES CUDA_SEPARABLE_COMPILATION ON) # Enables device code linking between .cu files - Important!
target_link_libraries(sigtekx_core PUBLIC CUDA::cufft)
if(SIGTEKX_WITH_NVTX)
  # Always compile profiling code; runtime will dynamically load NVTX if present
  target_compile_definitions(sigtekx_core PUBLIC SIGTEKX_ENABLE_PROFILING)
endif()
endif()


# ============================================================================
# Python module (pybind11)
# ============================================================================
if(SIGTEKX_WITH_PYTHON AND SIGTEKX_WITH_CUDA)
    pybind11_add_module(_native SHARED cpp/bindings/bindings.cpp) # produces [ _native.pyd (Win) / _native.so (linux) ]

    target_include_directories(_native PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/cpp/include)
    target_link_libraries(_native PRIVATE
        "$<TARGET_OBJECTS:sigtekx_core>"
        pybind11::module
        CUDA::cudart_static
        CUDA::cufft
    )
    if(SIGTEKX_WITH_NVTX)
        # _native compiles only bindings.cpp; profiling is handled in sigtekx_core object TUs.
        target_compile_definitions(_native PRIVATE SIGTEKX_ENABLE_PROFILING)
    endif()

    # If building via scikit-build-core, install into the package path
    if(DEFINED SKBUILD)
        # scikit-build-core provides ${SKBUILD_PLATLIB_DIR}
        install(TARGETS _native
            LIBRARY DESTINATION ${SKBUILD_PLATLIB_DIR}/sigtekx/core
            RUNTIME DESTINATION ${SKBUILD_PLATLIB_DIR}/sigtekx/core
            ARCHIVE DESTINATION ${SKBUILD_PLATLIB_DIR}/sigtekx/core
        )

        # If pre-staged runtime libs exist, include them in the wheel (optional)
        if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/sigtekx/.libs/windows")
            install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/src/sigtekx/.libs/windows/
                    DESTINATION ${SKBUILD_PLATLIB_DIR}/sigtekx/.libs/windows)
        endif()
        if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/src/sigtekx/.libs/linux")
            install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/src/sigtekx/.libs/linux/
                    DESTINATION ${SKBUILD_PLATLIB_DIR}/sigtekx/.libs/linux)
        endif()
    else()
        # Developer builds: drop beside the python package tree
        set(_SIGTEKX_PY_OUT "${CMAKE_CURRENT_SOURCE_DIR}/src/sigtekx/core")
        set_target_properties(_native PROPERTIES
            LIBRARY_OUTPUT_DIRECTORY  "${_SIGTEKX_PY_OUT}"
            RUNTIME_OUTPUT_DIRECTORY  "${_SIGTEKX_PY_OUT}"
            CUDA_SEPARABLE_COMPILATION ON
            CUDA_RESOLVE_DEVICE_SYMBOLS ON
        )

        # ---------------- Windows: optionally stage NVIDIA runtime DLLs beside the .pyd ----------------
        if(WIN32)
            set(_LIBS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src/sigtekx/.libs/windows")
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
                message(STATUS "[sigtekx] Staging CUDA DLLs from: ${_FOUND_DIR}")
                file(GLOB CUFFT_DLLS "${_FOUND_DIR}/cufft*.dll")
                file(GLOB CUDART_DLLS "${_FOUND_DIR}/cudart*.dll")

                if(CUFFT_DLLS OR CUDART_DLLS)
                    add_custom_command(TARGET _native POST_BUILD
                        COMMAND ${CMAKE_COMMAND} -E copy_if_different
                            ${CUFFT_DLLS}
                            ${CUDART_DLLS}
                            ${_LIBS_DIR}
                        COMMENT "[sigtekx] Staging CUDA runtime DLLs to ${_LIBS_DIR}"
                    )
                else()
                    message(STATUS "[sigtekx] CUDA DLLs not found in ${_FOUND_DIR} - will use system PATH (normal for some conda builds)")
                endif()
            else()
                message(STATUS "[sigtekx] No CUDA bin directory found for DLL staging; skipping.")
            endif()

            # Optional: import validation only for dev builds
            add_custom_command(TARGET _native POST_BUILD
                COMMAND ${Python3_EXECUTABLE} -c "import sys; sys.path.insert(0, '${CMAKE_CURRENT_SOURCE_DIR}/src'); import sigtekx; print('[sigtekx] Python extension import validated successfully.')"
                COMMENT "[sigtekx] Validating Python extension import"
                WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
            )
        endif()
    endif()
endif()


# ============================================================================
# Unit Tests (CTest, GTest)
# ============================================================================
if(SIGTEKX_WITH_TESTS AND SIGTEKX_WITH_CUDA)
    enable_testing()

    FetchContent_MakeAvailable(googletest)

    # Automatically include all unit test sources (organized in subdirectories)
    file(GLOB_RECURSE SIGTEKX_TEST_SOURCES CONFIGURE_DEPENDS
        "${CMAKE_CURRENT_SOURCE_DIR}/cpp/tests/**/*.cpp"
    )
    list(SORT SIGTEKX_TEST_SOURCES)

    add_executable(sigtekx_tests ${SIGTEKX_TEST_SOURCES})
    set_target_properties(sigtekx_tests PROPERTIES CUDA_SEPARABLE_COMPILATION ON CUDA_RESOLVE_DEVICE_SYMBOLS ON)

    # Add include dirs and set CUDA properties for the test executable - Important!
    target_include_directories(sigtekx_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/cpp/include)

    # Link against the object files from sigtekx_core directly + GTest + CUDA
    target_link_libraries(sigtekx_tests PRIVATE
        "$<TARGET_OBJECTS:sigtekx_core>"
        GTest::gtest_main
        CUDA::cudart_static
        CUDA::cufft
    )
    # NVTX3 is header-only in our integration; no additional linking required

    include(GoogleTest)
    gtest_discover_tests(sigtekx_tests)

    # ========================================================================
    # C++ Standalone Benchmark (Development Only)
    # ========================================================================
    # This executable is for C++ kernel development and iteration BEFORE Python
    # integration. For production profiling, use `iprof` with Python benchmarks.
    add_executable(sigtekx_benchmark
        cpp/benchmarks/main.cpp
    )
    set_target_properties(sigtekx_benchmark PROPERTIES CUDA_SEPARABLE_COMPILATION ON CUDA_RESOLVE_DEVICE_SYMBOLS ON)

    target_include_directories(sigtekx_benchmark PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/cpp/include)

    target_link_libraries(sigtekx_benchmark PRIVATE
        "$<TARGET_OBJECTS:sigtekx_core>"
        CUDA::cudart_static
        CUDA::cufft
    )

    if(SIGTEKX_WITH_NVTX)
        target_compile_definitions(sigtekx_benchmark PRIVATE SIGTEKX_ENABLE_PROFILING)
    endif()

    # ========================================================================
    # C++ Dataset Management CLI
    # ========================================================================
    # Standalone CLI for dataset operations: save, list, compare, delete.
    # Stores named snapshots under datasets/cpp/ (decoupled from Python).
    add_executable(sigtekx_dataset_cli
        cpp/benchmarks/dataset_cli.cpp
    )
    set_target_properties(sigtekx_dataset_cli PROPERTIES CUDA_SEPARABLE_COMPILATION ON CUDA_RESOLVE_DEVICE_SYMBOLS ON)

    target_include_directories(sigtekx_dataset_cli PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/cpp/include)

    target_link_libraries(sigtekx_dataset_cli PRIVATE
        "$<TARGET_OBJECTS:sigtekx_core>"
        CUDA::cudart_static
        CUDA::cufft
    )
endif()
