"""Deterministic directed acyclic graph for RADICH Core (M07)."""

from heapq import heappop, heappush

from ..contracts import EdgeSpec
from ..registry import NodeRegistry, UnknownNodeError


class DuplicateEdgeError(ValueError):
    """An edge already exists in the graph."""


class CycleError(ValueError):
    """An edge would create a directed cycle."""


class NodeGraph:
    """DAG of registered node IDs; does not execute any nodes."""

    def __init__(self, registry: NodeRegistry) -> None:
        if not isinstance(registry, NodeRegistry):
            raise TypeError("registry must be NodeRegistry")
        self._registry = registry
        self._adjacency: dict[str, set[str]] = {}

    def add_node(self, node_id: str) -> None:
        # Registry validates IDs and raises UnknownNodeError for missing nodes.
        self._registry.get(node_id)
        self._adjacency.setdefault(node_id, set())

    def add_edge(self, edge: EdgeSpec) -> None:
        if not isinstance(edge, EdgeSpec):
            raise TypeError("edge must be EdgeSpec")
        source, target = edge.source_id, edge.target_id
        if source not in self._adjacency or target not in self._adjacency:
            missing = source if source not in self._adjacency else target
            raise UnknownNodeError(missing)
        if target in self._adjacency[source]:
            raise DuplicateEdgeError(f"edge already exists: {source} -> {target}")
        if self._reachable(target, source):
            raise CycleError(f"edge creates a cycle: {source} -> {target}")
        self._adjacency[source].add(target)

    def _reachable(self, start: str, goal: str) -> bool:
        pending = [start]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current == goal:
                return True
            if current not in seen:
                seen.add(current)
                pending.extend(self._adjacency[current] - seen)
        return False

    def nodes(self) -> tuple[str, ...]:
        return tuple(sorted(self._adjacency))

    def edges(self) -> tuple[EdgeSpec, ...]:
        return tuple(
            EdgeSpec(source, target)
            for source in sorted(self._adjacency)
            for target in sorted(self._adjacency[source])
        )

    def successors(self, node_id: str) -> tuple[str, ...]:
        if node_id not in self._adjacency:
            raise UnknownNodeError(node_id)
        return tuple(sorted(self._adjacency[node_id]))

    def predecessors(self, node_id: str) -> tuple[str, ...]:
        if node_id not in self._adjacency:
            raise UnknownNodeError(node_id)
        return tuple(sorted(source for source, targets in self._adjacency.items()
                            if node_id in targets))

    def topological_order(self) -> tuple[str, ...]:
        """Kahn's algorithm with lexical tie-breaking."""
        indegree = {node_id: 0 for node_id in self._adjacency}
        for targets in self._adjacency.values():
            for target in targets:
                indegree[target] += 1
        ready: list[str] = []
        for node_id, count in indegree.items():
            if count == 0:
                heappush(ready, node_id)
        result: list[str] = []
        while ready:
            node_id = heappop(ready)
            result.append(node_id)
            for target in self._adjacency[node_id]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    heappush(ready, target)
        if len(result) != len(indegree):
            raise CycleError("graph contains a cycle")
        return tuple(result)
