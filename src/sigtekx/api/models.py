"""Request/response models for the benchmark orchestration API.

Design note: the engine half of the request is the project's existing
``EngineConfig`` verbatim, not a parallel copy. That buys three things for free:

1. Validation (nfft power-of-two, overlap bounds, enum membership) already
   exists and is exercised by the library's own test suite.
2. ``extra='forbid'`` means a typo like ``nfftt`` is a 422, not a silent no-op.
3. The OpenAPI schema at /docs is generated from the same field descriptions
   the library documents, so the API cannot drift from the engine.
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field

from sigtekx.config.schemas import EngineConfig


class RunMode(str, Enum):
    """Which workload the container runs on the instance.

    Mirrors the --smoke / --full / (default single) flags that
    scripts/aws/run_ec2_benchmark.sh already accepts.
    """

    SMOKE = "smoke"  # experiment=smoke_test, ~10s — proves the cloud path works
    SINGLE = "single"  # one benchmark via hydra args
    FULL = "full"  # the whole Snakemake suite, ~30min


class RunStatus(str, Enum):
    """Lifecycle state of a benchmark run.

    Deliberately distinguishes *provisioning* from *running*: on a spot
    instance the wait-for-SSH phase is where most failures happen, and
    collapsing it into "running" would hide that from the caller.
    """

    PENDING = "pending"  # accepted, not yet started
    PROVISIONING = "provisioning"  # EC2 launching / waiting for SSH
    RUNNING = "running"  # benchmark executing in the container
    DOWNLOADING = "downloading"  # pulling results from S3
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BenchmarkRequest(BaseModel):
    """Body of POST /benchmarks.

    Split by concern: ``engine`` is *workload* intent (what to compute),
    ``instance_type`` is the one piece of *deployment* config worth varying
    per request (which GPU to compute it on). Everything else about the
    deployment — AMI, subnet, security group, key pair, IAM profile — comes
    from the server environment, because it is account-specific and does not
    change from run to run.
    """

    engine: EngineConfig = Field(
        default_factory=EngineConfig,
        description="Engine configuration; validated by the library's own schema.",
    )
    run_mode: RunMode = Field(
        default=RunMode.SMOKE,
        description="smoke (~10s), single (one benchmark), or full (Snakemake suite, ~30min).",
    )
    hydra_args: list[str] = Field(
        default_factory=list,
        description=(
            "Extra hydra overrides for run_mode=single, e.g. "
            "['experiment=ionosphere_test', '+benchmark=latency']. "
            "Ignored for smoke/full."
        ),
    )
    instance_type: str | None = Field(
        default=None,
        description="EC2 instance type override. Defaults to SIGX_INSTANCE_TYPE (g4dn.xlarge).",
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "engine": {"nfft": 4096, "channels": 2, "overlap": 0.75},
                    "run_mode": "smoke",
                }
            ]
        },
    }


class BenchmarkRun(BaseModel):
    """A tracked run. Returned by GET /benchmarks/{id} and GET /benchmarks."""

    id: str
    status: RunStatus
    run_mode: RunMode
    instance_type: str
    created_at: datetime
    updated_at: datetime

    instance_id: str | None = Field(
        default=None, description="EC2 instance ID, once launched."
    )
    terminated: bool = Field(
        default=False,
        description="Whether the launched instance was confirmed terminated.",
    )
    result_location: str | None = Field(
        default=None, description="Local dataset dir or s3:// URI, once results exist."
    )
    error: str | None = Field(default=None, description="Failure reason, if failed.")

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)


class HealthResponse(BaseModel):
    """Body of GET /health."""

    status: str = "ok"
    mode: str = Field(description="'real' (launches EC2) or 'mock' (no AWS calls).")
    version: str
    active_runs: int = Field(description="Runs not yet in a terminal state.")
