"""M17.5: real PostgreSQL and HTTP end-to-end tests, including process crash."""

import json
import os
import subprocess
import sys
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from radich.agents.demo import AGENT_NODE
from radich.agents.service import (
    M17AgentRepository, M17AgentRunner, build_m17_app,
)


DSN = os.environ.get("RADICH_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="real PostgreSQL is required")


def headers():
    return {"X-API-Key": "test-m17-secret"}


def new_client(*, grant=True):
    return TestClient(build_m17_app(
        dsn=DSN, api_key="test-m17-secret", grant_skill=grant
    ))


def test_api_agent_persists_result_and_get_after_new_app_instance():
    client = new_client()
    first = client.post(
        "/v1/runs", headers=headers(),
        json={"initial_payloads": {"extract": {"text": "  saludo   a   RADICH  "}}},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["state"] == "COMPLETED"
    assert body["execution_order"] == ["extract", AGENT_NODE]
    assert body["outputs"][AGENT_NODE]["payload"]["normalized_text"] == "saludo a RADICH"
    assert body["outputs"][AGENT_NODE]["payload"]["agent_id"] == "A01"
    with psycopg.connect(DSN, autocommit=True) as conn:
        request = conn.execute(
            "SELECT initial_payloads FROM radich_m17_requests WHERE run_id = %s",
            (body["run_id"],),
        ).fetchone()
        assert request is not None
        checkpoints = conn.execute(
            "SELECT completed FROM radich_checkpoints WHERE run_id = %s",
            (body["run_id"],),
        ).fetchone()
        assert checkpoints is not None
        assert set(checkpoints[0]) == {"extract", AGENT_NODE}
    restarted = new_client()
    assert restarted.get(
        f"/v1/runs/{body['run_id']}", headers=headers()
    ).json() == body
    # A completed snapshot is immutable; resume must not run agent again.
    assert restarted.post(
        f"/v1/runs/{body['run_id']}/resume", headers=headers()
    ).json() == body
    progress = restarted.get(
        f"/v1/runs/{body['run_id']}/progress", headers=headers()
    )
    assert progress.status_code == 200
    assert progress.json() == {
        "run_id": body["run_id"], "phase": "FINALIZED",
        "terminal_state": "COMPLETED",
        "completed_nodes": ["extract", AGENT_NODE],
        "execution_order": ["extract", AGENT_NODE],
    }
    assert "saludo" not in progress.text
    assert "normalized_text" not in progress.text


def test_registered_progress_has_no_input_or_checkpoint_and_is_read_only():
    client = new_client()
    run_id = str(uuid4())
    secret_text = "private-test-payload-no-progress-leak"
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO radich_m17_requests (run_id, initial_payloads) "
            "VALUES (%s, %s::jsonb)",
            (run_id, json.dumps({"extract": {"text": secret_text}})),
        )
    url = f"/v1/runs/{run_id}/progress"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"X-API-Key": "wrong"}).status_code == 401
    response = client.get(url, headers=headers())
    assert response.status_code == 200
    assert response.json() == {
        "run_id": run_id, "phase": "REGISTERED", "terminal_state": None,
        "completed_nodes": [], "execution_order": [],
    }
    assert secret_text not in response.text
    assert client.get(f"/v1/runs/{run_id}", headers=headers()).status_code == 404
    assert client.get("/v1/runs/unknown-m19-progress/progress", headers=headers()).status_code == 404
    # A read must not create a checkpoint or terminal snapshot.
    with psycopg.connect(DSN, autocommit=True) as conn:
        assert conn.execute(
            "SELECT 1 FROM radich_checkpoints WHERE run_id = %s", (run_id,)
        ).fetchone() is None
        assert conn.execute(
            "SELECT 1 FROM radich_runs WHERE run_id = %s", (run_id,)
        ).fetchone() is None


def test_unauthorized_and_invalid_requests_fail_closed():
    client = new_client()
    endpoint = "/v1/runs"
    payload = {"initial_payloads": {"extract": {"text": "x"}}}
    assert client.post(endpoint, json=payload).status_code == 401
    assert client.post(endpoint, headers={"X-API-Key": "bad"}, json=payload).status_code == 401
    assert client.post("/v1/runs/x/resume").status_code == 401
    assert client.get("/v1/runs/x").status_code == 401
    assert client.post("/v1/runs/unknown/resume", headers=headers()).status_code == 404
    for bad in (
        {},
        {"extract": {"text": ""}},
        {"extract": {"text": 42}},
        {"extract": {"text": "x", "tool": "write"}},
        {"extract": {"text": "x"}, AGENT_NODE: {"skill_id": "tools.write"}},
        {"extract": {"text": "x" * 10001}},
    ):
        response = client.post(endpoint, headers=headers(),
                               json={"initial_payloads": bad})
        assert response.status_code == 422, response.text


