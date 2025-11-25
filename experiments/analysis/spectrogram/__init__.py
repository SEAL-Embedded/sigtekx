"""Spectrogram toolkit for analysis pipelines."""

from .data import (
    FloatArray,
    SpectrogramData,
    load_spectrogram_data as load_spectrogram,
    save_spectrogram_data as save_spectrogram,
)
from .generator import (
    SpectrogramGenerator,
    generate_spectrogram,
)
from .plotting import (
    plot_spectrogram,
)

__all__ = [
    "FloatArray",
    "SpectrogramData",
    "SpectrogramGenerator",
    "generate_spectrogram",
    "save_spectrogram",
    "load_spectrogram",
    "plot_spectrogram",
]
