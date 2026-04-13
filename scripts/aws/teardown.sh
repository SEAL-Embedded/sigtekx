#!/usr/bin/env bash
# teardown.sh — Delete all AWS resources created by setup_iam.sh.
#
# Removes: S3 bucket, IAM role + instance profile, CloudWatch log group.
# Safe to run multiple times (skips resources that don't exist).
#
# Does NOT terminate EC2 instances — terminate those yourself first with:
#   aws ec2 terminate-instances --instance-ids <id>
#
# Usage:
#   bash scripts/aws/teardown.sh           # prompts for confirmation
#   bash scripts/aws/teardown.sh --force   # skips confirmation

set -euo pipefail

ROLE_NAME="${SIGX_ROLE:-SigTekXEC2BenchmarkRole}"
INSTANCE_PROFILE_NAME="${SIGX_INSTANCE_PROFILE:-SigTekXEC2BenchmarkRole}"
BUCKET_NAME="${SIGX_BUCKET:-sigtekx-benchmark-results}"
LOG_GROUP="${SIGX_LOG_GROUP:-/sigtekx/benchmarks}"
REGION="${AWS_DEFAULT_REGION:-us-west-2}"
FORCE=false

if [ "${1:-}" = "--force" ]; then
    FORCE=true
fi

echo "=== SigTekX AWS Teardown ==="
echo "Region:    $REGION"
echo "Role:      $ROLE_NAME"
echo "Bucket:    $BUCKET_NAME"
echo "Log Group: $LOG_GROUP"
echo ""

if [ "$FORCE" = false ]; then
    read -r -p "This will permanently delete all resources listed above. Continue? [y/N] " confirm
    case "$confirm" in
        [yY][eE][sS]|[yY]) ;;
        *) echo "Aborted."; exit 0 ;;
    esac
    echo ""
fi

# --- 1. Delete S3 bucket and all contents ---
echo "[1/4] Deleting S3 bucket: s3://$BUCKET_NAME"
if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
    aws s3 rb "s3://$BUCKET_NAME" --force
    echo "  Deleted."
else
    echo "  Bucket does not exist, skipping."
fi

# --- 2. Remove IAM role + instance profile ---
echo "[2/4] Removing IAM role: $ROLE_NAME"
if aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME" 2>/dev/null | grep -q "InstanceProfileId"; then
    PROFILE_ROLES=$(aws iam get-instance-profile \
        --instance-profile-name "$INSTANCE_PROFILE_NAME" \
        --query "InstanceProfile.Roles[].RoleName" --output text 2>/dev/null || true)
    for r in $PROFILE_ROLES; do
        aws iam remove-role-from-instance-profile \
            --instance-profile-name "$INSTANCE_PROFILE_NAME" \
            --role-name "$r"
        echo "  Removed role $r from instance profile."
    done
    aws iam delete-instance-profile --instance-profile-name "$INSTANCE_PROFILE_NAME"
    echo "  Instance profile deleted."
else
    echo "  Instance profile does not exist, skipping."
fi

if aws iam get-role --role-name "$ROLE_NAME" 2>/dev/null | grep -q "RoleId"; then
    # Detach all managed policies
    ATTACHED=$(aws iam list-attached-role-policies \
        --role-name "$ROLE_NAME" \
        --query "AttachedPolicies[].PolicyArn" \
        --output text 2>/dev/null || true)
    for policy_arn in $ATTACHED; do
        aws iam detach-role-policy --role-name "$ROLE_NAME" --policy-arn "$policy_arn"
        echo "  Detached: $(basename "$policy_arn")"
    done

    # Delete all inline policies
    INLINE=$(aws iam list-role-policies \
        --role-name "$ROLE_NAME" \
        --query "PolicyNames" \
        --output text 2>/dev/null || true)
    for policy_name in $INLINE; do
        aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name "$policy_name"
        echo "  Deleted inline policy: $policy_name"
    done

    aws iam delete-role --role-name "$ROLE_NAME"
    echo "  Role deleted."
else
    echo "  Role does not exist, skipping."
fi

# --- 3. Delete CloudWatch log group ---
echo "[3/4] Deleting CloudWatch log group: $LOG_GROUP"
if aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --region "$REGION" \
    --query "logGroups[?logGroupName=='$LOG_GROUP']" --output text | grep -q "$LOG_GROUP"; then
    aws logs delete-log-group --log-group-name "$LOG_GROUP" --region "$REGION"
    echo "  Deleted."
else
    echo "  Log group does not exist, skipping."
fi

# --- 4. Summary ---
echo ""
echo "[4/4] Verifying cleanup..."
if aws iam get-role --role-name "$ROLE_NAME" 2>/dev/null >/dev/null; then
    echo "  WARNING: Role still exists."
else
    echo "  Role removed."
fi
if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
    echo "  WARNING: Bucket still exists."
else
    echo "  Bucket removed."
fi

echo ""
echo "=== Teardown Complete ==="
echo "All SigTekX AWS resources have been removed."
echo ""
echo "Reminder: EC2 instances are not touched by this script."
echo "  aws ec2 describe-instances --filters Name=instance-state-name,Values=running"
