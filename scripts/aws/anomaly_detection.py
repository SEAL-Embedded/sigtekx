#!/usr/bin/env python3
"""SageMaker Random Cut Forest anomaly detection on SigTekX spectral output.

Demonstrates ML pipeline integration: SigTekX spectral analysis -> RCF anomaly detection.
Designed for ionosphere VLF/ULF disturbance detection use case.

Pipeline:
    1. Generate synthetic spectral time-series (simulating SigTekX output)
    2. Inject anomalies (simulated ionospheric disturbances)
    3. Train RCF on "normal" patterns
    4. Score test data for anomalies
    5. Visualize results
    6. Clean up AWS resources

Prerequisites:
    - AWS CLI configured
    - SageMaker IAM role (scripts/aws/setup_iam.sh)
    - pip install sagemaker boto3 matplotlib

Usage:
    python scripts/aws/anomaly_detection.py
    python scripts/aws/anomaly_detection.py --local-only  # Skip SageMaker, use sklearn
"""

from __future__ import annotations

import argparse
import io
import os
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# -------------------------------------------------------------------
# 1. Synthetic Spectral Data Generation
# -------------------------------------------------------------------

def generate_spectral_timeseries(
    duration_sec: float = 300.0,
    sample_rate_hz: float = 48000.0,
    nfft: int = 4096,
    overlap: float = 0.75,
    n_freq_bins: int = 64,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Generate synthetic spectral magnitude time-series.

    Simulates SigTekX STFT output: each row is a time frame, each column
    is a frequency bin's magnitude.

    Args:
        duration_sec: Total duration of the synthetic signal.
        sample_rate_hz: Sample rate (Hz) — matches ionosphere config.
        nfft: FFT size.
        overlap: Overlap fraction.
        n_freq_bins: Number of frequency bins to use (subset of nfft/2+1).
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (time_frames, spectral_data, frame_rate_hz).
    """
    rng = np.random.default_rng(seed)
    hop = int(nfft * (1 - overlap))
    frame_rate = sample_rate_hz / hop
    n_frames = int(duration_sec * frame_rate)

    # Base spectral shape: VLF/ULF frequency profile (decreasing power with frequency)
    freq_profile = np.exp(-np.linspace(0, 3, n_freq_bins))

    # Generate time-varying spectral data with natural fluctuations
    t = np.arange(n_frames) / frame_rate
    data = np.zeros((n_frames, n_freq_bins), dtype=np.float32)

    for i in range(n_freq_bins):
        # Each bin has a baseline plus slow modulation plus noise
        baseline = freq_profile[i] * 100
        modulation = 5.0 * np.sin(2 * np.pi * 0.01 * t + rng.uniform(0, 2 * np.pi))
        noise = rng.normal(0, 2.0, n_frames)
        data[:, i] = baseline + modulation + noise

    return t, np.clip(data, 0, None), frame_rate


def inject_anomalies(
    data: np.ndarray,
    times: np.ndarray,
    frame_rate: float,
    n_anomalies: int = 5,
    seed: int = 123,
) -> tuple[np.ndarray, list[dict]]:
    """Inject synthetic ionospheric disturbances into spectral data.

    Anomaly types:
        - Power spike: Sudden broadband increase (solar flare / SID)
        - Frequency shift: Enhanced low-frequency power (geomagnetic storm)
        - Narrowband burst: Single-frequency spike (artificial VLF transmitter)

    Args:
        data: Spectral magnitude array (n_frames, n_bins).
        times: Time array.
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
        duration_frames = int(rng.uniform(1.0, 5.0) * frame_rate)
        start = max(0, center_frame - duration_frames // 2)
        end = min(n_frames, start + duration_frames)

        if atype == "power_spike":
            # Broadband power increase (3-8x normal)
            factor = rng.uniform(3.0, 8.0)
            anomalous[start:end, :] *= factor
        elif atype == "frequency_shift":
            # Enhanced low-frequency power
            low_bins = n_bins // 4
            anomalous[start:end, :low_bins] *= rng.uniform(4.0, 10.0)
        elif atype == "narrowband_burst":
            # Single frequency bin spike
            target_bin = rng.integers(0, n_bins)
            anomalous[start:end, target_bin] += rng.uniform(200, 500)

        anomalies.append({
            "type": atype,
            "start_time": times[start],
            "end_time": times[min(end, n_frames - 1)],
            "start_frame": int(start),
            "end_frame": int(end),
        })

    return anomalous, anomalies


# -------------------------------------------------------------------
# 2. Local Anomaly Detection (sklearn fallback)
# -------------------------------------------------------------------

def run_local_detection(
    train_data: np.ndarray,
    test_data: np.ndarray,
) -> np.ndarray:
    """Run anomaly detection locally using sklearn IsolationForest.

    This is the offline fallback when SageMaker is not available.
    Isolation Forest is conceptually similar to Random Cut Forest.

    Args:
        train_data: Normal spectral data for training.
        test_data: Data to score (may contain anomalies).

    Returns:
        Anomaly scores (higher = more anomalous).
    """
    from sklearn.ensemble import IsolationForest

    print("Training IsolationForest locally...")
    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(train_data)

    # Score: sklearn returns negative scores (more negative = more anomalous)
    # Convert to positive scores for consistency with RCF
    raw_scores = model.decision_function(test_data)
    # Invert and shift so higher = more anomalous
    scores = -raw_scores
    scores = (scores - scores.min()) / (scores.max() - scores.min() + 1e-10)
    return scores


# -------------------------------------------------------------------
# 3. SageMaker RCF Detection
# -------------------------------------------------------------------

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
        Anomaly scores from RCF.
    """
    import sagemaker
    from sagemaker import RandomCutForest

    session = sagemaker.Session()
    prefix = "sigtekx-rcf"

    # Upload training data to S3
    print("Uploading training data to S3...")
    train_buf = io.BytesIO()
    np.savetxt(train_buf, train_data, delimiter=",", fmt="%.6f")
    train_buf.seek(0)

    s3_train = session.upload_string_as_file_body(
        body=train_buf.getvalue().decode(),
        bucket=bucket,
        key=f"{prefix}/train/data.csv",
    )
    s3_train_path = f"s3://{bucket}/{prefix}/train/"

    # Train RCF
    print("Training Random Cut Forest...")
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
    print("Training complete.")

    # Deploy endpoint for inference
    print("Deploying endpoint (will delete after inference)...")
    predictor = rcf.deploy(
        initial_instance_count=1,
        instance_type="ml.m5.large",
    )

    try:
        # Score test data in batches
        print("Scoring test data...")
        batch_size = 500
        all_scores = []
        for i in range(0, len(test_data), batch_size):
            batch = test_data[i:i + batch_size].astype(np.float32)
            result = predictor.predict(batch)
            scores = [r["score"]["float32"] for r in result["scores"]]
            all_scores.extend(scores)

        scores = np.array(all_scores)
    finally:
        # CRITICAL: Always delete endpoint to avoid charges
        print("Deleting endpoint...")
        predictor.delete_endpoint()
        print("Endpoint deleted.")

    return scores


# -------------------------------------------------------------------
# 4. Visualization
# -------------------------------------------------------------------

def plot_results(
    times: np.ndarray,
    spectral_data: np.ndarray,
    scores: np.ndarray,
    anomaly_meta: list[dict],
    output_path: Path,
    title_suffix: str = "",
):
    """Create visualization of spectral data with anomaly overlay.

    Args:
        times: Time array.
        spectral_data: Spectral magnitude data.
        scores: Anomaly scores per frame.
        anomaly_meta: List of injected anomaly metadata.
        output_path: Path to save the figure.
        title_suffix: Additional title text.
    """
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    # Panel 1: Spectrogram
    ax1 = axes[0]
    im = ax1.imshow(
        spectral_data.T,
        aspect="auto",
        origin="lower",
        extent=[times[0], times[-1], 0, spectral_data.shape[1]],
        cmap="viridis",
    )
    ax1.set_ylabel("Frequency Bin")
    ax1.set_title(f"SigTekX Spectral Output{title_suffix}")
    plt.colorbar(im, ax=ax1, label="Magnitude")

    # Mark anomaly regions
    for a in anomaly_meta:
        ax1.axvspan(a["start_time"], a["end_time"], alpha=0.3, color="red", label=a["type"])

    # Panel 2: Anomaly scores
    ax2 = axes[1]
    ax2.plot(times[:len(scores)], scores, color="darkred", linewidth=0.5)
    ax2.set_ylabel("Anomaly Score")
    ax2.set_title("Anomaly Detection Scores")

    # Threshold line (mean + 2*std)
    threshold = np.mean(scores) + 2 * np.std(scores)
    ax2.axhline(y=threshold, color="orange", linestyle="--", label=f"Threshold ({threshold:.3f})")
    ax2.legend()

    # Mark anomaly regions
    for a in anomaly_meta:
        ax2.axvspan(a["start_time"], a["end_time"], alpha=0.2, color="red")

    # Panel 3: Detected anomalies (binary)
    ax3 = axes[2]
    detected = (scores > threshold).astype(float)
    ax3.fill_between(times[:len(scores)], detected, alpha=0.5, color="red", label="Detected")
    ax3.set_ylabel("Anomaly Detected")
    ax3.set_xlabel("Time (seconds)")
    ax3.set_title("Detection Results")
    ax3.set_ylim(-0.1, 1.5)

    # Ground truth markers
    for a in anomaly_meta:
        ax3.axvspan(a["start_time"], a["end_time"], alpha=0.2, color="blue", label="Ground Truth")

    ax3.legend(loc="upper right")

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Saved figure: {output_path}")
    plt.close(fig)


def compute_detection_metrics(
    scores: np.ndarray,
    anomaly_meta: list[dict],
    n_frames: int,
) -> dict:
    """Compute detection precision/recall against ground truth.

    Args:
        scores: Anomaly scores per frame.
        anomaly_meta: Injected anomaly metadata.
        n_frames: Total number of frames.

    Returns:
        Dictionary with precision, recall, F1.
    """
    threshold = np.mean(scores) + 2 * np.std(scores)
    detected = scores > threshold

    # Build ground truth mask
    gt_mask = np.zeros(n_frames, dtype=bool)
    for a in anomaly_meta:
        gt_mask[a["start_frame"]:a["end_frame"]] = True
    gt_mask = gt_mask[:len(scores)]

    tp = np.sum(detected & gt_mask)
    fp = np.sum(detected & ~gt_mask)
    fn = np.sum(~detected & gt_mask)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "threshold": float(threshold),
        "n_detected": int(np.sum(detected)),
        "n_anomalous_frames": int(np.sum(gt_mask)),
    }


# -------------------------------------------------------------------
# 5. Main
# -------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SigTekX + SageMaker RCF anomaly detection demo"
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Use sklearn IsolationForest instead of SageMaker RCF",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/anomaly_detection"),
        help="Output directory for results",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=300.0,
        help="Duration of synthetic signal (seconds)",
    )
    parser.add_argument(
        "--role",
        default="SageMakerSigTekX",
        help="IAM role name (for SageMaker mode)",
    )
    args = parser.parse_args()

    print("=== SigTekX Anomaly Detection Demo ===\n")

    # Step 1: Generate synthetic spectral data
    print("[1/5] Generating synthetic spectral time-series...")
    times, normal_data, frame_rate = generate_spectral_timeseries(
        duration_sec=args.duration,
    )
    print(f"  Generated {normal_data.shape[0]} frames, {normal_data.shape[1]} freq bins")
    print(f"  Frame rate: {frame_rate:.1f} Hz")

    # Step 2: Split into train (normal) and test, then inject anomalies into test
    split_idx = int(len(normal_data) * 0.6)
    train_data = normal_data[:split_idx]
    test_base = normal_data[split_idx:]
    test_times = times[split_idx:]

    print(f"\n[2/5] Injecting synthetic ionospheric disturbances...")
    test_data, anomaly_meta = inject_anomalies(
        test_base, test_times, frame_rate, n_anomalies=5,
    )
    # Adjust anomaly frame indices relative to test set
    for a in anomaly_meta:
        a["start_frame"] -= split_idx
        a["end_frame"] -= split_idx
    print(f"  Injected {len(anomaly_meta)} anomalies:")
    for a in anomaly_meta:
        print(f"    - {a['type']} at t={a['start_time']:.1f}s-{a['end_time']:.1f}s")

    # Step 3: Run anomaly detection
    if args.local_only:
        print(f"\n[3/5] Running local anomaly detection (IsolationForest)...")
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
            print(f"  SageMaker failed: {e}")
            print("  Falling back to local IsolationForest...")
            scores = run_local_detection(train_data, test_data)
            method = "IsolationForest (local fallback)"

    # Step 4: Compute metrics
    print(f"\n[4/5] Computing detection metrics...")
    metrics = compute_detection_metrics(scores, anomaly_meta, len(test_data))
    print(f"  Method:    {method}")
    print(f"  Precision: {metrics['precision']:.3f}")
    print(f"  Recall:    {metrics['recall']:.3f}")
    print(f"  F1 Score:  {metrics['f1']:.3f}")
    print(f"  Threshold: {metrics['threshold']:.4f}")
    print(f"  Detected frames: {metrics['n_detected']}/{len(scores)}")

    # Step 5: Visualize
    print(f"\n[5/5] Generating visualization...")
    plot_results(
        test_times,
        test_data,
        scores,
        anomaly_meta,
        args.output_dir / "anomaly_detection_results.png",
        title_suffix=f" — {method}",
    )

    # Save metrics
    metrics_df = pd.DataFrame([{**metrics, "method": method}])
    metrics_path = args.output_dir / "detection_metrics.csv"
    metrics_df.to_csv(metrics_path, index=False)
    print(f"Saved metrics: {metrics_path}")

    print(f"\n=== Demo Complete ===")
    print(f"Results in: {args.output_dir}/")


if __name__ == "__main__":
    main()
