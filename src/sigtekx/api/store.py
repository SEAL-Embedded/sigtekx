"""SQLite-backed run tracking.

Why SQLite and not a dict: a benchmark run outlives a request by minutes to an
hour, and an operator restarting the API should not lose the record of a run
that is *still billing* on EC2. Durable run state is what makes the orphaned
-instance audit in orchestrator.py possible after a crash.

Why stdlib sqlite3 and not an ORM: one table, four queries. An ORM here would
be more code to read, not less.

Concurrency note: ``check_same_thread=False`` is required because FastAPI's
BackgroundTasks runs in a threadpool, so writes arrive on a different thread
than the one that opened the connection. A short ``threading.Lock`` serialises
writes; at this scale contention is irrelevant and it keeps the invariant
obvious.
"""

import json
import sqlite3
import threading
from pathlib import Path

from sigtekx.api.models import BenchmarkRun, RunMode, RunStatus

TERMINAL_STATES = {RunStatus.SUCCEEDED, RunStatus.FAILED}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    status          TEXT NOT NULL,
    run_mode        TEXT NOT NULL,
    instance_type   TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    instance_id     TEXT,
    terminated      INTEGER NOT NULL DEFAULT 0,
    result_location TEXT,
    error           TEXT,
    request_json    TEXT
);
"""


class RunStore:
    """Persistent record of benchmark runs."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        if self._path.parent != Path("."):
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def create(self, run: BenchmarkRun, request_json: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs (id, status, run_mode, instance_type, created_at,"
                " updated_at, instance_id, terminated, result_location, error, request_json)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run.id,
                    run.status.value,
                    run.run_mode.value,
                    run.instance_type,
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                    run.instance_id,
                    int(run.terminated),
                    run.result_location,
                    run.error,
                    request_json,
                ),
            )
            self._conn.commit()

    def update(self, run_id: str, **fields: object) -> None:
        """Patch a run. Unknown keys are rejected loudly rather than ignored."""
        allowed = {
            "status",
            "instance_id",
            "terminated",
            "result_location",
            "error",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"cannot update unknown run fields: {sorted(unknown)}")

        sets, values = [], []
        for key, value in fields.items():
            sets.append(f"{key} = ?")
            if isinstance(value, RunStatus):
                values.append(value.value)
            elif isinstance(value, bool):
                values.append(int(value))
            else:
                values.append(value)

        sets.append("updated_at = ?")
        values.append(BenchmarkRun.now().isoformat())
        values.append(run_id)

        with self._lock:
            self._conn.execute(
                f"UPDATE runs SET {', '.join(sets)} WHERE id = ?", values
            )
            self._conn.commit()

    def get(self, run_id: str) -> BenchmarkRun | None:
        cur = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = cur.fetchone()
        return self._to_model(row) if row else None

    def list_recent(self, limit: int = 20) -> list[BenchmarkRun]:
        cur = self._conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [self._to_model(r) for r in cur.fetchall()]

    def active_count(self) -> int:
        """Runs not in a terminal state — i.e. possibly still costing money."""
        placeholders = ",".join("?" * len(TERMINAL_STATES))
        cur = self._conn.execute(
            f"SELECT COUNT(*) FROM runs WHERE status NOT IN ({placeholders})",
            [s.value for s in TERMINAL_STATES],
        )
        return int(cur.fetchone()[0])

    def unterminated_instances(self) -> list[tuple[str, str]]:
        """(run_id, instance_id) pairs that launched but were never confirmed
        terminated. Surfaced at startup so a crash mid-run is visible instead
        of silently billing."""
        cur = self._conn.execute(
            "SELECT id, instance_id FROM runs"
            " WHERE instance_id IS NOT NULL AND terminated = 0"
        )
        return [(r["id"], r["instance_id"]) for r in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _to_model(row: sqlite3.Row) -> BenchmarkRun:
        return BenchmarkRun(
            id=row["id"],
            status=RunStatus(row["status"]),
            run_mode=RunMode(row["run_mode"]),
            instance_type=row["instance_type"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            instance_id=row["instance_id"],
            terminated=bool(row["terminated"]),
            result_location=row["result_location"],
            error=row["error"],
        )


def serialise_request(payload: dict) -> str:
    """Store the originating request so a run is reproducible from its record."""
    return json.dumps(payload, default=str)