def test_missing_skill_permission_is_recorded_as_failure():
    client = new_client(grant=False)
    response = client.post(
        "/v1/runs", headers=headers(),
        json={"initial_payloads": {"extract": {"text": "allowed text"}}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "FAILED"
    assert body["outputs"][AGENT_NODE]["payload"] == {}
    assert body["outputs"][AGENT_NODE]["error"].startswith("DENY:")
    assert new_client(grant=True).get(
        f"/v1/runs/{body['run_id']}", headers=headers()
    ).json() == body
    # Changing the authorization configuration never replays a terminal run.
    assert new_client(grant=True).post(
        f"/v1/runs/{body['run_id']}/resume", headers=headers()
    ).json() == body
    progress = client.get(
        f"/v1/runs/{body['run_id']}/progress", headers=headers()
    )
    assert progress.status_code == 200
    assert progress.json() == {
        "run_id": body["run_id"], "phase": "FINALIZED",
        "terminal_state": "FAILED",
        "completed_nodes": ["extract"],
        "execution_order": ["extract", AGENT_NODE],
    }
    assert "allowed text" not in progress.text


def test_two_workers_cannot_resume_same_run_concurrently():
    repo = M17AgentRepository(DSN)
    repo.initialize_schema()
    run_id = str(uuid4())
    runner = M17AgentRunner(repo, grant_skill=True)
    runner.run(run_id, {"extract": {"text": "completed"}})
    with psycopg.connect(DSN, autocommit=True) as conn:
        assert conn.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s::text, 0))",
            (run_id,),
        ).fetchone()[0]
        try:
            r = new_client().post(f"/v1/runs/{run_id}/resume", headers=headers())
            assert r.status_code == 409, r.text
        finally:
            conn.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s::text, 0))",
                (run_id,),
            )
    assert new_client().post(
        f"/v1/runs/{run_id}/resume", headers=headers()
    ).status_code == 200


def test_agent_resumes_after_actual_process_exit():
    """Kill the child after extract is checkpointed and then resume via HTTP."""
    run_id = str(uuid4())
    script = r"""
import os, sys
from radich.agents import service
original = service.build_m17_components
def with_crash(run_id, *, grant_skill):
    graph, handlers = original(run_id, grant_skill=grant_skill)
    handlers["agent_a01"] = lambda unused: os._exit(17)
    return graph, handlers
service.build_m17_components = with_crash
repo = service.M17AgentRepository(os.environ["RADICH_TEST_DATABASE_URL"])
repo.initialize_schema()
service.M17AgentRunner(repo, grant_skill=True).run(
    sys.argv[1], {"extract": {"text": "   radich   survives   crash "}}
)
"""
    process = subprocess.run(
        [sys.executable, "-c", script, run_id],
        env=os.environ.copy(), capture_output=True, text=True, timeout=20,
    )
    assert process.returncode == 17, (process.stdout, process.stderr)
    with psycopg.connect(DSN, autocommit=True) as conn:
        row = conn.execute(
            "SELECT completed FROM radich_checkpoints WHERE run_id = %s",
            (run_id,),
        ).fetchone()
        assert row is not None
        assert set(row[0]) == {"extract"}
    client = new_client()
    # Interrupted requests do not yet have the immutable final snapshot.
    assert client.get(f"/v1/runs/{run_id}", headers=headers()).status_code == 404
    incomplete = client.get(f"/v1/runs/{run_id}/progress", headers=headers())
    assert incomplete.status_code == 200
    assert incomplete.json() == {
        "run_id": run_id, "phase": "CHECKPOINTED",
        "terminal_state": None,
        "completed_nodes": ["extract"], "execution_order": ["extract"],
    }
    assert "radich   survives" not in incomplete.text
    assert "payload" not in incomplete.text
    assert client.post(f"/v1/runs/{run_id}/resume").status_code == 401
    resumed = client.post(f"/v1/runs/{run_id}/resume", headers=headers())
    assert resumed.status_code == 200, resumed.text
    body = resumed.json()
    assert body["state"] == "COMPLETED"
    assert body["execution_order"] == ["extract", AGENT_NODE]
    assert body["outputs"][AGENT_NODE]["payload"]["normalized_text"] == "radich survives crash"
    assert new_client().get(
        f"/v1/runs/{run_id}", headers=headers()
    ).json() == body
    completed = client.get(f"/v1/runs/{run_id}/progress", headers=headers())
    assert completed.status_code == 200
    assert completed.json() == {
        "run_id": run_id, "phase": "FINALIZED",
        "terminal_state": "COMPLETED",
        "completed_nodes": ["extract", AGENT_NODE],
        "execution_order": ["extract", AGENT_NODE],
    }
