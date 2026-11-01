"""M13: deterministic, offline three-node demonstration workflow.

No external AI model is called: handlers are deliberately local and testable.
"""
from __future__ import annotations

from .contracts import EdgeSpec, NodeInput, NodeOutput, NodeSpec
from .graph import NodeGraph
from .policy import AuthorizedHandler, ExecutionContext, NodePolicy, PolicyEngine
from .registry import NodeRegistry
from .retry import RetryPolicy, RetryingScheduler


def build_demo_graph() -> NodeGraph:
    registry = NodeRegistry()
    graph = NodeGraph(registry)
    for node_id in ("extract", "validate", "summarize"):
        registry.register(NodeSpec(node_id, "demo." + node_id, "1.0"))
        graph.add_node(node_id)
    graph.add_edge(EdgeSpec("extract", "validate"))
    graph.add_edge(EdgeSpec("validate", "summarize"))
    return graph


def demo_handlers():
    def extract(inp: NodeInput) -> NodeOutput:
        text = inp.payload.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return NodeOutput(inp.run_id, inp.node_id, {}, False, "text is required")
        return NodeOutput(inp.run_id, inp.node_id, {"text": text.strip()}, True)

    def validate(inp: NodeInput) -> NodeOutput:
        text = inp.payload["dependencies"]["extract"]["text"]
        return NodeOutput(inp.run_id, inp.node_id,
                          {"text": text, "word_count": len(text.split())}, True)

    def summarize(inp: NodeInput) -> NodeOutput:
        data = inp.payload["dependencies"]["validate"]
        return NodeOutput(inp.run_id, inp.node_id,
                          {"summary": " ".join(data["text"].split()[:10]),
                           "word_count": data["word_count"]}, True)

    return {"extract": extract, "validate": validate, "summarize": summarize}


def build_demo_runner(run_id: str, *, approved: bool = True) -> RetryingScheduler:
    """Return a new scheduler per run; authorization is tied to its run ID."""
    context = ExecutionContext(
        run_id, "demo-user", permissions=frozenset({"demo.execute"}),
        approvals=frozenset({"summarize"}) if approved else frozenset(),
    )
    engine = PolicyEngine()
    handlers = {
        node_id: AuthorizedHandler(
            handler, engine, context,
            NodePolicy(required_permission="demo.execute",
                       requires_approval=(node_id == "summarize")),
        )
        for node_id, handler in demo_handlers().items()
    }
    return RetryingScheduler(build_demo_graph(), handlers,
                             {"extract": RetryPolicy(max_attempts=2)})
