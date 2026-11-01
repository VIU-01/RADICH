"""M05.2 contract tests."""

import pytest

from radich import EdgeSpec, NodeInput, NodeOutput, NodeSpec, RunState


def test_node_spec_valid_and_independent_defaults():
    first = NodeSpec("n1", "transform", "0.1")
    second = NodeSpec("n2", "verify", "0.1")
    first.config["x"] = 1
    assert second.config == {}


@pytest.mark.parametrize("field", ["node_id", "capability", "version"])
def test_node_spec_rejects_empty_required_fields(field):
    data = dict(node_id="n", capability="cap", version="v")
    data[field] = "  "
    with pytest.raises(ValueError):
        NodeSpec(**data)


def test_node_spec_rejects_invalid_config():
    with pytest.raises(TypeError):
        NodeSpec("n", "cap", "v", config=[])


def test_edge_direction_and_no_self_loop():
    edge = EdgeSpec("a", "b")
    assert (edge.source_id, edge.target_id) == ("a", "b")
    assert EdgeSpec("b", "a") != edge
    with pytest.raises(ValueError):
        EdgeSpec("a", "a")


@pytest.mark.parametrize("source,target", [("", "b"), ("a", " ")])
def test_edge_requires_ids(source, target):
    with pytest.raises(ValueError):
        EdgeSpec(source, target)


def test_node_input_valid_and_invalid():
    assert NodeInput("r", "n", {}).payload == {}
    with pytest.raises(ValueError):
        NodeInput("", "n", {})
    with pytest.raises(TypeError):
        NodeInput("r", "n", [])


def test_node_output_success_and_failure():
    assert NodeOutput("r", "n", {}, True).success
    assert NodeOutput("r", "n", {}, False, "failed").error == "failed"
    with pytest.raises(ValueError):
        NodeOutput("r", "n", {}, True, "error")
    with pytest.raises(ValueError):
        NodeOutput("r", "n", {}, False)
    with pytest.raises(ValueError):
        NodeOutput("r", " ", {}, True)
    with pytest.raises(TypeError):
        NodeOutput("r", "n", [], True)


def test_run_state_members():
    assert [state.value for state in RunState] == [
        "CREATED", "READY", "RUNNING", "WAITING_APPROVAL",
        "COMPLETED", "FAILED", "CANCELLED",
    ]
