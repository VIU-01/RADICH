"""M10: configurable retries and local idempotency for RADICH."""
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Callable, Mapping

from .contracts import NodeInput, NodeOutput
from .graph import NodeGraph
from .scheduler import Scheduler, SchedulerResult


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    retry_on_exception: bool = True
    retry_on_failed_output: bool = False

    def __post_init__(self):
        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("max_attempts must be positive integer")
        if type(self.retry_on_exception) is not bool or type(self.retry_on_failed_output) is not bool:
            raise TypeError("retry flags must be bool")


@dataclass(frozen=True)
class AttemptRecord:
    run_id: str
    node_id: str
    attempt: int
    success: bool
    error: str | None


class RetryingScheduler:
    """Wrap M08 handlers with opt-in retry policies; no delays or persistence."""

    def __init__(self, graph: NodeGraph, handlers: Mapping[str, Callable],
                 policies: Mapping[str, RetryPolicy] | None = None):
        if not isinstance(graph, NodeGraph) or not isinstance(handlers, Mapping):
            raise TypeError("invalid graph or handlers")
        self._graph = graph
        self._handlers = dict(handlers)
        self._policies = dict(policies or {})
        if set(self._policies) - set(graph.nodes()):
            raise ValueError("policy for unknown node")
        if any(not isinstance(p, RetryPolicy) for p in self._policies.values()):
            raise TypeError("invalid retry policy")
        self._attempts = ()

    @property
    def attempts(self) -> tuple[AttemptRecord, ...]:
        return self._attempts

    def run(self, run_id: str, initial_payloads: Mapping[str, dict] | None = None) -> SchedulerResult:
        history = []
        self._attempts = ()
        wrapped = {}
        for node_id, handler in self._handlers.items():
            policy = self._policies.get(node_id, RetryPolicy())

            def invoke(inp, *, _handler=handler, _policy=policy):
                for attempt in range(1, _policy.max_attempts + 1):
                    try:
                        output = _handler(deepcopy(inp))
                    except Exception as exc:
                        history.append(AttemptRecord(inp.run_id, inp.node_id, attempt, False,
                                                     f"{type(exc).__name__}: {exc}"))
                        if not _policy.retry_on_exception or attempt == _policy.max_attempts:
                            raise
                        continue
                    if not isinstance(output, NodeOutput) or output.run_id != inp.run_id or output.node_id != inp.node_id:
                        return output  # M08 validates contract errors; never retry them.
                    history.append(AttemptRecord(inp.run_id, inp.node_id, attempt,
                                                 output.success, output.error))
                    if output.success or not _policy.retry_on_failed_output or attempt == _policy.max_attempts:
                        return output
                raise RuntimeError("unreachable")

            wrapped[node_id] = invoke
        try:
            return Scheduler(self._graph, wrapped).run(run_id, initial_payloads)
        finally:
            self._attempts = tuple(history)


class InMemoryIdempotencyStore:
    """Thread-safe in-process cache; not durable across restarts or workers."""

    def __init__(self):
        self._values = {}
        self._lock = RLock()

    def get(self, key: str) -> NodeOutput | None:
        with self._lock:
            return deepcopy(self._values.get(key))

    def put_if_absent(self, key: str, value: NodeOutput) -> NodeOutput:
        if not isinstance(key, str) or not key.strip() or not isinstance(value, NodeOutput):
            raise ValueError("invalid key or output")
        with self._lock:
            if key not in self._values:
                self._values[key] = deepcopy(value)
            return deepcopy(self._values[key])


class IdempotentHandler:
    """Cache successful outputs by explicit key, rejecting cross-run key collisions."""

    def __init__(self, handler: Callable, store: InMemoryIdempotencyStore,
                 key_fn: Callable[[NodeInput], str]):
        if not callable(handler) or not callable(key_fn) or not isinstance(store, InMemoryIdempotencyStore):
            raise TypeError("invalid idempotent handler configuration")
        self._handler, self._store, self._key_fn = handler, store, key_fn

    def __call__(self, inp: NodeInput) -> NodeOutput:
        key = self._key_fn(inp)
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key must be nonempty")
        previous = self._store.get(key)
        if previous is not None:
            if previous.run_id != inp.run_id or previous.node_id != inp.node_id:
                raise ValueError("idempotency key belongs to a different run/node")
            return previous
        output = self._handler(inp)
        if isinstance(output, NodeOutput) and output.success and output.run_id == inp.run_id and output.node_id == inp.node_id:
            return self._store.put_if_absent(key, output)
        return output
