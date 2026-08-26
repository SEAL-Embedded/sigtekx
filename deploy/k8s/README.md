# Deploying the orchestration API

Two images, deliberately:

| Image | Built from | Base | Runs on | Purpose |
|-------|-----------|------|---------|---------|
| `sigtekx` | `Dockerfile` | `nvidia/cuda:13.0-runtime` | the EC2 GPU instance | the benchmark **workload** |
| `sigtekx-api` | `Dockerfile.api` | `python:3.11-slim` | anywhere (laptop, k8s) | the **orchestrator** that launches instances |

The API needs no GPU and no CUDA, so shipping it in the workload image would
mean pulling multiple GB to run a web server. Splitting them keeps the
orchestrator small and shrinks its attack surface.

## Docker

```bash
docker build -f Dockerfile.api -t sigtekx-api:dev .
docker run -p 8000:8000 -e SIGX_API_KEY=dev-key sigtekx-api:dev
curl localhost:8000/health
```

Verified: `/health` reports version 0.9.5, `/docs` renders, POST returns 202 and
the run completes, and the built-in HEALTHCHECK reports `healthy`.

Real mode additionally needs AWS credentials and the SSH key mounted in:

```bash
docker run -p 8000:8000 \
  -e SIGX_API_KEY=dev-key -e SIGX_API_MODE=real \
  -e AWS_DEFAULT_REGION=us-west-2 -e SIGX_AMI_ID=ami-... \
  -e SIGX_KEY_NAME=sigtekx -e SIGX_SECURITY_GROUP=sg-... \
  -v ~/.aws:/home/sigx/.aws:ro \
  -v ~/.ssh/sigtekx.pem:/home/sigx/.ssh/sigtekx.pem:ro \
  -e SIGX_SSH_KEY=/home/sigx/.ssh/sigtekx.pem \
  sigtekx-api:dev
```

## Kubernetes (local)

```bash
minikube start
eval $(minikube docker-env)                    # build into the cluster's daemon
docker build -f Dockerfile.api -t sigtekx-api:dev .
kubectl apply -f deploy/k8s/api.yaml
kubectl rollout status deploy/sigtekx-api
kubectl port-forward svc/sigtekx-api 8000:80
curl localhost:8000/health
```

Teardown: `kubectl delete -f deploy/k8s/api.yaml`

### What this deployment does and does not claim

It is a single-replica deployment of a stateful service on a local cluster.
That is the honest scope. Specifically:

- **`replicas: 1` is a hard limit, not a starting point.** Run state is a SQLite
  file on a ReadWriteOnce volume and background work is in-process, so a second
  replica would neither see the first's runs nor mount the same volume.
- **`strategy: Recreate`, not RollingUpdate** — with ReadWriteOnce, a rolling
  update deadlocks because the new pod cannot mount the volume until the old
  one releases it.
- **Mock mode by default**, so applying the manifest can never launch a
  billable instance. Real mode needs AWS credentials this manifest does not
  supply — a Secret with an IAM user's keys, or IRSA on EKS.
- Probes target `/health`, which is unauthenticated by design; an authenticated
  health endpoint would force the kubelet to carry a credential.
- Pods run non-root (uid 10001) with all capabilities dropped.

Scaling past one replica requires the Postgres + task-queue migration in
`docs/_personal/api-upgrade-path.md`. Doing that here would be building
infrastructure for load that does not exist.

### Known trade-off

The image is ~690MB, mostly AWS CLI v2, which `scripts/aws/*.sh` shell out to.
Using boto3 for the S3/CloudWatch calls instead would cut it substantially, at
the cost of duplicating logic the shell scripts already own.
