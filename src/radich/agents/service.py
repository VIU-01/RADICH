"""M17.5 opt-in API -> guarded agent -> PostgreSQL -> checkpoint recovery.

This does not replace the existing M15 deployment factory. There are no external
agent tools, network calls, LLMs or exactly-once external side-effect guarantees.
PostgreSQL advisory locks serialize executions of the same run_id.
"""
from __future__ import annotations

import json
from typing import Any

import psycopg

from ..api import create_app
from ..persistence.checkpoints import PostgresCheckpointStore
from ..persistence.postgres import DuplicateRunError, PostgresRunRepository
from ..recovery import RecoverableScheduler
from .demo import build_m17_components

_REQUEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS radich_m17_requests (
    run_id TEXT PRIMARY KEY,
    initial_payloads JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def _validate_payloads(value: Any) -> dict[str, dict[str, str]]:
    """Only the extract node can receive text; agent skill selection is server-side."""
    if not isinstance(value, dict) or set(value) != {"extract"}:
        raise ValueError("M17.5 only accepts an extract payload")
    extract = value["extract"]
    if not isinstance(extract, dict) or set(extract) != {"text"}:
        raise ValueError("extract only accepts text")
    text = extract["text"]
    if not isinstance(text, str) or not text.strip() or len(text) > 10_000:
        raise ValueError("text must be nonempty and at most 10000 characters")
    return {"extract": {"text": text}}


class M17AgentRepository:
    """The API's read adapter; connections are per operation and not shared."""

    def __init__(self, dsn: str):
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("PostgreSQL DSN is required")
        self.dsn = dsn

    def initialize_schema(self) -> None:
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            PostgresRunRepository(conn).initialize_schema()
            PostgresCheckpointStore(conn).initialize_schema()
            with conn.transaction():
                conn.execute(_REQUEST_SCHEMA)

    def get_run(self, run_id: str):
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            return PostgresRunRepository(conn).get_run(run_id)

    def get_progress(self, run_id: str) -> dict[str, Any] | None:
        """Single-snapshot metadata read; never return inputs or output payloads.

        Phase is an observation, not proof that a worker has stopped.
        """
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be nonempty")
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            # One SELECT gives the request, checkpoint and terminal snapshot
            # a consistent database view even during a concurrent resume.
            row = conn.execute(
                "SELECT r.run_id, c.execution_order, f.state, f.execution_order "
                "FROM radich_m17_requests AS r "
                "LEFT JOIN radich_checkpoints AS c ON c.run_id = r.run_id "
                "LEFT JOIN radich_runs AS f ON f.run_id = r.run_id "
                "WHERE r.run_id = %s",
                (run_id,),
            ).fetchone()
        if row is None:
            return None

        checkpoint_order = (
            json.loads(row[1]) if isinstance(row[1], str) else (row[1] or [])
        )
        final_order = (
            json.loads(row[3]) if isinstance(row[3], str) else (row[3] or [])
        )
        terminal_state = row[2]
        if terminal_state is not None:
            phase = "FINALIZED"
            order = final_order
        else:
            phase = "CHECKPOINTED" if checkpoint_order else "REGISTERED"
            order = checkpoint_order
        return {
            "run_id": row[0],
            "phase": phase,
            "terminal_state": terminal_state,
            "completed_nodes": list(checkpoint_order),
            "execution_order": list(order),
        }


class M17AgentRunner:
    """Recoverable opt-in executor; authorization never comes from HTTP payloads."""

    def __init__(self, repository: M17AgentRepository, *, grant_skill: bool = False):
        if not isinstance(repository, M17AgentRepository):
            raise TypeError("repository must be M17AgentRepository")
        if type(grant_skill) is not bool:
            raise TypeError("grant_skill must be an explicit boolean")
        self.repository = repository
        self.grant_skill = grant_skill

    def run(self, run_id: str, initial_payloads: Any):
        return self._execute(run_id, initial_payloads, create=True)

    def resume(self, run_id: str):
        """Resume using the original persisted input, never a replacement request."""
        return self._execute(run_id, None, create=False)

    def _execute(self, run_id: str, requested_payloads: Any, *, create: bool):
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be nonempty")
        payloads = _validate_payloads(requested_payloads) if create else None

        with psycopg.connect(self.repository.dsn, autocommit=True) as conn:
            # A session lock prevents two workers from running the same ID.
            # It is released automatically on disconnect, including a crash.
            lock_sql = "hashtextextended(%s::text, 0)"
            acquired = conn.execute(
                f"SELECT pg_try_advisory_lock({lock_sql})", (run_id,)
            ).fetchone()[0]
            if not acquired:
                raise DuplicateRunError("run is already executing")

            try:
                stored = PostgresRunRepository(conn).get_run(run_id)
                if create:
                    if stored is not None:
                        raise DuplicateRunError("run already exists")
                    try:
                        with conn.transaction():
                            conn.execute(
                                "INSERT INTO radich_m17_requests (run_id, initial_payloads) "
                                "VALUES (%s, %s::jsonb)",
                                (run_id, json.dumps(payloads)),
                            )
                    except psycopg.errors.UniqueViolation:
                        raise DuplicateRunError("run already exists") from None
                else:
                    row = conn.execute(
                        "SELECT initial_payloads FROM radich_m17_requests WHERE run_id = %s",
                        (run_id,),
                    ).fetchone()
                    if row is None:
                        raise KeyError(run_id)
                    payloads = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    payloads = _validate_payloads(payloads)
                    # A completed or failed snapshot is immutable and is not executed again.
                    if stored is not None:
                        return stored

                graph, handlers = build_m17_components(
                    run_id, grant_skill=self.grant_skill
                )
                result = RecoverableScheduler(
                    graph, handlers, PostgresCheckpointStore(conn)
                ).run(run_id, payloads)
                PostgresRunRepository(conn).save_result(result)
                return result
            finally:
                conn.execute(f"SELECT pg_advisory_unlock({lock_sql})", (run_id,))


def build_m17_app(*, dsn: str, api_key: str, grant_skill: bool = False):
    """Explicit opt-in factory. Does NOT replace radich.deployment.build_app."""
    repository = M17AgentRepository(dsn)
    repository.initialize_schema()
    runner = M17AgentRunner(repository, grant_skill=grant_skill)
    return create_app(
        runner=runner, repository=repository, api_key=api_key,
        resume_runner=runner,
        progress_reader=repository,
    )
