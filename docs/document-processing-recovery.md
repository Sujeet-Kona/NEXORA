# Document processing recovery

NEXORA currently runs document processing through FastAPI background tasks.
Because this work is in-process, a process restart can leave a document in
`processing` without a worker continuing it.

## State machine

- `pending -> processing`: the current legacy worker's status transition.
- `processing -> ready`: successful extraction and indexing.
- `processing -> failed`: processing error.
- `failed -> pending`: explicit retry/reset.
- `processing -> pending`: startup or document-specific stale recovery.
- `ready` has no normal processing transition; a new uploaded version starts
  a fresh `pending` cycle.

Retry intent for failed documents remains explicit.

## Stale-worker recovery (timestamp heuristic)

Recovery currently selects documents whose status is `processing` and whose
`updated_at` is older than 30 minutes. It returns those rows to `pending`,
clears the processing attempt and lease fields, and records a recovery reason.
Recovery uses PostgreSQL row locks with `SKIP LOCKED` to avoid multiple
recovery instances claiming the same row.

This is **not a true lease-based recovery implementation**: the recovery
predicate is timestamp-based and does not compare `processing_lease_expires_at`.
The legacy processing worker does not claim or renew an attempt token. The
worker refreshes `updated_at` once before embedding/indexing; that is not a
periodic heartbeat, so long-running work may still be incorrectly considered
stale after the threshold.

Attempt ownership and lease repository helpers are groundwork only; they are
not integrated end-to-end into the current worker.

## Cross-store mutation safety (known gap)

Document replacement and deletion lock the PostgreSQL document row while
checking and applying their SQL state changes. That lock is **not held across
Qdrant operations performed by the processing worker**, and it does not fence
late vector writes from a worker that has lost ownership. The current processing
worker still uses legacy document-scoped chunk replacement, vector deletion,
and best-effort failure cleanup.

Therefore, the existing row locks and tenant filters are not sufficient to
claim cross-store race safety. Attempt ownership and generation-scoped
repository primitives are groundwork only; they are not wired into the worker.
Until integration is completed and concurrency tests cover late writes, do not
run generation cleanup against live processing data or describe the pipeline as
fully concurrency-safe. The safe integration must keep the prior active
index available, write/delete only an attempt's generation, reject stale
promotion, and account for delayed Qdrant writes.
