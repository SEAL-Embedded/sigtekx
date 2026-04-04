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

# --- 3. Attach policies ---
echo "[3/3] Attaching policies"

# SageMaker managed policy (execution role needs broad SageMaker permissions to spin up compute)
SM_POLICY="arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"
SM_POLICY_NAME="AmazonSageMakerFullAccess"
if aws iam list-attached-role-policies --role-name "$ROLE_NAME" \
    --query "AttachedPolicies[?PolicyArn=='$SM_POLICY']" --output text | grep -q "$SM_POLICY_NAME"; then
    echo "  $SM_POLICY_NAME already attached."
else
    aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn "$SM_POLICY"
    echo "  Attached $SM_POLICY_NAME."
fi

# Scoped inline S3 policy — only the benchmark bucket (not account-wide S3FullAccess)
S3_POLICY_NAME="SigTekXS3BucketAccess"
EXISTING=$(aws iam list-role-policies --role-name "$ROLE_NAME" \
    --query "PolicyNames" --output text 2>/dev/null || true)
if echo "$EXISTING" | grep -q "$S3_POLICY_NAME"; then
    echo "  $S3_POLICY_NAME inline policy already exists."
else
    S3_INLINE_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::${BUCKET_NAME}",
        "arn:aws:s3:::${BUCKET_NAME}/*"
      ]
    }
  ]
}
EOF
)
    aws iam put-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-name "$S3_POLICY_NAME" \
        --policy-document "$S3_INLINE_POLICY"
    echo "  Created inline policy $S3_POLICY_NAME (scoped to s3://$BUCKET_NAME)."
fi

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
