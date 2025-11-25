"""Spectrogram generation using the core Engine."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
from numpy.typing import NDArray

from ionosense_hpc.config import EngineConfig
from ionosense_hpc.core import Engine

from .data import (
    FloatArray,
    SpectrogramData,
    load_spectrogram_data,
    save_spectrogram_data,
)
from .plotting import plot_spectrogram


class SpectrogramGenerator:
    """Generate spectrograms from time-series data using the Engine."""

    def __init__(self, config: EngineConfig):
        self.config = config
        self._engine: Engine | None = None

    def __enter__(self) -> SpectrogramGenerator:
        self._engine = Engine(config=self.config)
        self._engine.__enter__()
        return self

    def __exit__(self, *args) -> None:
        if self._engine is not None:
            self._engine.__exit__(*args)
            self._engine = None

    def generate(
        self,
        data: NDArray[np.float32],
        channel: int = 0,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> SpectrogramData:
        signal_data = self._normalize_input(data, channel)

        nfft = self.config.nfft
        hop_size = int(nfft * (1 - self.config.overlap))
        num_samples = len(signal_data)
        if num_samples < nfft:
            raise ValueError(
                f"Input data too short ({num_samples} samples) for NFFT={nfft}"
            )
        num_frames = 1 + (num_samples - nfft) // hop_size

        engine_context = None
        if self._engine is None:
            engine_context = Engine(config=self.config)
            engine_context.__enter__()
            engine = engine_context
        else:
            engine = self._engine

        try:
            magnitude_frames = []
            for frame_idx in range(num_frames):
                start_idx = frame_idx * hop_size
                end_idx = start_idx + nfft
                frame_data = signal_data[start_idx:end_idx]

                if self.config.channels > 1:
                    engine_input = np.tile(frame_data, self.config.channels)
                else:
                    engine_input = frame_data

                spectrum = engine.process(engine_input)
                magnitude_frames.append(spectrum[0])

                if progress_callback is not None:
                    progress_callback(frame_idx + 1, num_frames)

            spectrogram = np.vstack(magnitude_frames)
            times = self._calculate_time_axis(num_frames, hop_size)
            frequencies = self._calculate_frequency_axis()
            return SpectrogramData(
                spectrogram=spectrogram,
                times=times,
                frequencies=frequencies,
                config=self.config,
                channel=channel,
            )
        finally:
            if engine_context is not None:
                engine_context.__exit__(None, None, None)

    def _normalize_input(self, data: NDArray[np.float32], channel: int) -> NDArray[np.float32]:
        arr = np.asarray(data, dtype=np.float32)
        if arr.ndim == 1:
            if self.config.channels != 1:
                raise ValueError(
                    f"Config specifies {self.config.channels} channels, but input is 1D"
                )
            return arr
        if arr.ndim == 2:
            if channel >= arr.shape[0]:
                raise ValueError(
                    f"Channel {channel} requested but data has only {arr.shape[0]} channels"
                )
            return arr[channel]
        raise ValueError(f"Input data must be 1D or 2D, got shape {arr.shape}")

    def _calculate_time_axis(self, num_frames: int, hop_size: int) -> FloatArray:
        frame_centers = np.arange(num_frames) * hop_size + self.config.nfft / 2
        times = frame_centers / self.config.sample_rate_hz
        return times.astype(np.float32)

    def _calculate_frequency_axis(self) -> FloatArray:
        num_output_bins = self.config.nfft // 2 + 1
        return np.linspace(
            0,
            self.config.sample_rate_hz / 2,
            num_output_bins,
            dtype=np.float32,
        )

    @staticmethod
    def save(data: SpectrogramData, path: str | Path) -> None:
        save_spectrogram_data(data, path)

    @staticmethod
    def load(path: str | Path) -> SpectrogramData:
        return load_spectrogram_data(path)

    @staticmethod
    def plot(
        data: SpectrogramData,
        output_path: str | Path | None = None,
        **kwargs,
    ):
        return plot_spectrogram(data, output_path=output_path, **kwargs)


def generate_spectrogram(
    data: NDArray[np.float32],
    config: EngineConfig,
    channel: int = 0,
    progress_callback: Callable[[int, int], None] | None = None,
) -> SpectrogramData:
    with SpectrogramGenerator(config) as generator:
        return generator.generate(data, channel, progress_callback)


__all__ = [
    "SpectrogramGenerator",
    "generate_spectrogram",
]
