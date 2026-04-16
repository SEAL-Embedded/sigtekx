# Cloud Deployment — SigTekX

Instructions for running SigTekX benchmarks on AWS GPU instances.

## Overview

SigTekX runs cloud benchmarks on **EC2 spot GPU instances** using a Docker image
pulled from **Amazon ECR**. Results are uploaded to **S3** and container logs stream
to **CloudWatch Logs**.

Services used:

| Service | Role |
|---------|------|
| **IAM** | EC2 instance role scoped to the benchmark S3 bucket and CloudWatch log group |
| **ECR** | Private Docker registry for the `sigtekx` image |
| **EC2** | `g4dn.xlarge` spot GPU instance (NVIDIA T4) that runs the benchmark container |
| **S3** | Stores benchmark result CSVs (`sigtekx-benchmark-results`) |
| **CloudWatch Logs** | Captures container stdout/stderr in `/sigtekx/benchmarks` |

### Resource configuration reference

These are the recommended settings if provisioning via the AWS console instead of
`scripts/aws/setup_iam.sh`:

- **S3 bucket** `sigtekx-benchmark-results` (us-west-2): Block all public access
  **on**, ACLs disabled (bucket owner enforced), SSE-S3 encryption, versioning off.
- **ECR repository** `sigtekx` (us-west-2): private, image tag mutability **Mutable**
  (so `latest` can slide forward), AES-256 encryption.
- **CloudWatch log group** `/sigtekx/benchmarks` (us-west-2): standard log class,
  **30-day retention** to cap storage costs, deletion protection off.
- **IAM role** `SigTekXEC2BenchmarkRole`: trust policy for `ec2.amazonaws.com`.
  Either attach the inline policy from `setup_iam.sh` (scoped to the bucket and log
  group above) or the AWS managed policies `AmazonEC2ContainerRegistryReadOnly`,
  `CloudWatchAgentServerPolicy`, and an S3 policy covering the results bucket. An
  instance profile of the same name must exist so EC2 can assume the role at launch.

## Cost monitoring

Before running anything, wire up a billing alarm so a forgotten spot instance
can't silently burn through the budget:

1. Root account → **Billing preferences** → enable *Receive Billing Alerts*
   (publishes `EstimatedCharges` to CloudWatch in `us-east-1`).
2. **CloudWatch (us-east-1)** → create a static alarm on the `EstimatedCharges`
   metric with a threshold that matches your tolerance (e.g. $20 USD).
3. Create an **SNS topic** for the alarm action and confirm the email subscription
   from the SNS console — confirmation links delivered by email are sometimes
   pre-fetched by security scanners, which silently invalidates them.

## Prerequisites

- AWS CLI v2 configured (`aws configure`, region `us-west-2` / Oregon recommended)
- Docker running locally
- An SSH key pair in the target region (e.g. `sigtekx.pem`)
- GPU vCPU quota — new AWS accounts have 0. Request "Running On-Demand G and VT
  instances" (≥4 vCPUs) under Service Quotas → EC2. Approval takes 1–24 hours.
  Spot instances use a separate quota: "All G and VT Spot Instance Requests".

## Step-by-Step Setup

### 1. Build and test the image locally

```bash
docker build -t sigtekx:local .
docker run --gpus all sigtekx:local python -c "import sigtekx; print(sigtekx.__version__)"
docker run --gpus all sigtekx:local python benchmarks/run_latency.py \
    experiment=ionosphere_test +benchmark=latency
```

`--gpus all` is required for GPU access. Docker Desktop's "Run" button does not
pass this flag — always use the CLI for GPU workloads.

### 2. Create AWS resources (IAM, S3, instance profile)

```bash
bash scripts/aws/setup_iam.sh
```

This creates:

- S3 bucket `sigtekx-benchmark-results`
- IAM role `SigTekXEC2BenchmarkRole` (trust policy: `ec2.amazonaws.com`)
- Inline policy scoped to the bucket above and the `/sigtekx/benchmarks` log group
- Instance profile `SigTekXEC2BenchmarkRole` for attaching the role to EC2

### 3. Push the image to ECR

```bash
bash scripts/aws/push_ecr.sh
```

Authenticates Docker to ECR, creates the `sigtekx` repository if missing, builds
the image, and pushes both `latest` and the current git commit SHA.

### 4. Launch a g4dn.xlarge spot instance (AWS console)

