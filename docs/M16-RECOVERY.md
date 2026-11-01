# M16 — Recovery and resilience

## M16.1: Checkpoint contract and resumable sequential DAG

- `RunCheckpoint` records successfully completed node outputs and their execution order.
- `CheckpointStore` defines load/save; `MemoryCheckpointStore` is only for deterministic tests.
- `RecoverableScheduler` restores completed nodes, skips them, and retries incomplete or failed nodes.
- The checkpoint is saved after every successful node, not just after the entire graph.
- Failed nodes are not marked completed. Downstream nodes are cancelled until their predecessors complete.

## Important limitations

This is the **first M16 increment**, not a production crash-recovery solution.
PostgreSQL-backed checkpoint storage, locking/fencing concurrent workers, durable run inputs, graph-version compatibility, and recovery after abrupt process termination remain to implement.
External side effects cannot be guaranteed exactly-once merely by saving a checkpoint after a handler; handlers need idempotency keys and/or transactional outbox patterns.
Do not use this adapter for production crash recovery.

## Acceptance tests

- Failure after extract: resume does not repeat extract, but retries validate and completes summarize.
- New scheduler instance: all checkpointed nodes are reused.
- Invalid checkpoint rejected.

Target remains **Hetzner Cloud Linux**, not Windows local.

## M16.2: PostgreSQL checkpoint persistence

`PostgresCheckpointStore` in `src/radich/persistence/checkpoints.py` implements the same `CheckpointStore` protocol with an injected psycopg 3 connection. Call `initialize_schema()` before use.

- Stores completed outputs and execution order in `radich_checkpoints` as JSONB.
- Each save is atomic; a row-level `SELECT ... FOR UPDATE` serializes updates for the same run.
- Rejects stale writes, changed completed outputs and divergent checkpoint order.
- `load(run_id)` reconstructs and validates a `RunCheckpoint`.
- Can be injected into `RecoverableScheduler`; a new scheduler process can resume using the same database.

### Example

```python
import psycopg
from radich.persistence.checkpoints import PostgresCheckpointStore
from radich.recovery import RecoverableScheduler

with psycopg.connect(database_url) as connection:
    store = PostgresCheckpointStore(connection)
    store.initialize_schema()
    scheduler = RecoverableScheduler(graph, handlers, store)
    result = scheduler.run("stable-run-id", initial_payloads)
```

### Tests

`tests/test_m16_postgres_checkpoints.py` verifies persistence, stale/conflicting checkpoint rejection and recovery after a failed node. It requires `RADICH_TEST_DATABASE_URL` or `TEST_DATABASE_URL`; otherwise PostgreSQL-specific tests skip.

### Remaining M16 work

- Persist immutable initial inputs and graph version to prevent inconsistent resumption.
- Introduce run-level execution leases/fencing: row locking during `save` alone does **not** prevent two workers executing a handler simultaneously.
- Add restart/kill integration tests against actual Docker/PostgreSQL and wire the production API runner to the recoverable scheduler.
- Add idempotency protections for external actions; database checkpointing is not exactly-once execution.
