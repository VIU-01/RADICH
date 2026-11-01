"""M09 unit tests; no database needed."""
import json

import pytest

from radich import NodeOutput, RunState, SchedulerResult
from radich.persistence.postgres import _validate, PostgresRunRepository


def sample():
    return SchedulerResult(
        "r1", RunState.COMPLETED, {"a": RunState.COMPLETED},
        {"a": NodeOutput("r1", "a", {"answer": 42}, True)}, ("a",),
    )


def test_snapshot_serialization():
    header, nodes = _validate(sample())
    assert header["execution_order"] == ["a"]
    assert json.loads(json.dumps(nodes["a"]))["payload"] == {"answer": 42}


def test_mismatched_output_id_rejected():
    r = sample()
    r.outputs["a"] = NodeOutput("wrong", "a", {}, True)
    with pytest.raises(ValueError):
        _validate(r)


def test_invalid_json_rejected():
    r = sample()
    r.outputs["a"] = NodeOutput("r1", "a", {"bad": {1, 2}}, True)
    with pytest.raises(TypeError):
        _validate(r)


def test_inconsistent_state_rejected():
    r = sample()
    r.node_states["a"] = RunState.FAILED
    with pytest.raises(ValueError):
        _validate(r)


def test_missing_output_rejected():
    r = sample()
    r.outputs.clear()
    with pytest.raises(ValueError):
        _validate(r)


def test_cancelled_node_without_output_allowed():
    r = SchedulerResult("r2", RunState.FAILED,
                        {"a": RunState.FAILED, "b": RunState.CANCELLED},
                        {"a": NodeOutput("r2", "a", {}, False, "failed")}, ("a",))
    _, nodes = _validate(r)
    assert nodes["b"] is None


def test_repository_requires_connection():
    with pytest.raises(TypeError):
        PostgresRunRepository(None)


def test_duplicate_execution_order_rejected():
    r = sample()
    object.__setattr__(r, "execution_order", ("a", "a"))
    with pytest.raises(ValueError):
        _validate(r)
