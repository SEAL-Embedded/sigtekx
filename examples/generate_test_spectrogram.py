"""Example script to generate and validate a test spectrogram.

This script demonstrates the complete spectrogram generation pipeline:
1. Generate synthetic test signal (multi-frequency sine waves)
2. Create spectrogram using ionosense-hpc Engine
3. Save spectrogram to NPZ file
4. Load and visualize with matplotlib

Run this to validate the spectrogram pipeline is working correctly.
"""

import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt
import sys

# Add experiments to path for analysis module imports
_experiments_path = Path(__file__).parent.parent / "experiments"
if str(_experiments_path) not in sys.path:
    sys.path.insert(0, str(_experiments_path))

from ionosense_hpc.config import EngineConfig
from analysis.spectrogram import (
    SpectrogramGenerator,
    save_spectrogram,
    load_spectrogram,
    plot_spectrogram
)


def generate_test_signal(duration_sec: float = 5.0, sample_rate_hz: int = 48000) -> np.ndarray:
    """Generate a test signal with multiple sine wave components.

    Creates a signal containing:
    - 100 Hz tone (VLF)
    - 1 kHz tone (mid-frequency)
    - 5 kHz tone (higher frequency)
    - White noise background

    Args:
        duration_sec: Signal duration in seconds
        sample_rate_hz: Sampling rate in Hz

    Returns:
        1D float32 array of signal samples
    """
    num_samples = int(sample_rate_hz * duration_sec)
    t = np.arange(num_samples) / sample_rate_hz

    # Multi-frequency components
    signal = (
        0.8 * np.sin(2 * np.pi * 100 * t) +      # 100 Hz (strong)
        0.5 * np.sin(2 * np.pi * 1000 * t) +     # 1 kHz (moderate)
        0.3 * np.sin(2 * np.pi * 5000 * t) +     # 5 kHz (weak)
        0.1 * np.random.randn(num_samples)       # Noise
    )

    return signal.astype(np.float32)


