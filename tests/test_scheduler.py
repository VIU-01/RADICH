"""M08 scheduler tests."""

import pytest

from radich import (
    EdgeSpec, NodeGraph, NodeInput, NodeOutput, NodeRegistry,
    NodeSpec, RunState, Scheduler,
)


def setup_graph(*nodes, edges=()):
    registry = NodeRegistry()
    graph = NodeGraph(registry)
    for node_id in nodes:
        registry.register(NodeSpec(node_id, "task", "1"))
        graph.add_node(node_id)
    for source, target in edges:
        graph.add_edge(EdgeSpec(source, target))
    return graph


def echo(inp):
    return NodeOutput(inp.run_id, inp.node_id, {"received": inp.payload}, True)


def test_chain_propagates_predecessor_outputs():
    graph = setup_graph("a", "b", "c", edges=(("a", "b"), ("b", "c")))
    result = Scheduler(graph, {key: echo for key in "abc"}).run(
        "run1", {"a": {"value": 7}}
    )
    assert result.state == RunState.COMPLETED
    assert result.execution_order == ("a", "b", "c")
    assert result.outputs["b"].payload["received"]["dependencies"]["a"] == (
        result.outputs["a"].payload
    )
    assert result.outputs["a"].payload["received"]["value"] == 7


def test_failed_node_blocks_descendants_but_not_independent_branch():
    graph = setup_graph("a", "b", "c", edges=(("a", "b"),))
    def fail(inp):
        return NodeOutput(inp.run_id, inp.node_id, {}, False, "failed")
    result = Scheduler(graph, {"a": fail, "b": echo, "c": echo}).run("run")
    assert result.state == RunState.FAILED
    assert result.node_states == {
        "a": RunState.FAILED, "b": RunState.CANCELLED, "c": RunState.COMPLETED
    }
    assert result.execution_order == ("a", "c")
    assert "b" not in result.outputs


def test_exception_converted_to_failed_output():
    graph = setup_graph("a")
    def boom(_):
        raise RuntimeError("broken")
    result = Scheduler(graph, {"a": boom}).run("run")
    assert result.node_states["a"] == RunState.FAILED
    assert "RuntimeError: broken" in result.outputs["a"].error


def test_invalid_handler_result_converted_to_failure():
    graph = setup_graph("a")
    result = Scheduler(graph, {"a": lambda _: "invalid"}).run("run")
    assert result.node_states["a"] == RunState.FAILED
    assert "TypeError" in result.outputs["a"].error


def test_mismatched_ids_converted_to_failure():
    graph = setup_graph("a")
    result = Scheduler(graph, {"a": lambda _: NodeOutput("other", "a", {}, True)}).run("run")
    assert result.node_states["a"] == RunState.FAILED


def test_validation_before_execution():
    graph = setup_graph("a")
    called = []
    def handler(inp):
        called.append(inp)
        return echo(inp)
    scheduler = Scheduler(graph, {"a": handler})
    with pytest.raises(ValueError):
        scheduler.run("")
    with pytest.raises(ValueError):
        scheduler.run("r", {"missing": {}})
    with pytest.raises(ValueError):
        scheduler.run("r", {"a": {"dependencies": {}}})
    with pytest.raises(TypeError):
        scheduler.run("r", {"a": []})
    assert called == []
    with pytest.raises(ValueError):
        Scheduler(graph, {}).run("r")


def test_empty_graph_and_deterministic_order():
    empty = Scheduler(setup_graph(), {}).run("r")
    assert empty.state == RunState.COMPLETED
    assert empty.execution_order == ()
    graph = setup_graph("z", "a", "m")
    result = Scheduler(graph, {key: echo for key in ("z", "a", "m")}).run("r")
    assert result.execution_order == ("a", "m", "z")


def test_runs_isolated_and_input_payload_not_mutated():
    graph = setup_graph("a")
    initial = {"a": {"nested": {"x": 1}}}
    def mutate(inp):
        inp.payload["nested"]["x"] = 99
        return NodeOutput(inp.run_id, inp.node_id, {}, True)
    scheduler = Scheduler(graph, {"a": mutate})
    assert scheduler.run("first", initial).state == RunState.COMPLETED
    assert scheduler.run("second", initial).state == RunState.COMPLETED
    assert initial["a"]["nested"]["x"] == 1


def test_invalid_constructor():
    with pytest.raises(TypeError):
        Scheduler(None, {})
    with pytest.raises(TypeError):
        Scheduler(setup_graph(), {"a": None})
