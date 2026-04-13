#!/usr/bin/env bash
# push_ecr.sh — Build the SigTekX Docker image and push it to Amazon ECR.
#
# Authenticates Docker to ECR, ensures the repository exists, builds the image,
# and pushes two tags: `latest` and the current git commit SHA.
#
# Prerequisites:
#   - AWS CLI v2 configured (aws configure)
#   - Docker running locally
#   - IAM permissions for ecr:*
#
# Usage:
#   bash scripts/aws/push_ecr.sh

set -euo pipefail

REPO_NAME="sigtekx"
REGION="${AWS_DEFAULT_REGION:-us-west-2}"
DOCKERFILE_CONTEXT="${SIGX_DOCKER_CONTEXT:-.}"

GIT_SHA=$(git rev-parse --short HEAD)
ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE_URI="${REGISTRY}/${REPO_NAME}"

echo "=== SigTekX ECR Push ==="
echo "Region:   $REGION"
echo "Registry: $REGISTRY"
echo "Repo:     $REPO_NAME"
echo "Git SHA:  $GIT_SHA"
echo ""

# --- 1. Authenticate Docker to ECR ---
echo "[1/4] Authenticating Docker to ECR"
aws ecr get-login-password --region "$REGION" \
    | docker login --username AWS --password-stdin "$REGISTRY"
echo "  Logged in to $REGISTRY."

# --- 2. Ensure repository exists ---
echo "[2/4] Ensuring ECR repository exists: $REPO_NAME"
if aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "  Repository already exists, skipping."
else
    aws ecr create-repository \
        --repository-name "$REPO_NAME" \
        --region "$REGION" \
        --image-scanning-configuration scanOnPush=true >/dev/null
    echo "  Created."
fi

# --- 3. Build image ---
echo "[3/4] Building Docker image: ${IMAGE_URI}:${GIT_SHA}"
docker build \
    -t "${IMAGE_URI}:latest" \
    -t "${IMAGE_URI}:${GIT_SHA}" \
    "$DOCKERFILE_CONTEXT"
echo "  Built and tagged :latest and :${GIT_SHA}."

# --- 4. Push both tags ---
echo "[4/4] Pushing tags to ECR"
docker push "${IMAGE_URI}:latest"
docker push "${IMAGE_URI}:${GIT_SHA}"
echo "  Pushed :latest and :${GIT_SHA}."

echo ""
echo "=== Push Complete ==="
echo "Image URI (latest): ${IMAGE_URI}:latest"
echo "Image URI (sha):    ${IMAGE_URI}:${GIT_SHA}"
echo ""
echo "Next step:"
echo "  bash scripts/aws/run_ec2_benchmark.sh <instance-ip>"
