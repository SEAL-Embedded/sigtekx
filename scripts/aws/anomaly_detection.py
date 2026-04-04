#!/usr/bin/env python3
"""SageMaker Random Cut Forest anomaly detection on SigTekX spectral output.

Demonstrates end-to-end ML pipeline: raw signal → SigTekX STFT → RCF anomaly detection.
Designed for ionosphere VLF/ULF disturbance detection use case.

Pipeline:
    1. Generate synthetic VLF time-domain signal with SigTekX Engine
    2. Process through SigTekX STFT to get spectral magnitudes
    3. Inject anomalies into spectral output (simulated ionospheric disturbances)
    4. Train anomaly detector on "normal" spectral patterns
    5. Score test data, visualize results
    6. Clean up AWS resources

Prerequisites:
    - SigTekX built and installed (./scripts/cli.sh build)
    - For SageMaker mode: AWS CLI configured, IAM role created
    - pip install sagemaker boto3 matplotlib scikit-learn

Usage:
    python scripts/aws/anomaly_detection.py --local-only  # sklearn, no AWS needed
    python scripts/aws/anomaly_detection.py                # SageMaker RCF
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# -------------------------------------------------------------------
# 1. SigTekX Spectral Processing
# -------------------------------------------------------------------

def generate_spectral_timeseries(
    duration_sec: float = 60.0,
    sample_rate_hz: float = 48000.0,
    nfft: int = 4096,
    overlap: float = 0.75,
    channels: int = 1,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Generate spectral time-series using the SigTekX CUDA engine.

    Creates a synthetic VLF signal, processes it frame-by-frame through
    SigTekX's STFT pipeline, and returns the spectral magnitude output.

    Args:
        duration_sec: Signal duration in seconds.
        sample_rate_hz: Sample rate (Hz).
        nfft: FFT size.
        overlap: Overlap fraction between frames.
        channels: Number of channels.
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (time_per_frame, spectral_frames, n_output_bins).
    """
    from sigtekx import Engine, EngineConfig, ExecutionMode

    rng = np.random.default_rng(seed)
    hop = int(nfft * (1 - overlap))
    n_samples = int(duration_sec * sample_rate_hz)
    n_frames = (n_samples - nfft) // hop + 1
    n_output_bins = nfft // 2 + 1

    # Build a multi-tone VLF signal (simulating ionosphere monitoring)
    t = np.arange(n_samples) / sample_rate_hz
    signal = np.zeros(n_samples, dtype=np.float32)

    # VLF carrier frequencies typical of ionosphere monitoring
    vlf_freqs = [3000, 7800, 12000, 19800]  # Hz
    for freq in vlf_freqs:
        amplitude = rng.uniform(0.5, 2.0)
        phase = rng.uniform(0, 2 * np.pi)
        signal += amplitude * np.sin(2 * np.pi * freq * t + phase).astype(np.float32)

    # Add realistic noise floor
    signal += (rng.standard_normal(n_samples) * 0.1).astype(np.float32)

    # Process through SigTekX engine
    config = EngineConfig(
        nfft=nfft,
        channels=channels,
        sample_rate=sample_rate_hz,
        overlap=overlap,
        mode=ExecutionMode.BATCH,
    )
    engine = Engine(config=config)

    frames = []
    try:
        for i in range(n_frames):
            start = i * hop
            chunk = signal[start : start + nfft * channels]
            if len(chunk) < nfft * channels:
                break
            spectrum = engine.process(chunk)  # shape: (channels, n_output_bins)
            frames.append(spectrum[0])  # Take first channel
    finally:
        engine.close()

    spectral_data = np.array(frames, dtype=np.float32)  # (n_frames, n_output_bins)
    frame_times = np.arange(len(frames)) * hop / sample_rate_hz

    print(f"  SigTekX processed {len(frames)} frames through CUDA STFT pipeline")
    print(f"  Config: nfft={nfft}, overlap={overlap}, sample_rate={sample_rate_hz:.0f} Hz")
    print(f"  Output: {spectral_data.shape[0]} frames x {spectral_data.shape[1]} freq bins")

    return frame_times, spectral_data, n_output_bins


# -------------------------------------------------------------------
# 2. Anomaly Injection
# -------------------------------------------------------------------

