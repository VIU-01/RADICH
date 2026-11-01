"""Tests for M07 deterministic native Python DAG."""

import pytest

from radich import (CycleError, DuplicateEdgeError, EdgeSpec, NodeGraph,
                    NodeRegistry, NodeSpec, UnknownNodeError)


def graph(*ids):
    registry = NodeRegistry()
    for node_id in ids:
        registry.register(NodeSpec(node_id, "task", "1"))
    result = NodeGraph(registry)
    for node_id in ids:
        result.add_node(node_id)
    return result


def test_nodes_edges_and_topological_order():
    g = graph("save", "extract", "validate")
    g.add_edge(EdgeSpec("extract", "validate"))
    g.add_edge(EdgeSpec("validate", "save"))
    assert g.nodes() == ("extract", "save", "validate")
    assert g.edges() == (EdgeSpec("extract", "validate"), EdgeSpec("validate", "save"))
    assert g.topological_order() == ("extract", "validate", "save")


def test_duplicate_edge_does_not_change_graph():
    g = graph("a", "b")
    g.add_edge(EdgeSpec("a", "b"))
    with pytest.raises(DuplicateEdgeError):
        g.add_edge(EdgeSpec("a", "b"))
    assert len(g.edges()) == 1


def test_direct_and_indirect_cycles_rejected_atomically():
    g = graph("a", "b", "c")
    g.add_edge(EdgeSpec("a", "b"))
    g.add_edge(EdgeSpec("b", "c"))
    with pytest.raises(CycleError):
        g.add_edge(EdgeSpec("c", "a"))
    with pytest.raises(CycleError):
        g.add_edge(EdgeSpec("b", "a"))
    assert g.topological_order() == ("a", "b", "c")


def test_missing_nodes_and_invalid_edge():
    g = graph("a", "b")
    with pytest.raises(UnknownNodeError):
        g.add_edge(EdgeSpec("a", "missing"))
    with pytest.raises(UnknownNodeError):
        g.add_edge(EdgeSpec("missing", "a"))
    with pytest.raises(TypeError):
        g.add_edge("a -> b")


def test_node_must_be_registered_and_explicitly_added():
    registry = NodeRegistry()
    registry.register(NodeSpec("a", "task", "1"))
    g = NodeGraph(registry)
    with pytest.raises(UnknownNodeError):
        g.add_node("missing")
    g.add_node("a")
    with pytest.raises(UnknownNodeError):
        g.add_edge(EdgeSpec("a", "b"))


def test_successors_predecessors_and_isolated_nodes():
    g = graph("c", "b", "a")
    g.add_edge(EdgeSpec("a", "c"))
    g.add_edge(EdgeSpec("b", "c"))
    assert g.successors("a") == ("c",)
    assert g.predecessors("c") == ("a", "b")
    assert g.predecessors("a") == ()
    assert g.topological_order() == ("a", "b", "c")
    with pytest.raises(UnknownNodeError):
        g.successors("unknown")


def test_deterministic_order_for_independent_nodes():
    g = graph("z", "a", "m")
    assert g.topological_order() == ("a", "m", "z")


def test_invalid_registry():
    with pytest.raises(TypeError):
        NodeGraph(None)


def test_edge_spec_rejects_self_loop():
    with pytest.raises(ValueError):
        EdgeSpec("a", "a")
