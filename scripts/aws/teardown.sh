#!/usr/bin/env bash
# teardown.sh — Delete all AWS resources created by setup_iam.sh.
#
# Removes: SageMaker endpoints, S3 bucket, IAM role and policies.
# Safe to run multiple times (skips resources that don't exist).
#
# Usage:
#   bash scripts/aws/teardown.sh           # prompts for confirmation
#   bash scripts/aws/teardown.sh --force   # skips confirmation

set -euo pipefail

ROLE_NAME="${SIGX_ROLE:-SageMakerSigTekX}"
BUCKET_NAME="${SIGX_BUCKET:-sigtekx-benchmark-results}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
FORCE=false

if [ "${1:-}" = "--force" ]; then
    FORCE=true
fi

echo "=== SigTekX AWS Teardown ==="
echo "Region: $REGION"
echo "Role:   $ROLE_NAME"
echo "Bucket: $BUCKET_NAME"
echo ""

if [ "$FORCE" = false ]; then
    read -r -p "This will permanently delete all resources listed above. Continue? [y/N] " confirm
    case "$confirm" in
        [yY][eE][sS]|[yY]) ;;
        *) echo "Aborted."; exit 0 ;;
    esac
    echo ""
fi

# --- 1. Delete any active SageMaker endpoints (most expensive if orphaned) ---
echo "[1/4] Checking for active SageMaker endpoints..."
ENDPOINTS=$(aws sagemaker list-endpoints \
    --region "$REGION" \
    --query "Endpoints[].EndpointName" \
    --output text 2>/dev/null || true)

if [ -z "$ENDPOINTS" ] || [ "$ENDPOINTS" = "None" ]; then
    echo "  No active endpoints found."
else
    for ep in $ENDPOINTS; do
        echo "  Deleting endpoint: $ep"
        aws sagemaker delete-endpoint --endpoint-name "$ep" --region "$REGION"
    done
    echo "  Done. (Endpoints may take a minute to fully terminate.)"
fi

# --- 2. Delete S3 bucket and all contents ---
echo "[2/4] Deleting S3 bucket: s3://$BUCKET_NAME"
if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
    aws s3 rb "s3://$BUCKET_NAME" --force
    echo "  Deleted."
else
    echo "  Bucket does not exist, skipping."
fi

# --- 3. Detach managed policies from IAM role ---
echo "[3/4] Removing IAM role: $ROLE_NAME"
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

# --- 4. Summary ---
echo ""
echo "[4/4] Verifying cleanup..."
REMAINING_ENDPOINTS=$(aws sagemaker list-endpoints \
    --region "$REGION" \
    --query "length(Endpoints)" \
    --output text 2>/dev/null || echo "?")
echo "  Active endpoints remaining: $REMAINING_ENDPOINTS"

echo ""
echo "=== Teardown Complete ==="
echo "All SigTekX AWS resources have been removed."
