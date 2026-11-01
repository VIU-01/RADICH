"""Tests for M10 retry and idempotency."""
import pytest
from radich import NodeGraph, NodeRegistry, NodeSpec, NodeInput, NodeOutput, RunState, EdgeSpec
from radich.retry import RetryPolicy, RetryingScheduler, InMemoryIdempotencyStore, IdempotentHandler


def graph(*nodes, edges=()):
    registry = NodeRegistry()
    result = NodeGraph(registry)
    for node in nodes:
        registry.register(NodeSpec(node, "task", "1"))
        result.add_node(node)
    for source, target in edges:
        result.add_edge(EdgeSpec(source, target))
    return result


def test_retry_success_on_third_attempt():
    calls = []
    def handler(inp):
        calls.append(1)
        if len(calls) < 3:
            raise OSError("temporary")
        return NodeOutput(inp.run_id, inp.node_id, {"ok": True}, True)
    scheduler = RetryingScheduler(graph("a"), {"a": handler}, {"a": RetryPolicy(3)})
    assert scheduler.run("r").state == RunState.COMPLETED
    assert len(scheduler.attempts) == 3


def test_failure_cancels_descendant_but_not_independent_branch():
    def bad(inp):
        raise OSError("down")
    def good(inp):
        return NodeOutput(inp.run_id, inp.node_id, {}, True)
    scheduler = RetryingScheduler(graph("a", "b", "c", edges=[("a", "b")]),
                                  {"a": bad, "b": good, "c": good}, {"a": RetryPolicy(2)})
    result = scheduler.run("r")
    assert result.node_states == {
        "a": RunState.FAILED, "b": RunState.CANCELLED, "c": RunState.COMPLETED
    }
    assert len(scheduler.attempts) == 3


def test_failed_output_retry_is_opt_in():
    calls = []
    def handler(inp):
        calls.append(1)
        return NodeOutput(inp.run_id, inp.node_id, {}, len(calls) > 1,
                          None if len(calls) > 1 else "retry")
    scheduler = RetryingScheduler(graph("a"), {"a": handler},
                                  {"a": RetryPolicy(2, retry_on_failed_output=True)})
    assert scheduler.run("r").state == RunState.COMPLETED
    assert len(calls) == 2


def test_default_one_attempt():
    calls = []
    def handler(inp):
        calls.append(1)
        raise OSError("fail")
    scheduler = RetryingScheduler(graph("a"), {"a": handler})
    assert scheduler.run("r").state == RunState.FAILED
    assert len(calls) == 1


def test_invalid_retry_policy():
    with pytest.raises(ValueError):
        RetryPolicy(0)
    with pytest.raises(ValueError):
        RetryPolicy(True)


def test_idempotency_reuses_success_not_failure():
    calls = []
    def handler(inp):
        calls.append(1)
        return NodeOutput(inp.run_id, inp.node_id, {"n": len(calls)}, True)
    wrapped = IdempotentHandler(handler, InMemoryIdempotencyStore(),
                                lambda inp: f"{inp.run_id}:{inp.node_id}:{inp.payload['x']}")
    assert wrapped(NodeInput("r", "a", {"x": 1})) == wrapped(NodeInput("r", "a", {"x": 1}))
    assert len(calls) == 1
    assert wrapped(NodeInput("r", "a", {"x": 2})).payload["n"] == 2


def test_cross_run_key_collision_rejected():
    wrapped = IdempotentHandler(
        lambda inp: NodeOutput(inp.run_id, inp.node_id, {}, True),
        InMemoryIdempotencyStore(), lambda inp: "constant")
    wrapped(NodeInput("r1", "a", {}))
    with pytest.raises(ValueError):
        wrapped(NodeInput("r2", "a", {}))


def test_failed_outputs_not_cached():
    calls = []
    def handler(inp):
        calls.append(1)
        return NodeOutput(inp.run_id, inp.node_id, {}, False, "error")
    wrapped = IdempotentHandler(handler, InMemoryIdempotencyStore(), lambda inp: "key")
    wrapped(NodeInput("r", "a", {}))
    wrapped(NodeInput("r", "a", {}))
    assert len(calls) == 2
