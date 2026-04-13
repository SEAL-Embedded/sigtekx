#!/usr/bin/env bash
# setup_iam.sh — Create S3 bucket and EC2 IAM role for SigTekX cloud benchmarks.
#
# Prerequisites:
#   - AWS CLI v2 configured (aws configure)
#   - IAM permissions to create roles, instance profiles, and buckets
#
# Usage:
#   bash scripts/aws/setup_iam.sh

set -euo pipefail

ROLE_NAME="SigTekXEC2BenchmarkRole"
INSTANCE_PROFILE_NAME="SigTekXEC2BenchmarkRole"
BUCKET_NAME="sigtekx-benchmark-results"
LOG_GROUP="/sigtekx/benchmarks"
REGION="${AWS_DEFAULT_REGION:-us-west-2}"

echo "=== SigTekX AWS Setup ==="
echo "Region:      $REGION"
echo "Role:        $ROLE_NAME"
echo "Bucket:      $BUCKET_NAME"
echo "Log Group:   $LOG_GROUP"
echo ""

# --- 1. Create S3 bucket ---
echo "[1/4] Creating S3 bucket: $BUCKET_NAME"
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

# --- 2. Create IAM role for EC2 ---
echo "[2/4] Creating IAM role: $ROLE_NAME"

TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
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
        --description "EC2 instance role for SigTekX benchmark runs (S3 + CloudWatch Logs)"
    echo "  Created."
fi

# --- 3. Attach scoped inline policy (S3 bucket + CloudWatch Logs) ---
echo "[3/4] Attaching scoped inline policy"

POLICY_NAME="SigTekXBenchmarkAccess"
EXISTING=$(aws iam list-role-policies --role-name "$ROLE_NAME" \
    --query "PolicyNames" --output text 2>/dev/null || true)
if echo "$EXISTING" | grep -q "$POLICY_NAME"; then
    echo "  $POLICY_NAME inline policy already exists, refreshing."
fi

INLINE_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3BenchmarkBucketAccess",
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
    },
    {
      "Sid": "CloudWatchLogsWrite",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": "arn:aws:logs:${REGION}:*:log-group:${LOG_GROUP}:*"
    }
  ]
}
EOF
)

aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "$POLICY_NAME" \
    --policy-document "$INLINE_POLICY"
echo "  Wrote inline policy $POLICY_NAME (S3: $BUCKET_NAME, Logs: $LOG_GROUP)."

# --- 4. Create instance profile and attach role ---
echo "[4/4] Creating instance profile: $INSTANCE_PROFILE_NAME"
if aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" 2>/dev/null; then
    echo "  Instance profile already exists, skipping creation."
else
    aws iam create-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME"
    echo "  Created."
fi

ATTACHED_ROLES=$(aws iam get-instance-profile \
    --instance-profile-name "$INSTANCE_PROFILE_NAME" \
    --query "InstanceProfile.Roles[].RoleName" --output text 2>/dev/null || true)
if echo "$ATTACHED_ROLES" | grep -qw "$ROLE_NAME"; then
    echo "  Role already attached to instance profile."
else
    aws iam add-role-to-instance-profile \
        --instance-profile-name "$INSTANCE_PROFILE_NAME" \
        --role-name "$ROLE_NAME"
    echo "  Attached role to instance profile."
fi

# --- Print summary ---
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query "Role.Arn" --output text)
ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)

echo ""
echo "=== Setup Complete ==="
echo "Role ARN:         $ROLE_ARN"
echo "Instance Profile: $INSTANCE_PROFILE_NAME"
echo "S3 Bucket:        s3://$BUCKET_NAME"
echo "Log Group:        $LOG_GROUP"
echo "Account ID:       $ACCOUNT_ID"
echo ""
echo "Next steps:"
echo "  1. Push image to ECR:   bash scripts/aws/push_ecr.sh"
echo "  2. Launch g4dn.xlarge spot instance (attach instance profile: $INSTANCE_PROFILE_NAME)"
echo "  3. Run benchmark:       bash scripts/aws/run_ec2_benchmark.sh <instance-ip>"
