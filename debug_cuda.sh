#!/bin/bash

# Diagnostic script to check CUDA installation in Conda environment

echo "=== CUDA Installation Diagnostic ==="
echo ""

# Activate conda environment
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate ionosense-hpc

echo "Conda environment: $CONDA_PREFIX"
echo ""

echo "=== Checking for CUDA headers ==="
echo "Looking for cufft.h:"
find $CONDA_PREFIX -name "cufft.h" 2>/dev/null | head -5
echo ""

echo "Looking for cuda_runtime.h:"
find $CONDA_PREFIX -name "cuda_runtime.h" 2>/dev/null | head -5
echo ""

echo "=== Checking for CUDA libraries ==="
echo "Looking for libcufft.so:"
find $CONDA_PREFIX -name "libcufft.so*" 2>/dev/null | head -5
echo ""

echo "Looking for libcudart.so:"
find $CONDA_PREFIX -name "libcudart.so*" 2>/dev/null | head -5
echo ""

echo "=== Directory contents ==="
echo "Contents of $CONDA_PREFIX/targets/x86_64-linux/include (first 10 files):"
ls -la $CONDA_PREFIX/targets/x86_64-linux/include/ 2>/dev/null | head -10
echo ""

echo "Contents of $CONDA_PREFIX/lib (CUDA-related):"
ls -la $CONDA_PREFIX/lib/ | grep -E "(cuda|cufft|nvrtc)" | head -10
echo ""

echo "=== Testing nvcc ==="
echo "nvcc version:"
nvcc --version
echo ""

echo "nvcc include paths:"
echo '#include <cufft.h>' | nvcc -x cu --verbose -c - -o /dev/null 2>&1 | grep -E "(include|search)"
echo ""

conda deactivate