def inject_anomalies(
    data: np.ndarray,
    times: np.ndarray,
    frame_rate: float,
    n_anomalies: int = 5,
    seed: int = 123,
) -> tuple[np.ndarray, list[dict]]:
    """Inject synthetic ionospheric disturbances into spectral data.

    Anomaly types simulate real ionospheric phenomena:
        - Power spike: Sudden broadband increase (solar flare / SID)
        - Frequency shift: Enhanced low-frequency power (geomagnetic storm)
        - Narrowband burst: Single-frequency spike (VLF transmitter interference)

    Args:
        data: Spectral magnitude array (n_frames, n_bins).
        times: Time array per frame.
        frame_rate: Frames per second.
        n_anomalies: Number of anomalies to inject.
        seed: Random seed.

    Returns:
        Tuple of (modified_data, anomaly_metadata).
    """
    rng = np.random.default_rng(seed)
    n_frames, n_bins = data.shape
    anomalous = data.copy()
    anomalies = []

    anomaly_types = ["power_spike", "frequency_shift", "narrowband_burst"]

    for i in range(n_anomalies):
        atype = anomaly_types[i % len(anomaly_types)]
        # Place anomalies in the middle 80% of the data
        center_frame = rng.integers(int(n_frames * 0.1), int(n_frames * 0.9))
        duration_frames = max(5, int(rng.uniform(0.5, 2.0) * frame_rate))
        start = max(0, center_frame - duration_frames // 2)
        end = min(n_frames, start + duration_frames)

        if atype == "power_spike":
            # Broadband power increase (5-15x normal) — simulates SID
            factor = rng.uniform(5.0, 15.0)
            anomalous[start:end, :] *= factor
        elif atype == "frequency_shift":
            # Enhanced low-frequency power — simulates geomagnetic storm
            low_bins = n_bins // 4
            anomalous[start:end, :low_bins] *= rng.uniform(8.0, 20.0)
        elif atype == "narrowband_burst":
            # Single frequency bin spike — simulates VLF transmitter
            target_bin = rng.integers(n_bins // 8, n_bins // 2)
            median_power = np.median(data[:, target_bin])
            anomalous[start:end, target_bin] += median_power * rng.uniform(10, 30)

        anomalies.append({
            "type": atype,
            "start_time": float(times[start]),
            "end_time": float(times[min(end - 1, n_frames - 1)]),
            "start_frame": int(start),
            "end_frame": int(end),
        })

    return anomalous, anomalies


# -------------------------------------------------------------------
# 3. Anomaly Detection
# -------------------------------------------------------------------

def run_local_detection(
    train_data: np.ndarray,
    test_data: np.ndarray,
) -> np.ndarray:
    """Run anomaly detection locally using sklearn IsolationForest.

    IsolationForest is conceptually similar to SageMaker's Random Cut Forest —
    both are tree-based unsupervised anomaly detectors.

    Args:
        train_data: Normal spectral data for training.
        test_data: Data to score (may contain anomalies).

    Returns:
        Anomaly scores (higher = more anomalous, range [0, 1]).
    """
    from sklearn.ensemble import IsolationForest

    print("  Training IsolationForest locally...")
    model = IsolationForest(
        n_estimators=200,
        contamination="auto",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(train_data)

    # decision_function: higher = more normal, lower = more anomalous
    raw_scores = model.decision_function(test_data)
    # Invert so higher = more anomalous, then normalize to [0, 1]
    scores = -raw_scores
    score_min, score_max = scores.min(), scores.max()
    if score_max > score_min:
        scores = (scores - score_min) / (score_max - score_min)
    return scores


def run_sagemaker_rcf(
    train_data: np.ndarray,
    test_data: np.ndarray,
    role_arn: str,
    bucket: str = "sigtekx-benchmark-results",
) -> np.ndarray:
    """Train and run SageMaker Random Cut Forest.

    Args:
        train_data: Normal spectral data for training.
        test_data: Data to score.
        role_arn: SageMaker execution role ARN.
        bucket: S3 bucket for training data.

    Returns:
        Anomaly scores from RCF (higher = more anomalous).
    """
    import sagemaker
    from sagemaker import RandomCutForest

    session = sagemaker.Session()
    prefix = "sigtekx-rcf"

    # Upload training data to S3
    print("  Uploading training data to S3...")
    train_buf = io.BytesIO()
    np.savetxt(train_buf, train_data, delimiter=",", fmt="%.6f")
    train_buf.seek(0)

    session.upload_string_as_file_body(
        body=train_buf.getvalue().decode(),
        bucket=bucket,
        key=f"{prefix}/train/data.csv",
    )

    # Train RCF
    print("  Training Random Cut Forest...")
    rcf = RandomCutForest(
        role=role_arn,
        instance_count=1,
        instance_type="ml.m5.large",
        num_trees=100,
        num_samples_per_tree=256,
        output_path=f"s3://{bucket}/{prefix}/output/",
        sagemaker_session=session,
    )

    rcf.fit(rcf.record_set(train_data.astype(np.float32)))
    print("  Training complete.")

    # Deploy endpoint for inference
    print("  Deploying endpoint (will delete after inference)...")
    predictor = rcf.deploy(
        initial_instance_count=1,
        instance_type="ml.m5.large",
    )

    try:
        # Score test data in batches
        print("  Scoring test data...")
        batch_size = 500
        all_scores = []
        for i in range(0, len(test_data), batch_size):
            batch = test_data[i:i + batch_size].astype(np.float32)
            result = predictor.predict(batch)
            scores = [r["score"]["float32"] for r in result["scores"]]
            all_scores.extend(scores)

        scores = np.array(all_scores)
        # Normalize to [0, 1]
        score_min, score_max = scores.min(), scores.max()
        if score_max > score_min:
            scores = (scores - score_min) / (score_max - score_min)
    finally:
        # CRITICAL: Always delete endpoint to avoid charges ($2.76/day)
        print("  Deleting endpoint...")
        predictor.delete_endpoint()
        print("  Endpoint deleted.")

    return scores


# -------------------------------------------------------------------
# 4. Metrics & Visualization
# -------------------------------------------------------------------

def compute_detection_metrics(
    scores: np.ndarray,
    anomaly_meta: list[dict],
    threshold: float,
) -> dict:
    """Compute detection precision/recall against ground truth.

    Args:
        scores: Anomaly scores per frame (higher = more anomalous).
        anomaly_meta: Injected anomaly metadata with start_frame/end_frame.
        threshold: Detection threshold.

    Returns:
        Dictionary with precision, recall, F1, and counts.
    """
    detected = scores > threshold
    n_frames = len(scores)

    # Build ground truth mask from anomaly metadata
    gt_mask = np.zeros(n_frames, dtype=bool)
    for a in anomaly_meta:
        s = max(0, a["start_frame"])
        e = min(n_frames, a["end_frame"])
        gt_mask[s:e] = True

    tp = int(np.sum(detected & gt_mask))
    fp = int(np.sum(detected & ~gt_mask))
    fn = int(np.sum(~detected & gt_mask))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "threshold": float(threshold),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "n_detected": int(np.sum(detected)),
        "n_anomalous_frames": int(np.sum(gt_mask)),
        "n_total_frames": n_frames,
    }


def find_optimal_threshold(
    scores: np.ndarray,
    anomaly_meta: list[dict],
) -> float:
    """Find threshold that maximizes F1 score.

    Tests percentiles from 80th to 99th and picks the best.
    """
    best_f1, best_thresh = 0.0, float(np.percentile(scores, 95))
    for pct in range(80, 100):
        thresh = float(np.percentile(scores, pct))
        m = compute_detection_metrics(scores, anomaly_meta, thresh)
        if m["f1"] > best_f1:
            best_f1 = m["f1"]
            best_thresh = thresh
    return best_thresh


def plot_results(
    times: np.ndarray,
    spectral_data: np.ndarray,
    scores: np.ndarray,
    anomaly_meta: list[dict],
    threshold: float,
    metrics: dict,
    output_path: Path,
    title_suffix: str = "",
):
    """Create 3-panel visualization: spectrogram, scores, detections."""
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    # Panel 1: Spectrogram
    ax1 = axes[0]
    # Use a subset of bins for clearer visualization
    n_show_bins = min(256, spectral_data.shape[1])
    im = ax1.imshow(
        spectral_data[:, :n_show_bins].T,
        aspect="auto",
        origin="lower",
        extent=[times[0], times[-1], 0, n_show_bins],
        cmap="viridis",
    )
    ax1.set_ylabel("Frequency Bin")
    ax1.set_title(f"SigTekX STFT Spectral Output{title_suffix}")
    plt.colorbar(im, ax=ax1, label="Magnitude")
    for a in anomaly_meta:
        ax1.axvspan(a["start_time"], a["end_time"], alpha=0.3, color="red")

    # Panel 2: Anomaly scores
    ax2 = axes[1]
    ax2.plot(times[:len(scores)], scores, color="darkred", linewidth=0.5)
    ax2.axhline(y=threshold, color="orange", linestyle="--",
                label=f"Threshold ({threshold:.3f})")
    ax2.set_ylabel("Anomaly Score")
    ax2.set_title("Anomaly Detection Scores")
    for a in anomaly_meta:
        ax2.axvspan(a["start_time"], a["end_time"], alpha=0.2, color="red")
    ax2.legend()

    # Panel 3: Detection result
    ax3 = axes[2]
    detected = (scores > threshold).astype(float)
    ax3.fill_between(times[:len(scores)], detected, alpha=0.5, color="red", label="Detected")
    for i, a in enumerate(anomaly_meta):
        ax3.axvspan(a["start_time"], a["end_time"], alpha=0.2, color="blue",
                    label="Ground Truth" if i == 0 else None)
    ax3.set_ylabel("Anomaly Detected")
    ax3.set_xlabel("Time (seconds)")
    p, r, f = metrics["precision"], metrics["recall"], metrics["f1"]
    ax3.set_title(f"Detection Results  (Precision={p:.2f}  Recall={r:.2f}  F1={f:.2f})")
    ax3.set_ylim(-0.1, 1.5)
    ax3.legend(loc="upper right")

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"  Saved: {output_path}")
    plt.close(fig)


# -------------------------------------------------------------------
# 5. Main
# -------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SigTekX + anomaly detection demo (IsolationForest or SageMaker RCF)"
    )
    parser.add_argument(
        "--local-only", action="store_true",
        help="Use sklearn IsolationForest instead of SageMaker RCF",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("artifacts/anomaly_detection"),
        help="Output directory for results",
    )
    parser.add_argument(
        "--duration", type=float, default=60.0,
        help="Duration of synthetic signal in seconds (default: 60)",
    )
    parser.add_argument(
        "--nfft", type=int, default=4096,
        help="FFT size for SigTekX engine (default: 4096)",
    )
    parser.add_argument(
        "--role", default="SageMakerSigTekX",
        help="IAM role name (for SageMaker mode)",
    )
    args = parser.parse_args()

    print("=== SigTekX Anomaly Detection Demo ===\n")

    # Step 1: Generate spectral data using SigTekX CUDA engine
    print("[1/5] Processing signal through SigTekX STFT engine...")
    times, spectral_data, n_bins = generate_spectral_timeseries(
        duration_sec=args.duration,
        nfft=args.nfft,
    )
    frame_rate = 1.0 / (times[1] - times[0]) if len(times) > 1 else 1.0

    # Step 2: Split into train (normal) and test, inject anomalies into test
    split_idx = int(len(spectral_data) * 0.6)
    train_data = spectral_data[:split_idx]
    test_base = spectral_data[split_idx:]
    test_times = times[split_idx:]

    print(f"\n[2/5] Injecting synthetic ionospheric disturbances...")
    test_data, anomaly_meta = inject_anomalies(
        test_base, test_times, frame_rate, n_anomalies=5,
    )
    # Frame indices are already relative to test_base (inject_anomalies works on the subarray)
    print(f"  Injected {len(anomaly_meta)} anomalies:")
    for a in anomaly_meta:
        print(f"    {a['type']:20s}  t={a['start_time']:.2f}s - {a['end_time']:.2f}s  "
              f"({a['end_frame'] - a['start_frame']} frames)")

    # Step 3: Run anomaly detection
    if args.local_only:
        print(f"\n[3/5] Running anomaly detection (IsolationForest)...")
        scores = run_local_detection(train_data, test_data)
        method = "IsolationForest (local)"
    else:
        print(f"\n[3/5] Running SageMaker RCF anomaly detection...")
        try:
            import boto3
            role_arn = boto3.client("iam").get_role(
                RoleName=args.role
            )["Role"]["Arn"]
            scores = run_sagemaker_rcf(train_data, test_data, role_arn)
            method = "Random Cut Forest (SageMaker)"
        except Exception as e:
            print(f"  SageMaker unavailable: {e}")
            print("  Falling back to local IsolationForest...")
            scores = run_local_detection(train_data, test_data)
            method = "IsolationForest (local fallback)"

    # Step 4: Compute metrics with optimized threshold
    print(f"\n[4/5] Computing detection metrics...")
    threshold = find_optimal_threshold(scores, anomaly_meta)
    metrics = compute_detection_metrics(scores, anomaly_meta, threshold)
    print(f"  Method:    {method}")
    print(f"  Precision: {metrics['precision']:.3f}")
    print(f"  Recall:    {metrics['recall']:.3f}")
    print(f"  F1 Score:  {metrics['f1']:.3f}")
    print(f"  Threshold: {metrics['threshold']:.4f} (auto-optimized)")
    print(f"  Detected:  {metrics['n_detected']} frames "
          f"({metrics['true_positives']} TP, {metrics['false_positives']} FP, "
          f"{metrics['false_negatives']} FN)")

    # Step 5: Visualize
    print(f"\n[5/5] Generating visualization...")
    plot_results(
        test_times, test_data, scores, anomaly_meta, threshold, metrics,
        args.output_dir / "anomaly_detection_results.png",
        title_suffix=f" — {method}",
    )

    # Save metrics CSV
    metrics_df = pd.DataFrame([{**metrics, "method": method}])
    metrics_path = args.output_dir / "detection_metrics.csv"
    metrics_df.to_csv(metrics_path, index=False)
    print(f"  Saved: {metrics_path}")

    print(f"\n=== Demo Complete ===")
    print(f"Results in: {args.output_dir}/")


if __name__ == "__main__":
    main()
