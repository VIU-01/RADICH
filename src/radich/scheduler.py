"""Synchronous dependency-aware scheduler for RADICH (M08)."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Mapping

from .contracts import NodeInput, NodeOutput, RunState
from .graph import NodeGraph

NodeHandler = Callable[[NodeInput], NodeOutput]


@dataclass(frozen=True)
class SchedulerResult:
    run_id: str
    state: RunState
    node_states: dict[str, RunState]
    outputs: dict[str, NodeOutput]
    execution_order: tuple[str, ...]


class Scheduler:
    """Execute a DAG once, sequentially; no persistence or retry policy."""

    def __init__(self, graph: NodeGraph, handlers: Mapping[str, NodeHandler]) -> None:
        if not isinstance(graph, NodeGraph):
            raise TypeError("graph must be NodeGraph")
        if not isinstance(handlers, Mapping):
            raise TypeError("handlers must be a mapping")
        if any(not isinstance(key, str) or not callable(handler)
               for key, handler in handlers.items()):
            raise TypeError("handlers must map node IDs to callables")
        self._graph = graph
        self._handlers = dict(handlers)

    def run(
        self,
        run_id: str,
        initial_payloads: Mapping[str, dict] | None = None,
    ) -> SchedulerResult:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        payloads = {} if initial_payloads is None else initial_payloads
        if not isinstance(payloads, Mapping):
            raise TypeError("initial_payloads must be a mapping")
        order = self._graph.topological_order()
        unknown = set(payloads) - set(order)
        if unknown:
            raise ValueError(f"payload for unknown graph node: {sorted(unknown)!r}")
        for node_id, payload in payloads.items():
            if not isinstance(payload, dict):
                raise TypeError(f"payload for {node_id} must be a dict")
            if "dependencies" in payload:
                raise ValueError("dependencies is a reserved payload key")
        missing = set(order) - set(self._handlers)
        if missing:
            raise ValueError(f"missing handlers: {sorted(missing)!r}")

        node_states = {node_id: RunState.CREATED for node_id in order}
        outputs: dict[str, NodeOutput] = {}
        executed: list[str] = []

        for node_id in order:
            predecessors = self._graph.predecessors(node_id)
            if any(node_states[parent] != RunState.COMPLETED
                   for parent in predecessors):
                node_states[node_id] = RunState.CANCELLED
                continue
            node_states[node_id] = RunState.READY
            dependency_payloads = {
                parent: deepcopy(outputs[parent].payload) for parent in predecessors
            }
            payload = deepcopy(payloads.get(node_id, {}))
            payload["dependencies"] = dependency_payloads
            node_input = NodeInput(run_id, node_id, payload)
            node_states[node_id] = RunState.RUNNING
            executed.append(node_id)
            try:
                output = self._handlers[node_id](node_input)
                if not isinstance(output, NodeOutput):
                    raise TypeError("handler must return NodeOutput")
                if output.run_id != run_id or output.node_id != node_id:
                    raise ValueError("handler output IDs must match the input")
                output = deepcopy(output)
            except Exception as exc:
                output = NodeOutput(
                    run_id, node_id, {}, False,
                    f"{type(exc).__name__}: {exc}",
                )
            outputs[node_id] = output
            node_states[node_id] = (
                RunState.COMPLETED if output.success else RunState.FAILED
            )

        state = (
            RunState.FAILED if RunState.FAILED in node_states.values()
            else RunState.CANCELLED if RunState.CANCELLED in node_states.values()
            else RunState.COMPLETED
        )
        return SchedulerResult(run_id, state, node_states, outputs, tuple(executed))
