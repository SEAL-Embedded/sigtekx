# Stage 1: The "builder" stage for compiling C++/CUDA and Python dependencies
FROM nvidia/cuda:13.0.0-devel-ubuntu22.04 AS builder

# Set the working directory
WORKDIR /app

# Suppress interactive prompts from apt-get.
ENV DEBIAN_FRONTEND=noninteractive

# Install build essentials and Miniconda
RUN apt-get update && apt-get install -y build-essential wget && \
    wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh && \
    bash miniconda.sh -b -p /opt/conda && \
    rm miniconda.sh && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Add Conda to the PATH
ENV PATH="/opt/conda/bin:${PATH}"

# Accept Conda's Terms of Service non-interactively.
RUN conda config --set auto_update_conda false && \
    conda config --set channel_priority strict && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# Create the Conda environment from a dedicated "build" environment file
COPY environments/environment.build.yml .
RUN conda env create -f environment.build.yml && conda clean -afy

# Activate the Conda environment for subsequent commands
SHELL ["conda", "run", "-n", "sigtekx", "/bin/bash", "-c"]

# Suppress git-python warning (no git binary in container — expected)
ENV GIT_PYTHON_REFRESH=quiet

# Copy build configuration and all source code required for the C++ build.
# This includes the Python package directory, which CMake uses as the install destination for shared libraries.
COPY pyproject.toml .
COPY CMakeLists.txt CMakePresets.json ./
COPY src/ ./src/
COPY cpp/ ./cpp/

# Build the C++/CUDA components.
# This layer is cached as long as C++ or Python source doesn't change.
# The compiled extension will be placed inside the src/sigtekx directory.
ENV PYTHONPATH="/app/src"
RUN cmake --preset ci-linux && cmake --build --preset ci-linux-build

# Copy benchmark and experiment configurations for cloud/SageMaker runs.
# Placed after C++ build to preserve cache when only configs change.
COPY benchmarks/ ./benchmarks/
COPY experiments/conf/ ./experiments/conf/

# Copy the test files.
# We copy this last because tests might change frequently, and we don't want
# that to invalidate the C++ build cache.
COPY tests/ ./tests/

# Build the Python wheel
# This packages the Python code and the compiled C++ extension (.so file)
# into a single .whl file in the 'dist' directory.
COPY README.md .
RUN pip wheel . --wheel-dir dist/

# This ensures commands run against the CI image execute inside the conda env
ENTRYPOINT ["conda", "run", "-n", "sigtekx", "--no-capture-output"]

# ==================================================================================

# Stage 2: The "final" stage for the production image
FROM nvidia/cuda:13.0.0-runtime-ubuntu22.04

# Set the working directory
WORKDIR /app

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -s /bin/bash -d /app appuser

# Install Miniconda
# We need a separate Miniconda install for the final stage
RUN apt-get update && apt-get install -y wget && \
    wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh && \
    bash miniconda.sh -b -p /opt/conda && \
    rm miniconda.sh && \
    chown -R appuser:appuser /opt/conda && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Add Conda to the PATH
ENV PATH="/opt/conda/bin:${PATH}"

# Accept Conda's Terms of Service non-interactively.
RUN conda config --set auto_update_conda false && \
    conda config --set channel_priority strict && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r


# Create the clean runtime Conda environment
COPY --chown=appuser:appuser environments/environment.runtime.yml .
RUN conda env create -f environment.runtime.yml && conda clean -afy

# Activate the Conda environment
SHELL ["conda", "run", "-n", "sigtekx", "/bin/bash", "-c"]

# Suppress git-python warning (no git binary in container — expected)
ENV GIT_PYTHON_REFRESH=quiet

# Copy the Python wheel from the builder stage
COPY --from=builder --chown=appuser:appuser /app/dist/ .

# Install the Python wheel, then add workflow extras (hydra, omegaconf) for benchmarks
RUN pip install *.whl && pip install "sigtekx[workflow]"

# Copy benchmark scripts and experiment configs for SageMaker Processing Jobs.
COPY --chown=appuser:appuser benchmarks/ ./benchmarks/
COPY --chown=appuser:appuser experiments/conf/ ./experiments/conf/

# Create writable directories for benchmark output and MLflow artifacts
RUN mkdir -p /app/artifacts /app/mlruns && chown -R appuser:appuser /app/artifacts /app/mlruns

# Switch to the non-root user
USER appuser

# Set the entrypoint for the container
ENTRYPOINT ["conda", "run", "-n", "sigtekx", "--no-capture-output"]

# Default: run a quick validation benchmark
CMD ["python", "benchmarks/run_latency.py", "experiment=ionosphere_test", "+benchmark=latency"]
