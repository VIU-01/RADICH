"""M11: explicit, fail-closed authorization policies for RADICH nodes."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .contracts import NodeInput, NodeOutput


def _nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


@dataclass(frozen=True)
class ExecutionContext:
    run_id: str
    actor: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    approvals: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        _nonempty(self.run_id, "run_id")
        _nonempty(self.actor, "actor")
        for name in ("permissions", "approvals"):
            value = getattr(self, name)
            if not isinstance(value, frozenset):
                raise TypeError(f"{name} must be frozenset")
            for item in value:
                _nonempty(item, name)


@dataclass(frozen=True)
class NodePolicy:
    required_permission: str | None = None
    requires_approval: bool = False
    denied: bool = False

    def __post_init__(self) -> None:
        if self.required_permission is not None:
            _nonempty(self.required_permission, "required_permission")
        if type(self.requires_approval) is not bool or type(self.denied) is not bool:
            raise TypeError("policy flags must be bool")


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


@dataclass(frozen=True)
class PolicyDecision:
    decision: Decision
    reason: str


class PolicyEngine:
    """Pure evaluation: explicit denial wins, then permissions, then approval."""

    def evaluate(self, context: ExecutionContext, node_id: str,
                 policy: NodePolicy) -> PolicyDecision:
        if not isinstance(context, ExecutionContext):
            raise TypeError("context must be ExecutionContext")
        _nonempty(node_id, "node_id")
        if not isinstance(policy, NodePolicy):
            raise TypeError("policy must be NodePolicy")
        if policy.denied:
            return PolicyDecision(Decision.DENY, "node explicitly denied")
        if (policy.required_permission is not None
                and policy.required_permission not in context.permissions):
            return PolicyDecision(Decision.DENY, "required permission missing")
        if policy.requires_approval and node_id not in context.approvals:
            return PolicyDecision(Decision.APPROVAL_REQUIRED, "node approval missing")
        return PolicyDecision(Decision.ALLOW, "authorized")


class AuthorizedHandler:
    """Guard a node handler without executing it on failed authorization.

    Denial becomes a failed NodeOutput because M08 has no pause/resume support.
    """

    def __init__(self, handler: Callable[[NodeInput], NodeOutput],
                 engine: PolicyEngine, context: ExecutionContext,
                 policy: NodePolicy):
        if not callable(handler) or not isinstance(engine, PolicyEngine):
            raise TypeError("invalid handler or engine")
        if not isinstance(context, ExecutionContext) or not isinstance(policy, NodePolicy):
            raise TypeError("invalid context or policy")
        self._handler = handler
        self._engine = engine
        self._context = context
        self._policy = policy

    def __call__(self, inp: NodeInput) -> NodeOutput:
        if not isinstance(inp, NodeInput):
            raise TypeError("input must be NodeInput")
        if inp.run_id != self._context.run_id:
            return NodeOutput(inp.run_id, inp.node_id, {}, False,
                              "DENY: execution context run_id mismatch")
        decision = self._engine.evaluate(self._context, inp.node_id, self._policy)
        if decision.decision != Decision.ALLOW:
            return NodeOutput(inp.run_id, inp.node_id, {}, False,
                              f"{decision.decision.value}: {decision.reason}")
        return self._handler(inp)
