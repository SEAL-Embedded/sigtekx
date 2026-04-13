#!/usr/bin/env python3
"""Launch a SageMaker Processing Job to run SigTekX benchmarks on cloud GPU.

This script submits a Processing Job using the SigTekX Docker image from
Docker Hub. Results are written to S3 and can be synced locally.

Prerequisites:
    1. AWS CLI configured (aws configure)
    2. IAM role created (bash scripts/aws/setup_iam.sh)
    3. Docker image pushed to Docker Hub (kevinrhz/sigtekx:latest)
    4. GPU quota approved (ml.g4dn.xlarge requires G-instance vCPUs)

Usage:
    python scripts/aws/run_sagemaker_job.py
    python scripts/aws/run_sagemaker_job.py --instance ml.g4dn.xlarge --wait
    python scripts/aws/run_sagemaker_job.py --experiments ionosphere_test ionosphere_streaming
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import boto3
from sagemaker.processing import ScriptProcessor


def get_role_arn(role_name: str = "SageMakerSigTekX") -> str:
    """Get the ARN for the SageMaker execution role."""
    iam = boto3.client("iam")
    response = iam.get_role(RoleName=role_name)
    return response["Role"]["Arn"]


def main():
    parser = argparse.ArgumentParser(description="Launch SigTekX SageMaker Processing Job")
    parser.add_argument(
        "--instance",
        default="ml.g4dn.xlarge",
        help="SageMaker instance type (default: ml.g4dn.xlarge, T4 GPU)",
    )
    parser.add_argument(
        "--image",
        default="kevinrhz/sigtekx:latest",
        help="Docker image URI",
    )
    parser.add_argument(
        "--bucket",
        default="sigtekx-benchmark-results",
        help="S3 bucket for results",
    )
    parser.add_argument(
        "--role",
        default="SageMakerSigTekX",
        help="IAM role name",
    )
    parser.add_argument(
        "--experiments",
        nargs="+",
        default=None,
        help="Experiment names (default: demo set)",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for job to complete",
    )
    parser.add_argument(
        "--max-runtime",
        type=int,
        default=3600,
        help="Max runtime in seconds (default: 3600 = 1 hour)",
    )
    args = parser.parse_args()

    # Get role ARN
    role_arn = get_role_arn(args.role)
    print(f"Role ARN: {role_arn}")

    # Create job name with timestamp
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    job_name = f"sigtekx-benchmark-{timestamp}"

    # Build entry point arguments
    entry_args = []
    if args.experiments:
        entry_args.extend(["--experiments"] + args.experiments)

    # S3 output path
    s3_output = f"s3://{args.bucket}/jobs/{timestamp}/"

    print(f"\n=== SageMaker Processing Job ===")
    print(f"Job name:  {job_name}")
    print(f"Instance:  {args.instance}")
    print(f"Image:     {args.image}")
    print(f"S3 output: {s3_output}")
    if args.experiments:
        print(f"Experiments: {args.experiments}")
    print()

    # Create processor
    processor = ScriptProcessor(
        role=role_arn,
        image_uri=args.image,
        instance_count=1,
        instance_type=args.instance,
        command=["python3"],
        max_runtime_in_seconds=args.max_runtime,
    )

    # Submit the job
    from sagemaker.processing import ProcessingOutput

    processor.run(
        code="scripts/aws/sagemaker_entry.py",
        outputs=[
            ProcessingOutput(
                output_name="results",
                source="/opt/ml/processing/output",
                destination=s3_output,
            ),
        ],
        arguments=entry_args,
        wait=False,
        job_name=job_name,
    )

    print(f"Job submitted: {job_name}")
    print(f"\nMonitor in AWS Console:")
    region = boto3.session.Session().region_name or "us-east-1"
    print(f"  https://{region}.console.aws.amazon.com/sagemaker/home?region={region}#/processing-jobs/{job_name}")
    print(f"\nOr via CLI:")
    print(f"  aws sagemaker describe-processing-job --processing-job-name {job_name}")
    print(f"\nDownload results when complete:")
    print(f"  aws s3 sync {s3_output} artifacts/cloud/{timestamp}/")

    if args.wait:
        print("\nWaiting for job to complete...")
        sm = boto3.client("sagemaker")
        while True:
            resp = sm.describe_processing_job(ProcessingJobName=job_name)
            status = resp["ProcessingJobStatus"]
            print(f"  Status: {status}")
            if status in ("Completed", "Failed", "Stopped"):
                break
            time.sleep(30)

        if status == "Completed":
            print(f"\nJob completed successfully!")
            print(f"Sync results: aws s3 sync {s3_output} artifacts/cloud/{timestamp}/")
        else:
            reason = resp.get("FailureReason", "Unknown")
            print(f"\nJob {status}: {reason}")
            print("Check CloudWatch logs for details.")


if __name__ == "__main__":
    main()
