"""M12 HTTP API tests with injected fake runner/repository (no network/database)."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from radich import NodeOutput, RunState, SchedulerResult
from radich.api import create_app
from radich.persistence import DuplicateRunError


class FakeRepo:
    def __init__(self):
        self.runs = {}
        self.error = None

    def get_run(self, run_id):
        if self.error:
            raise self.error
        return self.runs.get(run_id)


class FakeRunner:
    def __init__(self, repo):
        self.repo = repo
        self.calls = []
        self.error = None

    def run(self, run_id, payloads):
        self.calls.append((run_id, deepcopy(payloads)))
        if self.error:
            raise self.error
        result = SchedulerResult(
            run_id, RunState.COMPLETED, {"a": RunState.COMPLETED},
            {"a": NodeOutput(run_id, "a", {"answer": 42}, True)}, ("a",)
        )
        self.repo.runs[run_id] = result
        return result


@pytest.fixture
def setup():
    repo = FakeRepo()
    runner = FakeRunner(repo)
    client = TestClient(create_app(runner=runner, repository=repo, api_key="test-secret"))
    return client, runner, repo


def headers():
    return {"X-API-Key": "test-secret"}


def test_health_without_credentials(setup):
    assert setup[0].get("/health").json() == {"status": "ok"}


def test_missing_api_key_denied(setup):
    client, runner, _ = setup
    assert client.post("/v1/runs", json={}).status_code == 401
    assert client.get("/v1/runs/abc").status_code == 401
    assert runner.calls == []


def test_wrong_api_key_denied(setup):
    assert setup[0].post("/v1/runs", headers={"X-API-Key": "bad"}, json={}).status_code == 401


def test_create_and_get_run(setup):
    client, runner, _ = setup
    response = client.post("/v1/runs", headers=headers(),
                           json={"initial_payloads": {"a": {"source": "doc"}}})
    assert response.status_code == 200
    result = response.json()
    assert result["state"] == "COMPLETED"
    assert result["outputs"]["a"]["payload"] == {"answer": 42}
    assert runner.calls == [(result["run_id"], {"a": {"source": "doc"}})]
    assert client.get(f"/v1/runs/{result['run_id']}", headers=headers()).json() == result


def test_server_generates_unique_run_ids(setup):
    client, _, _ = setup
    a = client.post("/v1/runs", headers=headers(), json={}).json()["run_id"]
    b = client.post("/v1/runs", headers=headers(), json={}).json()["run_id"]
    assert a != b


def test_missing_run_returns_404(setup):
    assert setup[0].get("/v1/runs/unknown", headers=headers()).status_code == 404


def test_payload_validation_returns_422(setup):
    client, runner, _ = setup
    assert client.post("/v1/runs", headers=headers(),
                       json={"initial_payloads": {"a": ["not a dict"]}}).status_code == 422
    assert runner.calls == []


def test_extra_fields_rejected(setup):
    assert setup[0].post("/v1/runs", headers=headers(),
                         json={"unexpected": 123}).status_code == 422


def test_duplicate_run_returns_409(setup):
    client, runner, _ = setup
    runner.error = DuplicateRunError("duplicate")
    assert client.post("/v1/runs", headers=headers(), json={}).status_code == 409


def test_runner_validation_error_does_not_leak(setup):
    client, runner, _ = setup
    runner.error = ValueError("private node name")
    response = client.post("/v1/runs", headers=headers(), json={})
    assert response.status_code == 422
    assert "private" not in response.text


def test_runner_exception_returns_generic_500(setup):
    client, runner, _ = setup
    runner.error = RuntimeError("database-password")
    response = client.post("/v1/runs", headers=headers(), json={})
    assert response.status_code == 500
    assert "database-password" not in response.text


def test_repository_exception_returns_generic_500(setup):
    client, _, repo = setup
    repo.error = RuntimeError("private-database-error")
    response = client.get("/v1/runs/id", headers=headers())
    assert response.status_code == 500
    assert "private" not in response.text


def test_empty_key_rejected():
    with pytest.raises(ValueError):
        create_app(runner=FakeRunner(FakeRepo()), repository=FakeRepo(), api_key="")


def test_invalid_dependencies_rejected():
    with pytest.raises(TypeError):
        create_app(runner=object(), repository=FakeRepo(), api_key="key")
    with pytest.raises(TypeError):
        create_app(runner=FakeRunner(FakeRepo()), repository=object(), api_key="key")
