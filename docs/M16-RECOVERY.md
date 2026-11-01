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
