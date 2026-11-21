"""Offline, side-effect-free skill handler for the first RADICH agent (M17).

The handler is deliberately not an autonomous agent. Call it through M11's
AuthorizedHandler; the demo builder wires that guard fail-closed.
"""

from ..contracts import NodeInput, NodeOutput
from .contracts import AgentSpec, SkillSpec


class SimulatedTextAgent:
    """Execute exactly one allowlisted text-normalization skill.

    Inputs are taken only from the predecessor's scheduler-generated payload,
    never from a requested skill name or arbitrary user-supplied tool call.
    """

    def __init__(
        self, agent: AgentSpec, skill: SkillSpec, *, node_id: str,
        predecessor_id: str = "extract",
    ) -> None:
        if not isinstance(agent, AgentSpec) or not isinstance(skill, SkillSpec):
            raise TypeError("agent and skill must use their declared contracts")
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id must be a nonempty string")
        if not isinstance(predecessor_id, str) or not predecessor_id.strip():
            raise ValueError("predecessor_id must be a nonempty string")
        if node_id == predecessor_id:
            raise ValueError("agent node cannot depend on itself")
        if skill.skill_id not in agent.skill_ids:
            raise ValueError("skill is not allowlisted for this agent")
        if skill.skill_id != "text.normalize":
            raise ValueError("only the offline text.normalize skill is implemented")
        self.agent = agent
        self.skill = skill
        self.node_id = node_id
        self.predecessor_id = predecessor_id

    def __call__(self, inp: NodeInput) -> NodeOutput:
        if not isinstance(inp, NodeInput):
            raise TypeError("input must be NodeInput")
        if inp.node_id != self.node_id:
            return NodeOutput(inp.run_id, inp.node_id, {}, False, "DENY: wrong agent node")
        if set(inp.payload) != {"dependencies"}:
            return NodeOutput(inp.run_id, inp.node_id, {}, False, "invalid agent input fields")
        dependencies = inp.payload["dependencies"]
        if not isinstance(dependencies, dict):
            return NodeOutput(inp.run_id, inp.node_id, {}, False, "invalid dependencies")
        upstream = dependencies.get(self.predecessor_id)
        if not isinstance(upstream, dict):
            return NodeOutput(inp.run_id, inp.node_id, {}, False, "missing predecessor output")
        text = upstream.get("text")
        if not isinstance(text, str) or not text.strip():
            return NodeOutput(inp.run_id, inp.node_id, {}, False, "missing text")
        # This capability does not perform networking, file I/O or LLM calls.
        normalized = " ".join(text.split())
        return NodeOutput(
            inp.run_id, inp.node_id,
            {
                "agent_id": self.agent.agent_id,
                "agent_version": self.agent.version,
                "skill_id": self.skill.skill_id,
                "skill_version": self.skill.version,
                "normalized_text": normalized,
            },
            True,
        )
