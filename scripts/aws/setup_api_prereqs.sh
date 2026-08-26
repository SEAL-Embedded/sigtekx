#!/usr/bin/env bash
# setup_api_prereqs.sh — Create the EC2 prerequisites the API's preflight needs.
#
# setup_iam.sh creates the S3 bucket, IAM role and instance profile. It does
# NOT create a key pair or a security group, and RealDriver.preflight() checks
# for both. This fills that gap and prints the exact env vars to export.
#
# Idempotent: skips anything that already exists.
#
# Usage:
#   bash scripts/aws/setup_api_prereqs.sh

set -euo pipefail
export AWS_PAGER=""

REGION="${AWS_DEFAULT_REGION:-us-west-2}"
KEY_NAME="${SIGX_KEY_NAME:-sigtekx}"
KEY_PATH="${SIGX_SSH_KEY:-$HOME/.ssh/sigtekx.pem}"
SG_NAME="${SIGX_SG_NAME:-sigtekx-benchmark-sg}"

echo "=== SigTekX API Prerequisites ==="
echo "Region:   $REGION"
echo "Key pair: $KEY_NAME"
echo "SG:       $SG_NAME"
echo ""

# --- 1. Key pair ---
echo "[1/4] Key pair: $KEY_NAME"
if aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "  Already exists in AWS."
    if [ ! -f "$KEY_PATH" ]; then
        echo "  WARNING: $KEY_PATH is missing locally but the key exists in AWS." >&2
        echo "           You cannot SSH without the private key. Either restore it," >&2
        echo "           or delete the AWS key pair and re-run to generate a new one:" >&2
        echo "             aws ec2 delete-key-pair --key-name $KEY_NAME --region $REGION" >&2
        exit 1
    fi
else
    echo "  Creating and saving to $KEY_PATH"
    mkdir -p "$(dirname "$KEY_PATH")"
    aws ec2 create-key-pair --key-name "$KEY_NAME" --region "$REGION" \
        --query "KeyMaterial" --output text > "$KEY_PATH"
    chmod 400 "$KEY_PATH"
    echo "  Created."
fi

# --- 2. Default VPC ---
echo "[2/4] Locating default VPC"
VPC_ID="$(aws ec2 describe-vpcs --region "$REGION" \
    --filters Name=isDefault,Values=true \
    --query "Vpcs[0].VpcId" --output text)"
if [ "$VPC_ID" = "None" ] || [ -z "$VPC_ID" ]; then
    echo "ERROR: No default VPC in $REGION. Pass SIGX_SUBNET_ID/SIGX_SECURITY_GROUP manually." >&2
    exit 1
fi
echo "  $VPC_ID"

# --- 3. Security group (inbound SSH from this machine only) ---
echo "[3/4] Security group: $SG_NAME"
SG_ID="$(aws ec2 describe-security-groups --region "$REGION" \
    --filters Name=group-name,Values="$SG_NAME" Name=vpc-id,Values="$VPC_ID" \
    --query "SecurityGroups[0].GroupId" --output text 2>/dev/null || echo "None")"

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
    SG_ID="$(aws ec2 create-security-group --region "$REGION" \
        --group-name "$SG_NAME" --vpc-id "$VPC_ID" \
        --description "SigTekX benchmark instances: SSH from the operator only" \
        --query "GroupId" --output text)"
    echo "  Created $SG_ID"
else
    echo "  Already exists: $SG_ID"
fi

# Scope SSH to this machine's public IP rather than 0.0.0.0/0.
MY_IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')"
echo "  Authorising SSH from ${MY_IP}/32"
if aws ec2 authorize-security-group-ingress --region "$REGION" \
        --group-id "$SG_ID" --protocol tcp --port 22 --cidr "${MY_IP}/32" \
        >/dev/null 2>&1; then
    echo "  Rule added."
else
    echo "  Rule already present, skipping."
fi

# --- 4. Latest Deep Learning AMI (ships Docker + NVIDIA toolkit) ---
echo "[4/4] Finding latest Deep Learning AMI in $REGION"
AMI_ID="$(aws ec2 describe-images --region "$REGION" --owners amazon \
    --filters "Name=name,Values=Deep Learning OSS Nvidia Driver AMI GPU PyTorch*Ubuntu*" \
              "Name=state,Values=available" \
    --query "sort_by(Images,&CreationDate)[-1].ImageId" --output text)"
if [ "$AMI_ID" = "None" ] || [ -z "$AMI_ID" ]; then
    echo "  WARNING: no Deep Learning AMI matched; set SIGX_AMI_ID by hand." >&2
    AMI_ID="<set-me>"
else
    AMI_NAME="$(aws ec2 describe-images --region "$REGION" --image-ids "$AMI_ID" \
        --query "Images[0].Name" --output text)"
    echo "  $AMI_ID"
    echo "  $AMI_NAME"
fi

SUBNET_ID="$(aws ec2 describe-subnets --region "$REGION" \
    --filters Name=vpc-id,Values="$VPC_ID" Name=default-for-az,Values=true \
    --query "Subnets[0].SubnetId" --output text)"

cat <<SUMMARY

=== Done. Export these to run the API in real mode ===

export SIGX_API_MODE=real
export SIGX_API_KEY='choose-a-secret'
export AWS_DEFAULT_REGION=$REGION
export SIGX_AMI_ID=$AMI_ID
export SIGX_KEY_NAME=$KEY_NAME
export SIGX_SSH_KEY=$KEY_PATH
export SIGX_SECURITY_GROUP=$SG_ID
export SIGX_SUBNET_ID=$SUBNET_ID

Then:
  uvicorn sigtekx.api.app:app --port 8000

Preflight will verify credentials, AMI, key pair and instance profile at
startup. Start with run_mode=smoke (~10s on the instance) before full.
SUMMARY
