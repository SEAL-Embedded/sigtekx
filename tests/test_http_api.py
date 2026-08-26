"""Tests for the HTTP orchestration API (src/sigtekx/api).

Note: tests/test_api.py covers the *engine's* Python API (presets, builder,
Engine). This file covers the *HTTP* API. Different surface, similar name.

Everything here runs against MockDriver, so the suite never touches AWS and
never costs money. The most important assertions are not the happy path but
the cost-safety ones: a failed run must still terminate its instance.
"""

import pytest

pytest.importorskip("fastapi", reason="requires the [api] extra")

from fastapi.testclient import TestClient  # noqa: E402

from sigtekx.api.models import (  # noqa: E402
    BenchmarkRequest,
    BenchmarkRun,
    RunMode,
    RunStatus,
)
from sigtekx.api.orchestrator import (  # noqa: E402
    MockDriver,
    StepFailed,
    execute_run,
)
from sigtekx.api.store import RunStore  # noqa: E402

API_KEY = "test-key"
AUTH = {"X-API-Key": API_KEY}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient wired to a throwaway SQLite file and a fast mock driver."""
    monkeypatch.setenv("SIGX_API_KEY", API_KEY)
    monkeypatch.setenv("SIGX_API_MODE", "mock")
    monkeypatch.setenv("SIGX_MOCK_DELAY", "0.01")
    monkeypatch.setenv("SIGX_API_DB", str(tmp_path / "runs.db"))

    from sigtekx.api.app import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def store(tmp_path):
    s = RunStore(tmp_path / "direct.db")
    yield s
    s.close()


def _new_run(run_id: str = "r1", status: RunStatus = RunStatus.PENDING) -> BenchmarkRun:
    now = BenchmarkRun.now()
    return BenchmarkRun(
        id=run_id,
        status=status,
        run_mode=RunMode.SMOKE,
        instance_type="g4dn.xlarge",
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuth:
    def test_health_needs_no_key(self, client):
        assert client.get("/health").status_code == 200

    def test_missing_key_is_401(self, client):
        assert client.get("/benchmarks").status_code == 401

    def test_wrong_key_is_401(self, client):
        r = client.get("/benchmarks", headers={"X-API-Key": "nope"})
        assert r.status_code == 401

    def test_valid_key_allows_access(self, client):
        assert client.get("/benchmarks", headers=AUTH).status_code == 200


# ---------------------------------------------------------------------------
# Validation -> 422, courtesy of EngineConfig
# ---------------------------------------------------------------------------


class TestValidation:
    def test_nfft_must_be_power_of_two(self, client):
        r = client.post("/benchmarks", json={"engine": {"nfft": 1000}}, headers=AUTH)
        assert r.status_code == 422
        assert "power of 2" in r.text

    def test_unknown_engine_field_rejected(self, client):
        """extra='forbid' turns a typo into a 422 instead of a silent default."""
        r = client.post("/benchmarks", json={"engine": {"nfftt": 4096}}, headers=AUTH)
        assert r.status_code == 422

    def test_overlap_out_of_range(self, client):
        r = client.post("/benchmarks", json={"engine": {"overlap": 1.5}}, headers=AUTH)
        assert r.status_code == 422

    def test_unknown_run_mode(self, client):
        r = client.post("/benchmarks", json={"run_mode": "turbo"}, headers=AUTH)
        assert r.status_code == 422

    def test_string_nfft_is_coerced(self, client):
        """Pydantic parses wire text into real types; '4096' is valid."""
        r = client.post("/benchmarks", json={"engine": {"nfft": "4096"}}, headers=AUTH)
        assert r.status_code == 202


# ---------------------------------------------------------------------------
# Run lifecycle over HTTP
# ---------------------------------------------------------------------------


class TestRunLifecycle:
    def test_post_returns_202_and_id(self, client):
        r = client.post("/benchmarks", json={"run_mode": "smoke"}, headers=AUTH)
        assert r.status_code == 202
        body = r.json()
        assert body["id"]
        assert body["status"] == RunStatus.PENDING.value

    def test_unknown_run_is_404(self, client):
        r = client.get("/benchmarks/nosuchrun", headers=AUTH)
        assert r.status_code == 404

    def test_run_completes_and_terminates(self, client):
        rid = client.post("/benchmarks", json={"run_mode": "smoke"}, headers=AUTH).json()["id"]
        run = client.get(f"/benchmarks/{rid}", headers=AUTH).json()
        assert run["status"] == RunStatus.SUCCEEDED.value
        assert run["terminated"] is True
        assert run["instance_id"]
        assert run["result_location"]

    def test_instance_type_override(self, client):
        r = client.post(
            "/benchmarks", json={"instance_type": "g5.xlarge"}, headers=AUTH
        )
        assert r.json()["instance_type"] == "g5.xlarge"

    def test_list_returns_recent_runs(self, client):
        for _ in range(3):
            client.post("/benchmarks", json={"run_mode": "smoke"}, headers=AUTH)
        runs = client.get("/benchmarks", headers=AUTH).json()
        assert len(runs) == 3

    def test_list_respects_limit(self, client):
        for _ in range(3):
            client.post("/benchmarks", json={"run_mode": "smoke"}, headers=AUTH)
        assert len(client.get("/benchmarks?limit=2", headers=AUTH).json()) == 2


# ---------------------------------------------------------------------------
# Cost safety -- the assertions that actually matter
# ---------------------------------------------------------------------------


class TestCostSafety:
    def test_failed_run_still_terminates_instance(self, store):
        """The whole point of the finally block."""

        class Exploding(MockDriver):
            def run_benchmark(self, public_ip, instance_id, req):
                raise StepFailed("simulated crash")

        store.create(_new_run("fail1"))
        driver = Exploding(step_delay_s=0.0)
        execute_run("fail1", BenchmarkRequest(), driver, store)

        run = store.get("fail1")
        assert run.status is RunStatus.FAILED
        assert "simulated crash" in run.error
        assert run.terminated is True
        assert driver.terminated == [run.instance_id]

    def test_execute_run_never_raises(self, store):
        """It runs in a threadpool; an escaped exception would strand the run."""

        class Unterminatable(MockDriver):
            def run_benchmark(self, public_ip, instance_id, req):
                raise StepFailed("crash")

            def terminate(self, instance_id):
                raise RuntimeError("AWS unreachable")

        store.create(_new_run("fail2"))
        execute_run("fail2", BenchmarkRequest(), Unterminatable(step_delay_s=0.0), store)

        run = store.get("fail2")
        assert run.status is RunStatus.FAILED
        assert run.terminated is False  # honest: we could not confirm it

    def test_unterminated_instance_is_auditable(self, store):
        """A leaked instance must be discoverable after a crash."""
        store.create(_new_run("leaked"))
        store.update("leaked", instance_id="i-0leaked")
        assert ("leaked", "i-0leaked") in store.unterminated_instances()

    def test_terminated_run_not_flagged_as_orphan(self, store):
        store.create(_new_run("clean"))
        store.update("clean", instance_id="i-0clean", terminated=True)
        assert all(r != "clean" for r, _ in store.unterminated_instances())


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class TestRunStore:
    def test_roundtrip(self, store):
        store.create(_new_run("a"))
        assert store.get("a").id == "a"

    def test_missing_returns_none(self, store):
        assert store.get("ghost") is None

    def test_update_rejects_unknown_field(self, store):
        store.create(_new_run("a"))
        with pytest.raises(ValueError, match="unknown run fields"):
            store.update("a", bogus="x")

    def test_active_count_excludes_terminal_states(self, store):
        store.create(_new_run("a", RunStatus.RUNNING))
        store.create(_new_run("b", RunStatus.SUCCEEDED))
        store.create(_new_run("c", RunStatus.FAILED))
        assert store.active_count() == 1

    def test_survives_reopen(self, tmp_path):
        """Durability is why this is SQLite and not a dict."""
        path = tmp_path / "persist.db"
        s1 = RunStore(path)
        s1.create(_new_run("keepme"))
        s1.update("keepme", instance_id="i-0abc")
        s1.close()

        s2 = RunStore(path)
        assert s2.get("keepme").instance_id == "i-0abc"
        s2.close()


# ---------------------------------------------------------------------------
# OpenAPI -- the /docs page is a deliverable
# ---------------------------------------------------------------------------


class TestOpenAPI:
    def test_docs_renders(self, client):
        assert client.get("/docs").status_code == 200

    def test_schema_documents_status_codes(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        assert "202" in paths["/benchmarks"]["post"]["responses"]
        assert "404" in paths["/benchmarks/{run_id}"]["get"]["responses"]

    def test_engine_config_is_in_schema(self, client):
        """The API contract is generated from the library's own schema."""
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
        assert "EngineConfig" in schemas


# ---------------------------------------------------------------------------
# Logging -- regression: a reserved extra= key once failed a live EC2 run
# ---------------------------------------------------------------------------


class TestLoggingSafety:
    def test_reserved_extra_keys_are_renamed(self):
        from sigtekx.api.app import _safe_extra

        out = _safe_extra(args=[1], script="s")
        assert out == {"x_args": [1], "script": "s"}

    def test_logging_reserved_keys_does_not_raise(self):
        """extra={"args": ...} raises inside logging; in a background task that
        would fail the run *after* an instance was already launched."""
        import logging

        from sigtekx.api.app import _safe_extra

        logging.getLogger("test.safe").info("x", extra=_safe_extra(args=["a"], name="n"))

    def test_run_script_does_not_use_reserved_key(self, tmp_path):
        """Guards the exact call site that broke: it must log argv, not args."""
        import inspect

        from sigtekx.api import orchestrator

        src = inspect.getsource(orchestrator._run_script)
        assert '"args": args' not in src
        assert '"argv": args' in src
