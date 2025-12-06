"""
Static spectrogram generation utilities for Streamlit dashboards.

This module renders publication-ready PNGs for:
1. General reference spectrogram used in executive/overview sections.
2. Accuracy comparison spectrograms (engine vs NumPy STFT) plus difference heatmap.

Outputs are saved under ``artifacts/figures/spectrograms`` by default so the
Streamlit pages can display them without recomputing heavy FFT pipelines.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sigtekx.config import EngineConfig, WindowSymmetry, WindowType

try:
    from . import SpectrogramData, SpectrogramGenerator
except ImportError:  # pragma: no cover - fallback for script execution
    import sys as _sys
    from pathlib import Path as _Path

    _script_dir = _Path(__file__).resolve().parent
    if str(_script_dir) not in _sys.path:
        _sys.path.insert(0, str(_script_dir))
    from spectrogram import SpectrogramData, SpectrogramGenerator  # type: ignore

# Default output paths
DEFAULT_OUTPUT_DIR = Path("artifacts/figures/spectrograms")
GENERAL_IMAGE = "general_spectrogram.png"
GENERAL_METADATA = "general_spectrogram.json"
ACCURACY_ENGINE_IMAGE = "accuracy_engine.png"
ACCURACY_NUMPY_IMAGE = "accuracy_numpy.png"
ACCURACY_DELTA_IMAGE = "accuracy_difference.png"
ACCURACY_METADATA = "accuracy_metrics.json"


@dataclass
class StaticSpectrogramResult:
    """Summary of generated spectrogram artifacts."""

    images: dict[str, str]
    metadata_path: str


def synthesize_signal(duration_sec: float, sample_rate_hz: int) -> np.ndarray:
    """Create a reusable multi-tone + chirp signal for visualization."""
    t = np.arange(0, duration_sec, 1 / sample_rate_hz, dtype=np.float32)

    tones = [
        np.sin(2 * np.pi * 55 * t) * 0.5,
        np.sin(2 * np.pi * 110 * t) * 0.4,
        np.sin(2 * np.pi * 440 * t) * 0.35,
        np.sin(2 * np.pi * 1200 * t) * 0.25,
    ]

    chirp = np.sin(
        2 * np.pi * (t * (20 + (sample_rate_hz / 8) * t / duration_sec))
    ) * 0.2

    noise = np.random.default_rng(42).normal(scale=0.05, size=t.shape)

    signal = np.sum(tones, axis=0) + chirp + noise
    return signal.astype(np.float32)


def _ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_metadata(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _config_dict(config: EngineConfig) -> dict:
    return {
        "nfft": config.nfft,
        "channels": config.channels,
        "overlap": config.overlap,
        "sample_rate_hz": config.sample_rate_hz,
        "window": config.window.value,
        "window_symmetry": config.window_symmetry.value,
        "window_norm": config.window_norm.value,
        "scale": config.scale.value,
    }


def _numpy_stft(
    signal: np.ndarray,
    config: EngineConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute a NumPy-only STFT matching the engine configuration."""
    hop = int(config.nfft * (1.0 - config.overlap))
    num_frames = 1 + (signal.size - config.nfft) // hop
    stride = signal.strides[0]
    shape = (num_frames, config.nfft)
    strides = (hop * stride, stride)
    frames = np.lib.stride_tricks.as_strided(signal, shape=shape, strides=strides).copy()

    window = _window_array(config)
    frames *= window

    spectrum = np.fft.rfft(frames, n=config.nfft, axis=1)
    magnitude = np.abs(spectrum).astype(np.float32)

    times = (np.arange(num_frames, dtype=np.float32) * hop + config.nfft / 2) / config.sample_rate_hz
    freqs = np.linspace(0.0, config.sample_rate_hz / 2, config.num_output_bins, dtype=np.float32)
    return times, freqs, magnitude


def _window_array(config: EngineConfig) -> np.ndarray:
    """Return window samples that mimic EngineConfig settings."""
    n = np.arange(config.nfft, dtype=np.float32)
    if config.window == WindowType.HANN:
        denom = config.nfft if config.window_symmetry == WindowSymmetry.PERIODIC else max(config.nfft - 1, 1)
        w = 0.5 - 0.5 * np.cos(2 * np.pi * n / denom)
    elif config.window == WindowType.BLACKMAN:
        denom = config.nfft if config.window_symmetry == WindowSymmetry.PERIODIC else max(config.nfft - 1, 1)
        w = 0.42 - 0.5 * np.cos(2 * np.pi * n / denom) + 0.08 * np.cos(4 * np.pi * n / denom)
    else:
        w = np.ones_like(n)
    return w.astype(np.float32)


def _save_plot(data: SpectrogramData, output_path: Path, **kwargs) -> None:
    SpectrogramGenerator.plot(
        data,
        output_path=output_path,
        **kwargs,
    )


