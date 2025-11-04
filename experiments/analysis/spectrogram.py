"""Spectrogram generation utilities for ionosense-hpc.

This module provides a reusable spectrogram generation pipeline that:
1. Processes raw time-series data through the Engine
2. Accumulates magnitude frames into 2D spectrograms
3. Saves/loads spectrogram data in NPZ format
4. Provides plotting utilities for visualization

Design principles:
- DRY: Single reusable utility for all spectrogram needs
- Lean: Uses existing Engine API, no new C++ code
- Scalable: Easy to extend for different use cases
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from ionosense_hpc.config import EngineConfig
from ionosense_hpc.core import Engine

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

# Type aliases
FloatArray = NDArray[np.float32]


@dataclass
class SpectrogramData:
    """Container for spectrogram data and metadata.

    Attributes:
        spectrogram: 2D array of shape (time_steps, freq_bins) containing magnitude values
        times: 1D array of time values in seconds
        frequencies: 1D array of frequency values in Hz
        config: Engine configuration used to generate the spectrogram
        channel: Channel index (0-based) for multi-channel data
    """
    spectrogram: FloatArray
    times: FloatArray
    frequencies: FloatArray
    config: EngineConfig
    channel: int = 0


class SpectrogramGenerator:
    """Generate spectrograms from time-series data using the Engine.

    This class provides a high-level interface for creating spectrograms
    by processing overlapping frames through the ionosense-hpc Engine.

    Examples:
        >>> from ionosense_hpc import EngineConfig
        >>> from ionosense_hpc.analysis import SpectrogramGenerator
        >>>
        >>> # Create generator with config
        >>> config = EngineConfig(nfft=4096, channels=1, overlap=0.75, sample_rate_hz=48000)
        >>> generator = SpectrogramGenerator(config)
        >>>
        >>> # Generate spectrogram from raw data
        >>> signal = np.random.randn(48000 * 10).astype(np.float32)  # 10 seconds
        >>> spec_data = generator.generate(signal)
        >>>
        >>> # Save to file
        >>> generator.save(spec_data, "artifacts/data/spectrograms/test.npz")
        >>>
        >>> # Load from file
        >>> loaded = generator.load("artifacts/data/spectrograms/test.npz")
    """

    def __init__(self, config: EngineConfig):
        """Initialize the spectrogram generator.

        Args:
            config: Engine configuration for spectrogram generation
        """
        self.config = config
        self._engine: Engine | None = None

    def __enter__(self) -> SpectrogramGenerator:
        """Enter context manager - initializes engine."""
        self._engine = Engine(config=self.config)
        self._engine.__enter__()
        return self

    def __exit__(self, *args) -> None:
        """Exit context manager - cleanup engine resources."""
        if self._engine is not None:
            self._engine.__exit__(*args)
            self._engine = None

    def generate(
        self,
        data: NDArray[np.float32],
        channel: int = 0,
        progress_callback: callable | None = None
    ) -> SpectrogramData:
        """Generate a spectrogram from time-series data.

        Args:
            data: Input time-series data. Shape can be:
                  - 1D: (samples,) - single channel
                  - 2D: (channels, samples) - multi-channel
            channel: Channel index to extract (0-based) for multi-channel data
            progress_callback: Optional callback(current, total) for progress updates

        Returns:
            SpectrogramData containing the spectrogram and metadata

        Raises:
            ValueError: If data shape is incompatible with config

        Examples:
            >>> # Single channel
            >>> signal = np.random.randn(48000).astype(np.float32)
            >>> spec_data = generator.generate(signal)
            >>>
            >>> # Multi-channel, extract channel 1
            >>> signal = np.random.randn(2, 48000).astype(np.float32)
            >>> spec_data = generator.generate(signal, channel=1)
        """
        # Validate and reshape input
        data = np.asarray(data, dtype=np.float32)

        if data.ndim == 1:
            # Single channel: reshape to (1, samples)
            if self.config.channels != 1:
                raise ValueError(
                    f"Config specifies {self.config.channels} channels, "
                    f"but input data is 1D (single channel)"
                )
            signal_data = data
        elif data.ndim == 2:
            # Multi-channel: extract specified channel
            if channel >= data.shape[0]:
                raise ValueError(
                    f"Channel {channel} requested but data has only {data.shape[0]} channels"
                )
            signal_data = data[channel]
        else:
            raise ValueError(f"Input data must be 1D or 2D, got shape {data.shape}")

        # Calculate frame parameters
        nfft = self.config.nfft
        hop_size = int(nfft * (1 - self.config.overlap))
        num_samples = len(signal_data)

        # Calculate number of complete frames
        if num_samples < nfft:
            raise ValueError(
                f"Input data too short ({num_samples} samples) for NFFT={nfft}"
            )

        num_frames = 1 + (num_samples - nfft) // hop_size

        # Prepare engine (use existing or create temporary)
        engine_context = None
        if self._engine is None:
            engine_context = Engine(config=self.config)
            engine_context.__enter__()
            engine = engine_context
        else:
            engine = self._engine

        try:
            # Process frames and collect magnitude spectra
            magnitude_frames = []

            for frame_idx in range(num_frames):
                start_idx = frame_idx * hop_size
                end_idx = start_idx + nfft

                # Extract frame
                frame_data = signal_data[start_idx:end_idx]

                # For multi-channel engine, replicate to all channels
                # (we only care about the output from one channel)
                if self.config.channels > 1:
                    # Create multi-channel input by replicating
                    engine_input = np.tile(frame_data, self.config.channels)
                else:
                    engine_input = frame_data

                # Process through engine
                spectrum = engine.process(engine_input)

                # spectrum shape: (channels, num_output_bins)
                # Extract first channel (all channels have same output since we replicated input)
                magnitude_frames.append(spectrum[0])

                # Progress callback
                if progress_callback is not None:
                    progress_callback(frame_idx + 1, num_frames)

            # Stack frames into 2D spectrogram: (time_steps, freq_bins)
            spectrogram = np.vstack(magnitude_frames)

            # Calculate time and frequency axes
            times = self._calculate_time_axis(num_frames, hop_size)
            frequencies = self._calculate_frequency_axis()

            return SpectrogramData(
                spectrogram=spectrogram,
                times=times,
                frequencies=frequencies,
                config=self.config,
                channel=channel
            )

        finally:
            # Cleanup temporary engine if created
            if engine_context is not None:
                engine_context.__exit__(None, None, None)

    def _calculate_time_axis(self, num_frames: int, hop_size: int) -> FloatArray:
        """Calculate time axis for spectrogram.

        Args:
            num_frames: Number of time frames
            hop_size: Samples between consecutive frames

        Returns:
            1D array of time values in seconds
        """
        # Time of each frame is the center of the window
        frame_centers = np.arange(num_frames) * hop_size + self.config.nfft / 2
        times = frame_centers / self.config.sample_rate_hz
        return times.astype(np.float32)

    def _calculate_frequency_axis(self) -> FloatArray:
        """Calculate frequency axis for spectrogram.

        Returns:
            1D array of frequency values in Hz
        """
        num_output_bins = self.config.nfft // 2 + 1
        frequencies = np.linspace(
            0,
            self.config.sample_rate_hz / 2,
            num_output_bins,
            dtype=np.float32
        )
        return frequencies

    @staticmethod
    def save(data: SpectrogramData, path: str | Path) -> None:
        """Save spectrogram data to NPZ file.

        Args:
            data: SpectrogramData to save
            path: Output file path (will create parent directories if needed)

        Examples:
            >>> spec_data = generator.generate(signal)
            >>> SpectrogramGenerator.save(spec_data, "outputs/spec.npz")
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Save arrays and metadata
        np.savez_compressed(
            path,
            spectrogram=data.spectrogram,
            times=data.times,
            frequencies=data.frequencies,
            # Config metadata (save as dict for easy loading)
            nfft=data.config.nfft,
            channels=data.config.channels,
            overlap=data.config.overlap,
            sample_rate_hz=data.config.sample_rate_hz,
            window=data.config.window.value,
            window_symmetry=data.config.window_symmetry.value,
            window_norm=data.config.window_norm.value,
            scale=data.config.scale.value,
            channel=data.channel
        )

    @staticmethod
    def load(path: str | Path) -> SpectrogramData:
        """Load spectrogram data from NPZ file.

        Args:
            path: Input file path

        Returns:
            SpectrogramData loaded from file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid

        Examples:
            >>> spec_data = SpectrogramGenerator.load("outputs/spec.npz")
            >>> print(spec_data.spectrogram.shape)
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Spectrogram file not found: {path}")

        # Load NPZ file
        npz = np.load(path)

        # Reconstruct config
        from ionosense_hpc.config import WindowType, WindowSymmetry, WindowNorm, ScalePolicy

        config = EngineConfig(
            nfft=int(npz['nfft']),
            channels=int(npz['channels']),
            overlap=float(npz['overlap']),
            sample_rate_hz=int(npz['sample_rate_hz']),
            window=WindowType(str(npz['window'])),
            window_symmetry=WindowSymmetry(str(npz['window_symmetry'])),
            window_norm=WindowNorm(str(npz['window_norm'])),
            scale=ScalePolicy(str(npz['scale']))
        )

        return SpectrogramData(
            spectrogram=npz['spectrogram'],
            times=npz['times'],
            frequencies=npz['frequencies'],
            config=config,
            channel=int(npz['channel'])
        )

    @staticmethod
    def plot(
        data: SpectrogramData,
        output_path: str | Path | None = None,
        db_scale: bool = True,
        vmin: float | None = None,
        vmax: float | None = None,
        cmap: str = 'viridis',
        figsize: tuple[float, float] = (12, 6),
        dpi: int = 150
    ) -> tuple[Figure, Axes]:
        """Plot spectrogram using matplotlib.

        Args:
            data: SpectrogramData to plot
            output_path: Optional path to save figure (PNG/PDF)
            db_scale: If True, plot in dB scale (20*log10)
            vmin: Minimum value for color scale (None = auto)
            vmax: Maximum value for color scale (None = auto)
            cmap: Colormap name (viridis, plasma, jet, etc.)
            figsize: Figure size in inches (width, height)
            dpi: Resolution in dots per inch

        Returns:
            Tuple of (figure, axes) for further customization

        Examples:
            >>> fig, ax = SpectrogramGenerator.plot(spec_data, "spec.png", db_scale=True)
            >>> ax.set_title("My Custom Title")
            >>> fig.savefig("custom_spec.png")
        """
        import matplotlib.pyplot as plt

        # Convert to dB scale if requested
        if db_scale:
            # Add small epsilon to avoid log(0)
            spec_db = 20 * np.log10(data.spectrogram + 1e-10)
            ylabel = "Frequency (Hz)"
            cbar_label = "Magnitude (dB)"
        else:
            spec_db = data.spectrogram
            ylabel = "Frequency (Hz)"
            cbar_label = "Magnitude"

        # Create figure
        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

        # Plot spectrogram
        extent = [
            data.times[0],
            data.times[-1],
            data.frequencies[0],
            data.frequencies[-1]
        ]

        im = ax.imshow(
            spec_db.T,  # Transpose so frequency is on y-axis
            aspect='auto',
            origin='lower',
            extent=extent,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            interpolation='bilinear'
        )

        # Labels and title
        ax.set_xlabel("Time (s)")
        ax.set_ylabel(ylabel)
        ax.set_title(
            f"Spectrogram (NFFT={data.config.nfft}, overlap={data.config.overlap:.2f}, "
            f"{data.config.window.value} window)"
        )

        # Colorbar
        cbar = fig.colorbar(im, ax=ax, label=cbar_label)

        # Tight layout
        fig.tight_layout()

        # Save if path provided
        if output_path is not None:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_path, dpi=dpi, bbox_inches='tight')

        return fig, ax


# ============================================================================
# Convenience Functions
# ============================================================================

def generate_spectrogram(
    data: NDArray[np.float32],
    config: EngineConfig,
    channel: int = 0,
    progress_callback: callable | None = None
) -> SpectrogramData:
    """Generate a spectrogram from time-series data.

    Convenience function that creates a SpectrogramGenerator and generates
    a spectrogram in one call.

    Args:
        data: Input time-series data (1D or 2D)
        config: Engine configuration
        channel: Channel index for multi-channel data
        progress_callback: Optional progress callback

    Returns:
        SpectrogramData containing the spectrogram and metadata

    Examples:
        >>> from ionosense_hpc import EngineConfig
        >>> from ionosense_hpc.analysis import generate_spectrogram
        >>>
        >>> config = EngineConfig(nfft=4096, overlap=0.75)
        >>> signal = np.random.randn(48000).astype(np.float32)
        >>> spec_data = generate_spectrogram(signal, config)
    """
    with SpectrogramGenerator(config) as generator:
        return generator.generate(data, channel, progress_callback)


def save_spectrogram(data: SpectrogramData, path: str | Path) -> None:
    """Save spectrogram data to NPZ file.

    Convenience wrapper for SpectrogramGenerator.save().

    Args:
        data: SpectrogramData to save
        path: Output file path
    """
    SpectrogramGenerator.save(data, path)


def load_spectrogram(path: str | Path) -> SpectrogramData:
    """Load spectrogram data from NPZ file.

    Convenience wrapper for SpectrogramGenerator.load().

    Args:
        path: Input file path

    Returns:
        SpectrogramData loaded from file
    """
    return SpectrogramGenerator.load(path)


def plot_spectrogram(
    data: SpectrogramData,
    output_path: str | Path | None = None,
    **kwargs
) -> tuple[Figure, Axes]:
    """Plot spectrogram using matplotlib.

    Convenience wrapper for SpectrogramGenerator.plot().

    Args:
        data: SpectrogramData to plot
        output_path: Optional path to save figure
        **kwargs: Additional arguments passed to SpectrogramGenerator.plot()

    Returns:
        Tuple of (figure, axes) for further customization
    """
    return SpectrogramGenerator.plot(data, output_path, **kwargs)
