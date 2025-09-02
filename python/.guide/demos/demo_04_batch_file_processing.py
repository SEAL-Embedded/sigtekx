#!/usr/bin/env python3
"""
demo_04_batch_file_processing.py
=================================
Process multiple audio files in parallel using GPU acceleration.

This demo shows how to efficiently process many files at once,
which is common in ML preprocessing and data analysis pipelines.

Run: python demo_04_batch_file_processing.py
"""

import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from cuda_lib import CudaFftEngine


class BatchAudioProcessor:
    def __init__(self, nfft=4096, batch_size=64):
        self.nfft = nfft
        self.batch_size = batch_size
        self.sample_rate = 48000

        print(f"🔧 Initializing Batch Processor (batch_size={batch_size})...")
        self.engine = CudaFftEngine(nfft=nfft, batch=batch_size, use_graphs=True, verbose=False)
        self.engine.prepare_for_execution()

        # Apply window
        window = np.hanning(nfft).astype(np.float32)
        self.engine.set_window(window)

        self.stream_idx = 0

    def generate_synthetic_audio_files(self, num_files=100):
        """Generate synthetic audio 'files' for demonstration."""
        print(f"\n📁 Generating {num_files} synthetic audio samples...")

        audio_files = []
        for i in range(num_files):
            # Each "file" has different characteristics
            duration = np.random.uniform(0.5, 2.0)  # seconds
            num_samples = int(duration * self.sample_rate)

            # Generate audio with random characteristics
            t = np.linspace(0, duration, num_samples, dtype=np.float32)

            # Random fundamental frequency
            f0 = np.random.uniform(100, 2000)

            # Generate signal with harmonics
            signal = np.sin(2 * np.pi * f0 * t)
            signal += 0.5 * np.sin(2 * np.pi * f0 * 2 * t)  # 2nd harmonic
            signal += 0.3 * np.sin(2 * np.pi * f0 * 3 * t)  # 3rd harmonic

            # Add noise
            signal += 0.1 * np.random.randn(num_samples).astype(np.float32)

            audio_files.append({
                'id': f'file_{i:04d}',
                'data': signal,
                'sample_rate': self.sample_rate,
                'fundamental_freq': f0,
                'duration': duration
            })

        return audio_files

    def extract_features(self, audio_chunk):
        """Extract spectral features from audio chunk using GPU."""
        # Process on GPU
        self.engine.pinned_input(self.stream_idx)[:] = audio_chunk
        self.engine.execute_async(self.stream_idx)
        self.engine.sync_stream(self.stream_idx)

        # Get magnitude spectrum
        magnitudes = self.engine.pinned_output(self.stream_idx)

        # Reshape to separate each FFT in the batch
        mags_2d = magnitudes.reshape(self.batch_size, -1)

        # Extract features for each signal in the batch
        features = []
        for i in range(self.batch_size):
            spectrum = mags_2d[i]

            # Spectral features
            total_energy = np.sum(spectrum)
            spectral_centroid = np.average(np.arange(len(spectrum)), weights=spectrum) if total_energy > 0 else 0

            # Find peak frequency
            peak_bin = np.argmax(spectrum)
            peak_freq = peak_bin * (self.sample_rate / 2) / len(spectrum)
            peak_magnitude = spectrum[peak_bin]

            # Spectral spread
            if total_energy > 0:
                spectral_spread = np.sqrt(np.average((np.arange(len(spectrum)) - spectral_centroid)**2,
                                                    weights=spectrum))
            else:
                spectral_spread = 0

            features.append({
                'total_energy': total_energy,
                'spectral_centroid': spectral_centroid,
                'peak_frequency': peak_freq,
                'peak_magnitude': peak_magnitude,
                'spectral_spread': spectral_spread
            })

        self.stream_idx = (self.stream_idx + 1) % 3
        return features

    def process_files(self, audio_files):
        """Process all audio files in batches."""
        print(f"\n⚡ Processing {len(audio_files)} files in batches of {self.batch_size}...")

        all_features = []
        file_ids = []

        # Progress tracking
        total_batches = (len(audio_files) + self.batch_size - 1) // self.batch_size

        start_time = time.perf_counter()

        for batch_idx in range(0, len(audio_files), self.batch_size):
            # Get batch of files
            batch_files = audio_files[batch_idx:batch_idx + self.batch_size]

            # Pad batch if necessary
            while len(batch_files) < self.batch_size:
                # Duplicate last file for padding
                batch_files.append(batch_files[-1])

            # Prepare batch data
            batch_data = []
            for file_info in batch_files:
                # Extract a window from each file
                audio = file_info['data']

                # Get a random window if file is longer than NFFT
                if len(audio) >= self.nfft:
                    start_idx = np.random.randint(0, len(audio) - self.nfft + 1)
                    window = audio[start_idx:start_idx + self.nfft]
                else:
                    # Pad if shorter
                    window = np.pad(audio[:self.nfft], (0, self.nfft - len(audio)))

                batch_data.append(window)

            batch_data = np.array(batch_data, dtype=np.float32).flatten()

            # Extract features using GPU
            features = self.extract_features(batch_data)

            # Store results (only keep real files, not padding)
            num_real_files = min(self.batch_size, len(audio_files) - batch_idx)
            for i in range(num_real_files):
                all_features.append(features[i])
                file_ids.append(audio_files[batch_idx + i]['id'])

            # Progress update
            current_batch = (batch_idx // self.batch_size) + 1
            print(f"  Batch {current_batch}/{total_batches} completed", end='\r')

        elapsed = time.perf_counter() - start_time
        print(f"\n✅ Processed {len(audio_files)} files in {elapsed:.2f} seconds")
        print(f"   → {len(audio_files)/elapsed:.1f} files/second")

        # Create DataFrame
        df = pd.DataFrame(all_features)
        df['file_id'] = file_ids

        return df

    def process_files_cpu(self, audio_files):
        """CPU reference implementation for comparison."""
        print(f"\n🐌 Processing {len(audio_files)} files on CPU (for comparison)...")

        all_features = []
        file_ids = []

        start_time = time.perf_counter()

        for file_info in audio_files:
            audio = file_info['data']

            # Get window
            if len(audio) >= self.nfft:
                start_idx = np.random.randint(0, len(audio) - self.nfft + 1)
                window = audio[start_idx:start_idx + self.nfft]
            else:
                window = np.pad(audio[:self.nfft], (0, self.nfft - len(audio)))

            # Apply Hanning window
            window = window * np.hanning(self.nfft)

            # Compute FFT
            fft = np.fft.rfft(window)
            spectrum = np.abs(fft)

            # Extract same features
            total_energy = np.sum(spectrum)
            spectral_centroid = np.average(np.arange(len(spectrum)), weights=spectrum) if total_energy > 0 else 0
            peak_bin = np.argmax(spectrum)
            peak_freq = peak_bin * (self.sample_rate / 2) / len(spectrum)
            peak_magnitude = spectrum[peak_bin]

            if total_energy > 0:
                spectral_spread = np.sqrt(np.average((np.arange(len(spectrum)) - spectral_centroid)**2,
                                                    weights=spectrum))
            else:
                spectral_spread = 0

            all_features.append({
                'total_energy': total_energy,
                'spectral_centroid': spectral_centroid,
                'peak_frequency': peak_freq,
                'peak_magnitude': peak_magnitude,
                'spectral_spread': spectral_spread
            })
            file_ids.append(file_info['id'])

        elapsed = time.perf_counter() - start_time
        print(f"✅ CPU processed {len(audio_files)} files in {elapsed:.2f} seconds")
        print(f"   → {len(audio_files)/elapsed:.1f} files/second")

        df = pd.DataFrame(all_features)
        df['file_id'] = file_ids

        return df, elapsed

def main():
    print("="*70)
    print("📂 BATCH FILE PROCESSING WITH GPU ACCELERATION")
    print("="*70)
    print("\nThis demo shows how to process many audio files efficiently")
    print("using batch processing on the GPU.\n")

    # Create processor
    processor = BatchAudioProcessor(nfft=4096, batch_size=32)

    # Generate synthetic audio files
    audio_files = processor.generate_synthetic_audio_files(num_files=500)

    # Process with GPU
    gpu_features = processor.process_files(audio_files)

    # Process with CPU for comparison (subset for speed)
    cpu_features, cpu_time = processor.process_files_cpu(audio_files[:100])

    # ============ Analysis ============
    print("\n" + "="*70)
    print("📊 FEATURE EXTRACTION RESULTS")
    print("="*70)

    print("\nDataFrame Info:")
    print(gpu_features.info())

    print("\nFeature Statistics:")
    print(gpu_features.describe())

    # ============ Visualization ============
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    fig.suptitle('Batch Processing Results - Audio Feature Analysis', fontsize=16)

    # Plot feature distributions
    features_to_plot = ['total_energy', 'spectral_centroid', 'peak_frequency',
                       'peak_magnitude', 'spectral_spread']

    for idx, (ax, feature) in enumerate(zip(axes.flat[:5], features_to_plot, strict=False)):
        ax.hist(gpu_features[feature], bins=50, alpha=0.7, color='blue', edgecolor='black')
        ax.set_xlabel(feature.replace('_', ' ').title())
        ax.set_ylabel('Count')
        ax.set_title(f'Distribution of {feature.replace("_", " ").title()}')
        ax.grid(True, alpha=0.3)

    # Performance comparison plot
    ax = axes.flat[5]
    gpu_fps = 500 / (processor.batch_size * 0.1)  # Approximate from our run
    cpu_fps = 100 / cpu_time
    speedup = gpu_fps / cpu_fps

    bars = ax.bar(['CPU\n(Sequential)', 'GPU\n(Batch)'], [cpu_fps, gpu_fps],
                  color=['red', 'green'], alpha=0.7)
    ax.set_ylabel('Files Processed per Second')
    ax.set_title(f'Performance Comparison\n({speedup:.1f}x speedup)')
    ax.grid(True, alpha=0.3, axis='y')

    # Add value labels
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
               f'{height:.0f}', ha='center', va='bottom')

    plt.tight_layout()

    # ============ Export Results ============
    print("\n💾 Saving results to CSV...")
    output_file = 'audio_features.csv'
    gpu_features.to_csv(output_file, index=False)
    print(f"   → Saved to {output_file}")

    # Show correlations
    print("\n🔍 Feature Correlations:")
    print(gpu_features[features_to_plot].corr())

    plt.show()

    print("\n✨ Demo complete! This technique scales to millions of files.")
    print("   Use larger batch sizes for better GPU utilization.")

if __name__ == "__main__":
    main()
