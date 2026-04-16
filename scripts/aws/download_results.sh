#!/usr/bin/env bash
# download_results.sh — Pull an EC2 benchmark run from S3 into datasets/.
#
# Lands cloud runs into datasets/aws-<timestamp>/ and writes a manifest so the
# Streamlit dashboard picks them up automatically. Never touches artifacts/data/
# (which stays the ephemeral local scratchpad).
#
# Usage:
#   bash scripts/aws/download_results.sh                        # latest run
#   bash scripts/aws/download_results.sh 20260415T120000Z       # specific run
#   bash scripts/aws/download_results.sh --list                 # list available runs

set -euo pipefail

BUCKET_NAME="${SIGX_BUCKET:-sigtekx-benchmark-results}"
REGION="${AWS_DEFAULT_REGION:-us-west-2}"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
DATASETS_ROOT="${REPO_ROOT}/datasets"

if [ "${1:-}" = "--list" ] || [ "${1:-}" = "-l" ]; then
    echo "Available EC2 runs in s3://${BUCKET_NAME}/runs/:"
    aws s3 ls "s3://${BUCKET_NAME}/runs/" --region "$REGION" \
        | awk '/PRE / {print "  " $2}' | sed 's|/||'
    exit 0
fi

if [ $# -ge 1 ]; then
    RUN_ID="$1"
else
    echo "Finding latest run in s3://${BUCKET_NAME}/runs/..."
    RUN_ID="$(aws s3 ls "s3://${BUCKET_NAME}/runs/" --region "$REGION" \
              | awk '/PRE / {print $2}' | sed 's|/||' | sort | tail -1)"
    if [ -z "$RUN_ID" ]; then
        echo "ERROR: No runs found in s3://${BUCKET_NAME}/runs/" >&2
        echo "       Did you run scripts/aws/run_ec2_benchmark.sh already?" >&2
        exit 1
    fi
fi

DATASET_NAME="aws-${RUN_ID}"
DATASET_DIR="${DATASETS_ROOT}/${DATASET_NAME}"
S3_PATH="s3://${BUCKET_NAME}/runs/${RUN_ID}/"

if [ -d "$DATASET_DIR" ]; then
    echo "ERROR: Dataset already exists at ${DATASET_DIR}" >&2
    echo "       Delete it first or pick a different run." >&2
    echo "       sigx dataset delete ${DATASET_NAME}" >&2
    exit 1
fi

echo "=== Downloading EC2 Run ==="
echo "S3 source:  $S3_PATH"
echo "Dataset:    $DATASET_DIR"
echo ""

mkdir -p "$DATASET_DIR"
aws s3 sync "$S3_PATH" "$DATASET_DIR/" --region "$REGION"

# Write a manifest so the Streamlit registry picks it up.
CREATED_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CSV_COUNT=0
if [ -d "${DATASET_DIR}/data" ]; then
    CSV_COUNT="$(find "${DATASET_DIR}/data" -name "*.csv" 2>/dev/null | wc -l)"
fi
SIZE_MB="$(du -sm "$DATASET_DIR" 2>/dev/null | awk '{print $1}')"

cat > "${DATASET_DIR}/manifest.json" <<MANIFEST
{
  "name": "${DATASET_NAME}",
  "source": "aws-ec2",
  "tag": null,
  "scope": "standard",
  "message": "Downloaded from s3://${BUCKET_NAME}/runs/${RUN_ID}/",
  "created": "${CREATED_ISO}",
  "run_id": "${RUN_ID}",
  "s3_uri": "${S3_PATH}",
  "region": "${REGION}",
  "csv_count": ${CSV_COUNT},
  "size_mb": ${SIZE_MB:-0}
}
MANIFEST

echo ""
echo "=== Download Complete ==="
echo "Dataset:    ${DATASET_NAME}"
echo "Location:   ${DATASET_DIR}"
echo "CSV files:  ${CSV_COUNT}"
echo "Size:       ${SIZE_MB:-?} MB"
echo ""
echo "View in the dashboard:"
echo "  sigx dashboard"
echo "  (select dataset '${DATASET_NAME}' from the sidebar)"
echo ""
echo "Compare against a local run:"
echo "  sigx dataset compare local-rtx-run1 ${DATASET_NAME}"
