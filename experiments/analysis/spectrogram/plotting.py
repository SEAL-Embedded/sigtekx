"""Visualization helpers for spectrogram data."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from .data import SpectrogramData

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure


def plot_spectrogram(
    data: SpectrogramData,
    output_path: str | Path | None = None,
    db_scale: bool = True,
    vmin: float | None = None,
    vmax: float | None = None,
    cmap: str = "viridis",
    figsize: tuple[float, float] = (12, 6),
    dpi: int = 150,
) -> tuple["Figure", "Axes"]:
    import matplotlib.pyplot as plt

    if db_scale:
        spec_db = 20 * np.log10(data.spectrogram + 1e-10)
        ylabel = "Frequency (Hz)"
        cbar_label = "Magnitude (dB)"
    else:
        spec_db = data.spectrogram
        ylabel = "Frequency (Hz)"
        cbar_label = "Magnitude"

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    extent = [
        data.times[0],
        data.times[-1],
        data.frequencies[0],
        data.frequencies[-1],
    ]
    im = ax.imshow(
        spec_db.T,
        aspect="auto",
        origin="lower",
        extent=extent,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        interpolation="bilinear",
    )
    ax.set_xlabel("Time (s)")
    ax.set_ylabel(ylabel)
    ax.set_title(
        f"Spectrogram (NFFT={data.config.nfft}, overlap={data.config.overlap:.2f}, "
        f"{data.config.window.value} window)"
    )
    fig.colorbar(im, ax=ax, label=cbar_label)
    fig.tight_layout()

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=dpi, bbox_inches="tight")

    return fig, ax


__all__ = ["plot_spectrogram"]
