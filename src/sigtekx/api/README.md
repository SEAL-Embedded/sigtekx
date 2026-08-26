# SigTekX Benchmark API

Self-service operational automation for a manual AWS workflow. Running a cloud
benchmark used to mean launching a GPU instance by hand in the EC2 console, then
running three shell scripts in sequence, then remembering to terminate the
instance. This service does all of it behind one HTTP call — and terminates the
instance in a `finally` block, so a failed run cannot silently keep billing.

Requests are validated by the project's own `EngineConfig`, so a bad `nfft`
is a 422 before any instance is launched. Runs are tracked in SQLite, logs are
structured JSON, and every run is driven asynchronously with a 202 + poll.

```bash
pip install -e ".[api]"
export SIGX_API_KEY=dev-key          # SIGX_API_MODE defaults to "mock" — no AWS, no cost
uvicorn sigtekx.api.app:app --reload # interactive docs at http://127.0.0.1:8000/docs
```

```bash
curl -X POST localhost:8000/benchmarks -H "X-API-Key: dev-key" \
  -H 'Content-Type: application/json' \
  -d '{"engine":{"nfft":4096,"channels":2,"overlap":0.75},"run_mode":"smoke"}'
```

## Endpoints

| Method | Path               | Auth | Notes |
|--------|--------------------|------|-------|
| GET    | `/health`          | no   | Mode, version, count of runs still active |
| POST   | `/benchmarks`      | yes  | **202** — accepted; instance does not exist yet |
| GET    | `/benchmarks`      | yes  | Recent runs, newest first (`?limit=`) |
| GET    | `/benchmarks/{id}` | yes  | **404** if unknown; result location once done |

Status flow: `pending → provisioning → running → downloading → succeeded|failed`.
`provisioning` is separate from `running` because waiting for SSH on a spot
instance is where most failures actually occur.

## Modes

`SIGX_API_MODE=mock` (default) simulates the whole lifecycle with no AWS calls,
so the service is demoable and testable for free. `SIGX_API_MODE=real` launches
a real spot GPU instance and shells out to the existing scripts in
`scripts/aws/`. Mock is the default deliberately: guessing wrong toward mock
costs nothing, guessing wrong toward real spends money.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `SIGX_API_KEY` | — | **Required.** Shared key checked against the `X-API-Key` header |
| `SIGX_API_MODE` | `mock` | `mock` or `real` |
| `SIGX_API_DB` | `artifacts/api/runs.db` | SQLite run-tracking database |
| `SIGX_API_LOG_LEVEL` | `INFO` | Log level for JSON output |
| `SIGX_INSTANCE_TYPE` | `g4dn.xlarge` | Default instance type (per-request overridable) |

Real mode additionally needs `SIGX_AMI_ID` (**required** — AMI IDs are
region-scoped), plus `SIGX_KEY_NAME`, `SIGX_SECURITY_GROUP`, `SIGX_SUBNET_ID`,
`SIGX_INSTANCE_PROFILE`, and `SIGX_USE_SPOT`. These live in the environment
rather than in source because they are account-specific and must not be
committed. See `docs/aws/cloud-deployment.md` for how they map to the manual
console procedure this replaces.

### Running in real mode

```bash
export SIGX_API_MODE=real
export AWS_DEFAULT_REGION=us-west-2
export SIGX_AMI_ID=ami-...          # Deep Learning AMI GPU PyTorch (Ubuntu)
export SIGX_KEY_NAME=sigtekx        # must exist in the account
export SIGX_SECURITY_GROUP=sg-...   # must allow inbound TCP 22
export SIGX_SSH_KEY=~/.ssh/sigtekx.pem
uvicorn sigtekx.api.app:app
```

Startup runs a **preflight**: it verifies credentials, then that the AMI, key
pair and instance profile all actually exist, and refuses to start if any is
missing — reporting every problem at once. All three checks are read-only, so
a misconfiguration costs a second instead of a boot cycle and the instance
minutes that go with it.

Start with `run_mode=smoke` (~10s on the instance) to confirm the path end to
end before spending 30 minutes on `full`.

## Cost safety

Instances are terminated in a `finally` block covering success, benchmark
failure, and timeout. Because that does **not** cover `SIGKILL` of the API
process, every instance also boots with a **dead-man switch** — a
`shutdown -h +120` in user-data (tunable via `SIGX_MAX_LIFETIME_MIN`) that
terminates it even if this service disappears entirely. Two further backstops: every instance is tagged `ManagedBy=sigtekx-api`, and the
instance ID is written to SQLite *before* the benchmark starts. On startup the
service audits for launched-but-not-terminated instances and logs them at
`ERROR` with the exact CLI command to find them.

Find orphans manually at any time:

```bash
aws ec2 describe-instances \
  --filters Name=tag:ManagedBy,Values=sigtekx-api \
            Name=instance-state-name,Values=running,pending \
  --query 'Reservations[].Instances[].InstanceId' --output text
```

## Known limitations

Single shared API key (no per-caller attribution or revocation without
restart). `BackgroundTasks` runs in-process, so a restart orphans in-flight
work — the SQLite record survives, the running benchmark does not. Both are
deliberate trade-offs for a single-operator internal tool; the upgrade path is
written up in `docs/_personal/api-upgrade-path.md`.
