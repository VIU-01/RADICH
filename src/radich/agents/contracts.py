"""Minimal, explicit contracts for an agent and its allowed skills (M17)."""

from dataclasses import dataclass


def _required_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class SkillSpec:
    """A named, versioned capability requiring an explicit permission."""

    skill_id: str
    version: str
    required_permission: str

    def __post_init__(self) -> None:
        for name in ("skill_id", "version", "required_permission"):
            _required_text(getattr(self, name), name)


@dataclass(frozen=True)
class AgentSpec:
    """A versioned agent restricted to an explicit allowlist of skills."""

    agent_id: str
    version: str
    skill_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _required_text(self.agent_id, "agent_id")
        _required_text(self.version, "version")
        if not isinstance(self.skill_ids, tuple):
            raise TypeError("skill_ids must be a tuple")
        if not self.skill_ids:
            raise ValueError("agent must declare at least one skill")
        for skill_id in self.skill_ids:
            _required_text(skill_id, "skill_id")
        if len(set(self.skill_ids)) != len(self.skill_ids):
            raise ValueError("duplicate agent skill IDs")
