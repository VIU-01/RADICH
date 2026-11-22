"""M17.5 opt-in resume route: compatibility and authorization without a database."""

from fastapi.testclient import TestClient
import pytest

from radich.api import create_app
from radich.contracts import NodeOutput, RunState
from radich.scheduler import SchedulerResult
from radich.persistence.postgres import DuplicateRunError


class FakeRepository:
    def get_run(self, run_id):
        return None


class FakeRunner:
    def __init__(self):
        self.resumes = []

    def run(self, run_id, initial_payloads):
        return self._result(run_id)

    def resume(self, run_id):
        self.resumes.append(run_id)
        if run_id == "unknown":
            raise KeyError(run_id)
        if run_id == "busy":
            raise DuplicateRunError("busy")
        if run_id == "invalid":
            raise ValueError("secret-validation-message")
        if run_id == "error":
            raise RuntimeError("secret-database-message")
        return self._result(run_id)

    @staticmethod
    def _result(run_id):
        return SchedulerResult(
            run_id, RunState.COMPLETED, {"extract": RunState.COMPLETED},
            {"extract": NodeOutput(run_id, "extract", {"text": "ok"}, True)},
            ("extract",),
        )


def test_existing_api_does_not_enable_resume_by_default():
    runner = FakeRunner()
    client = TestClient(create_app(runner=runner, repository=FakeRepository(), api_key="key"))
    assert client.post("/v1/runs/some-id/resume", headers={"X-API-Key": "key"}).status_code == 404
    assert runner.resumes == []


def test_resume_requires_auth_and_keeps_run_id():
    runner = FakeRunner()
    client = TestClient(create_app(
        runner=runner, repository=FakeRepository(), api_key="key", resume_runner=runner
    ))
    assert client.post("/v1/runs/known/resume").status_code == 401
    assert client.post("/v1/runs/known/resume", headers={"X-API-Key": "wrong"}).status_code == 401
    assert runner.resumes == []
    result = client.post("/v1/runs/known/resume", headers={"X-API-Key": "key"})
    assert result.status_code == 200
    assert result.json()["run_id"] == "known"
    assert runner.resumes == ["known"]


@pytest.mark.parametrize("run_id,status", [
    ("unknown", 404), ("busy", 409), ("invalid", 422), ("error", 500)
])
def test_resume_failures_are_mapped_without_leaking_secrets(run_id, status):
    runner = FakeRunner()
    client = TestClient(create_app(
        runner=runner, repository=FakeRepository(), api_key="key", resume_runner=runner
    ))
    r = client.post(f"/v1/runs/{run_id}/resume", headers={"X-API-Key": "key"})
    assert r.status_code == status
    assert "secret" not in r.text
    assert "database" not in r.text


def test_bad_resume_runner_rejected():
    with pytest.raises(TypeError):
        create_app(
            runner=FakeRunner(), repository=FakeRepository(), api_key="key",
            resume_runner=object(),
        )


class FakeProgressReader:
    def __init__(self):
        self.reads = []

    def get_progress(self, run_id):
        self.reads.append(run_id)
        if run_id == "unknown":
            return None
        if run_id == "error":
            raise RuntimeError("secret-postgres-connection")
        return {
            "run_id": run_id,
            "phase": "CHECKPOINTED",
            "terminal_state": None,
            "completed_nodes": ["extract"],
            "execution_order": ["extract"],
        }


def test_progress_is_opt_in_and_m15_routes_unchanged():
    runner = FakeRunner()
    client = TestClient(create_app(runner=runner, repository=FakeRepository(), api_key="key"))
    assert client.get("/v1/runs/known/progress", headers={"X-API-Key": "key"}).status_code == 404
    assert client.get("/v1/runs/known", headers={"X-API-Key": "key"}).status_code == 404
    assert runner.resumes == []


def test_progress_is_authenticated_read_only_and_has_no_payloads():
    runner = FakeRunner()
    progress = FakeProgressReader()
    client = TestClient(create_app(
        runner=runner, repository=FakeRepository(), api_key="key",
        progress_reader=progress,
    ))
    endpoint = "/v1/runs/known/progress"
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers={"X-API-Key": "wrong"}).status_code == 401
    assert progress.reads == []

    result = client.get(endpoint, headers={"X-API-Key": "key"})
    assert result.status_code == 200
    assert result.json() == {
        "run_id": "known", "phase": "CHECKPOINTED",
        "terminal_state": None,
        "completed_nodes": ["extract"], "execution_order": ["extract"],
    }
    assert "payload" not in result.text
    assert progress.reads == ["known"]
    assert runner.resumes == []
    assert client.get("/v1/runs/unknown/progress", headers={"X-API-Key": "key"}).status_code == 404


def test_progress_database_error_does_not_leak_details():
    client = TestClient(create_app(
        runner=FakeRunner(), repository=FakeRepository(), api_key="key",
        progress_reader=FakeProgressReader(),
    ))
    response = client.get("/v1/runs/error/progress", headers={"X-API-Key": "key"})
    assert response.status_code == 500
    assert "secret" not in response.text
    assert "postgres" not in response.text


def test_invalid_progress_reader_rejected():
    with pytest.raises(TypeError):
        create_app(
            runner=FakeRunner(), repository=FakeRepository(), api_key="key",
            progress_reader=object(),
        )
