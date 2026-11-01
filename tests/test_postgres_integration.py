"""M09 integration tests against a real PostgreSQL instance."""
import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
from radich import NodeOutput, RunState, SchedulerResult
from radich.persistence import DuplicateRunError, PostgresRunRepository


@pytest.fixture
def repo():
    url = os.getenv("RADICH_TEST_DATABASE_URL")
    if not url:
        pytest.skip("RADICH_TEST_DATABASE_URL not configured")
    with psycopg.connect(url, autocommit=True) as connection:
        repository = PostgresRunRepository(connection)
        repository.initialize_schema()
        yield repository


def test_roundtrip_and_duplicate(repo):
    run_id = "test-" + uuid.uuid4().hex
    result = SchedulerResult(
        run_id, RunState.COMPLETED, {"a": RunState.COMPLETED, "b": RunState.CANCELLED},
        {"a": NodeOutput(run_id, "a", {"n": [1, 2]}, True)}, ("a",),
    )
    assert repo.get_run(run_id) is None
    repo.save_result(result)
    assert repo.get_run(run_id) == result
    with pytest.raises(DuplicateRunError):
        repo.save_result(result)


def test_separate_runs(repo):
    ids = ["test-" + uuid.uuid4().hex for _ in range(2)]
    for run_id in ids:
        repo.save_result(SchedulerResult(run_id, RunState.COMPLETED, {}, {}, ()))
    assert repo.get_run(ids[0]).run_id == ids[0]
    assert repo.get_run(ids[1]).run_id == ids[1]
