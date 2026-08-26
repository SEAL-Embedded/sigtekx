"""FastAPI application: self-service benchmark orchestration.

Run locally::

    export SIGX_API_KEY=dev-key
    uvicorn sigtekx.api.app:app --reload
    # docs at http://127.0.0.1:8000/docs

Defaults to mock mode, so nothing here touches AWS until SIGX_API_MODE=real.
"""

import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.security import APIKeyHeader

from sigtekx.__version__ import __version__
from sigtekx.api.models import (
    BenchmarkRequest,
    BenchmarkRun,
    HealthResponse,
    RunStatus,
)
from sigtekx.api.orchestrator import ORPHAN_QUERY, build_driver, execute_run
from sigtekx.api.store import RunStore, serialise_request

API_KEY_HEADER = "X-API-Key"
DEFAULT_DB = "artifacts/api/runs.db"


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """One JSON object per line.

    Structured rather than formatted because these logs are meant to be
    queried (by run_id, by instance_id) in CloudWatch or any log aggregator,
    not read by eye. ``extra={...}`` fields from call sites are merged in.
    """

    _BUILTIN = set(
        logging.LogRecord("", 0, "", 0, "", (), None).__dict__
    ) | {"message", "asctime", "taskName"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(
            {k: v for k, v in record.__dict__.items() if k not in self._BUILTIN}
        )
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


# Reserved LogRecord attributes. Passing any of these via extra= makes the
# logging module raise, which inside a background task would fail the run --
# so callers get a prefixed key instead of an exception. Learned the hard way:
# extra={"args": [...]} killed a live EC2 run.
_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime"}


def _safe_extra(**fields: object) -> dict:
    """Build an extra= dict that cannot collide with reserved attributes."""
    return {(f"x_{k}" if k in _RESERVED else k): v for k, v in fields.items()}


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("sigtekx.api")
    root.handlers = [handler]
    root.setLevel(os.environ.get("SIGX_API_LOG_LEVEL", "INFO").upper())
    root.propagate = False


logger = logging.getLogger("sigtekx.api")


# ---------------------------------------------------------------------------
# App wiring
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build shared state once at startup, and audit for orphaned instances.

    The orphan audit is the recovery half of the cost guarantee: if a previous
    process died between launch and terminate, the instance is still billing
    and SQLite is the only remaining record of it.
    """
    _configure_logging()
    app.state.store = RunStore(os.environ.get("SIGX_API_DB", DEFAULT_DB))
    app.state.driver = build_driver()
    app.state.mode = os.environ.get("SIGX_API_MODE", "mock").lower()

    orphans = app.state.store.unterminated_instances()
    if orphans:
        logger.error(
            "ORPHANED INSTANCES may still be billing — terminate them",
            extra={"orphans": orphans, "find_command": ORPHAN_QUERY},
        )

    logger.info("api started", extra={"mode": app.state.mode, "version": __version__})
    yield
    app.state.store.close()


app = FastAPI(
    title="SigTekX Benchmark API",
    version=__version__,
    description=(
        "Self-service orchestration for GPU benchmark runs on AWS. Replaces a "
        "manual sequence of console steps and shell scripts with one HTTP call, "
        "and guarantees the EC2 instance is terminated afterwards."
    ),
    lifespan=lifespan,
)

_api_key_scheme = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def require_api_key(key: str | None = Depends(_api_key_scheme)) -> str:
    """Single shared API key from the environment.

    Sufficient because this is a single-operator internal tool. The honest
    limitation: one key means no per-caller attribution and no revocation
    without a restart. Real multi-user auth is a different design.
    """
    expected = os.environ.get("SIGX_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SIGX_API_KEY is not configured on the server",
        )
    # Constant-time compare: a plain == leaks key material through timing.
    import hmac

    if not key or not hmac.compare_digest(key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"missing or invalid {API_KEY_HEADER}",
        )
    return key


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Unauthenticated so load balancers and uptime checks can reach it."""
    return HealthResponse(
        mode=app.state.mode,
        version=__version__,
        active_runs=app.state.store.active_count(),
    )


@app.post(
    "/benchmarks",
    response_model=BenchmarkRun,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["benchmarks"],
    dependencies=[Depends(require_api_key)],
)
def create_benchmark(req: BenchmarkRequest, background: BackgroundTasks) -> BenchmarkRun:
    """Accept a benchmark request and start orchestration.

    202, not 201: the run has been *accepted*, and the EC2 instance it
    describes does not exist yet. Poll GET /benchmarks/{id} for progress.
    An invalid engine config is rejected as 422 by EngineConfig before
    reaching this body.
    """
    run_id = uuid.uuid4().hex[:12]
    now = BenchmarkRun.now()
    instance_type = req.instance_type or os.environ.get("SIGX_INSTANCE_TYPE", "g4dn.xlarge")

    run = BenchmarkRun(
        id=run_id,
        status=RunStatus.PENDING,
        run_mode=req.run_mode,
        instance_type=instance_type,
        created_at=now,
        updated_at=now,
    )
    app.state.store.create(run, serialise_request(req.model_dump(mode="json")))

    background.add_task(execute_run, run_id, req, app.state.driver, app.state.store)
    logger.info(
        "run accepted",
        extra={
            "run_id": run_id,
            "run_mode": req.run_mode.value,
            "instance_type": instance_type,
            "nfft": req.engine.nfft,
        },
    )
    return run


@app.get(
    "/benchmarks",
    response_model=list[BenchmarkRun],
    tags=["benchmarks"],
    dependencies=[Depends(require_api_key)],
)
def list_benchmarks(limit: int = 20) -> list[BenchmarkRun]:
    """Recent runs, newest first."""
    return app.state.store.list_recent(limit=limit)


@app.get(
    "/benchmarks/{run_id}",
    response_model=BenchmarkRun,
    tags=["benchmarks"],
    dependencies=[Depends(require_api_key)],
    responses={404: {"description": "Unknown run ID"}},
)
def get_benchmark(run_id: str) -> BenchmarkRun:
    """Status and, once finished, the result location."""
    run = app.state.store.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown run: {run_id}"
        )
    return run
