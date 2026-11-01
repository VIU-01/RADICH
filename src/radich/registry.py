"""In-memory registry of uniquely identified RADICH nodes (M06)."""

from copy import deepcopy

from .contracts import NodeSpec


class DuplicateNodeError(ValueError):
    """Raised when a node ID is already registered."""


class UnknownNodeError(KeyError):
    """Raised when a requested node ID is absent."""


class NodeRegistry:
    """Register and look up NodeSpec values; no graph or execution logic."""

    def __init__(self) -> None:
        self._nodes: dict[str, NodeSpec] = {}

    def register(self, spec: NodeSpec) -> None:
        if not isinstance(spec, NodeSpec):
            raise TypeError("spec must be NodeSpec")
        if spec.node_id in self._nodes:
            raise DuplicateNodeError(f"node already registered: {spec.node_id}")
        self._nodes[spec.node_id] = deepcopy(spec)

    def get(self, node_id: str) -> NodeSpec:
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        try:
            return deepcopy(self._nodes[node_id])
        except KeyError:
            raise UnknownNodeError(node_id) from None

    def contains(self, node_id: str) -> bool:
        return isinstance(node_id, str) and node_id in self._nodes

    def list_nodes(self) -> tuple[NodeSpec, ...]:
        """Return a stable, sorted snapshot independent of internal storage."""
        return tuple(deepcopy(self._nodes[key]) for key in sorted(self._nodes))

    def __len__(self) -> int:
        return len(self._nodes)
