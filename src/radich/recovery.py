"""M16.1: durable-checkpoint contract and safe sequential DAG resumption.

A checkpoint must be persisted by the caller after each completed node.
This module does not promise exactly-once external side effects.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable, Mapping, Protocol

from .contracts import NodeInput, NodeOutput, RunState
from .graph import NodeGraph
from .scheduler import SchedulerResult


@dataclass(frozen=True)
class RunCheckpoint:
    run_id: str
    completed: dict[str, NodeOutput] = field(default_factory=dict)
    execution_order: tuple[str, ...] = ()


class CheckpointStore(Protocol):
    def load(self, run_id: str) -> RunCheckpoint | None: ...
    def save(self, checkpoint: RunCheckpoint) -> None: ...


class MemoryCheckpointStore:
    """Test adapter. Restart recovery needs a persistent implementation."""
    def __init__(self):
        self._checkpoints: dict[str, RunCheckpoint] = {}

    def load(self, run_id: str) -> RunCheckpoint | None:
        return deepcopy(self._checkpoints.get(run_id))

    def save(self, checkpoint: RunCheckpoint) -> None:
        self._checkpoints[checkpoint.run_id] = deepcopy(checkpoint)


class RecoverableScheduler:
    """Resume a sequential DAG using previously committed successful outputs.

    Only completed nodes are skipped. A failed/interrupted node is retried.
    A store must atomically persist checkpoints for process-crash recovery.
    """
    def __init__(
        self, graph: NodeGraph, handlers: Mapping[str, Callable[[NodeInput], NodeOutput]],
        store: CheckpointStore,
    ):
        if not isinstance(graph, NodeGraph):
            raise TypeError("graph must be NodeGraph")
        self.graph = graph
        self.handlers = dict(handlers)
        self.store = store

    def run(self, run_id: str, initial_payloads: Mapping[str, dict] | None = None) -> SchedulerResult:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be nonempty")
        order = self.graph.topological_order()
        payloads = {} if initial_payloads is None else initial_payloads
        if not isinstance(payloads, Mapping) or set(payloads) - set(order):
            raise ValueError("invalid initial payloads")
        if set(order) - set(self.handlers):
            raise ValueError("missing handlers")
        for payload in payloads.values():
            if not isinstance(payload, dict) or "dependencies" in payload:
                raise ValueError("invalid node payload")

        checkpoint = self.store.load(run_id) or RunCheckpoint(run_id)
        if checkpoint.run_id != run_id:
            raise ValueError("checkpoint run_id mismatch")
        completed = deepcopy(checkpoint.completed)
        executed = list(checkpoint.execution_order)
        if len(set(executed)) != len(executed) or set(executed) != set(completed):
            raise ValueError("inconsistent checkpoint execution order")
        if not set(completed) <= set(order):
            raise ValueError("checkpoint contains unknown nodes")
        for node_id, output in completed.items():
            if (not isinstance(output, NodeOutput) or not output.success
                    or output.run_id != run_id or output.node_id != node_id
                    or not set(self.graph.predecessors(node_id)) <= set(completed)):
                raise ValueError("invalid checkpoint output or dependency")
        states = {node_id: RunState.CREATED for node_id in order}
        for node_id in completed:
            states[node_id] = RunState.COMPLETED
        outputs = deepcopy(completed)
        for node_id in order:
            if node_id in completed:
                continue
            predecessors = self.graph.predecessors(node_id)
            if any(states[parent] != RunState.COMPLETED for parent in predecessors):
                states[node_id] = RunState.CANCELLED
                continue
            payload = deepcopy(payloads.get(node_id, {}))
            payload["dependencies"] = {
                parent: deepcopy(outputs[parent].payload) for parent in predecessors
            }
            executed.append(node_id)
            try:
                output = self.handlers[node_id](NodeInput(run_id, node_id, payload))
                if (not isinstance(output, NodeOutput) or output.run_id != run_id
                        or output.node_id != node_id):
                    raise ValueError("invalid handler output")
                output = deepcopy(output)
            except Exception as exc:
                output = NodeOutput(run_id, node_id, {}, False, f"{type(exc).__name__}: {exc}")
            outputs[node_id] = output
            states[node_id] = RunState.COMPLETED if output.success else RunState.FAILED
            if output.success:
                completed[node_id] = deepcopy(output)
                self.store.save(RunCheckpoint(run_id, deepcopy(completed), tuple(
                    node for node in executed if node in completed
                )))
        state = (RunState.FAILED if RunState.FAILED in states.values()
                 else RunState.CANCELLED if RunState.CANCELLED in states.values()
                 else RunState.COMPLETED)
        return SchedulerResult(run_id, state, states, outputs, tuple(executed))
