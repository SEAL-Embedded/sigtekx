# 1. Start with the official NVIDIA CUDA development image.
FROM nvidia/cuda:13.0.0-devel-ubuntu22.04

# 2. Set the working directory inside the container.
WORKDIR /app

# 3. Suppress interactive prompts from apt-get.
ENV DEBIAN_FRONTEND=noninteractive

# 4. Install Miniconda.
RUN apt-get update && \
    apt-get install -y wget && \
    wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh && \
    bash miniconda.sh -b -p /opt/conda && \
    rm miniconda.sh && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 5. Add Conda to the PATH environment variable.
ENV PATH="/opt/conda/bin:${PATH}"

# 6. Accept Conda's Terms of Service non-interactively.
RUN conda config --set auto_update_conda false && \
    conda config --set channel_priority strict && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# 7. Copy ONLY the environment file first to leverage caching.
COPY environment.linux.yml .

# 8. Create the Conda environment from the file.
RUN conda env create -f environment.linux.yml && conda clean -afy

# 9. Tell Docker to run subsequent RUN commands inside the activated conda environment.
SHELL ["/opt/conda/bin/conda", "run", "-n", "ionosense-hpc", "/bin/bash", "-c"]

# 10. Now, copy the rest of your project files.
COPY . .

# 11. Install the Python package itself in editable mode with dev dependencies.
RUN pip install .[dev]

# 12. Set the entrypoint to automatically use the conda environment.
ENTRYPOINT ["/opt/conda/bin/conda", "run", "-n", "ionosense-hpc", "--no-capture-output"]