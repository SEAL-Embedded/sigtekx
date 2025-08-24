# -*- coding: utf-8 -*-
"""
test_cuda_fft.py – Pytest suite for validating the real‑time and batch FFT paths
in cuda_fft_pybind (CudaFftEngine).

Covers:
 1. Zero input → zero spectrum
 2. Impulse input → constant magnitude
 3. Random signal → matches numpy.fft.rfft
 4. Batch vs. real‑time consistency
 5. Invalid‑shape error handling

Requirements:
  - pytest, numpy in your .venv_311
  - cuda_fft_pybind.<…>.pyd in the project root
"""
import numpy as np
import pytest

# skip entire module if the extension isn’t built
try:
    from cuda_fft_pybind import CudaFftEngine
except ImportError:
    pytest.skip("cuda_fft_pybind extension not found", allow_module_level=True)

# tolerance for float comparisons
RTOL = 1e-6
ATOL = 1e-6


@pytest.mark.parametrize("nfft,batch", [
    (16, 1),
    (64, 2),
    (128, 3),
])
def test_zero_input(nfft, batch):
    """
    All-zero input → all-zero magnitude spectrum.
    """
    eng = CudaFftEngine(nfft, batch)

    # zero‑fill the pinned input
    eng.pinned_input()[:] = 0.0
    eng.compute()

    out = eng.pinned_output()
    assert out.shape == ((nfft // 2 + 1) * batch,)
    np.testing.assert_allclose(out, 0.0, rtol=RTOL, atol=ATOL)


@pytest.mark.parametrize("nfft,batch", [
    (16, 1),
    (64, 2),
    (128, 3),
])
def test_impulse_spectrum(nfft, batch):
    """
    Delta at t=0 in each channel → constant magnitude spectrum of 1.
    """
    eng = CudaFftEngine(nfft, batch)

    # build interleaved impulse: [1,0,0…] per channel
    buf = np.zeros(nfft * batch, dtype=np.float32)
    buf[0::nfft] = 1.0
    eng.pinned_input()[:] = buf

    eng.compute()
    out = eng.pinned_output()
    np.testing.assert_allclose(out, 1.0, rtol=RTOL, atol=ATOL)


def test_random_signal_matches_numpy():
    """
    Random float32 signal → numpy.fft.rfft magnitude.
    """
    nfft, batch = 32, 2
    eng = CudaFftEngine(nfft, batch)

    # generate reproducible random data per channel
    rng = np.random.default_rng(123)
    data = rng.standard_normal((batch, nfft), dtype=np.float32)

    # interleave: [ ch0[0],ch1[0],ch0[1],ch1[1], … ]
    inter = np.empty(nfft * batch, dtype=np.float32)
    for b in range(batch):
        inter[b::batch] = data[b]
    eng.pinned_input()[:] = inter

    eng.compute()
    out = eng.pinned_output().copy().reshape(batch, -1)

    # numpy reference magnitudes
    ref = np.abs(np.fft.rfft(data, axis=1))
    np.testing.assert_allclose(out, ref, rtol=RTOL, atol=ATOL)


@pytest.mark.parametrize("num_windows", [0, 1, 4])
def test_compute_batch_vs_compute(num_windows):
    """
    - num_windows=0 → no-op (output stays at sentinel)
    - num_windows=1 → matches real‑time compute()
    - higher num_windows runs without error
    """
    nfft, batch = 64, 2
    eng = CudaFftEngine(nfft, batch)

    total = nfft * batch * num_windows
    data = np.ones(total, dtype=np.float32) * 2.0  # constant nonzero
    out_flat = np.full((num_windows * batch * (nfft//2+1)), -5.0, dtype=np.float32)

    # run batch path
    eng.compute_batch(num_windows, data, out_flat)
    if num_windows == 0:
        # should be untouched
        assert np.all(out_flat == -5.0)
    else:
        # magnitudes of constant input=2 should be 2*(nfft)^(0.5) at bin0? but we just check non-negativity
        assert np.all(out_flat >= 0.0)

        # compare first window to real‑time compute()
        eng.pinned_input()[:] = data[:nfft*batch]
        eng.compute()
        rt = eng.pinned_output()
        batch0 = out_flat[: batch * (nfft//2+1)]
        np.testing.assert_allclose(rt, batch0, rtol=RTOL, atol=ATOL)


def test_invalid_shape_raises():
    """
    Mismatched lengths for compute_batch should raise a RuntimeError.
    """
    eng = CudaFftEngine(32, 1)
    with pytest.raises(RuntimeError):
        eng.compute_batch(1,
                          np.zeros(10, dtype=np.float32),  # wrong length
                          np.zeros(10, dtype=np.float32))
