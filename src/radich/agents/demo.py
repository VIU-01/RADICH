"""M17 controlled demonstration: one agent skill connected to the existing Core.

The two-node DAG is extract -> agent_a01. No external integrations, DB, API
changes, autonomous planning, or user-controlled skill selection are involved.
"""

from ..contracts import EdgeSpec, NodeSpec
from ..demo import demo_handlers
from ..graph import NodeGraph
from ..policy import AuthorizedHandler, ExecutionContext, NodePolicy, PolicyEngine
from ..registry import NodeRegistry
from ..scheduler import Scheduler
from .contracts import AgentSpec, SkillSpec
from .simulated import SimulatedTextAgent

AGENT_NODE = "agent_a01"
SKILL_PERMISSION = "skills.text.normalize"


def build_m17_components(
    run_id: str, *, grant_skill: bool = True
) -> tuple[NodeGraph, dict]:
    """Provide graph and permission-guarded handlers for a single run."""
    if type(grant_skill) is not bool:
        raise TypeError("grant_skill must be bool")

    skill = SkillSpec("text.normalize", "1.0", SKILL_PERMISSION)
    agent = AgentSpec("A01", "0.1", (skill.skill_id,))

    registry = NodeRegistry()
    graph = NodeGraph(registry)
    registry.register(NodeSpec("extract", "demo.extract", "1.0"))
    registry.register(NodeSpec(
        AGENT_NODE, "agent.skill", "1.0",
        config={"agent_id": agent.agent_id, "skill_id": skill.skill_id},
    ))
    graph.add_node("extract")
    graph.add_node(AGENT_NODE)
    graph.add_edge(EdgeSpec("extract", AGENT_NODE))

    context = ExecutionContext(
        run_id=run_id,
        actor="m17-demo",
        permissions=frozenset({skill.required_permission}) if grant_skill else frozenset(),
    )
    agent_handler = AuthorizedHandler(
        SimulatedTextAgent(agent, skill, node_id=AGENT_NODE),
        PolicyEngine(), context, NodePolicy(required_permission=skill.required_permission),
    )
    return graph, {"extract": demo_handlers()["extract"], AGENT_NODE: agent_handler}


def build_m17_runner(run_id: str, *, grant_skill: bool = True) -> Scheduler:
    """Backward-compatible M17 runner; M17.5 uses the same guarded components."""
    graph, handlers = build_m17_components(run_id, grant_skill=grant_skill)
    return Scheduler(graph, handlers)
