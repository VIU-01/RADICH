"""M14: real DAG/policy/retry integration through the HTTP boundary.

No fake scheduler: only the storage adapter is in-memory. PostgreSQL coverage
remains in the dedicated database CI workflow.
"""
from fastapi.testclient import TestClient

from radich.api import create_app
from radich.demo import build_demo_runner


class MemoryRepository:
    def __init__(self):
        self.results = {}

    def get_run(self, run_id):
        return self.results.get(run_id)


class DemoRunAdapter:
    """Construct per-run authorization context, then record the real result."""

    def __init__(self, repository, approved=True):
        self.repository = repository
        self.approved = approved

    def run(self, run_id, initial_payloads):
        result = build_demo_runner(run_id, approved=self.approved).run(
            run_id, initial_payloads
        )
        self.repository.results[run_id] = result
        return result


def client_for(approved=True):
    repository = MemoryRepository()
    return TestClient(create_app(
        runner=DemoRunAdapter(repository, approved=approved),
        repository=repository,
        api_key="m14-test-key",
    ))


HEADERS = {"X-API-Key": "m14-test-key"}


def test_http_executes_real_demo_dag_and_reads_result():
    client = client_for()
    response = client.post(
        "/v1/runs", headers=HEADERS,
        json={"initial_payloads": {"extract": {"text": "native Python graph"}}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "COMPLETED"
    assert body["execution_order"] == ["extract", "validate", "summarize"]
    assert body["outputs"]["summarize"]["payload"] == {
        "summary": "native Python graph", "word_count": 3
    }
    assert client.get(f"/v1/runs/{body['run_id']}", headers=HEADERS).json() == body


def test_http_real_graph_failure_cancels_dependents():
    client = client_for()
    response = client.post("/v1/runs", headers=HEADERS, json={})
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "FAILED"
    assert body["node_states"]["validate"] == "CANCELLED"
    assert body["node_states"]["summarize"] == "CANCELLED"


def test_http_real_policy_denies_unapproved_summary():
    client = client_for(approved=False)
    response = client.post(
        "/v1/runs", headers=HEADERS,
        json={"initial_payloads": {"extract": {"text": "hello world"}}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "FAILED"
    assert "APPROVAL_REQUIRED" in body["outputs"]["summarize"]["error"]


def test_http_authentication_blocks_real_execution():
    client = client_for()
    response = client.post(
        "/v1/runs", json={"initial_payloads": {"extract": {"text": "secret"}}}
    )
    assert response.status_code == 401


def test_http_distinct_runs_have_independent_policy_contexts():
    client = client_for()
    ids = []
    for text in ("first run", "second run"):
        response = client.post(
            "/v1/runs", headers=HEADERS,
            json={"initial_payloads": {"extract": {"text": text}}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["state"] == "COMPLETED"
        assert body["outputs"]["summarize"]["payload"]["summary"] == text
        ids.append(body["run_id"])
    assert ids[0] != ids[1]
