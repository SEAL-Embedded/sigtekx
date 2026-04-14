#!/usr/bin/env bash
# run_ec2_benchmark.sh — SSH into an EC2 GPU instance, pull the SigTekX image
# from ECR, run a benchmark inside the container with CloudWatch logging, and
# upload results to S3.
#
# Prerequisites:
#   - Instance launched with instance profile SigTekXEC2BenchmarkRole
#   - Docker + NVIDIA Container Toolkit installed on the instance
#     (use a Deep Learning AMI — it ships with both)
#   - SSH key available as $SIGX_SSH_KEY (default: ~/.ssh/sigtekx.pem)
#
# Usage:
#   bash scripts/aws/run_ec2_benchmark.sh <instance-public-ip> [instance-id] [--full | --smoke | -- <hydra args>...]
#
# Modes:
#   --smoke                     Run the minimal smoke test inside the container
#                               (experiment=smoke_test, ~10 seconds). Proves the
#                               cloud environment is wired up end-to-end.
#   --full                      Run the entire Snakemake suite inside the container
#                               (all `rule all` targets, ~1 hour on g5/g6).
#   -- <hydra args>...          Run a single benchmark with the given hydra args
#                               (defaults to experiment=ionosphere_test +benchmark=latency).
#
# Examples:
#   # Cloud environment sanity check
#   bash scripts/aws/run_ec2_benchmark.sh 1.2.3.4 i-abc --smoke
#
#   # Full suite — canonical cloud-truth dataset
#   bash scripts/aws/run_ec2_benchmark.sh 1.2.3.4 i-abc --full
#
#   # Single benchmark
#   bash scripts/aws/run_ec2_benchmark.sh 1.2.3.4 i-abc
#   bash scripts/aws/run_ec2_benchmark.sh 1.2.3.4 i-abc -- experiment=baseline_streaming_100k_latency +benchmark=latency
#   SIGX_BENCH_SCRIPT=run_throughput.py bash scripts/aws/run_ec2_benchmark.sh 1.2.3.4 i-abc -- experiment=ionosphere_streaming_throughput +benchmark=throughput

set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <instance-public-ip> [instance-id] [--full | --smoke | -- <hydra args>...]" >&2
    exit 1
fi

INSTANCE_IP="$1"
shift
INSTANCE_ID="<your-instance-id>"
if [ "$#" -gt 0 ] && [ "$1" != "--" ] && [ "$1" != "--full" ] && [ "$1" != "--smoke" ]; then
    INSTANCE_ID="$1"
    shift
fi

RUN_MODE="single"
if [ "$#" -gt 0 ] && [ "$1" = "--full" ]; then
    RUN_MODE="full"
    shift
elif [ "$#" -gt 0 ] && [ "$1" = "--smoke" ]; then
    RUN_MODE="smoke"
    shift
fi
if [ "$#" -gt 0 ] && [ "$1" = "--" ]; then
    shift
fi

BENCH_SCRIPT="${SIGX_BENCH_SCRIPT:-run_latency.py}"
if [ "$#" -gt 0 ]; then
    BENCH_ARGS=("$@")
else
    BENCH_ARGS=(experiment=ionosphere_test +benchmark=latency)
fi

SNAKEMAKE_CORES="${SIGX_SNAKEMAKE_CORES:-4}"

REPO_NAME="sigtekx"
BUCKET_NAME="sigtekx-benchmark-results"
LOG_GROUP="/sigtekx/benchmarks"
REGION="${AWS_DEFAULT_REGION:-us-west-2}"
SSH_USER="${SIGX_SSH_USER:-ubuntu}"
SSH_KEY="${SIGX_SSH_KEY:-$HOME/.ssh/sigtekx.pem}"
IMAGE_TAG="${SIGX_IMAGE_TAG:-latest}"

ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE_URI="${REGISTRY}/${REPO_NAME}:${IMAGE_TAG}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_STREAM="ec2-${RUN_ID}"

printf -v BENCH_ARGS_STR '%q ' "${BENCH_ARGS[@]}"
BENCH_ARGS_STR="${BENCH_ARGS_STR% }"

echo "=== SigTekX EC2 Benchmark ==="
echo "Instance IP:  $INSTANCE_IP"
echo "Image:        $IMAGE_URI"
echo "Bucket:       s3://$BUCKET_NAME"
echo "Log Group:    $LOG_GROUP"
echo "Log Stream:   $LOG_STREAM"
echo "Run mode:     $RUN_MODE"
if [ "$RUN_MODE" = "full" ]; then
    echo "Snakemake:    --cores $SNAKEMAKE_CORES (full suite)"
