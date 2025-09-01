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
@pytest.mark.parametrize("batch_size", [1, 8])
def test_numerical_accuracy_vs_numpy(fft_size, batch_size):
    """
    Compares the GPU FFT output against NumPy's rfft for a known signal.
    """
    processor = FFTProcessor(fft_size=fft_size, batch_size=batch_size, window='hann')
    
    params = SignalParameters(duration=fft_size/100_000, sample_rate=100_000)
    signals = generate_test_signal(params)
    
    ch1 = signals['ch1'][:fft_size]
    ch2 = signals['ch2'][:fft_size]

    inputs = [ch1, ch2] * (batch_size // 2) 
    if batch_size % 2 != 0:
        inputs.append(ch1)
    
    input_batch = np.array(inputs, dtype=np.float32)

    # GPU Processing
    gpu_result = processor.process_batch(input_batch)

    # CPU Reference Processing
    window = create_window('hann', fft_size)
    
    # --- THE FINAL, DEFINITIVE FIX ---
    # 1. Calculate the window gain compensation factor.
    #    A Hann window reduces the signal's energy; this factor corrects for it.
    window_gain = np.sum(window)
    gain_compensation = 1.0 / window_gain if window_gain > 0 else 1.0

    # 2. Apply the window to the signal batch.
    windowed_batch = input_batch * window
    
    # 3. Compute the FFT.
    cpu_fft = np.fft.rfft(windowed_batch, axis=1)
    cpu_magnitude = np.abs(cpu_fft)
    
    # 4. Create a correctly scaled amplitude spectrum.
    #    - Multiply by 2 because this is a single-sided spectrum (rfft).
    #    - Multiply by the gain compensation factor to correct for the window.
    cpu_amplitude_spectrum = cpu_magnitude * 2.0 * gain_compensation

    # The DC (0 Hz) and Nyquist components are not doubled.
    cpu_amplitude_spectrum[:, 0] = cpu_magnitude[:, 0] * gain_compensation
    if fft_size % 2 == 0:
        cpu_amplitude_spectrum[:, -1] = cpu_magnitude[:, -1] * gain_compensation
    # ------------------------------------

    # Using a realistic tolerance for comparing float32 (GPU) vs float64 (CPU)
    assert_allclose(gpu_result, cpu_amplitude_spectrum, rtol=1e-3, atol=1e-4,
                    err_msg="GPU results differ significantly from NumPy reference.")

