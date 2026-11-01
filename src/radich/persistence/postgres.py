"""Transactional PostgreSQL snapshots of SchedulerResult (M09)."""

from __future__ import annotations

import json
from typing import Any

from ..contracts import NodeOutput, RunState
from ..scheduler import SchedulerResult

_STATES = ", ".join(f"'{state.value}'" for state in RunState)
_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS radich_runs (
        run_id TEXT PRIMARY KEY,
        state TEXT NOT NULL CHECK (state IN (""" + _STATES + """)),
        execution_order JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS radich_node_runs (
        run_id TEXT NOT NULL REFERENCES radich_runs(run_id) ON DELETE CASCADE,
        node_id TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN (""" + _STATES + """)),
        output JSONB,
        PRIMARY KEY (run_id, node_id)
    )""",
)


class DuplicateRunError(ValueError):
    """A run ID is already present in the database."""


def _validate(result: SchedulerResult) -> tuple[dict[str, Any], dict[str, dict[str, Any] | None]]:
    if not isinstance(result, SchedulerResult):
        raise TypeError("result must be SchedulerResult")
    if not isinstance(result.run_id, str) or not result.run_id.strip():
        raise ValueError("run_id must be a nonempty string")
    if not isinstance(result.state, RunState):
        raise TypeError("state must be RunState")
    if any(not isinstance(node_id, str) or not node_id.strip() or not isinstance(state, RunState)
           for node_id, state in result.node_states.items()):
        raise ValueError("invalid node state")
    if len(set(result.execution_order)) != len(result.execution_order):
        raise ValueError("execution_order contains duplicates")
    if not set(result.execution_order) <= set(result.node_states):
        raise ValueError("execution_order contains unknown nodes")
    if not set(result.outputs) <= set(result.node_states):
        raise ValueError("outputs contain unknown nodes")
    records: dict[str, dict[str, Any] | None] = {}
    for node_id, output in result.outputs.items():
        if not isinstance(output, NodeOutput):
            raise TypeError("output must be NodeOutput")
        if output.run_id != result.run_id or output.node_id != node_id:
            raise ValueError("output identifiers do not match")
        if result.node_states[node_id] != (RunState.COMPLETED if output.success else RunState.FAILED):
            raise ValueError("output success conflicts with node state")
        records[node_id] = {
            "run_id": output.run_id, "node_id": output.node_id,
            "payload": output.payload, "success": output.success, "error": output.error,
        }
    for node_id, state in result.node_states.items():
        if state in (RunState.COMPLETED, RunState.FAILED) and node_id not in records:
            raise ValueError("terminal executed node is missing output")
        if state == RunState.CANCELLED and node_id in records:
            raise ValueError("cancelled node cannot have an output")
        records.setdefault(node_id, None)
    # Validate JSON before opening the database transaction.
    json.dumps(list(result.execution_order), allow_nan=False)
    for record in records.values():
        if record is not None:
            json.dumps(record, allow_nan=False)
    return {"run_id": result.run_id, "state": result.state.value,
            "execution_order": list(result.execution_order)}, records


class PostgresRunRepository:
    """Store immutable run snapshots using an injected psycopg 3 connection."""

    def __init__(self, connection: Any) -> None:
        if connection is None or not hasattr(connection, "execute") or not hasattr(connection, "transaction"):
            raise TypeError("connection must support execute() and transaction()")
        self._connection = connection

    def initialize_schema(self) -> None:
        with self._connection.transaction():
            for statement in _SCHEMA:
                self._connection.execute(statement)

    def save_result(self, result: SchedulerResult) -> None:
        header, records = _validate(result)
        # One transaction: either the run and every node are stored, or none.
        with self._connection.transaction():
            exists = self._connection.execute(
                "SELECT 1 FROM radich_runs WHERE run_id = %s", (header["run_id"],)
            ).fetchone()
            if exists is not None:
                raise DuplicateRunError(header["run_id"])
            self._connection.execute(
                "INSERT INTO radich_runs (run_id, state, execution_order) VALUES (%s, %s, %s::jsonb)",
                (header["run_id"], header["state"], json.dumps(header["execution_order"])),
            )
            for node_id, state in result.node_states.items():
                record = records[node_id]
                self._connection.execute(
                    "INSERT INTO radich_node_runs (run_id, node_id, state, output) "
                    "VALUES (%s, %s, %s, %s::jsonb)",
                    (header["run_id"], node_id, state.value,
                     json.dumps(record, allow_nan=False) if record is not None else None),
                )

    def get_run(self, run_id: str) -> SchedulerResult | None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a nonempty string")
        row = self._connection.execute(
            "SELECT run_id, state, execution_order FROM radich_runs WHERE run_id = %s",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        node_rows = self._connection.execute(
            "SELECT node_id, state, output FROM radich_node_runs WHERE run_id = %s ORDER BY node_id",
            (run_id,),
        ).fetchall()
        node_states: dict[str, RunState] = {}
        outputs: dict[str, NodeOutput] = {}
        for node_id, state, raw in node_rows:
            node_states[node_id] = RunState(state)
            if raw is not None:
                data = json.loads(raw) if isinstance(raw, str) else raw
                outputs[node_id] = NodeOutput(
                    data["run_id"], data["node_id"], data["payload"],
                    data["success"], data["error"],
                )
        order = json.loads(row[2]) if isinstance(row[2], str) else row[2]
        return SchedulerResult(row[0], RunState(row[1]), node_states, outputs, tuple(order))
