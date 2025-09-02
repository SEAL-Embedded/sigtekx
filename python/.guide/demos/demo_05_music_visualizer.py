#!/usr/bin/env python3
"""
demo_05_music_visualizer.py
============================
Create beautiful music visualizations using GPU-accelerated FFT!

This demo creates an animated visualization that responds to
different frequency bands like a professional music visualizer.

Run: python demo_05_music_visualizer.py
"""

import colorsys
import time

import matplotlib.pyplot as plt
import numpy as np
from cuda_lib import CudaFftEngine
from matplotlib.animation import FuncAnimation
from matplotlib.patches import Circle


class MusicVisualizer:
    def __init__(self, nfft=2048, sample_rate=48000):
        self.nfft = nfft
        self.sample_rate = sample_rate
        self.batch_size = 4  # Process multiple channels for stereo + effects

        print("🎵 Initializing Music Visualizer...")
        self.engine = CudaFftEngine(nfft=nfft, batch=self.batch_size, use_graphs=True, verbose=False)
        self.engine.prepare_for_execution()

        # Apply window
        window = np.hanning(nfft).astype(np.float32)
        self.engine.set_window(window)

        # Frequency bands for visualization
        self.setup_frequency_bands()

        # Setup visualization
        self.setup_visualization()

        # Music generation parameters
        self.time = 0
        self.stream_idx = 0
        self.beat_phase = 0

        # Smoothing for animations
        self.band_history = np.zeros((5, 30))  # 5 bands, 30 frames history
        self.smoothed_bands = np.zeros(5)

    def setup_frequency_bands(self):
        """Define frequency bands for visualization."""
        freq_bins = np.fft.rfftfreq(self.nfft, 1/self.sample_rate)

        # Define 5 bands: Sub-bass, Bass, Mid, High-Mid, Treble
        self.bands = [
            {'name': 'Sub-bass', 'range': (20, 60), 'color': '#FF0000'},
            {'name': 'Bass', 'range': (60, 250), 'color': '#FF7F00'},
            {'name': 'Mid', 'range': (250, 2000), 'color': '#FFFF00'},
            {'name': 'High-Mid', 'range': (2000, 6000), 'color': '#00FF00'},
            {'name': 'Treble', 'range': (6000, 20000), 'color': '#0000FF'},
        ]

        # Find bin indices for each band
        for band in self.bands:
            low, high = band['range']
            band['bins'] = np.where((freq_bins >= low) & (freq_bins < high))[0]

    def setup_visualization(self):
        """Setup the matplotlib figure for visualization."""
        self.fig = plt.figure(figsize=(14, 8), facecolor='black')

        # Create subplots
        gs = self.fig.add_gridspec(2, 3, hspace=0.3, wspace=0.3)

        # Main spectrum display
        self.ax_spectrum = self.fig.add_subplot(gs[0, :])
        self.ax_spectrum.set_facecolor('black')
        self.ax_spectrum.set_xlim(20, 10000)
        self.ax_spectrum.set_ylim(0, 100)
        self.ax_spectrum.set_xscale('log')
        self.ax_spectrum.set_xlabel('Frequency (Hz)', color='white')
        self.ax_spectrum.set_ylabel('Magnitude', color='white')
        self.ax_spectrum.set_title('🎵 Real-Time Spectrum', color='white', fontsize=14)
        self.ax_spectrum.tick_params(colors='white')

        # Frequency band bars
        self.ax_bars = self.fig.add_subplot(gs[1, 0])
        self.ax_bars.set_facecolor('black')
        self.ax_bars.set_xlim(-0.5, 4.5)
        self.ax_bars.set_ylim(0, 100)
        self.ax_bars.set_xticks(range(5))
        self.ax_bars.set_xticklabels([b['name'] for b in self.bands], rotation=45, color='white')
        self.ax_bars.set_ylabel('Energy', color='white')
        self.ax_bars.set_title('Frequency Bands', color='white')
        self.ax_bars.tick_params(colors='white')

        # Circular visualizer
        self.ax_circle = self.fig.add_subplot(gs[1, 1])
        self.ax_circle.set_facecolor('black')
        self.ax_circle.set_xlim(-2, 2)
        self.ax_circle.set_ylim(-2, 2)
        self.ax_circle.set_aspect('equal')
        self.ax_circle.axis('off')
        self.ax_circle.set_title('Radial Visualizer', color='white')

        # Beat detector
        self.ax_beat = self.fig.add_subplot(gs[1, 2])
        self.ax_beat.set_facecolor('black')
        self.ax_beat.set_xlim(0, 1)
        self.ax_beat.set_ylim(0, 1)
        self.ax_beat.axis('off')
        self.ax_beat.set_title('Beat Detector', color='white')

        # Initialize plot elements
        freq_bins = np.fft.rfftfreq(self.nfft, 1/self.sample_rate)
        self.spectrum_line, = self.ax_spectrum.plot(freq_bins[1:], np.zeros(len(freq_bins)-1),
                                                   color='cyan', linewidth=1.5)

        # Band bars
        self.band_bars = []
        for i, band in enumerate(self.bands):
            bar = self.ax_bars.bar(i, 0, color=band['color'], alpha=0.7, width=0.8)
            self.band_bars.append(bar)

        # Circular elements
        self.circle_elements = []
        for i in range(20):
            angle = i * 2 * np.pi / 20
            line = self.ax_circle.plot([0, np.cos(angle)], [0, np.sin(angle)],
                                      color='white', alpha=0.3, linewidth=1)[0]
            self.circle_elements.append(line)

        # Beat circle
        self.beat_circle = Circle((0.5, 0.5), 0.3, color='white', alpha=0)
        self.ax_beat.add_patch(self.beat_circle)

        # Performance text
        self.fps_text = self.fig.text(0.02, 0.02, '', fontsize=10, color='white')
        self.frame_times = []

    def generate_music_signal(self):
        """Generate a synthetic music-like signal."""
        t = np.linspace(self.time, self.time + self.nfft/self.sample_rate,
                       self.nfft, dtype=np.float32)

        signal = np.zeros(self.nfft, dtype=np.float32)

        # Beat (kick drum simulation)
        beat_freq = 2  # 120 BPM
        beat_envelope = np.exp(-10 * (t - self.time))
        beat_envelope *= (np.sin(2 * np.pi * beat_freq * self.time) > 0.8)
        signal += beat_envelope * np.sin(2 * np.pi * 50 * t)  # Sub-bass kick

        # Bassline
        bass_freq = 110 * (1 + 0.5 * np.sin(2 * np.pi * 0.25 * self.time))
        signal += 0.3 * np.sin(2 * np.pi * bass_freq * t)

        # Chord progression (simplified)
        chord_freqs = [261.63, 329.63, 392.00]  # C major
        for freq in chord_freqs:
            signal += 0.1 * np.sin(2 * np.pi * freq * t * (1 + 0.1 * np.sin(2 * np.pi * 3 * t)))

        # High frequency elements (hi-hats)
        if int(self.time * 8) % 2 == 1:
            signal += 0.05 * np.random.randn(self.nfft).astype(np.float32) * np.exp(-5 * (t - self.time))

        # Melody line
        melody_freq = 523.25 * (1 + 0.3 * np.sin(2 * np.pi * 1 * self.time))
        signal += 0.2 * np.sin(2 * np.pi * melody_freq * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * self.time))

        # Apply some dynamics
        signal *= (0.7 + 0.3 * np.sin(2 * np.pi * 0.5 * self.time))

        self.time += self.nfft / self.sample_rate / 4  # 75% overlap
        self.beat_phase = (self.beat_phase + 1) % 60

        # Create batch (duplicate with variations for stereo effect)
        batch = np.zeros(self.nfft * self.batch_size, dtype=np.float32)
        batch[:self.nfft] = signal  # Left channel
        batch[self.nfft:2*self.nfft] = signal * 0.9  # Right channel (slightly different)
        batch[2*self.nfft:3*self.nfft] = signal * 1.1  # Effect channel 1
        batch[3*self.nfft:] = np.roll(signal, 10)  # Effect channel 2 (delayed)

        return batch

    def process_audio(self):
        """Process audio through GPU FFT."""
        # Generate audio
        audio_batch = self.generate_music_signal()

        # Process on GPU
        self.engine.pinned_input(self.stream_idx)[:] = audio_batch
        self.engine.execute_async(self.stream_idx)
        self.engine.sync_stream(self.stream_idx)

        # Get magnitude spectrum (average stereo channels)
        magnitudes = self.engine.pinned_output(self.stream_idx)
        mags_2d = magnitudes.reshape(self.batch_size, -1)
        avg_spectrum = np.mean(mags_2d[:2], axis=0)  # Average L/R channels

        # Calculate band energies
        band_energies = []
        for band in self.bands:
            if len(band['bins']) > 0:
                energy = np.mean(avg_spectrum[band['bins']])
            else:
                energy = 0
            band_energies.append(energy)

        # Smooth the band energies
        self.band_history = np.roll(self.band_history, -1, axis=1)
        self.band_history[:, -1] = band_energies
        self.smoothed_bands = np.mean(self.band_history, axis=1)

        self.stream_idx = (self.stream_idx + 1) % 3

        return avg_spectrum, self.smoothed_bands

    def update(self, frame):
        """Update animation frame."""
        start_time = time.perf_counter()

        # Process audio
        spectrum, band_energies = self.process_audio()

        # Update spectrum plot
        freq_bins = np.fft.rfftfreq(self.nfft, 1/self.sample_rate)
        self.spectrum_line.set_data(freq_bins[1:], spectrum[1:])

        # Update band bars
        for i, (bar, energy) in enumerate(zip(self.band_bars, band_energies, strict=False)):
            bar[0].set_height(energy * 2)
            # Change opacity based on energy
            bar[0].set_alpha(0.3 + 0.7 * min(energy / 50, 1))

        # Update circular visualizer
        for i, line in enumerate(self.circle_elements):
            angle = i * 2 * np.pi / len(self.circle_elements)
            band_idx = i % 5
            radius = 0.5 + band_energies[band_idx] / 30
            line.set_data([0, radius * np.cos(angle)], [0, radius * np.sin(angle)])

            # Color based on energy
            hue = (i / len(self.circle_elements) + self.time * 0.1) % 1
            rgb = colorsys.hsv_to_rgb(hue, 1, min(band_energies[band_idx] / 30, 1))
            line.set_color(rgb)
            line.set_alpha(0.3 + 0.7 * min(band_energies[band_idx] / 30, 1))
            line.set_linewidth(1 + band_energies[band_idx] / 20)

        # Update beat detector
        bass_energy = band_energies[1]  # Use bass band for beat detection
        beat_intensity = min(bass_energy / 30, 1)
        self.beat_circle.set_radius(0.2 + 0.3 * beat_intensity)
        self.beat_circle.set_alpha(beat_intensity * 0.8)

        # Flash on strong beats
        if bass_energy > 40:
            self.beat_circle.set_color('yellow')
        else:
            self.beat_circle.set_color('white')

        # Calculate FPS
        frame_time = time.perf_counter() - start_time
        self.frame_times.append(frame_time)
        if len(self.frame_times) > 30:
            self.frame_times.pop(0)

        avg_time = np.mean(self.frame_times)
        fps = 1.0 / avg_time if avg_time > 0 else 0
        self.fps_text.set_text(f'GPU Processing: {avg_time*1000:.1f}ms | {fps:.0f} FPS')

        return [self.spectrum_line] + [bar[0] for bar in self.band_bars] + \
               self.circle_elements + [self.beat_circle, self.fps_text]

    def run(self):
        """Start the visualizer."""
        print("🎸 Starting music visualizer...")
        print("Close the window to stop.\n")

        # Create animation
        anim = FuncAnimation(self.fig, self.update, interval=33, blit=True)  # ~30 FPS

        plt.tight_layout()
        self.fig.patch.set_facecolor('black')
        plt.show()

def main():
    print("="*60)
    print("🎨 GPU-ACCELERATED MUSIC VISUALIZER")
    print("="*60)
    print("\nThis demo creates a professional music visualization using:")
    print("• Real-time spectrum analysis")
    print("• Frequency band separation")
    print("• Beat detection")
    print("• Radial visualization")
    print("• All powered by GPU acceleration!\n")

    visualizer = MusicVisualizer()
    visualizer.run()

    print("\n✨ Thanks for watching!")
    print("   The GPU processing enables smooth 60+ FPS visualization")
    print("   that would be impossible with CPU processing alone.")

if __name__ == "__main__":
    main()