1. EC2 → **Launch instances**
2. **AMI**: *Deep Learning AMI GPU PyTorch* (Ubuntu) — ships with Docker and the
   NVIDIA Container Toolkit pre-installed
3. **Instance type**: `g4dn.xlarge`
4. **Key pair**: choose your existing `sigtekx` key
5. **Network**: allow inbound SSH (port 22) from your IP
6. **Advanced details**:
   - **IAM instance profile**: `SigTekXEC2BenchmarkRole`
   - **Purchasing option**: check **Request Spot Instances**
   - **Request type**: one-time
7. Launch, then copy the instance's **public IPv4 address** and **instance ID**

### 5. Run the benchmark

```bash
bash scripts/aws/run_ec2_benchmark.sh <instance-public-ip> <instance-id>
```

The script:

1. Ensures CloudWatch log group `/sigtekx/benchmarks` exists
2. SSHes into the instance (user `ubuntu`, key `~/.ssh/sigtekx.pem` by default —
   override with `SIGX_SSH_USER` / `SIGX_SSH_KEY`)
3. Logs Docker into ECR and pulls `sigtekx:latest`
4. Runs the container with `--gpus all`, the `awslogs` log driver pointed at
   `/sigtekx/benchmarks`, and a mounted `/opt/sigtekx/results` volume
5. Uploads result CSVs to `s3://sigtekx-benchmark-results/runs/<timestamp>/`
6. Prints the `aws ec2 terminate-instances` command for the instance

### 6. Verify results

Cloud runs land in their own dataset directory, keeping your local RTX data
untouched. Use `download_results.sh` to pull them in:

```bash
# List cloud runs available in S3
bash scripts/aws/download_results.sh --list

# Pull the latest run into datasets/aws-<timestamp>/
bash scripts/aws/download_results.sh

# Or pull a specific run
bash scripts/aws/download_results.sh 20260415T120000Z

```

```bash
# CloudWatch logs
aws logs tail /sigtekx/benchmarks --follow --region us-west-2

# View locally — pick "aws-<timestamp>" from the sidebar dataset picker
sigx dashboard
```

## Cost Estimate

Approximate `us-west-2` (Oregon) prices for one ~30 minute benchmark run:

| Component | Rate | Cost / run |
|-----------|------|-----------|
| EC2 `g4dn.xlarge` spot | ~$0.16/hr | ~$0.08 |
| S3 storage (1 GB, 1 month) | $0.023/GB-mo | ~$0.02 |
| S3 PUT/GET requests | negligible | <$0.01 |
| CloudWatch Logs ingest (≤100 MB) | $0.50/GB | <$0.05 |
| CloudWatch Logs storage (1 month) | $0.03/GB-mo | <$0.01 |
| **Total per run** | | **~$0.12–$0.20** |

ECR storage is free for the first 500 MB private. (Current docker image builds to ~9.5 GB)

Spot instances can be reclaimed with 2 minutes notice — **always terminate
immediately after the run**, even if the script exits cleanly, so billing stops.

## Teardown

Terminate the EC2 instance first (it is not touched by `teardown.sh`):

```bash
aws ec2 terminate-instances --instance-ids <instance-id>
```

Then delete the remaining resources:

```bash
bash scripts/aws/teardown.sh            # prompts for confirmation
bash scripts/aws/teardown.sh --force    # no prompt
```

This removes the S3 bucket (including all objects), the IAM role and instance
profile, and the `/sigtekx/benchmarks` CloudWatch log group. The ECR repository
is intentionally left in place so cached image layers survive between runs —
delete it manually if you're fully done:

```bash
aws ecr delete-repository --repository-name sigtekx --force
```

## Architecture

See `docs/_personal/aws-cloud-architecture.md` for detailed architecture diagrams
and decision rationale.

## Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build (builder + production) |
| `scripts/aws/setup_iam.sh` | Creates S3 bucket, EC2 IAM role, instance profile |
| `scripts/aws/push_ecr.sh` | Builds and pushes the image to ECR (`latest` + git SHA) |
| `scripts/aws/run_ec2_benchmark.sh` | Runs the benchmark on an EC2 instance over SSH |
| `scripts/aws/download_results.sh` | Syncs S3 results to local `artifacts/` |
| `scripts/aws/teardown.sh` | Deletes S3 bucket, IAM role, CloudWatch log group |
