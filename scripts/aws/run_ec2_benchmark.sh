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
#   bash scripts/aws/run_ec2_benchmark.sh <instance-public-ip> [instance-id]

set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <instance-public-ip> [instance-id]" >&2
    exit 1
fi

INSTANCE_IP="$1"
INSTANCE_ID="${2:-<your-instance-id>}"

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

echo "=== SigTekX EC2 Benchmark ==="
echo "Instance IP:  $INSTANCE_IP"
echo "Image:        $IMAGE_URI"
echo "Bucket:       s3://$BUCKET_NAME"
echo "Log Group:    $LOG_GROUP"
echo "Log Stream:   $LOG_STREAM"
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

REMOTE_SCRIPT=$(cat <<REMOTE
set -euo pipefail

REGION="$REGION"
REGISTRY="$REGISTRY"
IMAGE_URI="$IMAGE_URI"
BUCKET_NAME="$BUCKET_NAME"
LOG_GROUP="$LOG_GROUP"
LOG_STREAM="$LOG_STREAM"
RUN_ID="$RUN_ID"

echo "  [remote] Authenticating Docker to ECR..."
aws ecr get-login-password --region "\$REGION" \
    | sudo docker login --username AWS --password-stdin "\$REGISTRY"

echo "  [remote] Pulling image: \$IMAGE_URI"
sudo docker pull "\$IMAGE_URI"

echo "  [remote] Preparing results volume..."
sudo mkdir -p /opt/sigtekx/results
sudo chmod 777 /opt/sigtekx/results

echo "  [remote] Running benchmark container (awslogs -> \$LOG_GROUP)..."
sudo docker run --rm --gpus all \
    --log-driver=awslogs \
    --log-opt awslogs-region="\$REGION" \
    --log-opt awslogs-group="\$LOG_GROUP" \
    --log-opt awslogs-stream="\$LOG_STREAM" \
    --log-opt awslogs-create-group=true \
    -v /opt/sigtekx/results:/workspace/artifacts/data \
    "\$IMAGE_URI" \
    python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency

echo "  [remote] Uploading results to s3://\$BUCKET_NAME/runs/\$RUN_ID/"
aws s3 cp /opt/sigtekx/results "s3://\$BUCKET_NAME/runs/\$RUN_ID/" \
    --recursive --exclude "*" --include "*.csv"

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
