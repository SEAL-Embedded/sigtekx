#!/usr/bin/env python3
"""
demo_02_live_spectrum.py
========================
Real-time audio spectrum analyzer using the GPU.

This demo simulates a live audio stream and displays
a real-time spectrum analyzer with peak detection.

Requirements: pip install matplotlib numpy
Run: python demo_02_live_spectrum.py
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from cuda_lib import CudaFftEngine
import time

class LiveSpectrumAnalyzer:
    def __init__(self, nfft=2048, sample_rate=48000):
        self.nfft = nfft
        self.sample_rate = sample_rate
        self.batch_size = 2  # Low batch for real-time response
        
        # Initialize GPU engine
        print("🎤 Initializing Live Spectrum Analyzer...")
        self.engine = CudaFftEngine(nfft=nfft, batch=self.batch_size, use_graphs=True, verbose=False)
        self.engine.prepare_for_execution()
        
        # Apply Hanning window for better spectrum
        window = np.hanning(nfft).astype(np.float32)
        self.engine.set_window(window)
        
        # Setup plot
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(12, 8))
        self.freq_bins = np.fft.rfftfreq(nfft, 1/sample_rate)
        
        # Spectrum plot
        self.line1, = self.ax1.plot(self.freq_bins, np.zeros(nfft//2+1), 'b-', linewidth=1)
        self.ax1.set_xlim(0, sample_rate//2)
        self.ax1.set_ylim(0, 100)
        self.ax1.set_xlabel('Frequency (Hz)')
        self.ax1.set_ylabel('Magnitude')
        self.ax1.set_title('🎵 Real-Time Spectrum (GPU Accelerated)')
        self.ax1.grid(True, alpha=0.3)
        
        # Spectrogram (waterfall)
        self.spectrogram_data = np.zeros((100, nfft//2+1))
        self.im = self.ax2.imshow(self.spectrogram_data, aspect='auto', 
                                  extent=[0, sample_rate//2, 0, 100],
                                  cmap='viridis', vmin=0, vmax=50)
        self.ax2.set_xlabel('Frequency (Hz)')
        self.ax2.set_ylabel('Time (frames)')
        self.ax2.set_title('📊 Spectrogram (Waterfall Display)')
        
        # Peak tracking
        self.peak_text = self.ax1.text(0.02, 0.95, '', transform=self.ax1.transAxes,
                                       verticalalignment='top', fontsize=12,
                                       bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.5))
        
        # Performance metrics
        self.fps_text = self.fig.text(0.02, 0.02, '', fontsize=10)
        self.frame_times = []
        
        # Audio simulation parameters
        self.time = 0
        self.stream_idx = 0
        
    def generate_audio_frame(self):
        """Simulate an audio signal with changing characteristics."""
        t = np.linspace(self.time, self.time + self.nfft/self.sample_rate, 
                       self.nfft, dtype=np.float32)
        
        # Create a complex signal with multiple components
        signal = np.zeros(self.nfft, dtype=np.float32)
        
        # Base frequency that sweeps
        base_freq = 1000 + 500 * np.sin(self.time * 0.5)
        signal += 0.5 * np.sin(2 * np.pi * base_freq * t)
        
        # Harmonics
        signal += 0.3 * np.sin(2 * np.pi * base_freq * 2 * t)
        signal += 0.2 * np.sin(2 * np.pi * base_freq * 3 * t)
        
        # Add some musical notes (A4, C#5, E5 - A major chord)
        if np.sin(self.time) > 0:
            signal += 0.4 * np.sin(2 * np.pi * 440 * t)     # A4
            signal += 0.3 * np.sin(2 * np.pi * 554.37 * t)  # C#5
            signal += 0.3 * np.sin(2 * np.pi * 659.25 * t)  # E5
        
        # Random noise
        signal += 0.05 * np.random.randn(self.nfft).astype(np.float32)
        
        # Amplitude modulation
        signal *= (1 + 0.3 * np.sin(2 * np.pi * 5 * t))
        
        self.time += self.nfft / self.sample_rate / 2  # 50% overlap
        
        # Create batch (duplicate for both channels)
        batch = np.tile(signal, self.batch_size)
        return batch
    
    def update(self, frame):
        """Update function for animation."""
        start_time = time.perf_counter()
        
        # Generate new audio
        audio_batch = self.generate_audio_frame()
        
        # Process on GPU
        self.engine.pinned_input(self.stream_idx)[:] = audio_batch
        self.engine.execute_async(self.stream_idx)
        self.engine.sync_stream(self.stream_idx)
        
        # Get magnitude spectrum (just use first channel)
        magnitudes = self.engine.pinned_output(self.stream_idx)[:self.nfft//2+1]
        
        # Update spectrum plot
        self.line1.set_ydata(magnitudes)
        
        # Find and annotate peaks
        peak_idx = np.argmax(magnitudes[10:2000]) + 10  # Ignore DC and very high frequencies
        peak_freq = self.freq_bins[peak_idx]
        peak_mag = magnitudes[peak_idx]
        self.peak_text.set_text(f'🎯 Peak: {peak_freq:.1f} Hz @ {peak_mag:.1f}')
        
        # Update spectrogram
        self.spectrogram_data = np.roll(self.spectrogram_data, -1, axis=0)
        self.spectrogram_data[-1, :] = magnitudes
        self.im.set_data(self.spectrogram_data)
        
        # Calculate and display FPS
        frame_time = time.perf_counter() - start_time
        self.frame_times.append(frame_time)
        if len(self.frame_times) > 30:
            self.frame_times.pop(0)
        
        avg_time = np.mean(self.frame_times)
        fps = 1.0 / avg_time if avg_time > 0 else 0
        self.fps_text.set_text(f'GPU Processing: {avg_time*1000:.1f}ms/frame ({fps:.0f} FPS)')
        
        # Rotate streams
        self.stream_idx = (self.stream_idx + 1) % 3
        
        return self.line1, self.im, self.peak_text, self.fps_text
    
    def run(self):
        """Start the live analyzer."""
        print("🎸 Starting live spectrum analyzer...")
        print("Close the window to stop.")
        
        # Create animation
        anim = FuncAnimation(self.fig, self.update, interval=30, blit=True)
        
        plt.tight_layout()
        plt.show()

def main():
    print("="*60)
    print("🎵 GPU-ACCELERATED LIVE SPECTRUM ANALYZER")
    print("="*60)
    print("\nThis demo simulates a live audio stream with:")
    print("• Sweeping frequencies")
    print("• Musical chord detection")
    print("• Real-time peak tracking")
    print("• Waterfall spectrogram display\n")
    
    analyzer = LiveSpectrumAnalyzer()
    analyzer.run()

if __name__ == "__main__":
    main()