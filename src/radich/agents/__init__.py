"""M17: explicitly permissioned, simulated agent and skill integration."""

from .contracts import AgentSpec, SkillSpec
from .demo import AGENT_NODE, SKILL_PERMISSION, build_m17_runner
from .simulated import SimulatedTextAgent

__all__ = [
    "AgentSpec", "SkillSpec", "SimulatedTextAgent",
    "AGENT_NODE", "SKILL_PERMISSION", "build_m17_runner",
]
