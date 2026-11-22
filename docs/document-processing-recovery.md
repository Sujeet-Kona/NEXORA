# Document processing recovery

NEXORA processes uploads with FastAPI background tasks. Because that work is
in-process, a worker can disappear after the document is marked `processing`.
The platform therefore treats `processing` as a leased state rather than a
permanent state.

## State machine

- `pending -> processing`: worker claim.
- `processing -> ready`: successful extraction and indexing.
- `processing -> failed`: processing error.
- `failed -> pending`: explicit retry/reset.
- `processing -> pending`: recovery of a stale worker lease.
- `ready` has no normal processing transition; a new uploaded version starts a
  fresh `pending` cycle.

A worker never silently treats `failed` as a retry request. Retry intent is
explicit.

## Stale-worker recovery

A document whose `updated_at` has been unchanged for more than 30 minutes
while `processing` is automatically returned to `pending` during application
startup. The background worker also performs a document-specific stale check
before claiming work.

The processing pipeline refreshes `updated_at` immediately before the
potentially expensive embedding/indexing stage. The 30-minute threshold is
intentionally conservative relative to normal document processing time.

Each recovery query uses a PostgreSQL row lock with `SKIP LOCKED`, so multiple
application instances can recover stale jobs without claiming the same row.

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
