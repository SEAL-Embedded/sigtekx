"""
End-to-end integration tests that verify the entire stack, from Python API
down to the CUDA kernels, by comparing results against a trusted reference.
"""
import pytest
import numpy as np
from numpy.testing import assert_allclose

from ionosense_hpc import FFTProcessor
from ionosense_hpc.utils.signals import generate_test_signal, create_window, SignalParameters

@pytest.mark.parametrize("fft_size", [1024, 4096])
@pytest.mark.parametrize("batch_size", [2, 8])
def test_numerical_accuracy_vs_numpy(fft_size, batch_size):
    """
    Compares the GPU FFT output against NumPy's rfft for a known signal.
    This is the most critical test for ensuring correctness.
    """
    # 1. Setup
    processor = FFTProcessor(fft_size=fft_size, batch_size=batch_size, window='hann')
    
    # Generate signals that are exactly fft_size long
    params = SignalParameters(duration=fft_size/100_000, sample_rate=100_000)
    signals = generate_test_signal(params)
    
    ch1 = signals['ch1'][:fft_size]
    ch2 = signals['ch2'][:fft_size]

    # Create a full batch of inputs for the processor
    # This repeats the two channels until the batch is full
    inputs = [ch1, ch2] * (batch_size // 2) 
    if batch_size % 2 != 0:
        inputs.append(ch1)
    
    input_batch = np.array(inputs)

    # 2. GPU Processing
    gpu_result = processor.process_batch(input_batch)

    # 3. CPU Reference Processing (NumPy)
    window = create_window('hann', fft_size)
    
    # Apply window and compute FFT for each signal in the batch
    windowed_batch = input_batch * window
    cpu_result = np.abs(np.fft.rfft(windowed_batch, axis=1))

    # 4. Comparison
    # We use a relative tolerance (rtol) because absolute error can be large for
    # high-magnitude values, but the relative difference should be small.
    # A tolerance of 1e-5 is standard for float32 comparisons.
    assert_allclose(gpu_result, cpu_result, rtol=1e-5, atol=1e-5,
                    err_msg="GPU results differ significantly from NumPy reference.")
