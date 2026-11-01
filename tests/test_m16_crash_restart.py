"""M16.3 subprocess crash/restart integration: PostgreSQL must survive SIGKILL."""
import os
import subprocess
import sys
import uuid

import pytest


def test_killed_worker_resumes_from_postgres():
    psycopg = pytest.importorskip("psycopg")
    dsn = os.getenv("RADICH_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("RADICH_TEST_DATABASE_URL required for crash integration")
    run_id = "m16-crash-" + uuid.uuid4().hex
    script = r'''
import os, sys
import psycopg
from radich.contracts import NodeOutput, RunState
from radich.demo import build_demo_graph, demo_handlers
from radich.persistence.checkpoints import PostgresCheckpointStore
from radich.recovery import RecoverableScheduler

run_id, mode = sys.argv[1:]
with psycopg.connect(os.environ["RADICH_TEST_DATABASE_URL"]) as conn:
    store = PostgresCheckpointStore(conn)
    store.initialize_schema()
    handlers = demo_handlers()
    extract = handlers["extract"]
    def guarded_extract(inp):
        if mode == "resume":
            raise AssertionError("checkpointed extract must not run again")
        return extract(inp)
    handlers["extract"] = guarded_extract
    if mode == "crash":
        def killed_validate(inp):
            # The preceding extract checkpoint has already been committed.
            os._exit(79)
        handlers["validate"] = killed_validate
    result = RecoverableScheduler(build_demo_graph(), handlers, store).run(
        run_id, {"extract": {"text": "crash recovery"}})
    assert result.state == RunState.COMPLETED
    assert result.outputs["summarize"].payload["summary"] == "crash recovery"
'''
    env = dict(os.environ)
    first = subprocess.run([sys.executable, "-c", script, run_id, "crash"],
                           env=env, capture_output=True, text=True, timeout=30)
    assert first.returncode == 79, first.stderr
    # A completely new Python process must load the durable checkpoint.
    second = subprocess.run([sys.executable, "-c", script, run_id, "resume"],
                            env=env, capture_output=True, text=True, timeout=30)
    assert second.returncode == 0, second.stderr
    with psycopg.connect(dsn) as conn:
        from radich.persistence.checkpoints import PostgresCheckpointStore
        checkpoint = PostgresCheckpointStore(conn).load(run_id)
    assert checkpoint.execution_order == ("extract", "validate", "summarize")
