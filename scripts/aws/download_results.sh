#!/usr/bin/env bash
# download_results.sh — Sync SageMaker job results from S3 to local artifacts/.
#
# Usage:
#   bash scripts/aws/download_results.sh                    # Sync latest job
#   bash scripts/aws/download_results.sh 20260319-120000    # Sync specific job

set -euo pipefail

BUCKET_NAME="sigtekx-benchmark-results"
LOCAL_DIR="artifacts"

if [ $# -ge 1 ]; then
    TIMESTAMP="$1"
else
    # Find the latest job timestamp
    echo "Finding latest job..."
    TIMESTAMP=$(aws s3 ls "s3://$BUCKET_NAME/jobs/" | sort | tail -1 | awk '{print $2}' | tr -d '/')
    if [ -z "$TIMESTAMP" ]; then
        echo "ERROR: No jobs found in s3://$BUCKET_NAME/jobs/"
        exit 1
    fi
fi

S3_PATH="s3://$BUCKET_NAME/jobs/$TIMESTAMP/"
LOCAL_PATH="$LOCAL_DIR/cloud/$TIMESTAMP"

echo "=== Downloading SageMaker Results ==="
echo "S3 source: $S3_PATH"
echo "Local dest: $LOCAL_PATH"
echo ""

mkdir -p "$LOCAL_PATH"
aws s3 sync "$S3_PATH" "$LOCAL_PATH/"

echo ""
echo "=== Download Complete ==="
echo "Files:"
find "$LOCAL_PATH" -type f | sort | head -20

# Also copy CSVs to the main data directory so the dashboard picks them up
DATA_DIR="$LOCAL_DIR/data"
mkdir -p "$DATA_DIR"
CSV_COUNT=0
for csv in "$LOCAL_PATH"/data/*.csv; do
    [ -f "$csv" ] || continue
    cp "$csv" "$DATA_DIR/"
    CSV_COUNT=$((CSV_COUNT + 1))
done

if [ "$CSV_COUNT" -gt 0 ]; then
    echo ""
    echo "Copied $CSV_COUNT CSV file(s) to $DATA_DIR/ for dashboard access."
    echo "Run 'sigx dashboard' to view results."
fi
