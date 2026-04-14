# AWS Cloud Architecture — SigTekX

Architecture reference for the SigTekX AWS cloud deployment.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ Local Development (WSL2)                                            │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│  │ SigTekX      │    │ Docker Build     │    │ Streamlit        │  │
│  │ Source Code  │───>│ (push_ecr.sh)    │    │ Dashboard        │  │
│  └──────────────┘    └────────┬─────────┘    └────────▲─────────┘  │
│                               │                       │             │
│                               │ docker push           │ s3 cp       │
│                               ▼                       │             │
│  ┌────────────────────────────┴──────────────────────┴───────────┐  │
│  │  artifacts/ (local)                                           │  │
│  │  └── data/*.csv   ← cloud results (downloaded via s3 cp)     │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               │ docker push (latest + git SHA)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Amazon ECR  (us-west-2)                                             │
│                                                                     │
│  <account>.dkr.ecr.us-west-2.amazonaws.com/sigtekx:latest          │
│  <account>.dkr.ecr.us-west-2.amazonaws.com/sigtekx:<git-sha>       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               │ docker pull (over SSH, on instance)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ AWS Cloud  (us-west-2)                                              │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ EC2 Spot Instance — g4dn.xlarge (T4 GPU, 16 GB)              │  │
│  │   AMI:  Deep Learning AMI GPU PyTorch (Ubuntu)               │  │
│  │   IAM:  instance profile SigTekXEC2BenchmarkRole             │  │
│  │                                                               │  │
│  │   docker run --gpus all                                       │  │
│  │     --log-driver awslogs                                      │  │
│  │     --log-opt awslogs-group=/sigtekx/benchmarks              │  │
│  │     -v /opt/sigtekx/results:/workspace/artifacts/data        │  │
│  │     sigtekx:latest                                           │  │
│  │                                                               │  │
│  │   Container user: appuser (non-root)                         │  │
│  │   Entrypoint: conda run -n sigtekx                           │  │
│  └───────────────┬──────────────────────────────────────────────┘  │
│                  │                                                   │
│          ┌───────┴────────┐                                         │
│          │                │                                         │
│          ▼                ▼                                         │
│  ┌───────────────┐  ┌─────────────────────────────────────────┐    │
│  │ S3            │  │ CloudWatch Logs                         │    │
│  │               │  │   /sigtekx/benchmarks                   │    │
│  │ sigtekx-      │  │   stream: ec2-<timestamp>               │    │
│  │ benchmark-    │  │                                         │    │
│  │ results/      │  │ Container stdout/stderr streamed via    │    │
│  │ runs/<ts>/    │  │ awslogs Docker log driver               │    │
│  │ *.csv         │  └─────────────────────────────────────────┘    │
│  └───────────────┘                                                  │
│                                                                     │
│  IAM Role: SigTekXEC2BenchmarkRole                                  │
│    Trust:  ec2.amazonaws.com                                        │
│    Policy: SigTekXBenchmarkAccess (inline, scoped)                  │
│      - s3:PutObject / GetObject / ListBucket → sigtekx-benchmark-* │
│      - logs:PutLogEvents / CreateLogStream  → /sigtekx/benchmarks  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Decision Rationale

### Why EC2 Spot (not SageMaker Processing Jobs)?

| Criteria | EC2 Spot | SageMaker Processing |
|----------|----------|----------------------|
| Abstractions needed | SSH + Docker | SageMaker SDK, job lifecycle, IAM |
| Output routing | Mount a volume, `aws s3 cp` | `/opt/ml/processing/output/` convention |
| Logging | `awslogs` Docker driver | CloudWatch via SageMaker agent |
| Spot support | Native | Managed interruption handling |
| Requires ML expertise | No | Yes (to use well) |
| Hourly cost (T4) | ~$0.16 spot | ~$0.53 on-demand |

SageMaker adds ML-specific abstractions (job queues, managed endpoints, model
artifacts, training channels) that are overhead for a benchmark workload. EC2
spot is lower cost, simpler to reason about, and requires no ML knowledge to
operate correctly.

### Why ECR (not Docker Hub)?

| Criteria | ECR | Docker Hub |
|----------|-----|-----------|
| Region co-location | Same region as EC2 — fast pull, no egress | Cross-region / internet |
| Pull cost | Free within region | Free, but cross-region egress |
| Auth | `aws ecr get-login-password` — uses instance role | Requires Docker Hub credentials |
| Git SHA tags | Easy to push both `latest` and `<sha>` | Possible but unmanaged |
| Pull rate limits | None | 100 pulls/6h unauthenticated |

The instance role already has ECR pull rights implicitly via the AWS-managed
`ecr:GetAuthorizationToken` + `ecr:BatchGetImage` defaults on the registry.
No separate credentials to manage.

### Why g4dn.xlarge?

| Instance | GPU | CUDA Arch | Spot Cost/hr | Notes |
|----------|-----|-----------|-------------|-------|
| **g4dn.xlarge** | **T4 16 GB** | **sm_75** | **~$0.16** | **Selected** |
| g5.xlarge | A10G 24 GB | sm_80 | ~$0.34 | 2× cost, excess VRAM |
| p3.2xlarge | V100 16 GB | sm_70 | ~$0.90 | 6× cost, sm_70 in arch list but old |

T4's sm_75 is already in `CMAKE_CUDA_ARCHITECTURES` (75, 86, 89). Cheapest
GPU option with native arch support and sufficient VRAM for all benchmark configs.

### Why awslogs log driver?

The `awslogs` Docker log driver is built into Docker — no sidecar, no agent,
no extra process to manage on the instance. Container stdout/stderr streams
directly to CloudWatch Logs. Log group and stream names are set at container
launch time in `run_ec2_benchmark.sh`, not baked into the image.

---

## Cost Model

### Per-run costs (us-west-2, ~30 min benchmark)

| Component | Rate | Cost |
|-----------|------|------|
| EC2 g4dn.xlarge spot | ~$0.16/hr | ~$0.08 |
| S3 storage (1 GB, 1 month) | $0.023/GB-mo | ~$0.02 |
| S3 requests | negligible | <$0.01 |
| CloudWatch Logs ingest (≤100 MB) | $0.50/GB | <$0.05 |
| **Total per run** | | **~$0.12–$0.20** |

ECR storage is free for the first 500 MB.

### Cost risks

| Risk | Cost | Mitigation |
|------|------|-----------|
| Forgot to terminate instance | ~$0.16/hr spot | `run_ec2_benchmark.sh` prints terminate command |
| Left S3 bucket with data | $0.02+/month | `teardown.sh --force` deletes bucket + contents |
| CloudWatch log retention | $0.03/GB-mo | Delete log group via `teardown.sh` |

---

## Integration with Existing Infrastructure

### Hydra Config System
- Experiment configs (`experiments/conf/`) are copied into the Docker image at build time
- The same `run_latency.py` / `run_throughput.py` commands used locally work
  identically inside the container
- Container's working directory is `/workspace`; results volume is mounted at
  `/workspace/artifacts/data` so Hydra writes CSVs to the right place

### Streamlit Dashboard
- `download_results.sh` syncs `s3://sigtekx-benchmark-results/runs/` to local
  `artifacts/data/`
- Dashboard's `load_data()` auto-merges all CSVs — cloud results appear
  alongside local results with no changes needed

### MLflow Tracking
- MLflow writes to a local SQLite file inside the container (ephemeral —
  discarded when the container exits)
- Persistent results flow through the CSV → S3 → local → Streamlit path

---

## Security

- IAM inline policy scoped to one S3 bucket and one CloudWatch log group —
  no wildcard resource ARNs
- EC2 trust policy only (`ec2.amazonaws.com`) — role cannot be assumed by
  any other service
- `appuser` non-root user runs inside the container
- No credentials in code, environment variables, or Docker image — all auth
  flows through the instance role
- S3 bucket and CloudWatch log group deleted on teardown