def main():
    """Main validation workflow."""
    print("=" * 70)
    print("Ionosense HPC - Spectrogram Generation Validation")
    print("=" * 70)

    # Configuration
    config = EngineConfig(
        nfft=4096,
        channels=1,
        overlap=0.75,
        sample_rate_hz=48000,
        window='hann'
    )

    print(f"\nConfiguration:")
    print(f"  NFFT: {config.nfft}")
    print(f"  Channels: {config.channels}")
    print(f"  Overlap: {config.overlap}")
    print(f"  Sample Rate: {config.sample_rate_hz} Hz")
    print(f"  Window: {config.window.value}")

    # Calculate resolution metrics
    freq_res_hz = config.sample_rate_hz / config.nfft
    hop_size = int(config.nfft * (1 - config.overlap))
    time_res_ms = (hop_size / config.sample_rate_hz) * 1000

    print(f"\nResolution:")
    print(f"  Frequency: {freq_res_hz:.2f} Hz")
    print(f"  Time: {time_res_ms:.2f} ms")

    # Generate test signal
    print("\n" + "-" * 70)
    print("Generating test signal...")
    duration_sec = 5.0
    signal = generate_test_signal(duration_sec, config.sample_rate_hz)
    print(f"  Duration: {duration_sec} seconds")
    print(f"  Samples: {len(signal)}")
    print(f"  Signal contains: 100 Hz, 1 kHz, 5 kHz tones + noise")

    # Generate spectrogram
    print("\n" + "-" * 70)
    print("Generating spectrogram...")

    with SpectrogramGenerator(config) as generator:
        spec_data = generator.generate(signal, progress_callback=None)

    print(f"  Time steps: {spec_data.spectrogram.shape[0]}")
    print(f"  Frequency bins: {spec_data.spectrogram.shape[1]}")
    print(f"  Duration: {spec_data.times[-1]:.2f} seconds")
    print(f"  Frequency range: 0 - {spec_data.frequencies[-1]:.0f} Hz")

    # Save spectrogram
    print("\n" + "-" * 70)
    print("Saving spectrogram...")

    output_dir = Path("artifacts/data/spectrograms")
    output_path = output_dir / "test_validation_nfft4096_ch1_ovlp0.75.npz"

    save_spectrogram(spec_data, output_path)
    print(f"  Saved to: {output_path}")
    print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")

    # Load spectrogram (validation)
    print("\n" + "-" * 70)
    print("Loading spectrogram (roundtrip validation)...")

    loaded_data = load_spectrogram(output_path)
    print(f"  ✓ Loaded successfully")
    print(f"  ✓ Shape matches: {loaded_data.spectrogram.shape == spec_data.spectrogram.shape}")
    print(f"  ✓ Data matches: {np.allclose(loaded_data.spectrogram, spec_data.spectrogram)}")

    # Generate matplotlib plots
    print("\n" + "-" * 70)
    print("Generating matplotlib plots...")

    # Plot 1: Full spectrogram
    fig1, ax1 = plot_spectrogram(
        spec_data,
        output_path=output_dir / "test_spectrogram_full.png",
        db_scale=True,
        cmap='viridis',
        figsize=(14, 6),
        dpi=150
    )
    print(f"  ✓ Saved: {output_dir / 'test_spectrogram_full.png'}")

    # Plot 2: Zoomed to VLF/ULF range (0-2 kHz)
    fig2, ax2 = plot_spectrogram(
        spec_data,
        db_scale=True,
        cmap='plasma',
        figsize=(14, 6),
        dpi=150
    )
    ax2.set_ylim([0, 2000])
    ax2.set_title(f"Spectrogram - VLF/ULF Range (NFFT={config.nfft}, overlap={config.overlap:.2f})")
    fig2.tight_layout()
    output_path_vlf = output_dir / "test_spectrogram_vlf.png"
    fig2.savefig(output_path_vlf, dpi=150, bbox_inches='tight')
    print(f"  ✓ Saved: {output_path_vlf}")

    # Verify expected frequencies are present
    print("\n" + "-" * 70)
    print("Validating frequency content...")

    # Average spectrum over time
    mean_spectrum = np.mean(spec_data.spectrogram, axis=0)

    # Find peaks for expected frequencies
    expected_freqs = [100, 1000, 5000]
    tolerance_hz = 2 * freq_res_hz  # 2x frequency resolution

    all_found = True
    for target_freq in expected_freqs:
        # Find nearest frequency bin
        freq_idx = np.argmin(np.abs(spec_data.frequencies - target_freq))
        actual_freq = spec_data.frequencies[freq_idx]

        # Check if frequency is within tolerance
        if abs(actual_freq - target_freq) < tolerance_hz:
            # Check if this is a local maximum (peak)
            window_size = 5
            local_region = mean_spectrum[max(0, freq_idx - window_size):min(len(mean_spectrum), freq_idx + window_size + 1)]
            is_peak = mean_spectrum[freq_idx] == np.max(local_region)

            if is_peak:
                print(f"  ✓ Found {target_freq} Hz peak at {actual_freq:.1f} Hz")
            else:
                print(f"  ⚠ {target_freq} Hz detected but not a peak at {actual_freq:.1f} Hz")
        else:
            print(f"  ✗ Expected {target_freq} Hz NOT found")
            all_found = False

    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    if all_found:
        print("✓ All validation checks PASSED")
        print(f"✓ Spectrogram saved to: {output_path}")
        print(f"✓ Plots saved to: {output_dir}")
        print("\nNext steps:")
        print("  1. View plots in artifacts/data/spectrograms/")
        print("  2. Launch Streamlit dashboard: iono dashboard")
        print("  3. Navigate to 'Ionosphere Research' → 'Spectrogram Viewer' tab")
        return 0
    else:
        print("⚠ Some validation checks failed")
        print("  This may be due to noise or insufficient signal strength")
        print(f"  Review plots in: {output_dir}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
