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

## Cross-store mutation ordering

Document replacement and deletion acquire the PostgreSQL document row lock
before mutating Qdrant. This prevents a processing worker from claiming the
same document between the SQL check and the vector-store mutation.

Qdrant operations remain organization-scoped, and failed processing removes
PostgreSQL chunks plus best-effort Qdrant vectors before the document is left
in `failed`.