elif [ "$RUN_MODE" = "smoke" ]; then
    echo "Smoke test:   experiment=smoke_test +benchmark=latency"
else
    echo "Bench script: $BENCH_SCRIPT"
    echo "Bench args:   ${BENCH_ARGS[*]}"
fi
echo ""

# --- 1. Ensure CloudWatch log group exists ---
echo "[1/3] Ensuring CloudWatch log group exists: $LOG_GROUP"
if aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --region "$REGION" \
    --query "logGroups[?logGroupName=='$LOG_GROUP']" --output text | grep -q "$LOG_GROUP"; then
    echo "  Log group already exists, skipping."
else
    aws logs create-log-group --log-group-name "$LOG_GROUP" --region "$REGION"
    echo "  Created."
fi

# --- 2. Run benchmark remotely over SSH ---
echo "[2/3] Running benchmark on $INSTANCE_IP"

if [ "$RUN_MODE" = "full" ]; then
    CONTAINER_CMD="snakemake --cores $SNAKEMAKE_CORES --snakefile experiments/Snakefile"
elif [ "$RUN_MODE" = "smoke" ]; then
    CONTAINER_CMD="python benchmarks/run_latency.py experiment=smoke_test +benchmark=latency"
else
    CONTAINER_CMD="python benchmarks/$BENCH_SCRIPT $BENCH_ARGS_STR"
fi

REMOTE_SCRIPT=$(cat <<REMOTE
set -euo pipefail

REGION="$REGION"
REGISTRY="$REGISTRY"
IMAGE_URI="$IMAGE_URI"
BUCKET_NAME="$BUCKET_NAME"
LOG_GROUP="$LOG_GROUP"
LOG_STREAM="$LOG_STREAM"
RUN_ID="$RUN_ID"
RUN_MODE="$RUN_MODE"

echo "  [remote] Authenticating Docker to ECR..."
aws ecr get-login-password --region "\$REGION" \
    | sudo docker login --username AWS --password-stdin "\$REGISTRY"

echo "  [remote] Pulling image: \$IMAGE_URI"
sudo docker pull "\$IMAGE_URI"

echo "  [remote] Preparing artifacts volume..."
sudo mkdir -p /opt/sigtekx/artifacts
sudo chmod 777 /opt/sigtekx/artifacts

echo "  [remote] Running container (mode=\$RUN_MODE, awslogs -> \$LOG_GROUP)..."
sudo docker run --rm --gpus all \
    --log-driver=awslogs \
    --log-opt awslogs-region="\$REGION" \
    --log-opt awslogs-group="\$LOG_GROUP" \
    --log-opt awslogs-stream="\$LOG_STREAM" \
    --log-opt awslogs-create-group=true \
    -e SIGX_OUTPUT_ROOT=/app/artifacts \
    -v /opt/sigtekx/artifacts:/app/artifacts \
    "\$IMAGE_URI" \
    bash -c "$CONTAINER_CMD"

echo "  [remote] Uploading results to s3://\$BUCKET_NAME/runs/\$RUN_ID/"
aws s3 cp /opt/sigtekx/artifacts/data "s3://\$BUCKET_NAME/runs/\$RUN_ID/data/" \
    --recursive --exclude "*" --include "*.csv" --include "*.json" --include "*.done"
if [ -d /opt/sigtekx/artifacts/figures ]; then
    aws s3 cp /opt/sigtekx/artifacts/figures "s3://\$BUCKET_NAME/runs/\$RUN_ID/figures/" \
        --recursive --exclude "*" --include "*.png" --include "*.json"
fi

echo "  [remote] Done."
REMOTE
)

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "${SSH_USER}@${INSTANCE_IP}" \
    "bash -s" <<<"$REMOTE_SCRIPT"

# --- 3. Summary ---
echo "[3/3] Benchmark complete"
echo ""
echo "=== Run Complete ==="
echo "Results:     s3://$BUCKET_NAME/runs/$RUN_ID/"
echo "Logs:        CloudWatch $LOG_GROUP / $LOG_STREAM"
echo ""
echo "View results:"
echo "  aws s3 ls s3://$BUCKET_NAME/runs/$RUN_ID/"
echo "  aws logs tail $LOG_GROUP --log-stream-names $LOG_STREAM --region $REGION"
echo ""
echo "!! TEARDOWN REMINDER !!"
echo "Spot instances keep billing until terminated. Terminate now with:"
echo "  aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $REGION"
