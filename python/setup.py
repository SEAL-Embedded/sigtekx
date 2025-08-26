from setuptools import setup, find_packages

setup(
    name="ionosense_hpc",
    version="0.1.0",
    packages=find_packages(),
    author="Kevin Rahsaz",
    description="A high-performance CUDA FFT engine and benchmarking suite.",
    long_description="A library for signal processing with CUDA and Python.",
    url="https://github.com/SEAL-Embedded/ionosense-hpc-lib",
    license="MIT",
)