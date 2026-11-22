"""Local-only smoke test for isolated RADICH M17.5/A01 testing profile.

Usage:
  python scripts/m18_a01_smoke.py create /tmp/radich-a01-smoke-id
  # after restarting only radich-a01/postgres-a01:
  python scripts/m18_a01_smoke.py verify /tmp/radich-a01-smoke-id

Never sends real data, prints a secret, or changes the main M15 deployment.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8001"
EXAMPLE = "  prueba    A01   RADICH   "
EXPECTED = "prueba A01 RADICH"


def read_key(name: str) -> str:
    """Read only a specifically named secret; never fall back from A01 to M15."""
    key = os.environ.get(name)
    if key:
        return key
    env = Path(__file__).resolve().parents[1] / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    raise RuntimeError(f"{name} not configured")


def call(path: str, *, key: str | None = None, payload: dict | None = None):
    headers = {}
    if key is not None:
        headers["X-API-Key"] = key
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(
        BASE + path, data=body, headers=headers,
        method="POST" if payload is not None else "GET",
    )
    try:
        with urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, None


def wait_healthy() -> None:
    for _ in range(45):
        try:
            with urlopen(BASE + "/health", timeout=3) as response:
                if json.load(response) == {"status": "ok"}:
                    return
        except (OSError, URLError, ValueError):
            pass
        time.sleep(2)
    raise RuntimeError("A01 localhost health never became ready")


def assert_run(run: dict) -> None:
    assert run["state"] == "COMPLETED", run
    assert run["execution_order"] == ["extract", "agent_a01"], run
    assert set(run["node_states"]) == {"extract", "agent_a01"}
    assert all(state == "COMPLETED" for state in run["node_states"].values())
    result = run["outputs"]["agent_a01"]
    assert result["success"] is True
    assert result["error"] is None
    assert result["payload"]["agent_id"] == "A01"
    assert result["payload"]["skill_id"] == "text.normalize"
    assert result["payload"]["normalized_text"] == EXPECTED


def create(state_file: Path, key: str) -> None:
    payload = {"initial_payloads": {"extract": {"text": EXAMPLE}}}
    assert call("/v1/runs", payload=payload)[0] == 401
    assert call("/v1/runs", key="wrong-key", payload=payload)[0] == 401
    assert call("/v1/runs", key=read_key("RADICH_API_KEY"), payload=payload)[0] == 401
    invalid = {"initial_payloads": {"extract": {"text": "x", "tool": "write"}}}
    assert call("/v1/runs", key=key, payload=invalid)[0] == 422
    status, run = call("/v1/runs", key=key, payload=payload)
    assert status == 200, (status, run)
    assert_run(run)
    state_file.write_text(run["run_id"] + "\n", encoding="ascii")
    print("PASS: A01 simulated run, 401/422 protection and normalization", run["run_id"])


def verify(state_file: Path, key: str) -> None:
    run_id = state_file.read_text(encoding="ascii").strip()
    status, run = call("/v1/runs/" + run_id, key=key)
    assert status == 200, (status, run)
    assert run["run_id"] == run_id
    assert_run(run)
    # A saved terminal run is immutable: POST resume may not replay A01.
    req = Request(BASE + "/v1/runs/" + run_id + "/resume",
                  method="POST", headers={"X-API-Key": key})
    with urlopen(req, timeout=5) as response:
        assert response.status == 200
        assert_run(json.load(response))
    print("PASS: A01 persisted across container restarts; completed resume immutable", run_id)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("create", "verify"):
        sys.exit("usage: m18_a01_smoke.py create|verify /path/to/state-file")
    wait_healthy()
    a01_key = read_key("RADICH_A01_API_KEY")
    if a01_key == read_key("RADICH_API_KEY"):
        raise RuntimeError("A01 API key must differ from the M15 API key")
    (create if sys.argv[1] == "create" else verify)(Path(sys.argv[2]), a01_key)
