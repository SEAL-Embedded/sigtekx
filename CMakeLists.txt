cmake_minimum_required(VERSION 3.18)
project(CudaWorkspace LANGUAGES CXX CUDA)

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
if(DEFINED Python3_EXECUTABLE)
    message(STATUS "Using specified Python: ${Python3_EXECUTABLE}")
elseif(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/.venv/Scripts/python.exe")
    set(Python3_EXECUTABLE "${CMAKE_CURRENT_SOURCE_DIR}/.venv/Scripts/python.exe")
    message(STATUS "Auto-detected venv Python: ${Python3_EXECUTABLE}")
endif()
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter Development)

# ============================================================================
# 3. CUDA CONFIGURATION
# ============================================================================
find_package(CUDAToolkit 13.0 REQUIRED)

# ============================================================================
# 4. EXTERNAL DEPENDENCIES
# ============================================================================
include(FetchContent)

# Pybind11 for Python bindings
FetchContent_Declare(pybind11 GIT_REPOSITORY https://github.com/pybind/pybind11.git GIT_TAG v2.12.0)

# GoogleTest for C++ unit testing
FetchContent_Declare(googletest GIT_REPOSITORY https://github.com/google/googletest.git GIT_TAG v1.14.0)

FetchContent_MakeAvailable(pybind11 googletest)

# ============================================================================
# 5. CORE ENGINE LIBRARY (fft_engine)
# ============================================================================
# Create a static library for the core FFT engine.
# This allows both the Python module and the C++ tests to link against it.
add_library(fft_engine STATIC
    src/fft/cuda_fft.cu
)

# Link the engine against required CUDA libraries
target_link_libraries(fft_engine PRIVATE CUDA::cufft CUDA::cudart)

# Expose the include directory for other targets (like our tests)
target_include_directories(fft_engine PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src/fft
)


# ============================================================================
# 6. CREATE PYTHON MODULE (cuda_lib)
# ============================================================================
pybind11_add_module(cuda_lib SHARED
    src/bindings/bindings.cpp
)

# Link the Python module against our core engine library
target_link_libraries(cuda_lib PRIVATE fft_engine CUDA::cudart)


# ============================================================================
# 7. DEPENDENCY DEPLOYMENT
# ============================================================================
if(WIN32)
    set(REQUIRED_DLLS cufft64_12.dll cudart64_13.dll)
    
foreach(DLL_NAME ${REQUIRED_DLLS})
    # Use a unique variable name for each find_file call to avoid issues in the loop
    find_file(DLL_PATH_${DLL_NAME} NAMES ${DLL_NAME} HINTS "${CUDAToolkit_BIN_DIR}")
    
    if(DLL_PATH_${DLL_NAME})
        message(STATUS "Found CUDA dependency: ${DLL_PATH_${DLL_NAME}}")
        add_custom_command(TARGET cuda_lib POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${DLL_PATH_${DLL_NAME}}"
                "$<TARGET_FILE_DIR:cuda_lib>"
            COMMENT "Deploying ${DLL_NAME} to output directory..."
        )
    else()
        message(WARNING "Could not find required CUDA DLL: ${DLL_NAME}")
    endif()
endforeach()
endif()

# ============================================================================
# 8. TESTING SETUP
# ============================================================================
# Enable CTest and define the BUILD_TESTING option (defaults to ON)
include(CTest)

# Only add the tests subdirectory if the user has testing enabled.
# This is the standard way to make testing modular and optional.
if(BUILD_TESTING)
    add_subdirectory(tests)
endif()