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
SHELL ["conda", "run", "-n", "ionosense-hpc", "/bin/bash", "-c"]

# Copy the source code and build the C++/CUDA components
COPY . .
RUN cmake --preset ci-linux && cmake --build --preset ci-linux-build

# Build the Python wheel
# This packages the Python code and the compiled C++ extension (.so file)
# into a single .whl file in the 'dist' directory.
RUN pip wheel . --wheel-dir dist/

# -----------------------------------------------------------------------------

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
SHELL ["conda", "run", "-n", "ionosense-hpc", "/bin/bash", "-c"]

# Copy the Python wheel from the builder stage
COPY --from=builder --chown=appuser:appuser /app/dist/ .

# Install the Python wheel using pip
# This will install your package and its Python dependencies
RUN pip install *.whl

# Switch to the non-root user
USER appuser

# Set the entrypoint for the container
ENTRYPOINT ["conda", "run", "-n", "ionosense-hpc", "--no-capture-output"]

# This runs the benchmark suite by calling its Python module directly.
# CMD ["python", "-m", "ionosense_hpc.benchmarks.suite"]