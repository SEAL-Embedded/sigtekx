# Cloud Deployment — SigTekX

Instructions for running SigTekX benchmarks on AWS GPU instances.

## Overview

SigTekX supports cloud deployment via Docker containers on AWS SageMaker Processing Jobs. This enables:

- **GPU benchmarking** on standardized cloud hardware (NVIDIA T4)
- **Reproducible experiments** for paper review
- **ML pipeline integration** via SageMaker Random Cut Forest anomaly detection

## Quick Start

### 1. Docker Build & Local Test

```bash
# Build the production image
docker build -t sigtekx:local .

# Verify the install
docker run --gpus all sigtekx:local python -c "import sigtekx; print(sigtekx.__version__)"

# Run a benchmark
docker run --gpus all sigtekx:local python benchmarks/run_latency.py \
    experiment=ionosphere_test +benchmark=latency
```

### 2. AWS Setup

```bash
# Install AWS CLI and configure credentials
aws configure  # us-east-1 recommended

# Create SageMaker IAM role and S3 bucket
bash scripts/aws/setup_iam.sh
```

**Note:** New AWS accounts have 0 GPU vCPUs. Request a quota increase for "Running On-Demand G and VT instances" (4 vCPUs) under Service Quotas → EC2. Approval takes 1-24 hours.

### 3. Push Image

```bash
docker tag sigtekx:local kevinrhz/sigtekx:latest
docker push kevinrhz/sigtekx:latest
```

Or use the CI workflow — merges to `main` automatically push `kevinrhz/sigtekx:latest`.

### 4. Run on SageMaker

```bash
# Submit a Processing Job (ml.g4dn.xlarge — T4 GPU, ~$0.53/hr)
python scripts/aws/run_sagemaker_job.py --wait

# Download results
bash scripts/aws/download_results.sh

# View in dashboard
sigx dashboard
```

### 5. Anomaly Detection Demo

```bash
# Local mode (sklearn IsolationForest, no AWS needed)
python scripts/aws/anomaly_detection.py --local-only

# SageMaker mode (Random Cut Forest)
python scripts/aws/anomaly_detection.py
```

## Cost Estimate

| Component | Cost |
|-----------|------|
| ml.g4dn.xlarge Processing Job (~30 min) | ~$0.26 |
| RCF training + inference | ~$0.03 |
| S3 storage (1 GB, 1 month) | ~$0.02 |
| **Total per run** | **~$0.31** |

## Teardown

Delete all AWS resources when done:

```bash
# Check for endpoints (CRITICAL — orphaned endpoints cost $2.76/day)
aws sagemaker list-endpoints

# Delete S3 bucket
aws s3 rb s3://sigtekx-benchmark-results --force

# Delete IAM role
aws iam detach-role-policy --role-name SageMakerSigTekX \
    --policy-arn arn:aws:iam::aws:policy/AmazonSageMakerFullAccess
aws iam detach-role-policy --role-name SageMakerSigTekX \
    --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam delete-role --role-name SageMakerSigTekX
```

## Architecture

See `docs/_personal/aws-cloud-architecture.md` for detailed architecture diagrams and decision rationale.

## Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build (builder + production) |
| `scripts/aws/setup_iam.sh` | Creates IAM role and S3 bucket |
| `scripts/aws/run_sagemaker_job.py` | Launches SageMaker Processing Job |
| `scripts/aws/sagemaker_entry.py` | Entry point that runs inside container |
| `scripts/aws/download_results.sh` | Syncs S3 results to local artifacts/ |
| `scripts/aws/anomaly_detection.py` | RCF anomaly detection demo |
| `notebooks/aws_anomaly_detection.ipynb` | Interactive notebook for class presentation |
