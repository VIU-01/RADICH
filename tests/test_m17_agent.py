"""M17: controlled first-agent integration with real RADICH graph and policies."""

from copy import deepcopy

import pytest

from radich.agents import (
    AGENT_NODE, AgentSpec, SimulatedTextAgent, SkillSpec, build_m17_runner,
)
from radich.contracts import NodeInput, RunState


def _run(run_id="m17-1", text="  RADICH  prueba\n del   agente  ", *, granted=True):
    return build_m17_runner(run_id, grant_skill=granted).run(
        run_id, {"extract": {"text": text}}
    )


def _handler():
    return SimulatedTextAgent(
        AgentSpec("A01", "0.1", ("text.normalize",)),
        SkillSpec("text.normalize", "1.0", "skills.text.normalize"),
        node_id=AGENT_NODE,
    )


def test_agent_is_connected_to_graph_and_returns_traceable_output():
    result = _run()
    assert result.state == RunState.COMPLETED
    assert result.execution_order == ("extract", AGENT_NODE)
    assert result.node_states[AGENT_NODE] == RunState.COMPLETED
    output = result.outputs[AGENT_NODE]
    assert (output.run_id, output.node_id, output.success) == ("m17-1", AGENT_NODE, True)
    assert output.payload == {
        "agent_id": "A01",
        "agent_version": "0.1",
        "skill_id": "text.normalize",
        "skill_version": "1.0",
        "normalized_text": "RADICH prueba del agente",
    }


def test_permission_is_denied_without_execution():
    result = _run(granted=False)
    assert result.state == RunState.FAILED
    assert result.node_states["extract"] == RunState.COMPLETED
    assert result.node_states[AGENT_NODE] == RunState.FAILED
    assert result.outputs[AGENT_NODE].payload == {}
    assert result.outputs[AGENT_NODE].error.startswith("DENY:")


def test_wrong_run_context_is_denied():
    result = build_m17_runner("expected").run(
        "unexpected", {"extract": {"text": "hi"}}
    )
    assert result.state == RunState.FAILED
    assert "mismatch" in result.outputs[AGENT_NODE].error


def test_missing_text_fails_upstream_and_cancels_agent():
    result = build_m17_runner("no-input").run("no-input")
    assert result.state == RunState.FAILED
    assert result.node_states["extract"] == RunState.FAILED
    assert result.node_states[AGENT_NODE] == RunState.CANCELLED
    assert AGENT_NODE not in result.outputs


def test_initial_payload_cannot_override_skill_selection():
    result = build_m17_runner("injection").run(
        "injection",
        {"extract": {"text": "ok"}, AGENT_NODE: {"skill_id": "tool.execute"}},
    )
    assert result.state == RunState.FAILED
    assert result.outputs[AGENT_NODE].error == "invalid agent input fields"


def test_run_input_not_mutated():
    payloads = {"extract": {"text": "  a \t b "}}
    original = deepcopy(payloads)
    result = build_m17_runner("immutable").run("immutable", payloads)
    assert result.state == RunState.COMPLETED
    assert payloads == original


def test_results_are_deterministic_and_isolated_across_runs():
    first = _run(run_id="run-a", text="  A   B ")
    second = _run(run_id="run-a", text="  A   B ")
    third = _run(run_id="run-b", text="other")
    assert first == second
    assert third.outputs[AGENT_NODE].run_id == "run-b"
    assert third.outputs[AGENT_NODE].payload["normalized_text"] == "other"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: AgentSpec("", "1", ("text.normalize",)),
        lambda: AgentSpec("A01", "", ("text.normalize",)),
        lambda: AgentSpec("A01", "1", ("",)),
        lambda: AgentSpec("A01", "1", ()),
        lambda: AgentSpec("A01", "1", ("x", "x")),
        lambda: SkillSpec("", "1", "read"),
        lambda: SkillSpec("text.normalize", "", "read"),
        lambda: SkillSpec("text.normalize", "1", ""),
    ],
)
def test_invalid_agent_and_skill_contracts_fail_closed(factory):
    with pytest.raises(ValueError):
        factory()


def test_skill_id_collection_must_be_immutable_tuple():
    with pytest.raises(TypeError):
        AgentSpec("A01", "1", ["text.normalize"])


def test_unapproved_or_unimplemented_skills_rejected_at_wiring():
    with pytest.raises(ValueError, match="allowlisted"):
        SimulatedTextAgent(
            AgentSpec("A01", "1", ("different",)),
            SkillSpec("text.normalize", "1", "read"),
            node_id=AGENT_NODE,
        )
    with pytest.raises(ValueError, match="only the offline"):
        SimulatedTextAgent(
            AgentSpec("A01", "1", ("tool.execute",)),
            SkillSpec("tool.execute", "1", "execute"),
            node_id=AGENT_NODE,
        )


def test_agent_rejects_unexpected_node_and_missing_dependencies():
    handler = _handler()
    wrong = handler(NodeInput("run", "other-node", {"dependencies": {}}))
    assert not wrong.success and "DENY" in wrong.error
    missing = handler(NodeInput("run", AGENT_NODE, {"dependencies": {}}))
    assert not missing.success and "missing predecessor" in missing.error
    bad = handler(NodeInput("run", AGENT_NODE, {"dependencies": {"extract": {"text": 5}}}))
    assert not bad.success and "missing text" in bad.error


def test_grant_skill_must_be_explicit_boolean():
    with pytest.raises(TypeError):
        build_m17_runner("run", grant_skill="yes")
