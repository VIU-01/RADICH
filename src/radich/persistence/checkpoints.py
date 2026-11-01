"""M16.2 PostgreSQL checkpoint store.

Requires a psycopg 3 autocommit connection so each checkpoint commits durably.
Only monotonic successful-node progress is accepted.
"""
from __future__ import annotations

import json
from typing import Any

from ..contracts import NodeOutput
from ..recovery import RunCheckpoint

_SCHEMA = """
CREATE TABLE IF NOT EXISTS radich_checkpoints (
    run_id TEXT PRIMARY KEY,
    completed JSONB NOT NULL,
    execution_order JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def _encode(checkpoint: RunCheckpoint) -> tuple[str, str]:
    if not isinstance(checkpoint, RunCheckpoint):
        raise TypeError("checkpoint must be RunCheckpoint")
    if not isinstance(checkpoint.run_id, str) or not checkpoint.run_id.strip():
        raise ValueError("run_id must be nonempty")
    order = checkpoint.execution_order
    if (len(set(order)) != len(order) or set(order) != set(checkpoint.completed)
            or any(not isinstance(node, str) or not node.strip() for node in order)):
        raise ValueError("checkpoint order must contain each completed node exactly once")
    encoded = {}
    for node, output in checkpoint.completed.items():
        if (not isinstance(output, NodeOutput) or not output.success
                or output.run_id != checkpoint.run_id or output.node_id != node):
            raise ValueError("checkpoint must contain matching successful outputs")
        encoded[node] = {"run_id": output.run_id, "node_id": output.node_id,
                         "payload": output.payload, "success": output.success,
                         "error": output.error}
    return json.dumps(encoded, allow_nan=False), json.dumps(list(order))


class PostgresCheckpointStore:
    """Atomic durable checkpoints; caller supplies connection and manages lifecycle.

    This adapter prevents stale checkpoint regression, but does not lock workers
    or ensure exactly-once execution of external side effects.
    """

    def __init__(self, connection: Any):
        if connection is None or not hasattr(connection, "execute") or not hasattr(connection, "transaction"):
            raise TypeError("connection must support execute() and transaction()")
        if getattr(connection, "autocommit", None) is not True:
            raise ValueError("checkpoint connection must use autocommit=True for crash durability")
        self._connection = connection

    def initialize_schema(self) -> None:
        with self._connection.transaction():
            self._connection.execute(_SCHEMA)

    def load(self, run_id: str) -> RunCheckpoint | None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be nonempty")
        row = self._connection.execute(
            "SELECT completed, execution_order FROM radich_checkpoints WHERE run_id = %s",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        raw, order = row
        raw = json.loads(raw) if isinstance(raw, str) else raw
        order = json.loads(order) if isinstance(order, str) else order
        completed = {node: NodeOutput(data["run_id"], data["node_id"],
                                     data["payload"], data["success"], data["error"])
                     for node, data in raw.items()}
        checkpoint = RunCheckpoint(run_id, completed, tuple(order))
        _encode(checkpoint)
        return checkpoint

    def save(self, checkpoint: RunCheckpoint) -> None:
        completed_json, order_json = _encode(checkpoint)
        with self._connection.transaction():
            self._connection.execute(
                "INSERT INTO radich_checkpoints (run_id, completed, execution_order) "
                "VALUES (%s, '{}'::jsonb, '[]'::jsonb) ON CONFLICT (run_id) DO NOTHING",
                (checkpoint.run_id,),
            )
            # Serialize concurrent updates to one run, reject stale or conflicting writes.
            row = self._connection.execute(
                "SELECT completed, execution_order FROM radich_checkpoints "
                "WHERE run_id = %s FOR UPDATE", (checkpoint.run_id,),
            ).fetchone()
            previous_raw, previous_order = row
            previous = json.loads(previous_raw) if isinstance(previous_raw, str) else previous_raw
            old_order = json.loads(previous_order) if isinstance(previous_order, str) else previous_order
            proposed = json.loads(completed_json)
            if (list(checkpoint.execution_order[:len(old_order)]) != old_order
                    or any(proposed.get(node) != data for node, data in previous.items())):
                raise ValueError("checkpoint regression or conflicting completed node")
            self._connection.execute(
                "UPDATE radich_checkpoints SET completed = %s::jsonb, "
                "execution_order = %s::jsonb, updated_at = now() WHERE run_id = %s",
                (completed_json, order_json, checkpoint.run_id),
            )
