#!/usr/bin/env bash
# setup_iam.sh — Create SageMaker IAM role and S3 bucket for SigTekX cloud experiments.
#
# Prerequisites:
#   - AWS CLI v2 configured (aws configure)
#   - IAM permissions to create roles and buckets
#
# Usage:
#   bash scripts/aws/setup_iam.sh

set -euo pipefail

ROLE_NAME="SageMakerSigTekX"
BUCKET_NAME="sigtekx-benchmark-results"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

echo "=== SigTekX AWS Setup ==="
echo "Region: $REGION"
echo "Role:   $ROLE_NAME"
echo "Bucket: $BUCKET_NAME"
echo ""

# --- 1. Create S3 bucket ---
echo "[1/3] Creating S3 bucket: $BUCKET_NAME"
if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
    echo "  Bucket already exists, skipping."
else
    if [ "$REGION" = "us-east-1" ]; then
        aws s3api create-bucket --bucket "$BUCKET_NAME" --region "$REGION"
    else
        aws s3api create-bucket --bucket "$BUCKET_NAME" --region "$REGION" \
            --create-bucket-configuration LocationConstraint="$REGION"
    fi
    echo "  Created."
fi

# --- 2. Create IAM role for SageMaker ---
echo "[2/3] Creating IAM role: $ROLE_NAME"

TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "sagemaker.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}'

if aws iam get-role --role-name "$ROLE_NAME" 2>/dev/null; then
    echo "  Role already exists, skipping creation."
else
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document "$TRUST_POLICY" \
        --description "SageMaker execution role for SigTekX benchmark experiments"
    echo "  Created."
fi

# --- 3. Attach required policies ---
echo "[3/3] Attaching policies"

POLICIES=(
    "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"
    "arn:aws:iam::aws:policy/AmazonS3FullAccess"
)

for policy_arn in "${POLICIES[@]}"; do
    policy_name=$(basename "$policy_arn")
    if aws iam list-attached-role-policies --role-name "$ROLE_NAME" \
        --query "AttachedPolicies[?PolicyArn=='$policy_arn']" --output text | grep -q "$policy_name"; then
        echo "  $policy_name already attached."
    else
        aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn "$policy_arn"
        echo "  Attached $policy_name."
    fi
done

# --- Print summary ---
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query "Role.Arn" --output text)
ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)

echo ""
echo "=== Setup Complete ==="
echo "Role ARN:    $ROLE_ARN"
echo "S3 Bucket:   s3://$BUCKET_NAME"
echo "Account ID:  $ACCOUNT_ID"
echo ""
echo "Next steps:"
echo "  1. Push Docker image:  docker push kevinrhz/sigtekx:latest"
echo "  2. Run SageMaker job:  python scripts/aws/run_sagemaker_job.py"
