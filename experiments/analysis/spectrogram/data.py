"""Data structures and serialization helpers for spectrograms."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from ionosense_hpc.config import (
    EngineConfig,
    ScalePolicy,
    WindowNorm,
    WindowSymmetry,
    WindowType,
)

FloatArray = NDArray[np.float32]


@dataclass
class SpectrogramData:
    """Container for spectrogram data and metadata."""

    spectrogram: FloatArray
    times: FloatArray
    frequencies: FloatArray
    config: EngineConfig
    channel: int = 0


def save_spectrogram_data(data: SpectrogramData, path: str | Path) -> None:
    """Persist spectrogram arrays + metadata in a compressed NPZ."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    np.savez_compressed(
        path,
        spectrogram=data.spectrogram,
        times=data.times,
        frequencies=data.frequencies,
        nfft=data.config.nfft,
        channels=data.config.channels,
        overlap=data.config.overlap,
        sample_rate_hz=data.config.sample_rate_hz,
        window=data.config.window.value,
        window_symmetry=data.config.window_symmetry.value,
        window_norm=data.config.window_norm.value,
        scale=data.config.scale.value,
        channel=data.channel,
    )


def load_spectrogram_data(path: str | Path) -> SpectrogramData:
    """Load spectrogram metadata/arrays from disk."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Spectrogram file not found: {path}")

    npz = np.load(path)
    config = EngineConfig(
        nfft=int(npz["nfft"]),
        channels=int(npz["channels"]),
        overlap=float(npz["overlap"]),
        sample_rate_hz=int(npz["sample_rate_hz"]),
        window=WindowType(str(npz["window"])),
        window_symmetry=WindowSymmetry(str(npz["window_symmetry"])),
        window_norm=WindowNorm(str(npz["window_norm"])),
        scale=ScalePolicy(str(npz["scale"])),
    )
    return SpectrogramData(
        spectrogram=npz["spectrogram"],
        times=npz["times"],
        frequencies=npz["frequencies"],
        config=config,
        channel=int(npz["channel"]),
    )


__all__ = [
    "FloatArray",
    "SpectrogramData",
    "save_spectrogram_data",
    "load_spectrogram_data",
]
