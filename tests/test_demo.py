"""M13 offline demonstration tests."""
from radich.contracts import RunState
from radich.demo import build_demo_graph, build_demo_runner


def test_demo_graph_is_dag():
    graph = build_demo_graph()
    assert graph.topological_order() == ("extract", "validate", "summarize")


def test_demo_success():
    result = build_demo_runner("demo-1").run(
        "demo-1", {"extract": {"text": "RADICH is a native Python graph"}})
    assert result.state == RunState.COMPLETED
    assert result.outputs["summarize"].payload == {
        "summary": "RADICH is a native Python graph", "word_count": 6}
    assert result.execution_order == ("extract", "validate", "summarize")


def test_demo_missing_input_cancels_downstream():
    result = build_demo_runner("demo-2").run("demo-2")
    assert result.state == RunState.FAILED
    assert result.node_states["validate"] == RunState.CANCELLED
    assert result.node_states["summarize"] == RunState.CANCELLED


def test_demo_approval_denied():
    result = build_demo_runner("demo-3", approved=False).run(
        "demo-3", {"extract": {"text": "a b c"}})
    assert result.state == RunState.FAILED
    assert "APPROVAL_REQUIRED" in result.outputs["summarize"].error


def test_demo_run_context_mismatch():
    result = build_demo_runner("demo-4").run(
        "other", {"extract": {"text": "a b"}})
    assert result.state == RunState.FAILED
    assert "mismatch" in result.outputs["extract"].error


def test_demo_deterministic():
    first = build_demo_runner("same").run("same", {"extract": {"text": "a b c"}})
    second = build_demo_runner("same").run("same", {"extract": {"text": "a b c"}})
    assert first == second
