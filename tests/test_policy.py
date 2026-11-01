"""M11 authorization tests."""
import pytest

from radich import EdgeSpec, NodeGraph, NodeInput, NodeOutput, NodeRegistry, NodeSpec, RunState, Scheduler
from radich.policy import (AuthorizedHandler, Decision, ExecutionContext,
                           NodePolicy, PolicyEngine)


def context(**kwargs):
    return ExecutionContext("run-1", "operator", **kwargs)


def test_permission_allows():
    d = PolicyEngine().evaluate(context(permissions=frozenset({"read"})), "a",
                                NodePolicy(required_permission="read"))
    assert d.decision == Decision.ALLOW


def test_permission_denies():
    d = PolicyEngine().evaluate(context(), "a", NodePolicy(required_permission="write"))
    assert d.decision == Decision.DENY


def test_approval_required():
    d = PolicyEngine().evaluate(context(), "a", NodePolicy(requires_approval=True))
    assert d.decision == Decision.APPROVAL_REQUIRED


def test_approved_node():
    d = PolicyEngine().evaluate(context(approvals=frozenset({"a"})), "a",
                                NodePolicy(requires_approval=True))
    assert d.decision == Decision.ALLOW


def test_explicit_denial_overrides_permissions_and_approval():
    d = PolicyEngine().evaluate(
        context(permissions=frozenset({"write"}), approvals=frozenset({"a"})),
        "a", NodePolicy(required_permission="write", requires_approval=True, denied=True))
    assert d.decision == Decision.DENY


def test_invalid_context():
    with pytest.raises(ValueError):
        ExecutionContext("", "operator")
    with pytest.raises(TypeError):
        ExecutionContext("r", "operator", permissions={"read"})


def test_invalid_policy():
    with pytest.raises(ValueError):
        NodePolicy(required_permission="")
    with pytest.raises(TypeError):
        NodePolicy(denied=1)


def test_denied_handler_never_invoked():
    calls = []
    def handler(inp):
        calls.append(1)
        return NodeOutput(inp.run_id, inp.node_id, {}, True)
    guarded = AuthorizedHandler(handler, PolicyEngine(), context(),
                                NodePolicy(required_permission="write"))
    out = guarded(NodeInput("run-1", "a", {}))
    assert not out.success and "DENY" in out.error
    assert not calls


def test_mismatched_run_id_denied():
    guarded = AuthorizedHandler(lambda inp: None, PolicyEngine(), context(), NodePolicy())
    out = guarded(NodeInput("other", "a", {}))
    assert not out.success and "mismatch" in out.error


def test_allowed_handler_runs():
    guarded = AuthorizedHandler(
        lambda inp: NodeOutput(inp.run_id, inp.node_id, {"ok": 1}, True),
        PolicyEngine(), context(), NodePolicy())
    assert guarded(NodeInput("run-1", "a", {})).payload == {"ok": 1}


def test_scheduler_cancels_descendant_on_denial():
    registry = NodeRegistry()
    graph = NodeGraph(registry)
    for node in ("a", "b"):
        registry.register(NodeSpec(node, "task", "1"))
        graph.add_node(node)
    graph.add_edge(EdgeSpec("a", "b"))
    calls = []
    def handler(inp):
        calls.append(inp.node_id)
        return NodeOutput(inp.run_id, inp.node_id, {}, True)
    guarded = AuthorizedHandler(handler, PolicyEngine(), context(),
                                NodePolicy(requires_approval=True))
    result = Scheduler(graph, {"a": guarded, "b": handler}).run("run-1")
    assert result.state == RunState.FAILED
    assert result.node_states["b"] == RunState.CANCELLED
    assert not calls


def test_policy_rechecks_each_invocation():
    guarded = AuthorizedHandler(
        lambda inp: NodeOutput(inp.run_id, inp.node_id, {}, True),
        PolicyEngine(), context(), NodePolicy(requires_approval=True))
    assert not guarded(NodeInput("run-1", "a", {})).success
    assert not guarded(NodeInput("run-1", "a", {})).success
