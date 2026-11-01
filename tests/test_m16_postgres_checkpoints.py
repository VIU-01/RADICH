"""M16.2 real PostgreSQL checkpoint persistence integration tests."""
import os
import uuid

import pytest

from radich.contracts import NodeOutput, RunState
from radich.demo import build_demo_graph, demo_handlers
from radich.persistence.checkpoints import PostgresCheckpointStore
from radich.recovery import RecoverableScheduler, RunCheckpoint


@pytest.fixture
def store():
    psycopg = pytest.importorskip("psycopg")
    url = os.getenv("RADICH_TEST_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("PostgreSQL integration requires RADICH_TEST_DATABASE_URL")
    with psycopg.connect(url, autocommit=True) as conn:
        result = PostgresCheckpointStore(conn)
        result.initialize_schema()
        yield result


def test_checkpoint_persists_across_connections(store):
    run_id = "m16-" + uuid.uuid4().hex
    output = NodeOutput(run_id, "extract", {"text": "durable"}, True)
    store.save(RunCheckpoint(run_id, {"extract": output}, ("extract",)))
    checkpoint = store.load(run_id)
    assert checkpoint.completed["extract"].payload == {"text": "durable"}
    assert checkpoint.execution_order == ("extract",)


def test_rejects_stale_checkpoint_and_conflicts(store):
    run_id = "m16-" + uuid.uuid4().hex
    a = NodeOutput(run_id, "extract", {"text": "original"}, True)
    b = NodeOutput(run_id, "validate", {"text": "original"}, True)
    store.save(RunCheckpoint(run_id, {"extract": a}, ("extract",)))
    store.save(RunCheckpoint(run_id, {"extract": a, "validate": b}, ("extract", "validate")))
    with pytest.raises(ValueError, match="regression"):
        store.save(RunCheckpoint(run_id, {"extract": a}, ("extract",)))
    changed = NodeOutput(run_id, "extract", {"text": "changed"}, True)
    with pytest.raises(ValueError, match="conflicting"):
        store.save(RunCheckpoint(run_id, {"extract": changed, "validate": b},
                                 ("extract", "validate")))
    assert len(store.load(run_id).completed) == 2


def test_scheduler_resumes_from_postgres(store):
    run_id = "m16-" + uuid.uuid4().hex
    handlers = demo_handlers()
    calls = {"extract": 0, "validate": 0}
    extract = handlers["extract"]
    validate = handlers["validate"]

    def tracked_extract(inp):
        calls["extract"] += 1
        return extract(inp)

    def flaky_validate(inp):
        calls["validate"] += 1
        if calls["validate"] == 1:
            raise RuntimeError("simulate interrupted work")
        return validate(inp)

    handlers["extract"] = tracked_extract
    handlers["validate"] = flaky_validate
    first = RecoverableScheduler(build_demo_graph(), handlers, store).run(
        run_id, {"extract": {"text": "recovery"}}
    )
    assert first.state == RunState.FAILED
    assert list(store.load(run_id).completed) == ["extract"]
    second = RecoverableScheduler(build_demo_graph(), handlers, store).run(
        run_id, {"extract": {"text": "recovery"}}
    )
    assert second.state == RunState.COMPLETED
    assert calls == {"extract": 1, "validate": 2}
