#!/bin/bash

# =================================================================================================
#
# ionosense-hpc-lib Command-Line Interface (CLI)
#
# This script provides a set of commands to manage the development lifecycle of the
# ionosense-hpc-lib project, including setup, building, testing, and cleaning.
# It is designed to be run in a Bash environment, particularly within WSL2.
#
# =================================================================================================

# --- Script Configuration and Helpers ---

# Exit immediately if a command exits with a non-zero status.
set -e

# Get the root directory of the project (the directory where this script is located)
# This makes the script runnable from any subdirectory.
PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# --- Color Codes for Output ---
COLOR_RESET='\033[0m'
COLOR_RED='\033[0;31m'
COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[0;33m'
COLOR_CYAN='\033[0;36m'
COLOR_BOLD='\033[1m'

# Helper function for logging messages
log() {
    echo -e "${COLOR_CYAN}[INFO]${COLOR_RESET} $1"
}

# Helper function for success messages
log_success() {
    echo -e "${COLOR_GREEN}[SUCCESS]${COLOR_RESET} $1"
}

# Helper function for warning messages
log_warn() {
    echo -e "${COLOR_YELLOW}[WARNING]${COLOR_RESET} $1"
}

# Helper function for error messages and exiting
log_error() {
    echo -e "${COLOR_RED}[ERROR]${COLOR_RESET} $1" >&2
    exit 1
}

# --- Project-Specific Variables ---
CONDA_ENV_NAME="ionosense-hpc"
ENV_FILE="environment.yml"
BUILD_DIR="build"

# --- Command Functions ---

#
# Display the help message
#
function show_help() {
    echo -e "${COLOR_BOLD}ionosense-hpc-lib CLI${COLOR_RESET}"
    echo "A script to manage the project's development lifecycle."
    echo
    echo "Usage: ./cli.sh [command]"
    echo
    echo "Commands:"
    echo -e "  ${COLOR_GREEN}setup${COLOR_RESET}      - Installs Miniconda (if needed) and creates the Conda environment."
    echo -e "  ${COLOR_GREEN}build${COLOR_RESET}      - Configures and builds the C++/CUDA source code using CMake."
    echo -e "  ${COLOR_GREEN}test${COLOR_RESET}       - Runs C++ and Python tests."
    echo -e "  ${COLOR_GREEN}clean${COLOR_RESET}      - Removes build artifacts and temporary files."
    echo -e "  ${COLOR_GREEN}dev${COLOR_RESET}        - Activates the Conda environment to start a development shell."
    echo -e "  ${COLOR_GREEN}help${COLOR_RESET}       - Shows this help message."
    echo
}

#
# Set up the development environment
#
function setup_environment() {
    log "Starting project setup..."

    # 1. Check for Conda
    if ! command -v conda &> /dev/null; then
        log_warn "Conda not found. Attempting to install Miniconda."
        # Download and install Miniconda
        local miniconda_installer="Miniconda3-latest-Linux-x86_64.sh"
        wget "https://repo.anaconda.com/miniconda/${miniconda_installer}" -O "/tmp/${miniconda_installer}"
        bash "/tmp/${miniconda_installer}" -b -p "${HOME}/miniconda"
        rm "/tmp/${miniconda_installer}"

        # Add conda to PATH for the current session and for future sessions
        export PATH="${HOME}/miniconda/bin:${PATH}"
        echo 'export PATH="${HOME}/miniconda/bin:${PATH}"' >> ~/.bashrc
        log_success "Miniconda installed successfully. Please restart your shell or run 'source ~/.bashrc' for changes to take effect."
    else
        log "Conda is already installed."
    fi

    # 2. Check if the environment already exists
    if conda env list | grep -q "${CONDA_ENV_NAME}"; then
        log "Conda environment '${CONDA_ENV_NAME}' already exists. Updating..."
        conda env update --name "${CONDA_ENV_NAME}" --file "${PROJECT_ROOT}/${ENV_FILE}" --prune
    else
        log "Creating Conda environment '${CONDA_ENV_NAME}' from ${ENV_FILE}..."
        conda env create --name "${CONDA_ENV_NAME}" --file "${PROJECT_ROOT}/${ENV_FILE}"
    fi

    log_success "Environment setup complete. Activate it with: ./cli.sh dev"
}

#
# Build the C++/CUDA source code
#
function build_project() {
    log "Building the project..."
    
    # Activate conda environment to ensure CMake finds the correct dependencies
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "${CONDA_ENV_NAME}"

    log "Configuring CMake..."
    cmake -S "${PROJECT_ROOT}" -B "${PROJECT_ROOT}/${BUILD_DIR}" \
          -DCMAKE_BUILD_TYPE=Release

    log "Compiling with CMake..."
    cmake --build "${PROJECT_ROOT}/${BUILD_DIR}" --parallel --verbose

    conda deactivate
    log_success "Project built successfully in '${BUILD_DIR}/'."
}

#
# Run all tests
#
function run_tests() {
    log "Running tests..."
    # Activate conda environment for python dependencies
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "${CONDA_ENV_NAME}"

    # Run C++ tests via CTest
    log "Running C++ tests..."
    (cd "${PROJECT_ROOT}/${BUILD_DIR}" && ctest --output-on-failure)

    # Run Python tests via pytest
    log "Running Python tests..."
    pytest "${PROJECT_ROOT}/tests/"

    conda deactivate
    log_success "All tests passed."
}

#
# Clean build artifacts
#
function clean_project() {
    log "Cleaning project..."
    if [ -d "${PROJECT_ROOT}/${BUILD_DIR}" ]; then
        rm -rf "${PROJECT_ROOT}/${BUILD_DIR}"
        log "Removed build directory: ${BUILD_DIR}"
    else
        log "Build directory not found, nothing to clean."
    fi

    # Remove Python cache files
    find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    log "Removed Python cache files."

    log_success "Project cleaned."
}

#
# Enter development shell
#
function start_dev_shell() {
    log "Activating development shell for '${CONDA_ENV_NAME}'..."
    log "Type 'exit' or press Ctrl+D to leave the shell."

    # Activate the conda environment and start a new interactive bash shell
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "${CONDA_ENV_NAME}"
    
    # The `bash -i` command starts a new interactive shell.
    # The environment variables, including the activated conda env, are inherited.
    bash -i
    
    conda deactivate
    log "Development shell closed."
}


# --- Main Script Logic ---
#
# Parses the first command-line argument and calls the corresponding function.
#
main() {
    cd "${PROJECT_ROOT}" # Ensure script operations run from the project root

    if [ $# -eq 0 ]; then
        log_error "No command provided. See usage below."
        show_help
        exit 1
    fi

    case "$1" in
        setup)
            setup_environment
            ;;
        build)
            build_project
            ;;
        test)
            run_tests
            ;;
        clean)
            clean_project
            ;;
        dev)
            start_dev_shell
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac
}

# Execute the main function with all provided command-line arguments
main "$@"