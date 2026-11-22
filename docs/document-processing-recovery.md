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

## Concurrency audit (2026-11-22)

The current recovery mechanism is a stale-status reset, not a worker lease with
ownership. The following risks were confirmed by inspecting the processing,
worker, recovery, indexing, Qdrant, chunk repository, and retrieval code:

- A worker does not carry an attempt identifier. A stale worker can continue
  after a recovery reset and a newer invocation starts.
- Processing writes SQL chunks before indexing. The indexer deletes existing
  document vectors before embedding/upserting the replacement batches; an
  interruption can leave a partial vector index.
- Failure cleanup deletes document chunks and vectors without proving that the
  failing worker still owns the current processing attempt. A stale worker's
  cleanup can therefore interfere with newer work.
- Startup recovery resets stale documents to `pending`, but the startup
  routine does not dispatch the recovered IDs. They wait for another trigger.
- The current worker entry path does acquire a PostgreSQL row lock through
  `get_document_by_id_unscoped`, then checks `pending` and commits the
  `processing` transition before releasing the lock. That serializes the initial
  claim on PostgreSQL; the earlier concern about an unlocked check/update is not
  accurate for this path. However, it does not provide attempt ownership after
  the claim: recovery can reset a stale row and a newer worker can claim it,
  while the original worker has no token to prove it was invalidated.

These are audit findings, not proof that every race has occurred in practice.

## Target design and implementation order

The fix must be delivered in coordinated, testable increments. Do not implement
startup dispatch before worker ownership and attempt-safe mutations are in place.

1. **Database ownership/attempt token.** Add a nullable processing-attempt
   identifier and lease timestamp (or equivalent dedicated job table). Worker
   claim must be an atomic conditional update from `pending` to `processing`,
   and must return the winning attempt token. Only that token may refresh the
   lease, write processing state, finalize `ready`/`failed`, or perform
   destructive cleanup. A stale token must be a no-op. Add a migration and
   PostgreSQL concurrency tests.
2. **Attempt-scoped SQL writes.** Chunk replacement and metadata updates must
   occur only while the caller's attempt is current. Validate ownership before
   commit; avoid holding database transactions across model/embedding calls.
3. **Generation-isolated vector staging.** Do not delete active vectors before
   replacement vectors are complete. Stage vectors with a generation/attempt
   identifier and include it in payload. Promote the generation in SQL only
   after all batches are written and validated. Retrieval must filter to the
   active generation and rehydrate from PostgreSQL. Cleanup must target only
   the abandoned generation, never the active one.
4. **Recovery/takeover.** Reclaim only expired attempts with a conditional
   update that changes the ownership token. Return recovered document IDs.
   Recovery must not make an old attempt valid again.
5. **Startup dispatch.** Once takeover and attempt-scoped cleanup are safe,
   startup recovery may dispatch recovered IDs using the application's task
   mechanism. If process-local tasks remain, document their crash semantics;
   durable queues are outside the current architecture unless deliberately
   adopted.
6. **Regression suite.** Test two concurrent claims, expired takeover,
   stale-worker finalization, stale-worker cleanup, interruption during vector
  staging, generation promotion/visibility, recovery dispatch, and existing
  API state-machine behavior. Run full CI with PostgreSQL/Qdrant integration.

## Invariants

- At most one attempt owns a document at a time; a takeover invalidates the
  previous attempt immediately.
- A stale attempt cannot mutate SQL state, active vectors, or cleanup state.
- Retrieval sees only vectors for the SQL-promoted generation and READY docs.
- Failed or interrupted replacement never deletes the previously active vector
  generation until a new generation is promoted.
- Startup recovery either dispatches reclaimed work or explicitly leaves it
  queued for a later scheduler; it must not imply work is running.

## Scope and non-goals

This design hardens the existing FastAPI in-process processing workflow. It does
not claim durable queue delivery or production deployment readiness. A durable
queue and multi-worker orchestration would be a separate architectural decision.
