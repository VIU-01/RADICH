"""Minimal validated data contracts for RADICH Core (M05.2)."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def _nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _payload(value: dict[str, Any], name: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be a dict")


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    capability: str
    version: str
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("node_id", "capability", "version"):
            _nonempty(getattr(self, name), name)
        _payload(self.config, "config")


@dataclass(frozen=True)
class EdgeSpec:
    source_id: str
    target_id: str

    def __post_init__(self) -> None:
        _nonempty(self.source_id, "source_id")
        _nonempty(self.target_id, "target_id")
        if self.source_id == self.target_id:
            raise ValueError("self-loops are not permitted")


@dataclass(frozen=True)
class NodeInput:
    run_id: str
    node_id: str
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        _nonempty(self.run_id, "run_id")
        _nonempty(self.node_id, "node_id")
        _payload(self.payload, "payload")


@dataclass(frozen=True)
class NodeOutput:
    run_id: str
    node_id: str
    payload: dict[str, Any]
    success: bool
    error: str | None = None

    def __post_init__(self) -> None:
        _nonempty(self.run_id, "run_id")
        _nonempty(self.node_id, "node_id")
        _payload(self.payload, "payload")
        if not isinstance(self.success, bool):
            raise TypeError("success must be bool")
        if self.success and self.error is not None:
            raise ValueError("successful output cannot contain an error")
        if not self.success:
            _nonempty(self.error, "error")


class RunState(str, Enum):
    CREATED = "CREATED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