def generate_general_spectrogram(output_dir: Path) -> StaticSpectrogramResult:
    """Render the reference/general spectrogram."""
    config = EngineConfig(
        nfft=4096,
        channels=1,
        overlap=0.75,
        sample_rate_hz=48_000,
        window=WindowType.HANN,
        window_symmetry=WindowSymmetry.PERIODIC,
    )
    signal = synthesize_signal(duration_sec=5.0, sample_rate_hz=config.sample_rate_hz)

    with SpectrogramGenerator(config) as generator:
        spec_data = generator.generate(signal)

    output_path = output_dir / GENERAL_IMAGE
    _save_plot(spec_data, output_path, cmap="viridis", dpi=200)

    metadata = {
        "type": "general",
        "description": "Synthetic multi-tone + chirp reference signal",
        "config": _config_dict(config),
        "duration_sec": len(signal) / config.sample_rate_hz,
        "time_steps": int(spec_data.spectrogram.shape[0]),
        "freq_bins": int(spec_data.spectrogram.shape[1]),
        "image": output_path.name,
    }
    metadata_path = output_dir / GENERAL_METADATA
    _write_metadata(metadata_path, metadata)

    return StaticSpectrogramResult(
        images={"general": output_path.name},
        metadata_path=metadata_path.name,
    )


def generate_accuracy_spectrograms(output_dir: Path) -> StaticSpectrogramResult:
    """Render engine vs NumPy STFT accuracy spectrograms."""
    config = EngineConfig(
        nfft=4096,
        channels=1,
        overlap=0.75,
        sample_rate_hz=48_000,
        window=WindowType.HANN,
        window_symmetry=WindowSymmetry.PERIODIC,
    )
    # Slightly longer signal for better averaging
    signal = synthesize_signal(duration_sec=6.0, sample_rate_hz=config.sample_rate_hz)

    with SpectrogramGenerator(config) as generator:
        engine_spec = generator.generate(signal)

    times, freqs, numpy_spec = _numpy_stft(signal, config)

    numpy_data = SpectrogramData(
        spectrogram=numpy_spec,
        times=times,
        frequencies=freqs,
        config=config,
        channel=0,
    )

    diff = np.abs(engine_spec.spectrogram - numpy_spec)
    delta_data = SpectrogramData(
        spectrogram=diff.astype(np.float32),
        times=engine_spec.times,
        frequencies=engine_spec.frequencies,
        config=config,
        channel=0,
    )

    _save_plot(engine_spec, output_dir / ACCURACY_ENGINE_IMAGE, cmap="plasma", dpi=200)
    _save_plot(numpy_data, output_dir / ACCURACY_NUMPY_IMAGE, cmap="plasma", dpi=200)
    _save_plot(
        delta_data,
        output_dir / ACCURACY_DELTA_IMAGE,
        db_scale=False,
        cmap="magma",
        vmin=0.0,
    )

    mae = float(np.mean(diff))
    rmse = float(np.sqrt(np.mean(diff**2)))
    max_err = float(np.max(diff))
    snr = float(
        20
        * np.log10(
            np.linalg.norm(engine_spec.spectrogram)
            / (np.linalg.norm(diff) + 1e-12)
        )
    )

    metadata = {
        "type": "accuracy",
        "description": "Engine vs NumPy STFT magnitude comparison",
        "config": _config_dict(config),
        "duration_sec": len(signal) / config.sample_rate_hz,
        "time_steps": int(engine_spec.spectrogram.shape[0]),
        "freq_bins": int(engine_spec.spectrogram.shape[1]),
        "metrics": {
            "mean_absolute_error": mae,
            "rmse": rmse,
            "max_absolute_error": max_err,
            "snr_db": snr,
        },
        "images": {
            "engine": ACCURACY_ENGINE_IMAGE,
            "numpy": ACCURACY_NUMPY_IMAGE,
            "difference": ACCURACY_DELTA_IMAGE,
        },
    }
    metadata_path = output_dir / ACCURACY_METADATA
    _write_metadata(metadata_path, metadata)

    return StaticSpectrogramResult(
        images={
            "engine": ACCURACY_ENGINE_IMAGE,
            "numpy": ACCURACY_NUMPY_IMAGE,
            "difference": ACCURACY_DELTA_IMAGE,
        },
        metadata_path=metadata_path.name,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate static spectrogram PNGs")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated PNG and JSON artifacts",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=["general", "accuracy"],
        help="Subset of spectrogram targets to render (default: both)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    targets: Iterable[str] = args.targets if args.targets else ("general", "accuracy")
    output_dir = args.output_dir
    _ensure_output_dir(output_dir)

    for target in targets:
        if target == "general":
            result = generate_general_spectrogram(output_dir)
        elif target == "accuracy":
            result = generate_accuracy_spectrograms(output_dir)
        else:
            raise ValueError(f"Unknown target {target}")
        print(f"[spectrogram] Generated {target}: {result.images} -> {result.metadata_path}")


if __name__ == "__main__":
    main()
